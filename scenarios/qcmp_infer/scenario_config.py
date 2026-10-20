ECMP_MAX_WEIGHT = 100
MAX_QUEUE_LENGTH = 200
PACKET_DIFF_MAX = 3

PORT_MAX_Q_STATE = 10
WEIGHT_STEP  = 5 # step size for weights (split granularity)
WEIGHT_MAX_Q_STATE = ECMP_MAX_WEIGHT // WEIGHT_STEP

REWARD_CONSTANT = 50
REWARD_THRESHOLD = 0.5

# Controller period kept consistent with the other evaluated modes.
LEARN_PERIOD_SEC = 0.5
MAX_LEARN_PERIOD_NO_ACTIVITY = 50

# In inference, epsilon should be 0 (controller also forces it when mode == infer)
HYPERPARAMS = {
    'decay_every_packets': 2400,
    'discount_factor': 0.95,
    'epsilon_value': 0.0,
    'learning_rate': 0.4,
}

STOP_LEARNING = {'EMA_SPAN': 50, 'ENABLED': True, 'RATIO_MIN': 0.01, 'RESUME_K': 5.0}

MODEL_CONFIG = {
    "learner": 'decision_making.learners.qcmp_learner.QcmpLearner',
    "qtable": 'decision_making.qtables.qcmp_qtable.QcmpQTable',
    "reward": 'decision_making.rewards.qcmp_reward.QcmpReward',
}

REWARD_CONFIG = {'CONGESTION_PENALTY': 0.5, 'IMBALANCE_PENALTY': 1, 'OVERFLOW_PENALTY': 2}

INCREMENTAL_SPLIT_ACTIONS = [
    ('inc_dec', 1),
    ('dec_inc', 1),
    ('no_change', 0),
]

CONTROLLER_CONFIG = {
    "p4info": "./build/switch.p4.p4info.txt",
    "seed": 1337,
    "mode": 'infer',
    "no_log": False,
}
