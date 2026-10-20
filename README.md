# MarioNet

MarioNet is a research prototype for **reinforcement-learning-based adaptive weighted ECMP** on programmable networks.
It combines a P4/BMv2 data plane, in-band queue telemetry, and a controller that periodically updates the mapping of virtual ECMP buckets to output ports.

The current implementation reproduces the two-path experimental setup used in the MarioNet paper and provides the learning models, baselines, experiment orchestration, logging, post-processing, and plotting utilities used in the evaluation.

## Associated paper

This repository contains the source code and experimental artifacts for:

> **Valentin Sicard, Emmanuel Lavinal, Urtzi Ayesta.**  
> **MarioNet: Learning Weighted-ECMP Splits Under Congestion.**  
> *IEEE Conference on Local Computer Networks (LCN)*, Coimbra, Portugal, October 2026.

If you use MarioNet in your work, please cite the paper:

```bibtex
@inproceedings{sicard2026marionet,
  author    = {Valentin Sicard and Emmanuel Lavinal and Urtzi Ayesta},
  title     = {MarioNet: Learning Weighted-ECMP Splits Under Congestion},
  booktitle = {IEEE Conference on Local Computer Networks (LCN)},
  year      = {2026},
  month     = {October},
  address   = {Coimbra, Portugal}
}
```

## Overview

MarioNet keeps ECMP's hash-based forwarding model while adapting the traffic split according to congestion. The implementation contains three main components:

1. **Programmable data plane.** A P4/BMv2 switch hashes the flow 5-tuple into a fixed table of virtual buckets. Each bucket maps to an output port, so changing the bucket-to-port allocation changes the weighted-ECMP split without maintaining per-flow state in the switch.
2. **Queue telemetry.** Dedicated telemetry packets periodically collect output-queue occupancy and report it to the controller.
3. **RL controller.** A tabular Q-learning controller observes discretized queue states and updates the weighted-ECMP split. The repository contains both MarioNet actuation models from the paper:
   - **Model A — incremental split update:** the controller applies bounded changes to the current split;
   - **Model B — absolute split selection:** the controller directly selects the next admissible split.

The repository also contains the static **ECMP** baseline and the **QCMP-style** learning baseline used in the evaluation.

## Repository layout

| Path | Description |
| --- | --- |
| `dataplane/` | P4 program and topology/runtime configuration for the BMv2/Mininet data plane. |
| `controlplane/` | Controller, telemetry processing, learners, Q-tables, reward functions, and logging. |
| `controlplane/controller_config.py` | Active controller configuration for a manual run. |
| `scenarios/` | Scenario-specific configurations for Model A, Model B, ECMP, and QCMP. |
| `scenarios.py` | Batch experiment definitions and Q-table paths. |
| `scripts/` | Switch initialization, traffic replay, batch execution, and paper-data-generation scripts. |
| `telemetry/` | Telemetry packet generation and telemetry path configuration. |
| `plots/` | Plotting utilities for experiment logs and PCAP traces. |
| `postprocess.py` | Post-processing of a single run. |
| `batch_postprocess.py` | Batch-level aggregation and summary generation. |
| `tcp_ooo_rate.py` | TCP out-of-order packet analysis. |

## Experimental setup used in the paper

The supplied scenario configurations match the main parameters of the paper evaluation:

| Parameter | Value |
| --- | ---: |
| Load-balanced output ports | 2 |
| Queue capacity | 200 packets |
| Aggregate service rate | 360 packets/s (180 packets/s per port) |
| Input traffic rate | 340 packets/s |
| Virtual buckets | 100 |
| Split granularity | 5 buckets |
| Telemetry period | 0.25 s |
| Controller / Q-learning period | 0.5 s |
| Discount factor `gamma` | 0.95 |
| Initial learning rate `alpha` | 0.4 |
| Initial exploration rate `epsilon` during training | 0.3 |
| Reward coefficients | congestion = 0.5, imbalance = 1, overflow = 2 |

These values are encoded in the scenario configuration files and in the switch/telemetry initialization scripts.

## Requirements

MarioNet is intended to run on Linux with a P4/BMv2/Mininet environment providing:

- `p4c` and BMv2 (`simple_switch_grpc`, `simple_switch_CLI`);
- Mininet;
- the P4Runtime Python library (`p4runtime_lib`);
- `tcpreplay`;
- Python 3.

The Makefile currently includes the Makefile from a local P4-Mininet environment:

```make
P4_MININET=~/p4-mininet
```

Update `P4_MININET` in `Makefile` if your installation is elsewhere.

The Python code directly uses the following third-party packages:

```text
numpy
pandas
PyYAML
matplotlib
dpkt
scapy
grpcio
```

Install them in the same Python environment used by your P4Runtime setup. The replay scripts also assume that `$HOME/p4setup.bash` activates/configures that environment.

## Traffic traces

The paper experiments use the **UNI1** data-center packet traces from Benson, Akella, and Maltz, *Network Traffic Characteristics of Data Centers in the Wild*, IMC 2010.

The original traces are **not redistributed in this repository**. However, the **preprocessed traces used in the paper are publicly available** from the following shared folder:

**[MarioNet paper traces (IRIT Cloud)](https://cloud.irit.fr/s/G6dc9qmCcsnn7oj)**

These traces have already been filtered and had their IP addresses rewritten to match the Mininet topology, so they are ready to use with the experiment scripts. They are named as follows:

```text
univ1_pt1_filtered_pnat.pcap
...
univ1_pt14_filtered_pnat.pcap
```

The paper uses:

- `pt1` to `pt9` for learning;
- `pt10` to `pt14` for inference/evaluation.

By default, `scripts/run_traffic_replay.sh` looks for captures in:

```bash
CAPTURES_DIR="$HOME/captures"
```

Change `CAPTURES_DIR` if necessary, or pass an explicit PCAP path when running the replay script manually.

## Configuration

The main configuration points are:

- **P4/Mininet environment:** `P4_MININET` in `Makefile`;
- **topology:** `dataplane/topo/topology.json`;
- **traffic traces:** `CAPTURES_DIR` in `scripts/run_traffic_replay.sh`;
- **telemetry period and source-routed telemetry paths:** `telemetry/telemetry_config.yaml`;
- **controller, learner, reward, and hyperparameters:** `controlplane/controller_config.py`;
- **paper experiment configurations:** `scenarios/*/scenario_config.py`;
- **batch experiment list:** `scenarios.py`.

During a batch run, the selected scenario configuration is temporarily copied over `controlplane/controller_config.py` and the original file is restored afterwards.

## Quick start: manual experiment

The following example runs **Model A with `K={1,4}` in learning mode**.

First, from the repository root, select the corresponding controller configuration:

```bash
cp scenarios/model_a_k1_k4_learn/scenario_config.py \
   controlplane/controller_config.py
```

Then use three terminals.

### Terminal 1 — start the P4/BMv2-Mininet data plane

```bash
make
```

### Terminal 2 — replay traffic

```bash
./scripts/run_traffic_replay.sh \
  --in-pps 340 \
  --capa 360 \
  univ1_pt1_filtered_pnat.pcap
```

### Terminal 3 — start the controller

```bash
sudo -E env PATH="$PATH" ./controlplane/core/controller.py \
  --mode learn \
  --test_name univ1_model_a_k1_k4_learn
```

The controller also accepts an explicit Q-table snapshot. For example, to run inference:

```bash
sudo -E env PATH="$PATH" ./controlplane/core/controller.py \
  --mode infer \
  --qtable logs_univ1_model_a_k1_k4_learn/q_table_snapshots/qtable.csv \
  --test_name univ1_model_a_k1_k4_infer_pt10
```

Supported controller modes are `auto`, `learn`, `infer`, and `ecmp`. In `auto` mode, the controller selects `infer` when a Q-table is supplied and `learn` otherwise.

When the experiment is finished, clean the Mininet/BMv2 state with:

```bash
make clean
```

## Batch experiments

Batch experiments are defined in `scenarios.py`. The file contains blocks for:

- ECMP;
- QCMP;
- Model A with `K={1}`;
- Model A with `K={1,4}`;
- Model A with `K={1,2,4}`;
- Model B, split-unaware;
- Model B, split-aware.

Enable the scenario block you want to run, verify the PCAP names and Q-table paths, and launch:

```bash
python3 scripts/batch_run_traffic_replay.py --keep \
  | tee batch_run_traffic_replay_output.txt
```

Use `--keep` when reproducing the paper results: without it, the batch runner removes several large intermediate log files after post-processing.

For the static ECMP baseline:

```bash
python3 scripts/batch_run_traffic_replay.py --keep --ecmp \
  | tee batch_run_traffic_replay_output.txt
```

The batch runner starts Mininet, traffic replay, and the controller; stores run metadata; archives the relevant PCAPs; performs post-processing; and updates `batch_summary.csv`.

## Output and post-processing

A controller run creates a directory named:

```text
logs_<test_name>/
```

Depending on the run mode and cleanup settings, it can contain:

- `config_snapshot.json` — controller configuration used for the run;
- `run_params.json` — traffic rate, capacity, and input PCAPs;
- `monitoring.log` — queue telemetry;
- `decisions.txt` — split decisions;
- `qtable_updates.log` and `learning_on_off.txt` — learning diagnostics;
- `q_table_snapshots/` — Q-table snapshots;
- `pcaps/` — archived sender/receiver captures;
- `plots/` — generated figures and TCP OOO report;
- `summary_row.json` — post-processed metrics.

To post-process one existing run:

```bash
python3 postprocess.py --name <test_name>
```

To generate the standard run plots directly:

```bash
python3 plots/plot_experiment_logs.py --folder logs_<test_name>/
```

## Reproducing the paper evaluation

For each MarioNet/QCMP learning configuration, the intended workflow is:

1. train on `pt1`-`pt9`;
2. keep the final Q-table snapshot produced by the learning run;
3. use that Q-table for inference on each of `pt10`-`pt14`;
4. retain full logs with `--keep`;
5. post-process the runs and generate the paper metrics/plots using `scripts/paper_data_generation/`.

## License

MarioNet is released under the GNU General Public License v3.0 (GPL-3.0-only).
See the [LICENSE](LICENSE) file for details.
