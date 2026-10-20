#!/usr/bin/env python3
import csv
import os
import re
import math

"""Generate Table III inference metrics

Input: one experiment folder.
The folder must contain:
  - batch_summary.csv
  - logs_*_infer_pt10 ... logs_*_infer_pt14

Each infer folder must contain:
  - decisions.txt
  - monitoring.log
  - plots/tcp_ooo_rate.txt

Metrics:
  - throughput_pps
  - loss_pct
  - |q1-q2|
  - TCP OOO (%)
  - |delta_w|

Execute examples:
  python3 comparison_table_inference.py \
  runs/model_a_k1 \
  table3_csv/inference/model_a_k1.csv

  python3 comparison_table_inference.py \
  runs/model_a_k1_k4 \
  table3_csv/inference/model_a_k1_k4.csv

  python3 comparison_table_inference.py \
  runs/model_a_k1_k2_k4 \
  table3_csv/inference/model_a_k1_k2_k4.csv

  python3 comparison_table_inference.py \
  runs/model_b_split_unaware \
  table3_csv/inference/model_b_split_unaware.csv

  python3 comparison_table_inference.py \
  runs/model_b_split_aware \
  table3_csv/inference/model_b_split_aware.csv
"""


PT_RX = re.compile(r"pt(\d+)")
SPLIT_RX = re.compile(r"^Split\s*:\s*(\d+)\s*->\s*(\d+)")

def read_batch_summary(summary_csv):
    # dict: scenario -> row dict
    data = {}
    with open(summary_csv, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            sc = row.get("scenario")
            if sc:
                data[sc] = row
    return data

def mean_abs_delta_w(decisions_txt):
    vals = []
    with open(decisions_txt, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = SPLIT_RX.search(line.strip())
            if m:
                old = int(m.group(1))
                new = int(m.group(2))
                vals.append(abs(new - old))
    if not vals:
        return float("nan")
    return sum(vals) / len(vals)

def to_float(x):
    if x is None or x == "":
        return float("nan")
    try:
        return float(x)
    except Exception:
        return float("nan")

def mean_ignore_nan(values):
    ok = [v for v in values if v == v]  # v==v filters NaN
    if not ok:
        return float("nan")
    return sum(ok) / len(ok)

def main(group_dir, out_csv):
    summary_csv = os.path.join(group_dir, "batch_summary.csv")
    if not os.path.exists(summary_csv):
        print("[warn] No batch_summary.csv found -> loss/throughput from summary will be NA")
        summary = {}
    else:
        summary = read_batch_summary(summary_csv)

    run_dirs = []
    for name in os.listdir(group_dir):
        p = os.path.join(group_dir, name)
        if os.path.isdir(p) and name.startswith("logs_"):
            m = PT_RX.search(name)
            if m:
                run_dirs.append((int(m.group(1)), name, p))
    run_dirs.sort(key=lambda x: x[0])

    rows = []
    for pt, folder, path in run_dirs:
        scenario = folder[len("logs_"):]
        row = summary.get(scenario, {})

        loss_pct = to_float(row.get("loss_rate_pct"))
        qdiff    = to_float(row.get("abs_Qp2_minus_Qp3"))
        tcp_ooo  = to_float(row.get("tcp_ooo_pct"))

        tp_pps   = to_float(row.get("mean_throughput_pps"))

        decisions = os.path.join(path, "decisions.txt")
        dW = mean_abs_delta_w(decisions) if os.path.exists(decisions) else float("nan")

        rows.append({
            "pt": pt,
            "scenario": scenario,
            "throughput_pps": tp_pps,
            "loss_pct": loss_pct,
            "abs_q1_minus_q2": qdiff,
            "tcp_ooo_pct": tcp_ooo,
            "abs_delta_w": dW,
        })

    # averages over all pt runs
    avg = {
        "pt": "avg",
        "scenario": "avg",
        "throughput_pps": mean_ignore_nan([r["throughput_pps"] for r in rows]),
        "loss_pct": mean_ignore_nan([r["loss_pct"] for r in rows]),
        "abs_q1_minus_q2": mean_ignore_nan([r["abs_q1_minus_q2"] for r in rows]),
        "tcp_ooo_pct": mean_ignore_nan([r["tcp_ooo_pct"] for r in rows]),
        "abs_delta_w": mean_ignore_nan([r["abs_delta_w"] for r in rows]),
    }

    fields = ["pt", "scenario", "throughput_pps", "loss_pct", "abs_q1_minus_q2", "tcp_ooo_pct", "abs_delta_w"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
        w.writerow(avg)

    print("[ok] wrote", out_csv)
    print("avg:",
          "loss=%s" % (("NA" if avg["loss_pct"] != avg["loss_pct"] else f"{avg['loss_pct']:.2f}")),
          "|q1-q2|=%s" % (("NA" if avg["abs_q1_minus_q2"] != avg["abs_q1_minus_q2"] else f"{avg['abs_q1_minus_q2']:.2f}")),
          "ooo=%s" % (("NA" if avg["tcp_ooo_pct"] != avg["tcp_ooo_pct"] else f"{avg['tcp_ooo_pct']:.2f}")),
          "|dW|=%s" % (("NA" if avg["abs_delta_w"] != avg["abs_delta_w"] else f"{avg['abs_delta_w']:.2f}")),
    )

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python <experiment_group_dir> <out.csv>")
        raise SystemExit(2)
    main(sys.argv[1], sys.argv[2])