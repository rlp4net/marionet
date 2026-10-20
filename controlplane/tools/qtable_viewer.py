import os
import numpy as np
import pandas as pd
from controlplane.core import logger


def save_snapshot(qt, path):
    folder = logger.OUTPUT_FOLDER
    if folder and not os.path.isabs(path):
        path = os.path.join(folder, "q_table_snapshots", path)

    out_dir = os.path.dirname(path) or "."
    os.makedirs(out_dir, exist_ok=True)

    arr  = qt.qtable
    bins = qt.state_bins
    rows = []
    if arr.ndim == 3:
        for q0 in range(bins):
            for q1 in range(bins):
                row = {"queue0_state": q0, "queue1_state": q1}
                row.update({act: arr[i, q0, q1]
                            for i, act in enumerate(qt.action_values)})
                rows.append(row)

    elif arr.ndim == 4:
        for w_idx, w_lbl in enumerate(qt.weight_bins):
            for q0 in range(bins):
                for q1 in range(bins):
                    row = {"queue0_state": q0,
                           "queue1_state": q1,
                           "weight_bin":   w_lbl}
                    row.update({act: arr[i, q0, q1, w_idx]
                                for i, act in enumerate(qt.action_values)})
                    rows.append(row)
    else:
        raise ValueError(f"Unsupported Q-table shape: {arr.shape}")

    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)

def _action_columns(df: pd.DataFrame, has_weight: bool) -> list[str]:
    meta = ["queue0_state", "queue1_state"] + (["weight_bin"] if has_weight else [])
    return [str(c) for c in df.columns if c not in meta]

def verify_compatibility(qtable, df: pd.DataFrame) -> bool:
    """
    Check that the active Q-table and the CSV snapshot are compatible.
    """
    if not {"queue0_state", "queue1_state"}.issubset(df.columns):
        return False
    has_weight = "weight_bin" in df.columns
    expects_weight = bool(getattr(qtable, "weight_learning", False))
    if has_weight != expects_weight:
        return False

    got_actions = sorted(_action_columns(df, has_weight))
    exp_actions = sorted(str(a) for a in getattr(qtable, "action_values", []))
    if got_actions != exp_actions:
        return False

    bins = int(getattr(qtable, "state_bins"))
    if df["queue0_state"].min() != 0 or df["queue0_state"].max() != bins - 1:
        return False
    if df["queue1_state"].min() != 0 or df["queue1_state"].max() != bins - 1:
        return False

    if has_weight:
        got_w = sorted(df["weight_bin"].drop_duplicates().tolist())
        exp_w = list(getattr(qtable, "weight_bins", []))
        if got_w != exp_w:
            return False
    return True

def load_snapshot_csv(qtable, csv_path: str) -> str:
    """
    Load a CSV snapshot into qtable.qtable after a compatibility check.
    """
    if not csv_path or not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Snapshot not found: {csv_path}")

    df = pd.read_csv(csv_path)
    if not verify_compatibility(qtable, df):
        raise ValueError("Snapshot is incompatible with the configured Q-table")

    has_weight = "weight_bin" in df.columns
    bins = int(getattr(qtable, "state_bins"))
    act_to_idx = {str(a): i for i, a in enumerate(getattr(qtable, "action_values", []))}
    action_cols = _action_columns(df, has_weight)

    if has_weight:
        w_to_idx = {int(w): i for i, w in enumerate(getattr(qtable, "weight_bins", []))}
        arr = np.zeros((len(act_to_idx), bins, bins, len(w_to_idx)), dtype=float)
        for _, r in df.iterrows():
            q0 = int(r["queue0_state"]); q1 = int(r["queue1_state"]); wi = w_to_idx[int(r["weight_bin"])]
            for col in action_cols:
                ai = act_to_idx[str(col)]
                arr[ai, q0, q1, wi] = float(r[col])
    else:
        arr = np.zeros((len(act_to_idx), bins, bins), dtype=float)
        for _, r in df.iterrows():
            q0 = int(r["queue0_state"]); q1 = int(r["queue1_state"])
            for col in action_cols:
                ai = act_to_idx[str(col)]
                arr[ai, q0, q1] = float(r[col])

    qtable.qtable = arr
    return csv_path