from abc import ABC, abstractmethod
import time
import threading
from datetime import datetime
import importlib
from typing import Dict, Optional

from controlplane.network.network_interpreter import NetworkInterpreter
from controlplane.custom_objects.telemetry_buffers import TelemetryBuffers

from controlplane.decision_making.hyperparams import HyperParams
from controlplane.custom_objects import PortInfo
from controlplane.custom_objects.ecmp_weights import EcmpWeights
from controlplane.network import QSwitch
from controlplane.core.logger import Logger
from controlplane.controller_config import MODEL_CONFIG, MAX_QUEUE_LENGTH, LEARN_PERIOD_SEC, MAX_LEARN_PERIOD_NO_ACTIVITY
from controlplane.tools.qtable_viewer import save_snapshot, load_snapshot_csv
from controlplane.tools.decision_log import dlog_pre_update, dlog_post_update

class Learner(ABC):
    """
    Abstract base class for a learning algorithm.
    """

    @abstractmethod
    def learn(self,
              switch_id: int,
              stop_evt: threading.Event,
#              learning_data: Dict[str, Any],
              net_interpreter: NetworkInterpreter,
              telemetry_buffers: TelemetryBuffers) -> None:
        pass

class SwitchLearnerBase(ABC):
    """
    Base class for switch learners implementing a RL-based decision-making process.:
      factors common to all learners are implemented here.

    subclasses must implement:
      - self.selected_action
      - _apply_selected_action()
    """

    def __init__(self,
                 switch_obj: QSwitch,
                 hyperparams: HyperParams,
                 qtable_csv_path: Optional[str] = None,
                 run_mode: str = "auto") -> None:
        
        self.switch_obj = switch_obj
        self.hyperparams = HyperParams.clone(hyperparams)

        self._run_mode = (run_mode or "auto").lower()
        if self._run_mode not in ("auto", "learn", "infer", "ecmp"):
            self._run_mode = "auto"

        # Q-table + reward(MODEL_CONFIG)
        qm, qc = MODEL_CONFIG["qtable"].rsplit(".", 1)
        rm, rc = MODEL_CONFIG["reward"].rsplit(".", 1)
        self.qtable = getattr(importlib.import_module(qm), qc)()
        self.reward_fn = getattr(importlib.import_module(rm), rc)()

        self._loaded_qtable_file = ""
        if qtable_csv_path:
            # load snapshot and put it inside self.qtable
            self._loaded_qtable_file = load_snapshot_csv(self.qtable, qtable_csv_path)

        # ECMP + ports
        self.old_ecmp_weights = EcmpWeights(self.switch_obj.get_ecmp_ports())
        self.new_ecmp_weights = EcmpWeights.clone(self.old_ecmp_weights)

        self.port_info_map: Dict[int, PortInfo] = {
            p: PortInfo() for p in self.switch_obj.get_ecmp_ports()
        }
        self.old_port_info_map: Dict[int, PortInfo] = {
            p: PortInfo() for p in self.switch_obj.get_ecmp_ports()
        }

        # learning state
        self.packet_number = 0
        self.current_reward = 0.0
        self.selected_action = 0
        self.prev_queue_history: list[list[int]] = []

        # Logs
        self.csv_logger = Logger("monitoring.log", "learning.log", "reward.log")
        if self._run_mode == "auto":
            self._run_mode = "infer" if self._loaded_qtable_file else "learn"
        if self._run_mode in ("infer", "ecmp"):
            self.hyperparams.epsilon_value = 0.0
        init = [f"Initial mode: {self._run_mode}"]
        if self._loaded_qtable_file:
            init.append(f"Loaded snapshot: {self._loaded_qtable_file}")
        self.csv_logger.log_learning_on_off(self.switch_obj.sid, init)

    def learn_from_data(
        self,
        stop_evt: threading.Event,
        net: NetworkInterpreter,
        telebuf: TelemetryBuffers,
    ) -> None:
        no_telemetry = 0
        while not stop_evt.is_set():
            t0 = time.perf_counter()
            cycle_start = time.time()
            self.packet_number += 1

            timestamp = datetime.now().strftime("%H:%M:%S")
            total_values = 0
            outputs = []

            for pid in self.port_info_map:
                values = telebuf.drain_all(pid)
                total_values += len(values)
                if values:
                    mean = round(sum(values) / len(values))
                    self.port_info_map[pid].update_queue_length(mean)
                    outputs.append(f"port {pid}: mean={mean} (from {len(values)} values)")
                else:
                    outputs.append(
                        f"port {pid}: No INT values in buffer! Setting MAX_QUEUE_LENGTH)"
                    )
                    self.port_info_map[pid].update_queue_length(MAX_QUEUE_LENGTH)

            if total_values == 0:
                print(f"[{timestamp}] Warning: all queues are empty — no telemetry to process.")
                no_telemetry += 1
                if MAX_LEARN_PERIOD_NO_ACTIVITY > 0 and no_telemetry >= MAX_LEARN_PERIOD_NO_ACTIVITY:
                    stop_evt.set()
            else:
                no_telemetry = 0
                print(f"[{timestamp}] " + " | ".join(outputs))

                for pid in self.port_info_map:
                    self.csv_logger.log_monitoring_data(
                        self.switch_obj.sid,
                        pid,
                        self.port_info_map[pid].last_known_queue,
                        self.packet_number,
                    )

                self._compute_reward()

                # ECMP baseline mode: keep dataplane weights fixed.
                # We still log telemetry + reward + (constant) weights, but we do not
                # update the Q-table, do not change weights, and do not push via gRPC.
                if self._run_mode != "ecmp":
                    dlog_pre_update(self, self.selected_action)

                    applied = False
                    if hasattr(self.qtable, "compute_update_with_transition"):
                        idx, old_q, new_q = self.qtable.compute_update_with_transition(
                            self.hyperparams,
                            self.old_port_info_map,
                            self.old_ecmp_weights,
                            float(self.current_reward),
                            self.port_info_map,
                            self.new_ecmp_weights,
                            self.selected_action,
                        )
                        if self._should_update_qtable():
                            self.qtable.apply_computed_update(idx, new_q)
                            applied = True
                    else:
                        if self._should_update_qtable():
                            self.qtable.update_with_transition(
                                self.hyperparams,
                                self.old_port_info_map,
                                self.old_ecmp_weights,
                                float(self.current_reward),
                                self.port_info_map,
                                self.new_ecmp_weights,
                                self.selected_action,
                            )
                            applied = True

                    self.selected_action = self.qtable.select_action(
                        self.hyperparams, self.port_info_map, self.new_ecmp_weights
                    )
                    self._apply_selected_action()
                    net.push_ecmp_weights(self.old_ecmp_weights, self.new_ecmp_weights)
                    self.hyperparams.update_periodically()

                    dlog_post_update(self, self.selected_action)
                    save_snapshot(self.qtable, "qtable.csv")  # overwrite each time
                    # save_snapshot(self.qtable, f"snap_{self.switch_obj.sid}_{self.packet_number}.csv")

                    if self._reset_check():
                        self.hyperparams = HyperParams.clone(self.hyperparams)
                else:
                    # Safety: ensure in-memory weights stay constant too.
                    self.new_ecmp_weights = EcmpWeights.clone(self.old_ecmp_weights)

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
                    self.switch_obj.sid, time.perf_counter() - t0, self.packet_number
                )

            elapsed = time.time() - cycle_start
            remaining = max(0.0, LEARN_PERIOD_SEC - elapsed)
            stop_evt.wait(remaining)


    # helpers--------------------------------------------
    def _compute_reward(self) -> None:
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

    def _reset_check(self) -> bool:
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

    def _should_update_qtable(self) -> bool:
        if self._run_mode == "learn":
            cont, event = self.qtable.should_learn()
        elif self._run_mode in ("infer", "ecmp"):
            cont, event = False, None
        else:  # auto mode after initialization
            cont, event = self.qtable.should_learn()

        if event:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            msg = f"{ts} {event} (switch {self.switch_obj.sid} pkt={self.packet_number})"
            print(msg)
            self.csv_logger.log_learning_on_off(self.switch_obj.sid, [msg])
        return cont

    @abstractmethod
    def _apply_selected_action(self) -> None:
        raise NotImplementedError