from controlplane.decision_making.rewards.abstract_reward import RewardFunction
from controlplane.controller_config import REWARD_CONSTANT, REWARD_THRESHOLD

class QcmpPaperReward(RewardFunction):
    def compute_reward(self, old_ecmp, new_ecmp, old_ports, new_ports, packet_number):
        old_avg = old_ecmp.weighted_average_queue(old_ports, ignore_mean=True)
        new_avg = new_ecmp.weighted_average_queue(new_ports, ignore_mean=True)
        new_diff = new_ecmp.difference_term(new_ports, REWARD_CONSTANT)
        old_diff = old_ecmp.difference_term(old_ports, REWARD_CONSTANT)
        raw_value = (old_avg - new_avg + new_diff - old_diff)

        if raw_value > REWARD_THRESHOLD:
            return 1, new_diff, new_avg
        elif raw_value < REWARD_THRESHOLD:
            return -1, new_diff, new_avg
        else:
            return 0, new_diff, new_avg
