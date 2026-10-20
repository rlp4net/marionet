from typing import Dict, Any, List
from collections import defaultdict
import importlib
import time

from controlplane.custom_objects.enumerations import Bound
from controlplane.custom_objects.ecmp_weights import EcmpWeights
from controlplane.custom_objects import PortInfo
from controlplane.network import QSwitch
from controlplane.network.network_interpreter import NetworkInterpreter
from controlplane.core.logger import Logger
from controlplane.decision_making.hyperparams import HyperParams
from controlplane.controller_config import MODEL_CONFIG
from controlplane.tools.qtable_viewer import save_snapshot
from controlplane.tools.decision_log import dlog_pre_update, dlog_post_update
from .abstract_learner import Learner


# ----------------------------------------------------------------------
# Per-switch learner
# ----------------------------------------------------------------------
class BatchAbsoluteSplitSwitchLearner:
    def __init__(self, sw: QSwitch, hp: HyperParams, batch_size: int = 3):
        self.batch_size = batch_size
        self.buffer: List[Dict[str, Any]] = []

        self.switch_obj = sw
        self.hyperparams = HyperParams.clone(hp)

        qm, qc = MODEL_CONFIG["qtable"].rsplit(".", 1)
        rm, rc = MODEL_CONFIG["reward"].rsplit(".", 1)
        self.qtable = getattr(importlib.import_module(qm), qc)()
        self.reward_fn = getattr(importlib.import_module(rm), rc)()

        self.old_ecmp_weights = EcmpWeights(self.switch_obj.get_ecmp_ports())
        self.new_ecmp_weights = EcmpWeights.clone(self.old_ecmp_weights)

        self.port_info_map: Dict[int, PortInfo] = {
            p: PortInfo() for p in self.switch_obj.get_ecmp_ports()
        }
        self.old_port_info_map: Dict[int, PortInfo] = {
            p: PortInfo() for p in self.switch_obj.get_ecmp_ports()
        }

        self.packet_number = 0
        self.current_reward = 0.0
        self.selected_action = 0
        self.prev_queue_history = []

        self.csv_logger = Logger("monitoring.log", "learning.log", "reward.log")
        self.learn_counter = 0

    # ------------------------------------------------------------------
    # Called once per packet
    # ------------------------------------------------------------------
    def learn_from_data(self, data: Dict[str, Any], net: NetworkInterpreter):
        self.buffer.append(data)
        if len(self.buffer) < self.batch_size:
            return

        self._aggregate_buffer()
        self._reward()

        dlog_pre_update(self, self.selected_action)

        self.qtable.update_with_transition(
                self.hyperparams,
                self.old_port_info_map,
                self.old_ecmp_weights,
                float(self.current_reward),
                self.port_info_map,
                self.new_ecmp_weights,
                self.selected_action,
            )

        self.selected_action = self.qtable.select_action(
            self.hyperparams, self.port_info_map, self.new_ecmp_weights
        )
        self._apply()
        net.push_ecmp_weights(self.old_ecmp_weights, self.new_ecmp_weights)
        self.hyperparams.update_periodically()

        dlog_post_update(self, self.selected_action)

        if self.learn_counter % 10 == 0:
            save_snapshot(
                self.qtable, f"snap_{self.switch_obj.sid}_{self.packet_number}.csv"
            )
        self.learn_counter += 1

        if self._reset():
            self.hyperparams = HyperParams.clone(self.hyperparams)

        for p in self.port_info_map:
            self.old_port_info_map[p].packet_diff_count = (
                self.port_info_map[p].packet_diff_count
            )
            self.old_port_info_map[p].last_known_queue = (
                self.port_info_map[p].last_known_queue
            )
            self.port_info_map[p].reset_counters()

        self.csv_logger.log_learning_data(
            self.switch_obj.sid, self.new_ecmp_weights, self.packet_number
        )
        self.csv_logger.log_grpc_update_time(
            self.switch_obj.sid, time.perf_counter(), self.packet_number
        )

        self.buffer.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _aggregate_buffer(self):
        """Computes mean queue length per port over the buffer."""
        sum_q = defaultdict(int)
        cnt_q = defaultdict(int)
        max_pkt = -1

        for d in self.buffer:
            pid, qlen = d["port"], d["queue_length"]
            sum_q[pid] += qlen
            cnt_q[pid] += 1
            max_pkt = max(max_pkt, d.get("packet_number", -1))
            self.csv_logger.log_monitoring_data(
                self.switch_obj.sid, pid, qlen, d.get("packet_number", -1)
            )

        for pid in self.port_info_map:
            if cnt_q[pid]:
                mean_q = sum_q[pid] / cnt_q[pid]
                self.port_info_map[pid].update_queue_length(mean_q)
            else:
                self.port_info_map[pid].mark_missing_packet()

        self.packet_number = max_pkt

    def _reward(self):
        self.current_reward, d, a = self.reward_fn.compute_reward(
            self.old_ecmp_weights,
            self.new_ecmp_weights,
            self.old_port_info_map,
            self.port_info_map,
            self.packet_number,
        )
        self.last_diff, self.last_avg = d, a
        self.csv_logger.log_reward_data(
            self.switch_obj.sid, self.current_reward, d, a, self.packet_number
        )

    def _apply(self):
        w = self.qtable.action_to_weight(self.selected_action)
        p = self.switch_obj.get_ecmp_ports()
        self.old_ecmp_weights = EcmpWeights.clone(self.new_ecmp_weights)
        self.new_ecmp_weights.set_bound_weight(p[0], Bound.UPPER_BOUND.value, w)
        self.new_ecmp_weights.set_bound_weight(p[1], Bound.LOWER_BOUND.value, w)

    def _reset(self):
        q = [pi.last_known_queue for pi in self.port_info_map.values()]
        self.prev_queue_history.append(q)
        if len(self.prev_queue_history) == 10:
            a = all(x[0] > 98 for x in self.prev_queue_history) and all(
                x[1] < 2 for x in self.prev_queue_history
            )
            b = all(x[1] > 98 for x in self.prev_queue_history) and all(
                x[0] < 2 for x in self.prev_queue_history
            )
            if a or b:
                self.prev_queue_history = []
                return True
            self.prev_queue_history.pop(0)
        return False


# ----------------------------------------------------------------------
# Global learner
# ----------------------------------------------------------------------
class BatchAbsoluteSplitLearner(Learner):
    def __init__(
        self,
        sw_map: Dict[int, QSwitch],
        hp: HyperParams,
        batch_size: int = 3,
    ):
        super().__init__()
        self.sw_learners = {
            sid: BatchAbsoluteSplitSwitchLearner(sw, hp, batch_size)
            for sid, sw in sw_map.items()
        }

    def learn(
        self,
        switch_id: int,
        learning_data: Dict[str, Any],
        net_interpreter: NetworkInterpreter,
    ) -> None:
        self.sw_learners[switch_id].learn_from_data(learning_data, net_interpreter)