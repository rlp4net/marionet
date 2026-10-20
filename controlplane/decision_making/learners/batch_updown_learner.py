from typing import Dict, Any, List
from collections import defaultdict
import time

from .abstract_learner import Learner
from controlplane.decision_making.hyperparams import HyperParams
from controlplane.custom_objects.enumerations import TwoPortsActions, Bound, PortAction
from controlplane.custom_objects.ecmp_weights import EcmpWeights, EcmpGlobalAction
from controlplane.custom_objects import PortInfo
from controlplane.tools.qtable_viewer import save_snapshot
from controlplane.core.logger import Logger
from controlplane.tools.decision_log import dlog_pre_update, dlog_post_update

from controlplane.network import QSwitch
from controlplane.network.network_interpreter import NetworkInterpreter

import importlib
from controlplane.controller_config import MODEL_CONFIG


# ------------------------------------------------------------------ #
#  Per-switch learner                                                #
# ------------------------------------------------------------------ #
class BatchUpdownSwitchLearner:
    def __init__(self, sw: QSwitch, hp: HyperParams, batch_size: int = 3) -> None:
        self.batch_size = batch_size
        self.buffer: List[Dict[str, Any]] = []

        self.switch_obj = sw
        self.hyperparams = HyperParams.clone(hp)

        qt_path =       MODEL_CONFIG["qtable"]
        reward_path =   MODEL_CONFIG["reward"]
        qt_mod, qt_clas = qt_path.rsplit(".", 1)
        rw_mod, rw_clas = reward_path.rsplit(".", 1)
        self.qtable     = getattr(importlib.import_module(qt_mod), qt_clas)()
        self.reward_fn  = getattr(importlib.import_module(rw_mod), rw_clas)()

        self.old_ecmp_weights = EcmpWeights(self.switch_obj.get_ecmp_ports())
        self.new_ecmp_weights = EcmpWeights.clone(self.old_ecmp_weights)

        self.port_info_map: Dict[int, PortInfo] = {p: PortInfo() for p in self.switch_obj.get_ecmp_ports()}
        self.old_port_info_map: Dict[int, PortInfo] = {p: PortInfo() for p in self.switch_obj.get_ecmp_ports()}

        self.packet_number = 0
        self.current_reward = 0
        self.selected_two_ports_action = TwoPortsActions.ACTION_NO_CHANGE.value
        self.prev_queue_history: List[List[int]] = []

        self.csv_logger = Logger("monitoring.log", "learning.log", "reward.log")
        self.learn_counter = 0


    def learn_from_data(self, data: Dict[str, Any], net: NetworkInterpreter) -> None:
        self.buffer.append(data)
        if len(self.buffer) < self.batch_size:
            return

        t0 = time.perf_counter()
        # mean queue per port
        self.packet_number = self.buffer[-1].get("packet_number", getattr(self, "packet_number", 0))
        self._aggregate_buffer()
        self._compute_current_reward()

        dlog_pre_update(self, self.selected_two_ports_action)

        self.qtable.update(self.hyperparams,
                           self.port_info_map,
                           self.new_ecmp_weights,
                           float(self.current_reward),
                           self.selected_two_ports_action)

        self.selected_two_ports_action = self.qtable.select_action(
            self.hyperparams, self.port_info_map, self.new_ecmp_weights)

        self._apply_selected_action()
        net.push_ecmp_weights(self.old_ecmp_weights, self.new_ecmp_weights)
        #self.hyperparams.update_periodically()
        dlog_post_update(self, self.selected_two_ports_action)

        if self.learn_counter % 10 == 0:
            save_snapshot(self.qtable, f"snap_{self.switch_obj.sid}_{self.packet_number}.csv")
        self.learn_counter += 1

        if self._reset_check():
            self.hyperparams = HyperParams.clone(self.hyperparams)


        for p in self.port_info_map:
            self.old_port_info_map[p].packet_diff_count = self.port_info_map[p].packet_diff_count
            self.old_port_info_map[p].last_known_queue = self.port_info_map[p].last_known_queue
            self.port_info_map[p].reset_counters()

        self.csv_logger.log_learning_data(self.switch_obj.sid, self.new_ecmp_weights, self.packet_number)
        self.csv_logger.log_grpc_update_time(self.switch_obj.sid, time.perf_counter() - t0, self.packet_number)

        self.buffer.clear()

    def _aggregate_buffer(self) -> None:
        sum_q, cnt_q, max_pkt = defaultdict(int), defaultdict(int), -1
        for d in self.buffer:
            pid, qlen = d["port"], d["queue_length"]
            self.csv_logger.log_monitoring_data(self.switch_obj.sid, pid, qlen, d.get("packet_number", -1))
            sum_q[pid] += qlen
            cnt_q[pid] += 1
            max_pkt = max(max_pkt, d.get("packet_number", -1))

        for pid in self.port_info_map:
            if cnt_q[pid]:
                self.port_info_map[pid].update_queue_length(sum_q[pid] / cnt_q[pid])
            else:
                self.port_info_map[pid].mark_missing_packet()

        self.packet_number = max_pkt


    def _compute_current_reward(self) -> None:
        self.current_reward, diff, avg = self.reward_fn.compute_reward(
            self.old_ecmp_weights,
            self.new_ecmp_weights,
            self.old_port_info_map,
            self.port_info_map,
            self.packet_number,
        )
        self.last_diff, self.last_avg = diff, avg

        self.csv_logger.log_reward_data(
            self.switch_obj.sid, self.current_reward, diff, avg, self.packet_number
        )

    def _apply_selected_action(self) -> None:
        global_action = EcmpGlobalAction()
        p = self.switch_obj.get_ecmp_ports()
        if self.selected_two_ports_action == TwoPortsActions.ACTION_INCREASE_DECREASE.value:
            global_action.set_action_for_bound(p[0], Bound.UPPER_BOUND.value, PortAction.INCREASE)
            global_action.set_action_for_bound(p[1], Bound.LOWER_BOUND.value, PortAction.INCREASE)
        elif self.selected_two_ports_action == TwoPortsActions.ACTION_DECREASE_INCREASE.value:
            global_action.set_action_for_bound(p[0], Bound.UPPER_BOUND.value, PortAction.DECREASE)
            global_action.set_action_for_bound(p[1], Bound.LOWER_BOUND.value, PortAction.DECREASE)
        else:
            global_action.set_action_for_bound(p[0], Bound.UPPER_BOUND.value, PortAction.UNCHANGED)
            global_action.set_action_for_bound(p[1], Bound.LOWER_BOUND.value, PortAction.UNCHANGED)

        self.old_ecmp_weights = EcmpWeights.clone(self.new_ecmp_weights)
        self.new_ecmp_weights.apply_global_action(global_action, self.hyperparams.action_weight)

    def _reset_check(self) -> bool:
        q = [pi.last_known_queue for pi in self.port_info_map.values()]
        self.prev_queue_history.append(q)
        if len(self.prev_queue_history) == 10:
            a = all(x[0] > 98 for x in self.prev_queue_history) and all(x[1] < 2 for x in self.prev_queue_history)
            b = all(x[1] > 98 for x in self.prev_queue_history) and all(x[0] < 2 for x in self.prev_queue_history)
            if a or b:
                self.prev_queue_history = []
                return True
            self.prev_queue_history.pop(0)
        return False

# ------------------------------------------------------------------ #
#  Global learner                                                    #
# ------------------------------------------------------------------ #
class BatchUpdownLearner(Learner):
    def __init__(self, sw_map: Dict[int, QSwitch], hp: HyperParams, batch_size: int = 3) -> None:
        super().__init__()
        self.sw_learners = {sid: BatchUpdownSwitchLearner(sw, hp, batch_size)
                            for sid, sw in sw_map.items()}

    def learn(self, switch_id: int, learning_data: Dict[str, Any], net: NetworkInterpreter) -> None:
        self.sw_learners[switch_id].learn_from_data(learning_data, net)