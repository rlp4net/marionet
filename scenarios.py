from typing import Dict, List

# --------------------------------------------------------------------
# Scenarios (see scenarios/ folders):
#   - Model A: incremental split update, K={1}, K={1,4}, K={1,2,4}
#   - Model B: absolute split selection, split-unaware vs split-aware
#
# Paths are relative to the repo root.
# --------------------------------------------------------------------

QTABLE_QCMP = 'logs_univ1_qcmp_learn/q_table_snapshots/qtable.csv'
QTABLE_MODEL_A_K1 = 'logs_univ1_model_a_k1_learn/q_table_snapshots/qtable.csv'
QTABLE_MODEL_A_K1_K4 = 'logs_univ1_model_a_k1_k4_learn/q_table_snapshots/qtable.csv'
QTABLE_MODEL_A_K1_K2_K4 = 'logs_univ1_model_a_k1_k2_k4_learn/q_table_snapshots/qtable.csv'
QTABLE_MODEL_B_SPLIT_UNAWARE = 'logs_univ1_model_b_split_unaware_learn/q_table_snapshots/qtable.csv'
QTABLE_MODEL_B_SPLIT_AWARE = 'logs_univ1_model_b_split_aware_learn/q_table_snapshots/qtable.csv'

# Select one scenario block before launching a batch run.

# Baseline ECMP
# Make sure to run scripts/batch_run_traffic_replay.py with --keep --ecmp options
# SCENARIOS: List[Dict] = [
#     {
#         'name': 'univ1_ecmp_pt10',
#         'overrides': {'controlplane/controller_config.py': 'scenarios/ecmp_baseline/scenario_config.py'},
#         'run_args': ['univ1_pt10_filtered_pnat.pcap'],
#     },
#     {
#         'name': 'univ1_ecmp_pt11',
#         'overrides': {'controlplane/controller_config.py': 'scenarios/ecmp_baseline/scenario_config.py'},
#         'run_args': ['univ1_pt11_filtered_pnat.pcap'],
#     },
#     {
#         'name': 'univ1_ecmp_pt12',
#         'overrides': {'controlplane/controller_config.py': 'scenarios/ecmp_baseline/scenario_config.py'},
#         'run_args': ['univ1_pt12_filtered_pnat.pcap'],
#     },
#     {
#         'name': 'univ1_ecmp_pt13',
#         'overrides': {'controlplane/controller_config.py': 'scenarios/ecmp_baseline/scenario_config.py'},
#         'run_args': ['univ1_pt13_filtered_pnat.pcap'],
#     },
#     {
#         'name': 'univ1_ecmp_pt14',
#         'overrides': {'controlplane/controller_config.py': 'scenarios/ecmp_baseline/scenario_config.py'},
#         'run_args': ['univ1_pt14_filtered_pnat.pcap'],
#     }
# ]

# Baseline QCMP
# SCENARIOS: List[Dict] = [
#     {
#         'name': 'univ1_qcmp_learn',
#         'overrides': {'controlplane/controller_config.py': 'scenarios/qcmp_learn/scenario_config.py'},
#         'run_args': [
#             'univ1_pt1_filtered_pnat.pcap',
#             'univ1_pt2_filtered_pnat.pcap',
#             'univ1_pt3_filtered_pnat.pcap',
#             'univ1_pt4_filtered_pnat.pcap',
#             'univ1_pt5_filtered_pnat.pcap',
#             'univ1_pt6_filtered_pnat.pcap',
#             'univ1_pt7_filtered_pnat.pcap',
#             'univ1_pt8_filtered_pnat.pcap',
#             'univ1_pt9_filtered_pnat.pcap',
#         ],
#     },
#     {
#         'name': 'univ1_qcmp_infer_pt10',
#         'overrides': {'controlplane/controller_config.py': 'scenarios/qcmp_infer/scenario_config.py'},
#         'qtable': QTABLE_QCMP,
#         'run_args': ['univ1_pt10_filtered_pnat.pcap'],
#     },
#     {
#         'name': 'univ1_qcmp_infer_pt11',
#         'overrides': {'controlplane/controller_config.py': 'scenarios/qcmp_infer/scenario_config.py'},
#         'qtable': QTABLE_QCMP,
#         'run_args': ['univ1_pt11_filtered_pnat.pcap'],
#     },
#     {
#         'name': 'univ1_qcmp_infer_pt12',
#         'overrides': {'controlplane/controller_config.py': 'scenarios/qcmp_infer/scenario_config.py'},
#         'qtable': QTABLE_QCMP,
#         'run_args': ['univ1_pt12_filtered_pnat.pcap'],
#     },
#     {
#         'name': 'univ1_qcmp_infer_pt13',
#         'overrides': {'controlplane/controller_config.py': 'scenarios/qcmp_infer/scenario_config.py'},
#         'qtable': QTABLE_QCMP,
#         'run_args': ['univ1_pt13_filtered_pnat.pcap'],
#     },
#     {
#         'name': 'univ1_qcmp_infer_pt14',
#         'overrides': {'controlplane/controller_config.py': 'scenarios/qcmp_infer/scenario_config.py'},
#         'qtable': QTABLE_QCMP,
#         'run_args': ['univ1_pt14_filtered_pnat.pcap'],
#     },
# ]

# Model A, K={1}
SCENARIOS: List[Dict] = [
    {'name': 'univ1_model_a_k1_learn',
     'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_learn/scenario_config.py'},
     'run_args': ['univ1_pt1_filtered_pnat.pcap',
                  'univ1_pt2_filtered_pnat.pcap',
                  'univ1_pt3_filtered_pnat.pcap',
                  'univ1_pt4_filtered_pnat.pcap',
                  'univ1_pt5_filtered_pnat.pcap',
                  'univ1_pt6_filtered_pnat.pcap',
                  'univ1_pt7_filtered_pnat.pcap',
                  'univ1_pt8_filtered_pnat.pcap',
                  'univ1_pt9_filtered_pnat.pcap']},
    {'name': 'univ1_model_a_k1_infer_pt10',
     'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_infer/scenario_config.py'},
     'qtable': QTABLE_MODEL_A_K1,
     'run_args': ['univ1_pt10_filtered_pnat.pcap']},
    {'name': 'univ1_model_a_k1_infer_pt11',
     'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_infer/scenario_config.py'},
     'qtable': QTABLE_MODEL_A_K1,
     'run_args': ['univ1_pt11_filtered_pnat.pcap']},
    {'name': 'univ1_model_a_k1_infer_pt12',
     'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_infer/scenario_config.py'},
     'qtable': QTABLE_MODEL_A_K1,
     'run_args': ['univ1_pt12_filtered_pnat.pcap']},
    {'name': 'univ1_model_a_k1_infer_pt13',
     'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_infer/scenario_config.py'},
     'qtable': QTABLE_MODEL_A_K1,
     'run_args': ['univ1_pt13_filtered_pnat.pcap']},
    {'name': 'univ1_model_a_k1_infer_pt14',
     'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_infer/scenario_config.py'},
     'qtable': QTABLE_MODEL_A_K1,
     'run_args': ['univ1_pt14_filtered_pnat.pcap']},
]

# Model A, K={1, 4}
# SCENARIOS: List[Dict] = [
#     {'name': 'univ1_model_a_k1_k4_learn',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_k4_learn/scenario_config.py'},
#      'run_args': ['univ1_pt1_filtered_pnat.pcap',
#                   'univ1_pt2_filtered_pnat.pcap',
#                   'univ1_pt3_filtered_pnat.pcap',
#                   'univ1_pt4_filtered_pnat.pcap',
#                   'univ1_pt5_filtered_pnat.pcap',
#                   'univ1_pt6_filtered_pnat.pcap',
#                   'univ1_pt7_filtered_pnat.pcap',
#                   'univ1_pt8_filtered_pnat.pcap',
#                   'univ1_pt9_filtered_pnat.pcap']},
#     {'name': 'univ1_model_a_k1_k4_infer_pt10',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_k4_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_A_K1_K4,
#      'run_args': ['univ1_pt10_filtered_pnat.pcap']},
#     {'name': 'univ1_model_a_k1_k4_infer_pt11',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_k4_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_A_K1_K4,
#      'run_args': ['univ1_pt11_filtered_pnat.pcap']},
#     {'name': 'univ1_model_a_k1_k4_infer_pt12',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_k4_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_A_K1_K4,
#      'run_args': ['univ1_pt12_filtered_pnat.pcap']},
#     {'name': 'univ1_model_a_k1_k4_infer_pt13',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_k4_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_A_K1_K4,
#      'run_args': ['univ1_pt13_filtered_pnat.pcap']},
#     {'name': 'univ1_model_a_k1_k4_infer_pt14',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_k4_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_A_K1_K4,
#      'run_args': ['univ1_pt14_filtered_pnat.pcap']}
# ]

# Model A, K={1, 2, 4}
# SCENARIOS: List[Dict] = [
#     {'name': 'univ1_model_a_k1_k2_k4_learn',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_k2_k4_learn/scenario_config.py'},
#      'run_args': ['univ1_pt1_filtered_pnat.pcap',
#                   'univ1_pt2_filtered_pnat.pcap',
#                   'univ1_pt3_filtered_pnat.pcap',
#                   'univ1_pt4_filtered_pnat.pcap',
#                   'univ1_pt5_filtered_pnat.pcap',
#                   'univ1_pt6_filtered_pnat.pcap',
#                   'univ1_pt7_filtered_pnat.pcap',
#                   'univ1_pt8_filtered_pnat.pcap',
#                   'univ1_pt9_filtered_pnat.pcap']},
#     {'name': 'univ1_model_a_k1_k2_k4_infer_pt10',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_k2_k4_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_A_K1_K2_K4,
#      'run_args': ['univ1_pt10_filtered_pnat.pcap']},
#     {'name': 'univ1_model_a_k1_k2_k4_infer_pt11',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_k2_k4_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_A_K1_K2_K4,
#      'run_args': ['univ1_pt11_filtered_pnat.pcap']},
#     {'name': 'univ1_model_a_k1_k2_k4_infer_pt12',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_k2_k4_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_A_K1_K2_K4,
#      'run_args': ['univ1_pt12_filtered_pnat.pcap']},
#     {'name': 'univ1_model_a_k1_k2_k4_infer_pt13',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_k2_k4_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_A_K1_K2_K4,
#      'run_args': ['univ1_pt13_filtered_pnat.pcap']},
#     {'name': 'univ1_model_a_k1_k2_k4_infer_pt14',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_a_k1_k2_k4_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_A_K1_K2_K4,
#      'run_args': ['univ1_pt14_filtered_pnat.pcap']}
# ]

# Model B, split-unaware: state is (q1, q2)
# SCENARIOS: List[Dict] = [
#     {'name': 'univ1_model_b_split_unaware_learn',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_unaware_learn/scenario_config.py'},
#      'run_args': ['univ1_pt1_filtered_pnat.pcap',
#                   'univ1_pt2_filtered_pnat.pcap',
#                   'univ1_pt3_filtered_pnat.pcap',
#                   'univ1_pt4_filtered_pnat.pcap',
#                   'univ1_pt5_filtered_pnat.pcap',
#                   'univ1_pt6_filtered_pnat.pcap',
#                   'univ1_pt7_filtered_pnat.pcap',
#                   'univ1_pt8_filtered_pnat.pcap',
#                   'univ1_pt9_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_unaware_infer_pt10',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_unaware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_UNAWARE,
#      'run_args': ['univ1_pt10_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_unaware_infer_pt11',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_unaware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_UNAWARE,
#      'run_args': ['univ1_pt11_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_unaware_infer_pt12',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_unaware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_UNAWARE,
#      'run_args': ['univ1_pt12_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_unaware_infer_pt13',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_unaware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_UNAWARE,
#      'run_args': ['univ1_pt13_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_unaware_infer_pt14',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_unaware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_UNAWARE,
#      'run_args': ['univ1_pt14_filtered_pnat.pcap']}
# ]

# Model B, split-aware: state is (q1, q2, w)
# Learn pt1-pt9
# SCENARIOS: List[Dict] = [
#     {'name': 'univ1_model_b_split_aware_learn',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_aware_learn/scenario_config.py'},
#      'run_args': ['univ1_pt1_filtered_pnat.pcap',
#                   'univ1_pt2_filtered_pnat.pcap',
#                   'univ1_pt3_filtered_pnat.pcap',
#                   'univ1_pt4_filtered_pnat.pcap',
#                   'univ1_pt5_filtered_pnat.pcap',
#                   'univ1_pt6_filtered_pnat.pcap',
#                   'univ1_pt7_filtered_pnat.pcap',
#                   'univ1_pt8_filtered_pnat.pcap',
#                   'univ1_pt9_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_aware_infer_pt10',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_aware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_AWARE,
#      'run_args': ['univ1_pt10_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_aware_infer_pt11',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_aware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_AWARE,
#      'run_args': ['univ1_pt11_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_aware_infer_pt12',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_aware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_AWARE,
#      'run_args': ['univ1_pt12_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_aware_infer_pt13',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_aware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_AWARE,
#      'run_args': ['univ1_pt13_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_aware_infer_pt14',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_aware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_AWARE,
#      'run_args': ['univ1_pt14_filtered_pnat.pcap']}
# ]

# Model B, split-aware: state is (q1, q2, w)
# Learn pt1-pt10
# SCENARIOS: List[Dict] = [
#     {'name': 'univ1_model_b_split_aware_learn',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_aware_learn/scenario_config.py'},
#      'run_args': ['univ1_pt1_filtered_pnat.pcap',
#                   'univ1_pt2_filtered_pnat.pcap',
#                   'univ1_pt3_filtered_pnat.pcap',
#                   'univ1_pt4_filtered_pnat.pcap',
#                   'univ1_pt5_filtered_pnat.pcap',
#                   'univ1_pt6_filtered_pnat.pcap',
#                   'univ1_pt7_filtered_pnat.pcap',
#                   'univ1_pt8_filtered_pnat.pcap',
#                   'univ1_pt9_filtered_pnat.pcap',
#                   'univ1_pt10_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_aware_infer_pt11',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_aware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_AWARE,
#      'run_args': ['univ1_pt11_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_aware_infer_pt12',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_aware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_AWARE,
#      'run_args': ['univ1_pt12_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_aware_infer_pt13',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_aware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_AWARE,
#      'run_args': ['univ1_pt13_filtered_pnat.pcap']},
#     {'name': 'univ1_model_b_split_aware_infer_pt14',
#      'overrides': {'controlplane/controller_config.py': 'scenarios/model_b_split_aware_infer/scenario_config.py'},
#      'qtable': QTABLE_MODEL_B_SPLIT_AWARE,
#      'run_args': ['univ1_pt14_filtered_pnat.pcap']}
# ]
