#!/usr/bin/env python3
"""
Batch adapter for MarioNet post-processing.

The reusable, one-run logic lives in postprocess.py.  This module keeps only
batch-specific responsibilities:
  - initialize and update batch_summary.csv
  - rebuild the batch summary from per-run summary_row.json files
  - generate the global PDR-vs-load plot
  - expose the functions used by scripts/batch_run_traffic_replay.py
"""

from __future__ import annotations

import csv
import os
import shutil
from pathlib import Path
from typing import Dict

import postprocess as run_postprocess

REPO_ROOT = str(run_postprocess.REPO_ROOT)
SUMMARY_CSV = os.path.join(REPO_ROOT, "batch_summary.csv")
PCAP_DIR = str(run_postprocess.PCAP_DIR)
PCAP_SENDER = str(run_postprocess.PCAP_DIR / run_postprocess.SENDER_PCAP_NAME)
PCAP_RECEIVER = str(run_postprocess.PCAP_DIR / run_postprocess.RECEIVER_PCAP_NAME)

# Re-export common constants/functions for backward compatibility with callers
# that used to import them from batch_postprocess.py.
LOG_PCAPS_DIR = run_postprocess.LOG_PCAPS_DIR
SUMMARY_ROW_JSON = run_postprocess.SUMMARY_ROW_JSON
RUN_PARAMS_JSON = run_postprocess.RUN_PARAMS_JSON
ERROR_FLOAT = run_postprocess.ERROR_FLOAT
ERROR_INT = run_postprocess.ERROR_INT
LogFn = run_postprocess.LogFn

write_run_params = run_postprocess.write_run_params
archive_pcaps = run_postprocess.archive_pcaps
save_summary_row = run_postprocess.save_summary_row
load_summary_row = run_postprocess.load_summary_row
compute_run_stats = run_postprocess.compute_run_stats
list_logged_scenarios = run_postprocess.list_logged_runs
cleanup_scenario = run_postprocess.cleanup_run


def _logs_dir(name: str) -> str:
    return str(run_postprocess.logs_dir(name))


def _scenario_pcap(name: str, filename: str) -> str:
    return str(run_postprocess._scenario_pcap(name, filename))


def _pcap_packet_count(path: str, log: LogFn, label: str) -> int:
    return run_postprocess._pcap_packet_count(Path(path), log, label)


def _compute_mean_throughput(path: str, log: LogFn, label: str, window: float = 1.0) -> float:
    return run_postprocess._compute_mean_throughput(Path(path), log, label, window)


def _compute_queue_means(monitoring_file: str, log: LogFn, label: str):
    return run_postprocess._compute_queue_means(Path(monitoring_file), log, label)


def _compute_tcp_ooo(pcap_path: str, log: LogFn, label: str) -> float:
    return run_postprocess._compute_tcp_ooo(Path(pcap_path), log, label)


SUMMARY_COLUMNS = [
    "scenario",
    "mean_throughput_pps",
    "loss_rate_pct",
    "mean_Q_p2",
    "mean_Q_p3",
    "abs_Qp2_minus_Qp3",
    "tcp_ooo_pct",
    "in_pps_cfg",
    "capa_pps_cfg",
    "mean_in_pps",
    "pdr_pct",
    "load_pct",
]


def init_summary_csv(log: LogFn) -> None:
    """Initialize the batch summary CSV file."""
    try:
        with open(SUMMARY_CSV, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(SUMMARY_COLUMNS)
        log(f"[batch] Summary CSV initialized: {SUMMARY_CSV}")
    except OSError as exc:
        log(f"[batch] WARNING: unable to create summary CSV ({SUMMARY_CSV}): {exc}")


def save_summary_snapshot(name: str, log: LogFn) -> None:
    """Copy the current batch_summary.csv into logs_<name>/ for traceability."""
    if not os.path.exists(SUMMARY_CSV):
        return

    dst = run_postprocess.logs_dir(name) / os.path.basename(SUMMARY_CSV)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SUMMARY_CSV, dst)
    log(f"[{name}] Summary snapshot saved: {dst}")


def _needs_stats_recompute(stats: Dict) -> bool:
    """True when pcap-derived stats are missing or still contain error sentinels."""
    if not stats:
        return True

    for key in (
        "mean_throughput_pps",
        "loss_rate_pct",
        "mean_in_pps",
        "pdr_pct",
        "load_pct",
    ):
        try:
            value = float(stats.get(key, ERROR_FLOAT))
        except (TypeError, ValueError):
            return True
        if value < 0.0:
            return True

    return False


def append_summary_row(stats: Dict, log: LogFn) -> None:
    """Append one postprocess_run stats dict to batch_summary.csv."""
    try:
        with open(SUMMARY_CSV, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([stats.get(col, ERROR_FLOAT if col != "scenario" else "") for col in SUMMARY_COLUMNS])
    except OSError as exc:
        log(f"[batch] WARNING: unable to write to summary CSV ({SUMMARY_CSV}): {exc}")


def post_process_scenario(name: str, log: LogFn) -> None:
    """Batch wrapper around the reusable one-run postprocess."""
    stats = run_postprocess.postprocess_run(name, log)
    if not stats:
        return

    append_summary_row(stats, log)
    save_summary_snapshot(name, log)


def rebuild_summary_csv(log: LogFn, names=None) -> None:
    if names is None:
        names = list_logged_scenarios()

    init_summary_csv(log)

    for name in names:
        stats = load_summary_row(name)
        if _needs_stats_recompute(stats):
            if stats:
                log(f"[{name}] summary_row.json contains invalid pcap-derived stats, recomputing from logs")
            else:
                log(f"[{name}] summary_row.json not found, recomputing from logs")
            stats = compute_run_stats(name, log)
            save_summary_row(name, stats, log)
        append_summary_row(stats, log)

    plot_pdr_vs_load(log)


# Plot PDR vs load
def plot_pdr_vs_load(log: LogFn, output_png: str = "batch_pdr_vs_load.png") -> None:
    if not os.path.exists(SUMMARY_CSV):
        return

    try:
        import pandas as pd
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        log(f"[batch] WARNING: plot dependencies missing: {exc}")
        return

    try:
        df = pd.read_csv(SUMMARY_CSV)
    except Exception as exc:
        log(f"[batch] WARNING: unable to read summary CSV: {exc}")
        return

    if "load_pct" not in df.columns or "pdr_pct" not in df.columns:
        return

    sub = df[(df["load_pct"] >= 0) & (df["pdr_pct"] >= 0)].copy()
    if sub.empty:
        return

    plt.figure(figsize=(8, 5))
    plt.plot(sub["load_pct"], sub["pdr_pct"], linestyle="none", marker="o")
    for _, row in sub.iterrows():
        try:
            plt.text(float(row["load_pct"]), float(row["pdr_pct"]), str(row.get("scenario", "")), fontsize=8)
        except Exception:
            pass

    plt.xlabel("Load (%)")
    plt.ylabel("PDR (%)")
    plt.title("PDR vs Load")
    plt.grid(True, ls="--", alpha=.5)
    plt.tight_layout()

    out_path = os.path.join(REPO_ROOT, output_png)
    try:
        plt.savefig(out_path, dpi=200)
        log(f"[batch] Plot written: {out_path}")
    except Exception as exc:
        log(f"[batch] WARNING: unable to save plot {out_path}: {exc}")
    finally:
        plt.close()