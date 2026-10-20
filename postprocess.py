#!/usr/bin/env python3
"""
Post-processing utilities for one MarioNet run.

This module is intentionally not batch-specific.  It contains the reusable
post-processing primitives used by:
  - batch_postprocess.py, which adapts one-run stats to batch_summary.csv

Optional/experimental FCT post-processing code is also kept in this module,
but is currently disabled in the public release. It was originally intended
for generated-traffic experiments not included in this repository.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Callable, Dict, Iterable

REPO_ROOT = Path(__file__).resolve().parent
PCAP_DIR = REPO_ROOT / "pcaps"

# PCAPs used by the macro stats: h1 input and h6 output.
SENDER_PCAP_NAME = "s1-eth1_in.pcap"
RECEIVER_PCAP_NAME = "s6-eth3_out.pcap"
DEFAULT_ARCHIVED_PCAPS = [RECEIVER_PCAP_NAME, SENDER_PCAP_NAME]
LOG_PCAPS_DIR = "pcaps"

SUMMARY_ROW_JSON = "summary_row.json"
RUN_PARAMS_JSON = "run_params.json"
TRAFFIC_LOG_MARKER = "traffic_log_folder.txt"

ERROR_FLOAT = -1.0
ERROR_INT = -1

LogFn = Callable[[str], None]

FCT_FLOW_FIELDS = [
    "source_log",
    "batch_id",
    "connection_id",
    "status",
    "bytes_sent",
    "bucket",
    "fct_ms",
    "goodput_mbps",
    "error",
]

FCT_STATS_FIELDS = [
    "bucket",
    "n_flows",
    "total_bytes",
    "bytes_min",
    "bytes_max",
    "fct_min_ms",
    "fct_avg_ms",
    "fct_p50_ms",
    "fct_p95_ms",
    "fct_p99_ms",
    "fct_max_ms",
    "goodput_avg_mbps",
    "baseline_fct_avg_ms",
    "slowdown_avg",
]


def default_log(msg: str) -> None:
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


def normalize_run_name(name: str) -> str:
    """Accept both 'run_name' and 'logs_run_name'."""
    path = Path(name)

    if path.name.startswith("logs_"):
        return path.name[len("logs_"):]

    return name


def logs_dir(name: str) -> Path:
    name = normalize_run_name(name)
    return REPO_ROOT / f"logs_{name}"


def _scenario_pcap(name: str, filename: str) -> Path:
    """Return the archived PCAP when available, otherwise the live PCAP path."""
    archived = logs_dir(name) / LOG_PCAPS_DIR / filename
    if archived.exists():
        return archived
    return PCAP_DIR / filename


def archive_pcaps(
    name: str,
    filenames: Iterable[str] = DEFAULT_ARCHIVED_PCAPS,
    log: LogFn = default_log,
) -> None:
    """Copy live PCAPs into logs_<name>/pcaps for reproducible post-processing."""
    dst_dir = logs_dir(name) / LOG_PCAPS_DIR
    dst_dir.mkdir(parents=True, exist_ok=True)

    for filename in filenames:
        src = PCAP_DIR / filename
        dst = dst_dir / filename

        if not src.exists():
            log(f"[{name}] WARNING: pcap not found: {src}")
            continue

        # Moving pcaps rather than copying to save disk space
        # shutil.copy2(src, dst)
        shutil.move(src, dst)
        log(f"[{name}] Archived pcap: {dst}")


def write_run_params(name: str, params: Dict, log: LogFn = default_log) -> None:
    """Store run metadata in logs_<name>/run_params.json."""
    run_dir = logs_dir(name)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / RUN_PARAMS_JSON
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(params, f, indent=2)
    except OSError as exc:
        log(f"[{name}] WARNING: unable to write run params ({path}): {exc}")


def _read_run_params(run_dir: Path, log: LogFn, label: str) -> Dict:
    path = run_dir / RUN_PARAMS_JSON
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log(f"[{label}] WARNING: unable to read run params ({path}): {exc}")
        return {}


def save_summary_row(name: str, stats: Dict, log: LogFn = default_log) -> None:
    path = logs_dir(name) / SUMMARY_ROW_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    log(f"[{name}] Summary row saved: {path}")


def load_summary_row(name: str) -> Dict:
    path = logs_dir(name) / SUMMARY_ROW_JSON
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return data if isinstance(data, dict) else {}


def list_logged_runs() -> list[str]:
    names: list[str] = []
    for entry in sorted(REPO_ROOT.iterdir()):
        if not entry.is_dir() or not entry.name.startswith("logs_"):
            continue

        has_postprocess_files = (
            (entry / RUN_PARAMS_JSON).exists()
            or (entry / SUMMARY_ROW_JSON).exists()
        )
        if has_postprocess_files:
            names.append(entry.name[len("logs_"):])

    return names


def _pcap_packet_count(path: Path, log: LogFn, label: str) -> int:
    """Count packets in a pcap by reusing plots.plot_experiment_logs.read_timestamps_from_pcap."""
    if not path.exists():
        log(f"[{label}] WARNING: pcap not found: {path}")
        return ERROR_INT

    try:
        from plots.plot_experiment_logs import read_timestamps_from_pcap

        ts = read_timestamps_from_pcap(str(path))
    except Exception as exc:  # depends on external environment
        log(f"[{label}] WARNING: failed to read pcap ({path}): {exc}")
        return ERROR_INT

    return len(ts)


def _compute_mean_throughput(
    pcap_path: Path,
    log: LogFn,
    label: str,
    window: float = 1.0,
) -> float:
    """Mean throughput in packets per second measured on a pcap."""
    if not pcap_path.exists():
        log(f"[{label}] WARNING: pcap not found: {pcap_path}")
        return ERROR_FLOAT

    try:
        from plots.plot_experiment_logs import read_timestamps_from_pcap, count_timestamps_per_window

        ts = read_timestamps_from_pcap(str(pcap_path))
        if not ts:
            log(f"[{label}] WARNING: no timestamps in {pcap_path}")
            return ERROR_FLOAT

        counts = count_timestamps_per_window(ts, window)
        if not counts:
            log(f"[{label}] WARNING: unable to compute mean throughput on {pcap_path}")
            return ERROR_FLOAT

        return float(sum(counts)) / float(len(counts))
    except Exception as exc:
        log(f"[{label}] WARNING: compute_mean_throughput exception trace ({pcap_path}): {exc}")
        return ERROR_FLOAT


def _compute_queue_means(
    monitoring_file: Path,
    log: LogFn,
    label: str,
) -> tuple[float, float]:
    """Calculate mean Q(p2) and mean Q(p3) from monitoring.log."""
    if not monitoring_file.exists():
        log(f"[{label}] WARNING: monitoring.log not found: {monitoring_file}")
        return ERROR_FLOAT, ERROR_FLOAT

    sum2 = sum3 = 0.0
    n2 = n3 = 0

    try:
        with monitoring_file.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                port_raw = row.get("port_id", "")
                depth_raw = row.get("queue_depth", "")

                if not port_raw or not depth_raw:
                    continue

                try:
                    port = int(port_raw)
                    q = float(depth_raw)
                except ValueError:
                    continue

                if port == 2:
                    sum2 += q
                    n2 += 1
                elif port == 3:
                    sum3 += q
                    n3 += 1
    except Exception as exc:
        log(f"[{label}] WARNING: erreur lecture monitoring.log ({monitoring_file}): {exc}")
        return ERROR_FLOAT, ERROR_FLOAT

    mean_q2 = (sum2 / n2) if n2 else ERROR_FLOAT
    mean_q3 = (sum3 / n3) if n3 else ERROR_FLOAT

    if mean_q2 < 0.0:
        log(f"[{label}] WARNING: no queue data for p2 found in monitoring.log")
    if mean_q3 < 0.0:
        log(f"[{label}] WARNING: no queue data for p3 found in monitoring.log")

    return mean_q2, mean_q3


def _compute_tcp_ooo(pcap_path: Path, log: LogFn, label: str) -> float:
    """Global percentage of out-of-order TCP segments."""
    if not pcap_path.exists():
        log(f"[{label}] WARNING: receiver pcap not found for TCP OOO: {pcap_path}")
        return ERROR_FLOAT

    try:
        import tcp_ooo_rate
    except ImportError as exc:
        log(f"[{label}] WARNING: tcp_ooo_rate not available: {exc}")
        return ERROR_FLOAT

    try:
        log(f"[{label}] RUN: TCP OOO via tcp_ooo_rate.analyze_pcap({pcap_path})")
        flows = tcp_ooo_rate.analyze_pcap(str(pcap_path))
    except Exception as exc:
        log(f"[{label}] TCP OOO analysis failed ({pcap_path}): {exc}")
        return ERROR_FLOAT

    try:
        report_path = logs_dir(label) / "plots" / "tcp_ooo_rate.txt"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as f:
            with redirect_stdout(f):
                tcp_ooo_rate.print_stats(flows)
        log(f"[{label}] TCP OOO report saved: {report_path}")
    except Exception as exc:
        log(f"[{label}] WARNING: unable to write TCP OOO report: {exc}")

    total_segments = 0
    total_ooo = 0

    for stats in flows.values():
        total_segments += getattr(stats, "total_segments", 0)
        total_ooo += getattr(stats, "ooo_segments", 0)

    if total_segments <= 0:
        log(f"[{label}] no usable TCP segments in {pcap_path}")
        return ERROR_FLOAT

    return (total_ooo / total_segments) * 100.0


def _as_float(value, default: float = ERROR_FLOAT) -> float:
    try:
        return float(value)
    except Exception:
        return default


def compute_run_stats(
    name: str,
    log: LogFn = default_log,
    *,
    sender_pcap: str | Path | None = None,
    receiver_pcap: str | Path | None = None,
    run_params: Dict | None = None,
) -> Dict:
    """Calculate macro statistics for one run.

    The returned dict contains the same metrics previously computed by the
    batch post-process: throughput, loss, PDR, load, queue means and TCP OOO.
    """
    run_dir = logs_dir(name)
    monitoring_file = run_dir / "monitoring.log"
    sender = Path(sender_pcap) if sender_pcap is not None else _scenario_pcap(name, SENDER_PCAP_NAME)
    receiver = Path(receiver_pcap) if receiver_pcap is not None else _scenario_pcap(name, RECEIVER_PCAP_NAME)

    params = dict(run_params or {})
    if not params:
        params = _read_run_params(run_dir, log, name)

    in_pps_cfg = _as_float(params.get("in_pps", ERROR_FLOAT))
    capa_pps_cfg = _as_float(params.get("capa_pps", params.get("capa", ERROR_FLOAT)))

    # Queues
    mean_q2, mean_q3 = _compute_queue_means(monitoring_file, log, name)
    diff_q = abs(mean_q2 - mean_q3) if mean_q2 >= 0.0 and mean_q3 >= 0.0 else ERROR_FLOAT

    # Mean throughput + losses
    mean_tp_out = _compute_mean_throughput(receiver, log, name)
    mean_tp_in = _compute_mean_throughput(sender, log, f"{name}/sender")

    sent = _pcap_packet_count(sender, log, f"{name}/sender")
    received = _pcap_packet_count(receiver, log, f"{name}/receiver")

    if sent < 0 or received < 0:
        loss_pct = ERROR_FLOAT
        pdr_pct = ERROR_FLOAT
    elif sent == 0:
        log(f"[{name}] INFO: no packets sent, loss rate set to 0%")
        loss_pct = 0.0
        pdr_pct = 100.0
    else:
        lost = max(0, sent - received)
        loss_pct = (lost / sent) * 100.0
        pdr_pct = (received / sent) * 100.0

    if mean_tp_in >= 0.0 and capa_pps_cfg > 0:
        load_pct = (mean_tp_in / capa_pps_cfg) * 100.0
    else:
        load_pct = ERROR_FLOAT

    tcp_ooo_pct = _compute_tcp_ooo(receiver, log, name)

    return {
        "scenario": name,
        "mean_throughput_pps": mean_tp_out,
        "loss_rate_pct": loss_pct,
        "mean_Q_p2": mean_q2,
        "mean_Q_p3": mean_q3,
        "abs_Qp2_minus_Qp3": diff_q,
        "tcp_ooo_pct": tcp_ooo_pct,
        "in_pps_cfg": in_pps_cfg,
        "capa_pps_cfg": capa_pps_cfg,
        "mean_in_pps": mean_tp_in,
        "pdr_pct": pdr_pct,
        "load_pct": load_pct,
    }


def run_log_plots(
    name: str,
    log: LogFn = default_log,
    *,
    metrics: list[str] | None = None,
    pcap_only: bool = False,
) -> None:
    """Run plots/plot_experiment_logs.py for one run."""
    run_dir = logs_dir(name)
    plot_script = REPO_ROOT / "plots" / "plot_experiment_logs.py"
    if not plot_script.is_file():
        log(f"[{name}] WARNING: plot script not found: {plot_script}")
        return

    cmd = [sys.executable, str(plot_script), "--folder", str(run_dir)]
    if metrics:
        cmd += ["--metrics", *metrics]
    if pcap_only:
        cmd += ["--pcap-only"]

    log(f"[{name}] Post-processing plots: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)
    except Exception as exc:
        log(f"[{name}] WARNING: plot_experiment_logs.py failed: {exc}")


def find_generated_traffic_dir(
    name: str,
    *,
    traffic_root: str | Path | None = None,
) -> Path | None:
    """Return latest logs_traffic_generation/<name>_* folder, if any."""
    root = Path(traffic_root) if traffic_root is not None else REPO_ROOT / "logs_traffic_generation"
    if not root.exists():
        return None

    matches = [p for p in root.glob(f"{name}_*") if p.is_dir()]
    if not matches:
        return None

    return max(matches, key=lambda p: p.stat().st_mtime)


def _write_fct_global(out_dir: Path, rows: list[Dict], log: LogFn, label: str) -> Dict:
    global_rows = [row for row in rows if row.get("bucket") == "ALL"]
    if not global_rows:
        return {}

    row = dict(global_rows[0])
    path = out_dir / "fct_global.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)
    log(f"[{label}] Wrote {path}")

    # Prefix non-FCT fields to make them safe to merge into summary_row.json,
    # but keep existing names such as fct_avg_ms readable (not fct_fct_avg_ms).
    def summary_key(key: str) -> str:
        if key.startswith("fct_"):
            return key
        if key == "baseline_fct_avg_ms":
            return "fct_baseline_avg_ms"
        return f"fct_{key}"

    return {summary_key(str(key)): value for key, value in row.items() if key != "bucket"}


def postprocess_fct(
    name: str,
    log: LogFn = default_log,
    *,
    traffic_dir: str | Path | None = None,
    traffic_root: str | Path | None = None,
    baseline_csv: str | Path | None = None,
) -> Dict:
    """Analyze generated TCP flow logs and write FCT CSVs in logs_<name>."""
    run_dir = logs_dir(name)
    run_dir.mkdir(parents=True, exist_ok=True)

    src_dir = Path(traffic_dir) if traffic_dir is not None else find_generated_traffic_dir(
        name,
        traffic_root=traffic_root,
    )
    if src_dir is None:
        log(f"[{name}] No generated traffic log folder found")
        return {}

    try:
        from fct_by_size import collect_flows, load_baseline, summarize, write_csv

        flows = collect_flows(src_dir)
        baseline = load_baseline(Path(baseline_csv) if baseline_csv else None)
        rows = summarize(flows, baseline)

        write_csv(run_dir / "fct_flows.csv", flows, FCT_FLOW_FIELDS)
        write_csv(run_dir / "fct_by_size.csv", rows, FCT_STATS_FIELDS)
        (run_dir / TRAFFIC_LOG_MARKER).write_text(
            str(src_dir.relative_to(REPO_ROOT) if src_dir.is_relative_to(REPO_ROOT) else src_dir) + "\n",
            encoding="utf-8",
        )

        log(f"[{name}] FCT summary: {src_dir} -> {run_dir}")
        return _write_fct_global(run_dir, rows, log, name)
    except Exception as exc:
        log(f"[{name}] WARNING: FCT post-processing failed ({src_dir}): {exc}")
        return {}


def _fmt_stat(value) -> str:
    try:
        value_f = float(value)
    except Exception:
        return "NA"
    return f"{value_f:.2f}" if value_f >= 0.0 else "NA"


def log_stats_summary(name: str, stats: Dict, log: LogFn = default_log) -> None:
    """Log the core macro stats in one readable line."""
    log(
        f"[{name}] Stats: "
        f"Mean throughput = {_fmt_stat(stats.get('mean_throughput_pps'))} pps, "
        f"Loss = {_fmt_stat(stats.get('loss_rate_pct'))} %, "
        f"PDR = {_fmt_stat(stats.get('pdr_pct'))} %, "
        f"Load = {_fmt_stat(stats.get('load_pct'))} %, "
        f"Q(p2) = {_fmt_stat(stats.get('mean_Q_p2'))}, "
        f"Q(p3) = {_fmt_stat(stats.get('mean_Q_p3'))}, "
        f"|Q2-Q3| = {_fmt_stat(stats.get('abs_Qp2_minus_Qp3'))}, "
        f"TCP OOO = {_fmt_stat(stats.get('tcp_ooo_pct'))} %"
    )


def postprocess_run(
    name: str,
    log: LogFn = default_log,
    *,
    run_plots: bool = True,
    plot_metrics: list[str] | None = None,
    pcap_only: bool = False,
    include_fct: bool = False,
    traffic_dir: str | Path | None = None,
    traffic_root: str | Path | None = None,
    baseline_csv: str | Path | None = None,
    run_params: Dict | None = None,
    archive_pcap_filenames: Iterable[str] | None = None,
    save_summary: bool = True,
) -> Dict:
    """Post-process one MarioNet run and return its stats.

    This is the shared entry point.  It does not touch batch_summary.csv;
    batch_postprocess.py is responsible for adapting the returned stats to the
    batch CSV format.
    """
    run_dir = logs_dir(name)
    if not run_dir.exists() and run_params is None and archive_pcap_filenames is None:
        log(f"[{name}] WARNING: logs directory not found, skipping post-processing: {run_dir}")
        return {}

    if run_params is not None:
        write_run_params(name, run_params, log)

    if archive_pcap_filenames is not None:
        archive_pcaps(name, archive_pcap_filenames, log)

    if run_plots:
        run_log_plots(name, log, metrics=plot_metrics, pcap_only=pcap_only)

    log(f"[{name}] RUN: compute_run_stats (queue/throughput/loss/PDR/load/TCP-OOO)")
    stats = compute_run_stats(name, log, run_params=run_params)

    # FCT post-processing is currently disabled in the public release.
    # The code is kept below for future generated-traffic experiments.
    # It depends on fct_by_size.py, which is not distributed with
    # the current MarioNet artifact.
    #
    # if include_fct or traffic_dir is not None:
    #     stats.update(
    #         postprocess_fct(
    #             name,
    #             log,
    #             traffic_dir=traffic_dir,
    #             traffic_root=traffic_root,
    #             baseline_csv=baseline_csv,
    #         )
    #     )

    if save_summary:
        save_summary_row(name, stats, log)

    log_stats_summary(name, stats, log)
    return stats


def cleanup_run(name: str, log: LogFn = default_log) -> None:
    """Remove heavy logs from logs_<name>/ after post-processing."""
    run_dir = logs_dir(name)
    if not run_dir.is_dir():
        return

    keep_dirs = {"plots", "q_table_snapshots", LOG_PCAPS_DIR}
    keep_files = {"learning_on_off.txt", TRAFFIC_LOG_MARKER}
    keep_ext = {".png", ".csv", ".json"}

    for entry in run_dir.iterdir():
        if entry.is_dir():
            if entry.name in keep_dirs:
                continue
            shutil.rmtree(entry, ignore_errors=True)
            continue

        if entry.name in keep_files:
            continue

        if entry.suffix.lower() in keep_ext:
            continue

        try:
            entry.unlink()
        except FileNotFoundError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-process one MarioNet run")
    parser.add_argument("--name", required=True, help="Run name, without the logs_ prefix")
    parser.add_argument("--no-plot", action="store_true", help="Do not generate plots")
    parser.add_argument("--pcap-only", action="store_true", help="Only generate pcap plots")
    parser.add_argument("--metrics", nargs="+", default=None, help="Optional plot_experiment_logs.py metrics")
    parser.add_argument("--archive-pcaps", action="store_true", help="Copy live pcaps into logs_<name>/pcaps before stats")
    # Optional FCT/generated-traffic support -- currently disabled.
    # parser.add_argument(
    #     "--generated-traffic",
    #     action="store_true",
    #     help="Also compute FCT stats from logs_traffic_generation",
    # )
    # parser.add_argument("--traffic-dir", default=None,
    #                     help="Explicit generated traffic folder")
    # parser.add_argument("--traffic-root", default=None,
    #                     help="Generated traffic root folder")
    # parser.add_argument("--baseline-csv", default=None,
    #                     help="Optional baseline fct_by_size.csv")
    parser.add_argument("--in-pps", type=float, default=None, help="Optional configured input pps")
    parser.add_argument("--capa-pps", type=float, default=None, help="Optional configured capacity pps")
    args = parser.parse_args()
    args.name = normalize_run_name(args.name)

    params = {}
    if args.in_pps is not None:
        params["in_pps"] = args.in_pps
    if args.capa_pps is not None:
        params["capa_pps"] = args.capa_pps

    postprocess_run(
        args.name,
        default_log,
        run_plots=not args.no_plot,
        plot_metrics=args.metrics,
        pcap_only=args.pcap_only,
        # include_fct=args.generated_traffic,
        # traffic_dir=args.traffic_dir,
        # traffic_root=args.traffic_root,
        # baseline_csv=args.baseline_csv,
        run_params=params or None,
        archive_pcap_filenames=DEFAULT_ARCHIVED_PCAPS if args.archive_pcaps else None,
    )


if __name__ == "__main__":
    main()
