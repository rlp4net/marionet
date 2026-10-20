from typing import Dict

from controlplane.decision_making.rewards.abstract_reward import RewardFunction
from controlplane.controller_config import REWARD_CONSTANT, REWARD_THRESHOLD
from controlplane.custom_objects import PortInfo
from controlplane.custom_objects.ecmp_weights import EcmpWeights


class QcmpReward(RewardFunction):
    """
    QCMP reward based on a score difference and a weighted queue average.
    """

    def _score(self, ecmp: EcmpWeights, ports: Dict[int, PortInfo]) -> float:
        # Rebuild queue and weight vectors in a deterministic port order.
        port_ids = sorted(ports.keys())
        if len(port_ids) != 2:
            raise ValueError("QcmpReward requires exactly 2 ports")

        # QCMP uses qdepth / 2 as the path queue signal.
        queues = [ports[p].last_known_queue / 2.0 for p in port_ids]

        weights_map = ecmp.get_port_weights()
        weights = [weights_map[p] for p in port_ids]

        if sum(weights) <= 0:
            return 0.0

        queue_diff = abs(queues[0] - queues[1])
        weighted_avg = sum(q * w for q, w in zip(queues, weights)) / sum(weights)

        return (-queue_diff + REWARD_CONSTANT) + weighted_avg

    def compute_reward(
        self,
        old_ecmp: EcmpWeights,
        new_ecmp: EcmpWeights,
        old_ports: Dict[int, PortInfo],
        new_ports: Dict[int, PortInfo],
        packet_number: int,
    ):
        old_score = self._score(old_ecmp, old_ports)
        new_score = self._score(new_ecmp, new_ports)

        diff = new_score - old_score
        if new_score < old_score - REWARD_THRESHOLD:
            reward = 1
        elif new_score > old_score + REWARD_THRESHOLD:
            reward = -1
        else:
            reward = 0

        # Values kept for reward.log diagnostics.
        difference_term = diff
        average = new_score
        return reward, difference_term, average