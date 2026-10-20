#!/usr/bin/env python3
"""
Usage examples:
python3 plot_experiment_logs.py --folder logs_2025
python3 plot_experiment_logs.py                       # latest logs, all curves vs time
python3 plot_experiment_logs.py --metrics reward      # reward only
python3 plot_experiment_logs.py --xaxis both --save   # save PNGs vs time and packet index
"""
import os, argparse
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import time
import shutil
import re

try:
    from .plot_learning_ratio import plot_learning_ratio_from_folder
except ImportError:  # script execution from plots/
    from plot_learning_ratio import plot_learning_ratio_from_folder

# Ensure the script runs from the project root directory
import os
os.chdir(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

RED, RESET = "\033[91m", "\033[0m"
GRAY = "#888888"

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
class LogReader:
    def __init__(self, monitoring_file, learning_file):
        self.monitoring_file = monitoring_file
        self.learning_file = learning_file

    def load_monitoring_data(self):
        return pd.read_csv(self.monitoring_file)

    def load_learning_data(self):
        return pd.read_csv(self.learning_file)


def _convert_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    t0 = df["timestamp"].min()
    df["relative_time"] = (df["timestamp"] - t0).dt.total_seconds()
    return df


def _choose_x(df: pd.DataFrame, xaxis: str) -> str:
    if xaxis == "packet":
        if "packet_number" in df.columns:
            return "packet_number"
        if "packet_num" in df.columns:
            return "packet_num"
        return "packet_number"
    return "relative_time"


def _latest_logs_folder(base=".") -> str:
    candidates = [
        (e.path, os.path.getctime(e.path))
        for e in os.scandir(base)
        if e.is_dir() and e.name.startswith("logs_")
    ]
    if not candidates:
        raise FileNotFoundError("No logs_* folder found")
    return max(candidates, key=lambda t: t[1])[0]


# ----------------------------------------------------------------------
# PCAP helpers
# ----------------------------------------------------------------------
def read_timestamps_from_pcap(file_path):
    try:
        import dpkt
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError("dpkt is required only for the pcap plot") from e

    timestamps = []
    with open(file_path, "rb") as f:
        pcap = dpkt.pcap.Reader(f)
        begin_ts = -1
        for ts, _ in pcap:
            if begin_ts == -1:
                begin_ts = ts
            timestamps.append(ts)
    return timestamps


def count_timestamps_per_window(timestamps, window):
    if not timestamps:
        return []
    t0 = timestamps[0]
    window_start, count, counts = t0, 0, []
    for ts in timestamps:
        if ts < window_start + window:
            count += 1
        else:
            counts.append(count)
            window_start += window
            while ts >= window_start + window:
                counts.append(0)
                window_start += window
            count = 1
    counts.append(count)
    return counts


def add_text_label(mean, std, win):
    text = f"Mean: {mean:.2f}/ {win}s\nStd: {std:.2f}/ {win}s"
    plt.text(
        0.98, 0.98, text, transform=plt.gca().transAxes,
        ha="right", va="top", fontsize=10,
        bbox=dict(facecolor="white", alpha=0.8),
    )


def plot_timestamp_counts(counts, win, file_root, mean, std):
    plt.figure()
    plt.plot(counts, color="green")
    plt.xlabel("Time (seconds)")
    plt.ylabel(f"Packets per {win}s")
    plt.title("Network throughput")
    plt.ylim(0)
    plt.grid(True, ls="--", alpha=.5)
    add_text_label(mean, std, win)
    plt.savefig(file_root + ".png", dpi=200)
    plt.close()

    plt.figure()
    plt.hist(counts, bins=20, alpha=.7, color="blue", density=True)
    plt.xlabel(f"Throughput per {win}s")
    plt.ylabel("Probability Density")
    plt.title("Histogram repartition of throughput")
    plt.grid(True, ls="--", alpha=.5)
    add_text_label(mean, std, win)
    plt.savefig(file_root + "_histogram.png", dpi=200)
    plt.close()

    sorted_counts = np.sort(counts)
    cdf = np.arange(1, len(sorted_counts) + 1) / len(sorted_counts)
    plt.figure()
    plt.plot(sorted_counts, cdf, marker=".", linestyle="none", color="red")
    plt.xlabel(f"Throughput per {win}s")
    plt.ylabel("Cumulative Probability")
    plt.title("Cumulative Distribution Function")
    plt.grid(True, ls="--", alpha=.5)
    add_text_label(mean, std, win)
    plt.savefig(file_root + "_cdf.png", dpi=200)
    plt.close()

# ----------------------------------------------------------------------
# Learning logs (delta q / EMA or fallback TD/EMA)
# ----------------------------------------------------------------------
def _load_learning_df(folder: str) -> tuple[pd.DataFrame | None, str]:
    """
    Return (df, kind) where kind in {"delta", "td"}.
    - qtable_updates.log: columns delta, ema_delta
    - learning_progress.log: td_error, td_error_ma_W (fallback)
    """
    qupd = os.path.join(folder, "qtable_updates.log")
    lprog = os.path.join(folder, "learning_progress.log")

    if os.path.exists(qupd):
        df = pd.read_csv(qupd)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        need = {"packet_num", "switch_id", "delta", "ema_delta"}
        missing = [c for c in need if c not in df.columns]
        if missing:
            print(f"{RED}[warn] qtable_updates.log missing {missing} – partial plot{RESET}")
        return _convert_timestamps(df), "delta"

    if os.path.exists(lprog):
        df = pd.read_csv(lprog)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["delta"] = df.get("td_error", 0).abs()
        df["ema_delta"] = df.get("td_error_ma_W", 0).abs()
        return _convert_timestamps(df), "td"

    return None, ""


def _load_learning_events(folder: str) -> pd.DataFrame:
    path = os.path.join(folder, "learning_on_off.txt")
    rows = []
    if not os.path.exists(path):
        return pd.DataFrame(columns=["type", "switch_id", "packet_num"])
    rx = re.compile(r"\[(STOP|RESUME)-LEARNING\].*switch\s+(\d+).*pkt=(\d+)")
    with open(path, "r") as f:
        for line in f:
            m = rx.search(line)
            if m:
                rows.append({"type": m.group(1), "switch_id": int(m.group(2)), "packet_num": int(m.group(3))})
    return pd.DataFrame(rows)

def _read_pcap_dir_from_makefile(makefile_path="Makefile"):
    if not os.path.exists(makefile_path):
        return None
    with open(makefile_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("PCAP_DIR"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    print(f"PATH of pcaps {os.path.expanduser(parts[1].strip())}")
                    return os.path.expanduser(parts[1].strip())
    return None


def _maybe_decimate(df, max_points=5000):
    """
    If the series is very long, we keep only one point every `step`
    to make the plot lighter. We return (df_decimated, step).
    """
    n = len(df)
    if n <= max_points or n == 0:
        return df, 1
    step = int(np.ceil(n / max_points))
    return df.iloc[::step].copy(), step


def _add_ema_for_plot(df, col, span=None):
    """
    Add a '<col>_ema' column with an EMA to smooth the curve.

    - if span is None, we choose it automatically (~1% of the length),
      limited between 20 and 500 points so it works on short/long runs.
    """
    df = df.copy()
    n = len(df)
    if n == 0:
        return df, 0
    if span is None:
        span = max(20, min(500, max(1, n // 100)))
    ema_col = col + "_ema"
    df[ema_col] = df[col].ewm(span=span, adjust=False).mean()
    return df, span

# ----------------------------------------------------------------------
# Grapher
# ----------------------------------------------------------------------
class Grapher:
    @staticmethod
    def plot_learning(df: pd.DataFrame,
                      events: pd.DataFrame | None = None,
                      *,
                      xaxis="time",
                      save_to=None):
        if df is None or df.empty:
            print(f"{RED}[error] learning log empty – plot skipped{RESET}")
            return
        xcol = _choose_x(df, xaxis)
        switch_ids = sorted(df["switch_id"].unique()) if "switch_id" in df.columns else [0]
        fig, axes = plt.subplots(len(switch_ids), 1, figsize=(12, 4 * len(switch_ids)), sharex=True)
        if len(switch_ids) == 1:
            axes = [axes]

        for ax, sid in zip(axes, switch_ids):
            sub = df if "switch_id" not in df.columns else df[df["switch_id"] == sid]
            sub = sub.sort_values(xcol)
            ax.plot(sub[xcol], sub["ema_delta"], label="EMA(abs(delta q))", linewidth=2.0)
            ax.plot(sub[xcol], sub["delta"], label="abs(delta q)", linewidth=1.0, alpha=.7)

            if events is not None and not events.empty:
                evs = events if "switch_id" not in events.columns else events[events["switch_id"] == sid]
                for _, e in evs.iterrows():
                    if xaxis == "packet":
                        x = e["packet_num"]
                    else:
                        pkt_col = "packet_num" if "packet_num" in sub.columns else (
                                  "packet_number" if "packet_number" in sub.columns else None)
                        if pkt_col is None:
                            continue
                        row = sub[sub[pkt_col] == e.get("packet_num")]
                        if row.empty:
                            continue
                        x = row.iloc[0]["relative_time"]
                    ax.axvline(x, color=("red" if e["type"] == "STOP" else "green"), linestyle="--", alpha=.5)

            ax.grid(True, ls="--", alpha=.5)
            ax.legend(loc="upper right")
            ax.set_ylabel(f"Switch {sid}" if "switch_id" in df.columns else "Learning")
        axes[-1].set_xlabel("Time (s)" if xaxis == "time" else "Packet #")
        fig.suptitle("Learning progress (abs(delta q) and EMA(abs(delta q)))")
        fig.tight_layout(rect=[0, 0, 1, .96])
        plt.savefig(save_to, dpi=150)
        plt.close()

    @staticmethod
    def plot_queue(data: pd.DataFrame, *, xaxis="time", save_to=None):
        data = _convert_timestamps(data)
        xcol = _choose_x(data, xaxis)

        switch_ids = sorted(data["switch_id"].unique())
        fig, axes = plt.subplots(len(switch_ids), 1, figsize=(12, 4 * len(switch_ids)), sharex=True)
        if len(switch_ids) == 1:
            axes = [axes]

        for ax, sid in zip(axes, switch_ids):
            sub = data[data["switch_id"] == sid]

            for pid, grp in sub.groupby("port_id"):
                grp = grp.sort_values(xcol)
                mean_q = grp["queue_depth"].mean()

                # EMA
                grp, span = _add_ema_for_plot(grp, "queue_depth")

                # Raw but decimated
                grp_raw, step = _maybe_decimate(grp)

                # First the raw points with low alpha (really good rendering aspect I think)
                ax.scatter(
                    grp_raw[xcol], grp_raw["queue_depth"],
                    s=3, alpha=0.12,
                    label=None  # already in legend
                )

                # then the EMA line for tendency
                label = f"Port {pid} (mean={mean_q:.1f}, EMA span={span})"
                ax.plot(grp[xcol], grp["queue_depth_ema"], label=label, linewidth=1.5)

            ax.set_ylabel(f"Switch {sid}")
            ax.grid(True, ls="--", alpha=.5)
            ax.legend(loc="upper right")

        axes[-1].set_xlabel("Time (s)" if xaxis == "time" else "Packet #")
        fig.suptitle("Queue depth evolution (brut + EMA par port)")
        fig.tight_layout(rect=[0, 0, 1, .97])

        plt.savefig(save_to, dpi=150)
        plt.close()


    @staticmethod
    def plot_weights(data: pd.DataFrame, *, xaxis="time", save_to=None):
        data = _convert_timestamps(data)
        xcol = _choose_x(data, xaxis)
        plt.figure(figsize=(12, 4))

        # One color per (switch, port)
        # Not sure if we should keep each port because if we have 2,
        # we only need one display because the other one is just complementary.
        colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        keys = sorted(
            data[["switch_id", "port_id"]].drop_duplicates().itertuples(index=False, name=None)
        )
        color_map = {k: colors[i % len(colors)] for i, k in enumerate(keys)}

        for (sid, pid), grp in data.groupby(["switch_id", "port_id"]):
            grp = grp.sort_values(xcol)

            # EMA
            grp, span = _add_ema_for_plot(grp, "weight")

            # Raw but decimated
            grp_raw, step = _maybe_decimate(grp)

            color = color_map[(sid, pid)]

            # First the raw points with low alpha (really good rendering aspect I think)
            plt.scatter(
                grp_raw[xcol], grp_raw["weight"],
                s=4, alpha=0.15, color=color
            )

            # then the EMA line for tendency
            label = f"S{sid} P{pid} (EMA span={span})"
            plt.plot(grp[xcol], grp["weight_ema"], label=label, color=color, linewidth=1.5)

        plt.ylim(0, 100)
        plt.xlabel("Time (s)" if xaxis == "time" else "Packet #")
        plt.ylabel("ECMP weights")
        plt.title("Weight evolution par port (brut + EMA)")
        plt.grid(True, ls="--", alpha=.5)
        plt.legend(fontsize=9)
        plt.tight_layout()

        plt.savefig(save_to, dpi=150)
        plt.close()


    @staticmethod
    def plot_reward(data: pd.DataFrame, *, xaxis="time", save_to=None):
        data = _convert_timestamps(data)
        xcol = _choose_x(data, xaxis)

        switch_ids = sorted(data["switch_id"].unique())
        fig, axes = plt.subplots(len(switch_ids), 1, figsize=(12, 4 * len(switch_ids)), sharex=True)
        if len(switch_ids) == 1:
            axes = [axes]

        for ax, sid in zip(axes, switch_ids):
            sub = data[data["switch_id"] == sid].sort_values(xcol)

            # EMA
            sub, span = _add_ema_for_plot(sub, "reward")

            # Raw but decimated
            sub_raw, step = _maybe_decimate(sub)

            # First the raw points with low alpha (really good rendering aspect I think)
            ax.scatter(
                sub_raw[xcol], sub_raw["reward"],
                s=4, alpha=0.15, color="red",
                label=f"Reward brut (1 point / {step})"
            )

            # then the EMA line for tendency
            ax.plot(
                sub[xcol], sub["reward_ema"],
                color="black", linewidth=2,
                label=f"EMA reward (span={span} pts)"
            )

            ax.set_ylabel(f"Switch {sid}")
            ax.grid(True, ls="--", alpha=.5)
            ax.legend(loc="upper right")

        axes[-1].set_xlabel("Time (s)" if xaxis == "time" else "Packet #")
        fig.suptitle("Reward evolution (brut + EMA)")
        fig.tight_layout(rect=[0, 0, 1, .97])

        plt.savefig(save_to, dpi=150)
        plt.close()


    @staticmethod
    def plot_pcap(pcap_path: str, *, window: float, save_to: str):
        timestamps = read_timestamps_from_pcap(pcap_path)
        counts = count_timestamps_per_window(timestamps, window)
        mean_pps, std_pps = np.mean(counts), np.std(counts)
        base = os.path.splitext(save_to)[0]
        plot_timestamp_counts(counts, window, base, mean_pps, std_pps)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--folder", help="logs_* folder; default = newest")
    p.add_argument("--metrics", nargs="+",
                   choices=["queue", "weights", "reward", "learning", "learning_ratio", "pcap", "all"],
                   default=["all"])
    p.add_argument("--xaxis", choices=["time", "packet", "both"], default="time")
    p.add_argument("--pcap", help="Path to a .pcap (default = first found in log folder)")
    p.add_argument("--win", type=float, default=1.0, help="Time-window size in seconds")
    p.add_argument("--pcap-only", action="store_true", help="Plot only throughput (no controller logs)")
    p.add_argument("--plots-dir", default="plots", help="subfolder name for PNG outputs")
    p.add_argument("--learning-title", default="Learning convergence",
                   help="title used for the learning_ratio plot")
    p.add_argument("--learning-threshold", type=float, default=0.01,
                   help="stop threshold on EMA(|ΔQ|)/EMA(|Q|)")
    p.add_argument("--learning-resume-k", type=float, default=5.0,
                   help="resume line = learning-threshold * k")
    p.add_argument("--learning-ema-span", type=int, default=50,
                   help="EMA span used to rebuild EMA(|Q|) from qtable_updates.log")

    args = p.parse_args()

    folder = args.folder or _latest_logs_folder()
    if not args.folder:
        print(f"[info] folder not given – using latest: {folder}")

    # If controller logs are missing (e.g., classic ECMP baseline run),
    # automatically fall back to "pcap-only" so we can still plot throughput.
    if not args.pcap_only:
        needed = [
            os.path.join(folder, "monitoring.log"),
            os.path.join(folder, "learning.log"),
            os.path.join(folder, "reward.log"),
        ]
        missing = [os.path.basename(p) for p in needed if not os.path.exists(p)]
        if missing:
            print(f"{RED}[warn] missing controller logs {missing} – switching to --pcap-only{RESET}")
            args.pcap_only = True

    # Ensure --pcap-only really means throughput only
    if args.pcap_only:
        args.metrics = ["pcap"]

    if not args.pcap_only:
        logs = {
            "queue": pd.read_csv(os.path.join(folder, "monitoring.log")),
            "weights": pd.read_csv(os.path.join(folder, "learning.log")),
            "reward": pd.read_csv(os.path.join(folder, "reward.log")),
        }

        learning_df, learning_kind = _load_learning_df(folder)
        learning_events = _load_learning_events(folder)

    if "all" in args.metrics:
        args.metrics = ["queue", "weights", "reward", "learning", "pcap", "learning_ratio"]

    # Locate pcaps
    pcap_path = None
    if args.pcap_only or "pcap" in args.metrics:
        if args.pcap:
            pcap_path = args.pcap
        else:
            fname = "s6-eth3_out.pcap"
            in_log = os.path.join(folder, fname)
            in_log_subdir = os.path.join(folder, "pcaps", fname)
            if os.path.exists(in_log):
                pcap_path = in_log
            elif os.path.exists(in_log_subdir):
                pcap_path = in_log_subdir
            else:
                # try dir for pcap that could be defined in makefile for me who use /local
                pcap_dir = _read_pcap_dir_from_makefile()
                if pcap_dir:
                    src = os.path.join(pcap_dir, fname)
                    if os.path.exists(src):
                        shutil.copy2(src, in_log)
                        pcap_path = in_log

                # Old version that is still working
                if not pcap_path:
                    src = os.path.join("pcaps", fname)
                    if os.path.exists(src):
                        shutil.copy2(src, folder)
                        pcap_path = in_log

        if not pcap_path or not os.path.exists(pcap_path):
            print(f"{RED}[error] PCAP not found – throughput plot skipped{RESET}")
            args.metrics.remove("pcap")

    xchoices = ["time", "packet"] if args.xaxis == "both" else [args.xaxis]

    plot_dir = os.path.join(folder, args.plots_dir)
    os.makedirs(plot_dir, exist_ok=True)

    if not args.pcap_only and "learning" in args.metrics and (learning_df is None or learning_df.empty):
        print(f"{RED}[warn] no learning log found (qtable_updates.log or learning_progress.log){RESET}")
        args.metrics = [m for m in args.metrics if m != "learning"]

    for metric in args.metrics:
        metric_xchoices = ["time"] if metric == "learning_ratio" else xchoices
        for x in metric_xchoices:
            fname = os.path.join(plot_dir, f"{metric}_{x}.png")

            if metric == "queue":
                Grapher.plot_queue(logs["queue"], xaxis=x, save_to=fname)
            elif metric == "weights":
                Grapher.plot_weights(logs["weights"], xaxis=x, save_to=fname)
            elif metric == "reward":
                Grapher.plot_reward(logs["reward"], xaxis=x, save_to=fname)
            elif metric == "learning":
                Grapher.plot_learning(
                    learning_df, events=learning_events, xaxis=x, save_to=fname)
            elif metric == "learning_ratio":
                plot_learning_ratio_from_folder(
                    folder, fname,
                    title=args.learning_title,
                    ratio_min=args.learning_threshold,
                    resume_k=args.learning_resume_k,
                    ema_span=args.learning_ema_span,
                )
            elif metric == "pcap":
                through_dir = os.path.join(plot_dir, "throughput")
                os.makedirs(through_dir, exist_ok=True)
                fname = os.path.join(through_dir, "throughput.png")
                Grapher.plot_pcap(pcap_path, window=args.win, save_to=fname)
            print(f"[saved] {fname}")


if __name__ == "__main__":
    main()