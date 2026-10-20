#!/usr/bin/env python3

"""
Learning convergence plot used in the paper.

The curve is:
    EMA(|delta_Q|) / EMA(|Q|)

It is reconstructed only from the logs, without changing the current log format:
  - qtable_updates.log
  - learning_on_off.txt

Examples:
  python3 plots/plot_learning_ratio.py \
      --folder logs_univ1_model_a_k1_k4_learn \
      --title 'Model A'

  python3 plots/plot_learning_ratio.py \
      --folder logs_univ1_model_a_k1_k4_learn \
      --save-to logs_univ1_model_a_k1_k4_learn/plots/learning_ratio_time.png
"""

import argparse
import os
import re
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def read_updates(log_folder, ema_span=50):
    path = os.path.join(log_folder, 'qtable_updates.log')
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    df = pd.read_csv(path)
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df['switch_id'] = pd.to_numeric(df['switch_id'], errors='coerce')
    df['new'] = pd.to_numeric(df['new'], errors='coerce')
    df['ema_delta'] = pd.to_numeric(df['ema_delta'], errors='coerce')
    df = df.dropna(subset=['timestamp', 'switch_id', 'new', 'ema_delta'])

    switch_ids = sorted(df['switch_id'].astype(int).unique())
    if len(switch_ids) != 1:
        raise ValueError(f'learning_ratio supports one switch only, found: {switch_ids}')

    df = df.sort_values('timestamp').copy()
    df['ema_abs_q'] = df['new'].abs().ewm(span=ema_span, adjust=False).mean()
    df['ratio'] = df['ema_delta'] / df['ema_abs_q'].replace(0, np.nan)
    df = df[df['ratio'] > 0].copy()
    return df


def read_events(log_folder, switch_id):
    path = os.path.join(log_folder, 'learning_on_off.txt')
    if not os.path.exists(path):
        return pd.DataFrame(columns=['timestamp', 'event'])

    rows = []
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if '[START-LEARNING]' in line:
                event = 'START'
            elif '[STOP-LEARNING]' in line:
                event = 'STOP'
            elif '[RESUME-LEARNING]' in line:
                event = 'RESUME'
            else:
                continue

            m_switch = re.search(r'switch\s+(\d+)', line)
            if m_switch and int(m_switch.group(1)) != switch_id:
                continue

            try:
                ts = datetime.strptime(line[:19], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                continue

            rows.append({'timestamp': ts, 'event': event})

    if not rows:
        return pd.DataFrame(columns=['timestamp', 'event'])

    return pd.DataFrame(rows).sort_values('timestamp').reset_index(drop=True)


def add_relative_hours(updates, events):
    t0 = updates['timestamp'].min()
    if not events.empty:
        t0 = min(t0, events['timestamp'].min())

    updates = updates.copy()
    updates['hours'] = (updates['timestamp'] - t0).dt.total_seconds() / 3600.0

    events = events.copy()
    if not events.empty:
        events['hours'] = (events['timestamp'] - t0).dt.total_seconds() / 3600.0

    return updates, events


def shade_pauses(ax, events, x_end):
    paused_from = None

    for row in events.itertuples(index=False):
        x = float(row.hours)
        if row.event == 'STOP' and paused_from is None:
            paused_from = x
        elif row.event in ('START', 'RESUME') and paused_from is not None:
            if x > paused_from:
                ax.axvspan(paused_from, x, color='#ececec', zorder=0)
            paused_from = None

    if paused_from is not None and x_end > paused_from:
        ax.axvspan(paused_from, x_end, color='#ececec', zorder=0)


def plot_learning_ratio_from_folder(
    log_folder,
    save_to,
    *,
    title='',
    ratio_min=0.01,
    resume_k=5.0,
    ema_span=50,
    dpi=200,
):
    updates = read_updates(log_folder, ema_span=ema_span)
    switch_id = int(updates['switch_id'].iloc[0])
    events = read_events(log_folder, switch_id)
    updates, events = add_relative_hours(updates, events)

    fig, ax = plt.subplots(figsize=(12, 4.8))
    shade_pauses(ax, events, float(updates['hours'].max()))
    ax.plot(updates['hours'], updates['ratio'], linewidth=1.3)

    for row in events.itertuples(index=False):
        ax.axvline(row.hours, color='0.60', linestyle='--', linewidth=1.0, alpha=0.9)

    ax.axhline(ratio_min * resume_k, color='0.25', linestyle=(0, (1.5, 2.0)), linewidth=1.3)
    ax.axhline(ratio_min, color='0.10', linestyle='--', linewidth=1.5)

    ax.set_yscale('log')
    ax.set_ylim(1e-3, 1.2)
    ax.set_xlim(left=0.0)
    ax.grid(True, which='both', linestyle='--', alpha=0.45)
    ax.set_xlabel('time (hours)')
    ax.set_ylabel('EMA(|ΔQ|)/EMA(|Q|)')
    ax.set_title(title or os.path.basename(os.path.abspath(log_folder)))

    out_dir = os.path.dirname(save_to)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    fig.tight_layout()
    plt.savefig(save_to, dpi=dpi)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', required=True)
    parser.add_argument('--save-to')
    parser.add_argument('--title', default='')
    parser.add_argument('--threshold', type=float, default=0.01)
    parser.add_argument('--resume-k', type=float, default=5.0)
    parser.add_argument('--ema-span', type=int, default=50)
    args = parser.parse_args()

    save_to = args.save_to or os.path.join(args.folder, 'plots', 'learning_ratio_time.png')
    plot_learning_ratio_from_folder(
        args.folder,
        save_to,
        title=args.title,
        ratio_min=args.threshold,
        resume_k=args.resume_k,
        ema_span=args.ema_span,
    )
    print(f'[saved] {save_to}')


if __name__ == '__main__':
    main()