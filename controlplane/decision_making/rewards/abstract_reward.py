from abc import ABC, abstractmethod

class RewardFunction(ABC):
    @abstractmethod
    def compute_reward(self, old_ecmp, new_ecmp, old_ports, new_ports, packet_number):
        pass
