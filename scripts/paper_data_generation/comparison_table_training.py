#!/usr/bin/env python3

"""Generate Table III training metrics

Input: one learning logs folder.
The folder must contain:
  - q_table_snapshots/qtable.csv
  - qtable_updates.log
  - learning_on_off.txt

Execute examples:
  python3 comparison_table_training.py \
  logs_univ1_model_a_k1_learn \
  table3_csv/training/model_a_k1.csv

  python3 comparison_table_training.py \
  logs_univ1_model_a_k1_k4_learn \
  table3_csv/training/model_a_k1_k4.csv

  python3 comparison_table_training.py \
  logs_univ1_model_a_k1_k2_k4_learn \
  table3_csv/training/model_a_k1_k2_k4.csv

  python3 comparison_table_training.py \
  logs_univ1_model_b_split_unaware_learn \
  table3_csv/training/model_b_split_unaware.csv

  python3 comparison_table_training.py \
  logs_univ1_model_b_split_aware_learn \
  table3_csv/training/model_b_split_aware.csv
"""

import csv
import os
from datetime import datetime

META_COLS = {"queue0_state", "queue1_state", "weight_bin"}

def q_size_from_snapshot(qtable_csv):
    # |Q| = n_states * n_actions
    with open(qtable_csv, newline="") as f:
        r = csv.reader(f)
        header = next(r)
        action_cols = [c for c in header if c not in META_COLS]
        n_actions = len(action_cols)
        n_states = sum(1 for _ in r)
    return n_states * n_actions

def coverage_pct_from_updates(qtable_updates_csv, q_size):
    # Cov(%) = unique indices / |Q| * 100
    seen = set()
    last_ts = None

    with open(qtable_updates_csv, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            idx = row.get("index")
            if idx:
                seen.add(idx)
            ts = row.get("timestamp")
            if ts:
                try:
                    last_ts = datetime.fromisoformat(ts)
                except Exception:
                    pass

    cov = (len(seen) / q_size) * 100.0 if q_size > 0 else float("nan")
    return cov, last_ts

def stop_time_hours(learning_on_off_txt, t_end_fallback):
    # Stop(h) = time from START-LEARNING to final STOP-LEARNING
    # If never stopped -> return duration and stopped=False
    t_start = None
    last_stop = None
    stopped = False

    if not os.path.exists(learning_on_off_txt):
        return float("nan"), False, "NA"

    with open(learning_on_off_txt, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            ts = None
            try:
                ts = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

            if "[START-LEARNING]" in line and t_start is None:
                t_start = ts
            elif "[STOP-LEARNING]" in line:
                last_stop = ts
                stopped = True
            elif "[RESUME-LEARNING]" in line:
                stopped = False

    if t_start is None:
        return float("nan"), False, "NA"

    if stopped and last_stop is not None:
        h = (last_stop - t_start).total_seconds() / 3600.0
        return h, True, f"{h:.2f}"

    if t_end_fallback is None:
        return float("nan"), False, "NA"

    h = (t_end_fallback - t_start).total_seconds() / 3600.0
    return h, False, f">{h:.2f}"

def main(logs_learn_dir, out_csv):
    snap = os.path.join(logs_learn_dir, "q_table_snapshots", "qtable.csv")
    upd  = os.path.join(logs_learn_dir, "qtable_updates.log")
    onoff = os.path.join(logs_learn_dir, "learning_on_off.txt")

    if not os.path.exists(snap):
        raise SystemExit(f"Missing snapshot: {snap}")
    if not os.path.exists(upd):
        raise SystemExit(f"Missing updates log: {upd}")

    q_size = q_size_from_snapshot(snap)
    cov_pct, t_end = coverage_pct_from_updates(upd, q_size)
    stop_h, stopped, stop_display = stop_time_hours(onoff, t_end)

    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run", "q_size", "coverage_pct", "stop_h", "stop_display", "stopped"])
        w.writerow([
            os.path.basename(logs_learn_dir),
            q_size,
            round(cov_pct, 2),
            round(stop_h, 2) if stop_h == stop_h else "",
            stop_display,
            int(stopped),
        ])

    print("[ok] wrote", out_csv)

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: <logs_*_learn_dir> <out.csv>")
        raise SystemExit(2)
    main(sys.argv[1], sys.argv[2])