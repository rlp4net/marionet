#!/usr/bin/env python3
"""
Batch runner for MarioNet — RQ3 / Univ1 (model selection stage).

Scenarios that are run: see the scenarios.py file.
"""

import os
import shutil
import signal
import subprocess
import sys
import time

from typing import Dict, List, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import batch_postprocess
from scenarios import SCENARIOS

SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

# Optional: ECMP baseline mode (controller enabled, weights frozen)
ECMP_BASELINE = ("--ecmp" in sys.argv)

# Batch option:
#   - --keep : keep all logs
#   - default : remove heavy log files after each scenario (keep only plots + q_table_snapshots)
CLEANUP_ARTIFACTS = ("--keep" not in sys.argv)

# Default values used when running from the batch runner
DEFAULT_IN_PPS = 340
DEFAULT_CAPA_PPS = 360

# PCAPs copied into logs_<scenario>/pcaps
ARCHIVED_PCAPS = [
    "s6-eth3_out.pcap",
    "s1-eth1_in.pcap",
]

def log(msg: str) -> None:
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)

# Resolve per-scenario input rate + infra capacity with a simple priority order
def _resolve_rates(cfg: Dict) -> Tuple[int, int]:
    capa_pps = int(cfg.get("capa_pps", DEFAULT_CAPA_PPS))

    if "in_pps" in cfg:
        in_pps = int(cfg["in_pps"])
    elif "load_pct" in cfg:
        in_pps = int(round((float(cfg["load_pct"]) / 100.0) * capa_pps))
    else:
        in_pps = DEFAULT_IN_PPS

    return in_pps, capa_pps


def apply_overrides(name: str, overrides: Dict[str, str]) -> Dict[str, str]:
    """Copy scenario-specific files. Returns backups."""
    backups: Dict[str, str] = {}
    if not overrides:
        return backups

    log(f"[{name}] Applying overrides...")
    for dest_rel, src_rel in overrides.items():
        dest_abs = os.path.join(REPO_ROOT, dest_rel)
        src_abs = os.path.join(REPO_ROOT, src_rel)
        if not os.path.isfile(src_abs):
            raise RuntimeError(f"Override source not found: {src_abs}")
        os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
        if os.path.exists(dest_abs) and dest_abs not in backups:
            backup_abs = dest_abs + ".batch_backup"
            shutil.copy(dest_abs, backup_abs)
            backups[dest_abs] = backup_abs
        shutil.copy(src_abs, dest_abs)
        log(f"[{name}]   {src_rel} -> {dest_rel}")
    return backups


def restore_overrides(name: str, backups: Dict[str, str]) -> None:
    if not backups:
        return
    log(f"[{name}] Restoring original files...")
    for dest_abs, backup_abs in backups.items():
        if os.path.exists(backup_abs):
            shutil.move(backup_abs, dest_abs)


def start_mininet() -> subprocess.Popen:
    log("Starting Mininet: `make`")
    proc = subprocess.Popen(
        ["make"],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    # Small delay to let Mininet start
    time.sleep(18.0)
    return proc


def stop_mininet() -> None:
    log("`make clean`")
    try:
        subprocess.run(["make", "clean"], cwd=REPO_ROOT, check=False)
    except Exception as e:
        log(f"WARNING: make clean failed: {e}")


def start_controller(name: str, qtable: str = "") -> subprocess.Popen:
    controller_path = os.path.join(REPO_ROOT, "controlplane", "core", "controller.py")

    base_env = ["env", f"PATH={os.environ.get('PATH', '')}"]

    if os.geteuid() == 0:
        cmd = base_env + [controller_path]
    else:
        cmd = ["sudo", "-E"] + base_env + [controller_path]

    if name:
        cmd += ["--test_name", name]
    if qtable:
        cmd += ["--qtable", qtable]

    if ECMP_BASELINE:
        cmd += ["--mode", "ecmp"]
        log(f"[{name}] ECMP baseline: controller enabled (mode=ecmp, no weight updates)")

    log(f"[{name}] Starting controller: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    return proc


def stop_process(name: str, what: str, proc: subprocess.Popen) -> None:
    if proc is None or proc.poll() is not None:
        return
    log(f"[{name}] Stopping {what} (SIGINT)...")
    try:
        proc.send_signal(signal.SIGINT)
    except Exception:
        pass
    try:
        proc.wait(timeout=15.0)
    except subprocess.TimeoutExpired:
        log(f"[{name}] {what} did not stop, killing it...")
        try:
            proc.kill()
        except Exception:
            pass


def start_traffic(name: str, run_args: List[str]) -> subprocess.Popen:
    cmd = ["./run_traffic_replay.sh"] + list(run_args or [])
    log(f"[{name}] Starting traffic: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=SCRIPTS_DIR,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    # Small delay to let init the switches
    time.sleep(7.0)
    return proc


def run_scenario(cfg: Dict) -> None:
    name = cfg.get("name", "unnamed")
    overrides = dict(cfg.get("overrides", {}))

    # prepare run args
    in_pps, capa_pps = _resolve_rates(cfg)
    pcap_args = list(cfg.get("run_args", []))
    run_args = ["--in-pps", str(in_pps), "--capa", str(capa_pps)] + pcap_args

    log(f"=== SCENARIO: {name} ===")
    log(f"[{name}] Params: in_pps={in_pps} / capa_pps={capa_pps}")
    log(f"[{name}] PCAPs: {pcap_args}")

    backups: Dict[str, str] = {}
    make_proc = None
    ctrl_proc = None
    run_proc = None
    post_ok = False

    try:
        # Override files if requested
        backups = apply_overrides(name, overrides)

        # Mininet
        make_proc = start_mininet()

        # Traffic
        run_proc = start_traffic(name, run_args)

        # Controller
        ctrl_proc = start_controller(cfg.get("name", ""), str(cfg.get("qtable", "")))

        # Wait for scenario to finish: run_traffic_replay.sh ends when there are no more packets
        exit_code = run_proc.wait()
        log(f"[{name}] run_traffic_replay.sh finished with exit code {exit_code}")

        # Save run params (include PCAP list for reproducibility)
        batch_postprocess.write_run_params(
            name,
            {"in_pps": in_pps, "capa_pps": capa_pps, "pcaps": pcap_args},
            log,
        )
        batch_postprocess.archive_pcaps(name, ARCHIVED_PCAPS, log)

        try:
            batch_postprocess.post_process_scenario(name, log)
            post_ok = True
        except Exception as e:
            log(f"[{name}] WARNING: post-processing failed: {e}")

    finally:
        # Whatever happens, clean up everything
        stop_process(name, "controller", ctrl_proc)
        if make_proc is not None and make_proc.poll() is None:
            stop_process(name, "make", make_proc)
        stop_mininet()
        restore_overrides(name, backups)
        if CLEANUP_ARTIFACTS and post_ok:
            try:
                batch_postprocess.cleanup_scenario(name, log)
            except Exception as e:
                log(f"[{name}] WARNING: cleanup failed: {e}")

        log(f"=== END SCENARIO: {name} ===")


def main() -> None:
    log("Batch MarioNet runner (RQ3/Univ1) started.")
    batch_postprocess.init_summary_csv(log)
    if CLEANUP_ARTIFACTS:
        log("Mode cleanup : heavy logs will be removed after each scenario")
    else:
        log("Mode KEEP : keep all logs after each scenario")

    for cfg in SCENARIOS:
        try:
            run_scenario(cfg)
        except KeyboardInterrupt:
            log("CTRL+C received, stopping batch runner.")
            break
        except Exception as e:
            name = cfg.get("name", "unnamed")
            log(f"[{name}] ERROR: {e}")
            continue

    try:
        batch_postprocess.plot_pdr_vs_load(log)
    except Exception as exc:
        log(f"[batch] WARNING: PDR plot failed: {exc}")

    log("Batch MarioNet runner (RQ3/Univ1) finished.")


if __name__ == "__main__":
    main()
