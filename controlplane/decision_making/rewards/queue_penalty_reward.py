from typing import Dict
from controlplane import controller_config as cfg
from controlplane.controller_config import REWARD_CONFIG
from controlplane.decision_making.rewards.abstract_reward import RewardFunction


class QueuePenaltyReward(RewardFunction):
    """Penalty-based reward used by MARIONET.

    The reward combines normalized congestion, queue imbalance and a
    near-overflow penalty. This matches the objective described in the paper.
    """

    def compute_reward(
        self,
        old_ecmp,
        new_ecmp,
        old_ports: Dict[int, "PortInfo"],
        new_ports: Dict[int, "PortInfo"],
        packet_number: int,
    ):
        # Normalized congestion: average queue occupancy over the two ports.
        queues = [pi.last_known_queue for pi in new_ports.values()]
        congestion = sum(queues)
        congestion /= cfg.MAX_QUEUE_LENGTH * 2

        # Near-overflow safety term.
        if any(q >= 0.95 * cfg.MAX_QUEUE_LENGTH for q in queues):
            overflow = 1
        else:
            overflow = 0

        # Normalized squared imbalance between the two queues.
        imbalance = abs(queues[0] - queues[1])
        imbalance /= cfg.MAX_QUEUE_LENGTH
        imbalance **= 2

        reward = (
            -(REWARD_CONFIG.get("CONGESTION_PENALTY") * congestion)
            -(REWARD_CONFIG.get("IMBALANCE_PENALTY") * imbalance)
            -(REWARD_CONFIG.get("OVERFLOW_PENALTY") * overflow)
        )

        difference_term = 0
        average = 0
        return reward, difference_term, average
