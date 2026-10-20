ECMP_MAX_WEIGHT = 100
MAX_QUEUE_LENGTH = 200
PACKET_DIFF_MAX = 3

PORT_MAX_Q_STATE = 10
WEIGHT_STEP  = 5 # step size for weights (split granularity)
WEIGHT_MAX_Q_STATE = ECMP_MAX_WEIGHT // WEIGHT_STEP

REWARD_CONSTANT = 50 # Used in QCMP
REWARD_THRESHOLD = 0.5 # Used in QCMP

# Period (in seconds) between each learning cycle
LEARN_PERIOD_SEC = 0.5
# Maximum number of learning cycles with no telemetry before stopping learner thread
# (set to 0 to keep running even if no telemetry)
MAX_LEARN_PERIOD_NO_ACTIVITY = 50

HYPERPARAMS = {'decay_every_packets': 2400, 'discount_factor': 0.95, 'epsilon_value': 0.0, 'learning_rate': 0.4}

STOP_LEARNING = {'EMA_SPAN': 50, 'ENABLED': True, 'RATIO_MIN': 0.01, 'RESUME_K': 5.0}

MODEL_CONFIG = {
    "learner": 'decision_making.learners.absolute_split_learner.AbsoluteSplitLearner',
    "qtable": 'decision_making.qtables.absolute_split_qtable.AbsoluteSplitQTable',
    "reward": 'decision_making.rewards.queue_penalty_reward.QueuePenaltyReward',
}

REWARD_CONFIG = {'CONGESTION_PENALTY': 0.5, 'IMBALANCE_PENALTY': 1, 'OVERFLOW_PENALTY': 2}

# Incremental Model A actions. Ignored by absolute-split and baseline modes.
# Each non-zero action changes the split by step_factor * WEIGHT_STEP buckets.
INCREMENTAL_SPLIT_ACTIONS = [
    ('inc_dec', 1),
    ('dec_inc', 1),
    ('no_change', 0),
]

# Controller options (used by controller.py)
CONTROLLER_CONFIG = {
    "p4info": "./build/switch.p4.p4info.txt",
    "seed": 1337,
    "mode": 'infer',
    "no_log": False,
}
