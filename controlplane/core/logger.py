import sys as _sys
if __name__ == "controlplane.core.logger":
    _sys.modules["logger"] = _sys.modules[__name__]
elif __name__ == "logger":
    _sys.modules["controlplane.core.logger"] = _sys.modules[__name__]


import csv
import os
from datetime import datetime
from typing import Optional
from collections import defaultdict


OUTPUT_FOLDER: Optional[str] = None
NO_LOG: bool = False

def set_output_folder(path: str) -> None:
    global OUTPUT_FOLDER
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
        os.chmod(path, 0o777)
    OUTPUT_FOLDER = path

def set_no_log_mode(enabled: bool) -> None:
    global NO_LOG
    NO_LOG = bool(enabled)

def ensure_directory(file_path: str) -> None:
    dir_path = os.path.dirname(file_path)
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)

class Logger:
    def __init__(self,
                 monitoring_file: str,
                 learning_file: str,
                 reward_file: str,
                 grpc_file: str = "grpc_update.log") -> None:
        self.monitoring_file = self._final_path(monitoring_file)
        self.learning_file = self._final_path(learning_file)
        self.reward_file = self._final_path(reward_file)
        self.grpc_file = self._final_path(grpc_file)

        # decision log
        self.decisions_file = self._final_path("decisions.txt")
        # per-switch decision counters
        self._decision_count = defaultdict(int)

        ensure_directory(self.monitoring_file)
        ensure_directory(self.learning_file)
        ensure_directory(self.reward_file)
        ensure_directory(self.grpc_file)
        ensure_directory(self.decisions_file)

        # Q-table learning progress
        self.qupdates_file = self._final_path("qtable_updates.log")
        ensure_directory(self.qupdates_file)

        self.learning_on_off_file = self._final_path("learning_on_off.txt")
        ensure_directory(self.learning_on_off_file)
        self._learning_started_sids = set()

        self._init_csv(self.monitoring_file,
                       ['timestamp','packet_num','switch_id','port_id','queue_depth'])
        self._init_csv(self.learning_file,
                       ['timestamp','packet_num','switch_id','port_id','weight'])
        self._init_csv(self.reward_file,
                       ['timestamp','packet_num','switch_id','reward','difference_term','average'])
        self._init_csv(self.grpc_file,
                       ['timestamp','packet_num','switch_id','grpc_update_time'])
        self._init_csv(self.qupdates_file,
                       ['timestamp','packet_num','switch_id',
                        'index','old','new','delta','ema_delta','updates'])
        
        with open(self.decisions_file, 'w') as f:
            f.write("# Decision log\n")

    def _final_path(self, raw_path: str) -> str:
        if OUTPUT_FOLDER and not os.path.isabs(raw_path):
            return os.path.join(OUTPUT_FOLDER, raw_path)
        return raw_path

    def _init_csv(self, file_path: str, headers: list) -> None:
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)

    def log_decision_block(self, switch_id: int, lines: list[str]) -> int:
        """
        Handle logging of decision blocks for a specific switch. and count decisions.
        """
        self._decision_count[switch_id] += 1
        with open(self.decisions_file, 'a') as f:
            for ln in lines:
                f.write(ln.rstrip('\n') + "\n")
            f.write("\n")
        return self._decision_count[switch_id]

    def log_monitoring_data(self,
                            switch_id: int,
                            port_id: int,
                            queue_depth: int,
                            packet_num: int) -> None:
        if NO_LOG:
            return
        with open(self.monitoring_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(),
                             packet_num,
                             switch_id,
                             port_id,
                             queue_depth])

    def log_learning_data(self,
                          switch_id: int,
                          ecmp_obj: 'EcmpWeights',
                          packet_num: int) -> None:
        if NO_LOG:
            return
        pw = ecmp_obj.get_port_weights()
        with open(self.learning_file, 'a', newline='') as f:
            writer = csv.writer(f)
            for port, weight in pw.items():
                writer.writerow([datetime.now().isoformat(),
                                 packet_num,
                                 switch_id,
                                 port,
                                 weight])

    def log_reward_data(self,
                        switch_id: int,
                        reward_val: int,
                        difference_term: float,
                        average_val: float,
                        packet_num: int) -> None:
        if NO_LOG:
            return
        with open(self.reward_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(),
                             packet_num,
                             switch_id,
                             reward_val,
                             difference_term,
                             average_val])

    def log_grpc_update_time(self,
                             switch_id: int,
                             update_time: float,
                             packet_num: int) -> None:
        if NO_LOG:
            return
        with open(self.grpc_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(),
                             packet_num,
                             switch_id,
                             update_time])
            
    def log_qtable_update(self,
                          switch_id: int,
                          packet_num: int,
                          index,
                          old_val,
                          new_val,
                          delta,
                          ema_delta,
                          updates: int) -> None:
        if NO_LOG:
            return
        with open(self.qupdates_file, 'a', newline='') as f:
            w = csv.writer(f)
            w.writerow([datetime.now().isoformat(), packet_num, switch_id,
                        str(index),
                        "" if old_val is None else round(float(old_val), 6),
                        "" if new_val is None else round(float(new_val), 6),
                        "" if delta   is None else round(float(delta),   6),
                        "" if ema_delta is None else round(float(ema_delta), 6),
                        int(updates or 0)])

    def log_learning_on_off(self, switch_id: int, lines: list[str]) -> None:
        first_for_switch = switch_id not in self._learning_started_sids
        if first_for_switch:
            self._learning_started_sids.add(switch_id)
        with open(self.learning_on_off_file, 'a') as f:
            if first_for_switch:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{ts} [START-LEARNING] switch {switch_id} pkt=0\n")
            for line in lines:
                f.write(line.rstrip('\n') + "\n")