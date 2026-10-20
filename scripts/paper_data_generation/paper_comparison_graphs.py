#!/usr/bin/env python3
"""Generate paper comparison metrics graphs

Input: logs folders (one per approach).
Each folder must contain:
  - s6-eth3_out.pcap   (destination pcap)
  - monitoring.log     (queue telemetry)

Execute example:
  python3 paper_comparison_graphs.py --out out_pt11 \
  "Model A 1.4=logs_univ1_model_a_k1_k4_infer_pt11" \
  "Model B split unaware=logs_univ1_model_b_split_unaware_infer_pt11" \
  "ECMP=logs_univ1_ecmp_pt11" \
  "QCMP=logs_univ1_qcmp_infer_pt11"
"""

import argparse
import os
import socket
from collections import defaultdict

import dpkt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


STYLE = {
    "Model A 1.4": "o",
    "Model B split unaware": "*",
    "ECMP": "+",
    "QCMP": "x",
    # Example of extra baseline
    "YOLOCMP": "^",
}
ORDER = ["Model A 1.4", "Model B split unaware", "ECMP", "QCMP", "YOLOCMP"]


def _ip_to_str(b: bytes) -> str:
    if len(b) == 4:
        return socket.inet_ntoa(b)
    if len(b) == 16:
        return socket.inet_ntop(socket.AF_INET6, b)
    return str(b)


def _parse_series(items):
    out = []
    for raw in items:
        if "=" in raw:
            label, folder = raw.split("=", 1)
            out.append((label.strip(), folder.strip()))
        else:
            folder = raw.strip()
            out.append((os.path.basename(folder), folder))

    rank = {name: i for i, name in enumerate(ORDER)}
    return sorted(out, key=lambda kv: rank.get(kv[0], 999))


def throughput_pps(pcap_path: str, win_s: float, n_bins: int) -> np.ndarray:
    counts = np.zeros(n_bins, dtype=np.int64)
    with open(pcap_path, "rb") as f:
        pcap = dpkt.pcap.Reader(f)
        t0 = None
        for ts, _buf in pcap:
            if t0 is None:
                t0 = ts
            rel = ts - t0
            if rel < 0:
                continue
            idx = int(rel // win_s)
            if idx >= n_bins:
                break
            counts[idx] += 1
    return counts.astype(np.float64) / float(win_s)


class FlowState:
    def __init__(self):
        self.max_seq = None
        self.seen = set()  # (seq, payload_len)

    def observe(self, seq: int, payload_len: int):
        # same behaviour as tcp_ooo_rate.FlowStats.update()
        total_inc = 1
        ooo_inc = 0

        key = (seq, payload_len)
        if key in self.seen:
            return total_inc, 0

        if self.max_seq is None:
            self.max_seq = seq + payload_len
            self.seen.add(key)
            return total_inc, 0

        if seq < self.max_seq:
            ooo_inc = 1

        end_seq = seq + payload_len
        if end_seq > self.max_seq:
            self.max_seq = end_seq

        self.seen.add(key)
        return total_inc, ooo_inc


def tcp_ooo_pct(pcap_path: str, win_s: float, n_bins: int) -> np.ndarray:
    total = np.zeros(n_bins, dtype=np.int64)
    ooo = np.zeros(n_bins, dtype=np.int64)
    flows = defaultdict(FlowState)

    with open(pcap_path, "rb") as f:
        pcap = dpkt.pcap.Reader(f)
        t0 = None

        for ts, buf in pcap:
            if t0 is None:
                t0 = ts
            rel = ts - t0
            if rel < 0:
                continue
            idx = int(rel // win_s)
            if idx >= n_bins:
                break

            try:
                eth = dpkt.ethernet.Ethernet(buf)
                pkt = eth.data
            except Exception:
                continue

            ip_ver = 4 if isinstance(pkt, dpkt.ip.IP) else (6 if isinstance(pkt, dpkt.ip6.IP6) else None)
            if ip_ver is None:
                continue

            ip = pkt
            tcp = ip.data
            if not isinstance(tcp, dpkt.tcp.TCP):
                continue

            tcp_hlen = (tcp.off * 4) if getattr(tcp, "off", 0) else 20

            if ip_ver == 4:
                ip_hlen = (ip.hl * 4) if getattr(ip, "hl", 0) else 20
                ip_len = ip.len if ip.len is not None else 0
                payload_len = ip_len - ip_hlen - tcp_hlen
            else:
                plen = ip.plen if ip.plen is not None else 0
                payload_len = plen - tcp_hlen

            if payload_len <= 0:
                continue  # ignore pure ACKs

            key = (_ip_to_str(ip.src), tcp.sport, _ip_to_str(ip.dst), tcp.dport)
            t_inc, o_inc = flows[key].observe(int(tcp.seq), int(payload_len))
            total[idx] += t_inc
            ooo[idx] += o_inc

    out = np.full(n_bins, np.nan, dtype=np.float64)
    m = total > 0
    out[m] = (ooo[m] / total[m]) * 100.0
    return out


def queue_imbalance(monitoring_path: str, win_s: float, n_bins: int, port_a: int, port_b: int) -> np.ndarray:
    df = pd.read_csv(monitoring_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return np.full(n_bins, np.nan, dtype=np.float64)

    t0 = df["timestamp"].min()
    df["rel_s"] = (df["timestamp"] - t0).dt.total_seconds()
    df = df[(df["rel_s"] >= 0) & (df["rel_s"] < n_bins * win_s)]
    df = df[df["port_id"].isin([port_a, port_b])]

    df["bin"] = (df["rel_s"] // win_s).astype(int)
    piv = (
        df.groupby(["bin", "port_id"])["queue_depth"].mean().unstack("port_id")
        .reindex(range(n_bins))
    )

    if port_a not in piv.columns or port_b not in piv.columns:
        return np.full(n_bins, np.nan, dtype=np.float64)

    return (piv[port_a] - piv[port_b]).abs().to_numpy(dtype=np.float64)


def save_scatter(out_png: str, x_min: np.ndarray, series: dict, title: str, ylab: str, legend_loc: str):
    plt.figure(figsize=(10.5, 4.2))
    for label, y in series.items():
        marker = STYLE.get(label, "o")
        plt.scatter(x_min, y, label=label, marker=marker, s=18)

    plt.title(title)
    plt.xlabel("Time since start (minutes)")
    plt.ylabel(ylab)
    plt.grid(True, ls="--", alpha=0.5)
    plt.legend(loc=legend_loc, fontsize=8)
    plt.tight_layout()
    plt.savefig(out_png, dpi=250)
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series", nargs="+", help="folder paths, or 'Label=folder'")
    ap.add_argument("--out", default="paper_plots", help="output directory")
    ap.add_argument("--win", type=float, default=30.0, help="window size in seconds")
    ap.add_argument("--duration", type=float, default=40.0, help="duration in minutes")
    ap.add_argument("--pcap", default="s6-eth3_out.pcap", help="pcap filename in each logs folder")
    ap.add_argument("--monitor", default="monitoring.log", help="monitoring filename in each logs folder")
    ap.add_argument("--port-a", type=int, default=2)
    ap.add_argument("--port-b", type=int, default=3)
    args = ap.parse_args()

    win_s = float(args.win)
    duration_s = float(args.duration) * 60.0
    n_bins = int(duration_s // win_s)
    x_min = ((np.arange(n_bins) + 0.5) * win_s) / 60.0

    items = _parse_series(args.series)

    tp, qimb, ooo = {}, {}, {}
    for label, folder in items:
        pcap_path = os.path.join(folder, args.pcap)
        mon_path = os.path.join(folder, args.monitor)
        if not os.path.exists(pcap_path):
            raise FileNotFoundError(pcap_path)
        if not os.path.exists(mon_path):
            raise FileNotFoundError(mon_path)

        tp[label] = throughput_pps(pcap_path, win_s, n_bins)
        qimb[label] = queue_imbalance(mon_path, win_s, n_bins, args.port_a, args.port_b)
        ooo[label] = tcp_ooo_pct(pcap_path, win_s, n_bins)

    os.makedirs(args.out, exist_ok=True)

    save_scatter(
        os.path.join(args.out, "network_throughput.png"),
        x_min,
        tp,
        "Network throughput",
        f"Throughput (pps, {int(win_s)}s window)",
        legend_loc="lower left",
    )

    save_scatter(
        os.path.join(args.out, "queue_imbalance.png"),
        x_min,
        qimb,
        "Queue imbalance (|q1 - q2|)",
        f"|q1 - q2| (queue depth, {int(win_s)}s window)",
        legend_loc="upper left",
    )

    save_scatter(
        os.path.join(args.out, "tcp_ooo_rate.png"),
        x_min,
        ooo,
        "TCP out-of-order (OOO)",
        f"TCP OOO (%, {int(win_s)}s window)",
        legend_loc="upper left",
    )

    print(f"[saved] {args.out}")


if __name__ == "__main__":
    main()