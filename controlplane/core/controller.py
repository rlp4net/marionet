#!/usr/bin/env python3

import os
import sys
if __package__ is None or __package__ == "":
    _here = os.path.dirname(__file__)
    _pkg_dir = os.path.abspath(os.path.join(_here, ".."))
    _root_dir = os.path.abspath(os.path.join(_here, "..", ".."))
    sys.path.insert(0, os.path.abspath(os.path.join(_here, "..")))
    sys.path.insert(0, os.path.abspath(os.path.join(_here, "..", ".."))) 
    for _p in (_pkg_dir, _root_dir):
        if _p not in sys.path:
            sys.path.insert(0, _p)


import argparse
import time, datetime
import os, json, random
import numpy as np
import threading

from typing import Dict, Tuple, Any, Optional
from logger import set_output_folder, set_no_log_mode
from controlplane.custom_objects.telemetry_buffers import TelemetryBuffers
from controlplane.decision_making.hyperparams import HyperParams
from controlplane.network.qswitch import QSwitch
from controlplane.network.network_interpreter import NetworkInterpreter
from controlplane.decision_making.learners.abstract_learner import Learner

MAX_NUM_PORTS_ON_SW = 4

# Import of the learner from the config file
import importlib
from controlplane import controller_config as cfg
from controlplane.controller_config import MODEL_CONFIG
import inspect
def build_learner(sw_map, qtable_csv_path: Optional[str] = None, run_mode: str = "auto"):
    path = MODEL_CONFIG.get("learner")

    module_path, class_name = path.rsplit(".", 1)
    LearnerClass = getattr(importlib.import_module(module_path),
                           class_name)

    kwargs = {}
    if "batch" in MODEL_CONFIG:
        if "batch_size" in inspect.signature(LearnerClass.__init__).parameters:
            kwargs["batch_size"] = MODEL_CONFIG["batch"]

    sig = inspect.signature(LearnerClass.__init__)
    if "qtable_csv_path" in sig.parameters:
        kwargs["qtable_csv_path"] = qtable_csv_path
    if "run_mode" in sig.parameters:
        kwargs["run_mode"] = run_mode
    return LearnerClass(sw_map, HyperParams(), **kwargs) 



#sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def receive_loop(stop_evt: threading.Event,
                 controller_nw: NetworkInterpreter,
                 switch_nw: Dict[int, Tuple[NetworkInterpreter, TelemetryBuffers]],
                 switch_map: Dict[int, QSwitch]) -> None:
    count = 0
    while not stop_evt.is_set():
        t0 = time.perf_counter()
        pkt = controller_nw.receive_pkt()
        if not pkt:
            continue

        # print(f"pkt received: {pkt.summary()}")
        mri = controller_nw.extract_packet_mri(pkt)
        path = controller_nw.extract_packet_path(mri) if mri else []
        used = False
        for sid, sw in switch_map.items():
            p = sw.identify_mri_path(path)
            # print(f"Path: {path}, Switch: {sw.sid}, Port: {p}")
            if p != -1:
                info: Dict[str, Any] = {
                    "port": p,
                    "queue_length": controller_nw.getqlength(mri, sw.sid),
                    "packet_number": count
                }
                # Enqueue the telemetry info in the buffer associated to the port
                switch_nw[sid][1].put(info["port"], info["queue_length"])
                
                used = True
                break
        if not used:
            print(f"No match for path {path}")
        count += 1
        dt = time.perf_counter() - t0
        # print(f"Packet #{count} processed in {dt:.5f}s")


def set_run_seed(seed: int) -> None:
    """Set deterministic seeds for this run."""
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    print(f"[run] seed = {seed}")

def write_run_config(out_dir: str, seed: int, *, qtable_csv_path: Optional[str], run_mode: str) -> None:
    """Write a simple JSON with the knobs used for this run."""
    snap = {
        "seed": seed,
        "timestamp": datetime.datetime.now().isoformat(),
        "HYPERPARAMS": dict(cfg.HYPERPARAMS),
        "MODEL_CONFIG": dict(cfg.MODEL_CONFIG),
        "REWARD_CONFIG": dict(cfg.REWARD_CONFIG),
        "constants": {
            "LEARN_PERIOD_SEC": cfg.LEARN_PERIOD_SEC,
            "WEIGHT_STEP": cfg.WEIGHT_STEP,
            "MAX_QUEUE_LENGTH": cfg.MAX_QUEUE_LENGTH,
            "PORT_MAX_Q_STATE": cfg.PORT_MAX_Q_STATE,
            "WEIGHT_MAX_Q_STATE": cfg.WEIGHT_MAX_Q_STATE,
            "ECMP_MAX_WEIGHT": cfg.ECMP_MAX_WEIGHT,
            "PACKET_DIFF_MAX": cfg.PACKET_DIFF_MAX,
            "REWARD_CONSTANT": cfg.REWARD_CONSTANT,
            "REWARD_THRESHOLD": cfg.REWARD_THRESHOLD,
        },
        "run": {
            "mode": run_mode,
            "qtable_csv": qtable_csv_path or ""
        },
        "INCREMENTAL_SPLIT_ACTIONS": list(cfg.INCREMENTAL_SPLIT_ACTIONS),
    }
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "config_snapshot.json")
    with open(path, "w") as f:
        json.dump(snap, f, indent=2, sort_keys=True)
    print(f"[run] config -> {path}")

def main(p4info: str,
         test_name: str = "",
         seed: int = 1337,
         qtable_csv_path: Optional[str] = None,
         run_mode: str = "auto",
         no_log: bool = False) -> None:
    if not test_name:
        test_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = f"logs_{test_name}"
    set_output_folder(folder)
    if no_log:
        set_no_log_mode(True)
    set_run_seed(seed)
    write_run_config(folder, seed, qtable_csv_path=qtable_csv_path, run_mode=run_mode)

    s1 = QSwitch(1, "s1", 50051, 0)
    s1.add_nhop_dmac(2, "00:00:00:00:01:04")
    s1.add_nhop_dmac(3, "00:00:00:00:01:05")


    s1.add_path(2, [6,2,1])
    s1.add_path(3, [6,3,1])


    # switch_map = {s1.sid: s1, s2.sid: s2, s3.sid: s3}
    switch_map = {s1.sid: s1}
    switch_nw: Dict[int, Tuple[NetworkInterpreter, TelemetryBuffers]] = {}
    for sid, sw_obj in switch_map.items():
        switch_nw[sid] = (NetworkInterpreter(p4info, sw_obj), TelemetryBuffers(sid, MAX_NUM_PORTS_ON_SW))

    s6 = QSwitch(6, "s6", 50056, 5)
    controller_nw = NetworkInterpreter(p4info, s6)

    stop_evt = threading.Event()

    print("Running receive telemetry thread...")
    receive_telemetry = threading.Thread(target=receive_loop, args=(stop_evt, controller_nw, switch_nw, switch_map), daemon=True)
    receive_telemetry.start()

    # Instantiate learner "container" (i.e. containing one learner per switch)
    learner = build_learner(switch_map, qtable_csv_path=qtable_csv_path, run_mode=run_mode)

    sw_learners = []
    for sid, value in switch_nw.items():
        print("Running learning thread for switch " + str(sid) + "...")
        # value[0] NetworkInterpreter, value[1] TelemetryBuffers
        sl_th = threading.Thread(target=learner.learn, args=(sid, stop_evt, value[0], value[1]), daemon=True)
        sl_th.start()
        sw_learners.append(sl_th)

    try:
        # Main loop: run while any learning thread is still alive (or until Ctrl+C)
        while any(th.is_alive() for th in sw_learners):
            time.sleep(1.0)
        print("All learners are done, stopping main thread.")
    except KeyboardInterrupt:
        print("\nStopping...")
        stop_evt.set()
        # Give threads a moment to exit cleanly
        receive_telemetry.join(timeout=2.0)
        for sw_learner in sw_learners:
            sw_learner.join(timeout=2.0)
        print("Stopped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    # Defaults are resolved as: CLI > cfg.CONTROLLER_CONFIG > hard defaults
    parser.add_argument("--p4info", type=str, default=None)
    parser.add_argument("--test_name", type=str, default=None)
    parser.add_argument("--seed", type=int, default=None, help="Reproducibility seed")
    parser.add_argument("--qtable", type=str, default=None, help="Path to the Q-table CSV snapshot to load")
    parser.add_argument("--mode", type=str, default=None, help="auto|learn|infer|ecmp (default: auto)")

    # Allow overriding config no_log both ways
    parser.add_argument("--no-log", action="store_true", default=None, help="Reduce CSV log output")
    parser.add_argument("--log", action="store_true", default=None, help="Force CSV logs, overriding no_log=True from config")
    args = parser.parse_args()

    controller_cfg = getattr(cfg, "CONTROLLER_CONFIG", {}) or {}

    # Helper to pick value from CLI args or config dict or default
    def pick(cli_value, key: str, default):
        if cli_value is not None:
            return cli_value
        return controller_cfg.get(key, default)

    try:
        def _norm_mode(s: str) -> str:
            s = (s or "").strip().lower()
            if s in ("learn", "training", "train"):
                return "learn"
            if s in ("infer", "inference", "use", "eval", "freeze"):
                return "infer"
            if s in ("ecmp", "classic", "classique", "baseline", "read-only", "readonly", "no-update", "no_update"):
                return "ecmp"
            if s in ("auto", ""):
                return "auto"
            return "auto"

        p4info = pick(args.p4info, "p4info", "./build/switch.p4.p4info.txt")
        test_name = pick(args.test_name, "test_name", "")
        seed = pick(args.seed, "seed", 1337)

        qtable_raw = pick(args.qtable, "qtable", "")
        csv_path = qtable_raw or None

        mode_raw = pick(args.mode, "mode", "")
        mode_in = _norm_mode(mode_raw)
        if mode_in == "auto":
            final_mode = "infer" if csv_path else "learn"
        else:
            final_mode = mode_in

        # ECMP baseline (read-only) must not depend on a Q-table snapshot.
        # This keeps the run compatible with existing scenario configs that
        # reference a qtable path that may not exist on the current machine.
        if final_mode == "ecmp":
            csv_path = None

        if args.no_log is True:
            no_log = True
        elif args.log is True:
            no_log = False
        else:
            no_log = bool(controller_cfg.get("no_log", False))

        main(p4info, test_name, seed, qtable_csv_path=csv_path, run_mode=final_mode, no_log=no_log)
    except KeyboardInterrupt:
        print("Stopping.")
        sys.exit(0)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        sys.exit(2)
