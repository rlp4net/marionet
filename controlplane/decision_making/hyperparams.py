import math
import numpy as np
from controlplane import controller_config as cfg

class HyperParams:
    def __init__(self,
                 learning_rate:   float = cfg.HYPERPARAMS["learning_rate"],
                 discount_factor: float = cfg.HYPERPARAMS["discount_factor"],
                 epsilon_value:   float = cfg.HYPERPARAMS["epsilon_value"],
                 action_weight:   int   = cfg.WEIGHT_STEP,
                 packet_counter:  int   = 0) -> None:
        self.learning_rate   = learning_rate
        self.discount_factor = discount_factor
        self.epsilon_value   = epsilon_value
        self.action_weight   = action_weight
        self.packet_counter  = packet_counter
        self._decay_every    = int(cfg.HYPERPARAMS.get("decay_every_packets", 0) or 0)

    @classmethod
    def clone(cls, existing: 'HyperParams') -> 'HyperParams':
        if existing is None:
            return cls()
        return cls(existing.learning_rate,
                   existing.discount_factor,
                   existing.epsilon_value,
                   existing.action_weight,
                   existing.packet_counter)

    def update_periodically(self) -> None:
        self.packet_counter += 1
        if self._decay_every <= 0:
            return
        if self.packet_counter % self._decay_every != 0:
            return
        # Keep a small exploration floor during learning; inference scenarios set epsilon to 0.
        if self.epsilon_value > 0.01:
            self.epsilon_value = max(0.01, round(self.epsilon_value - 0.05, 2))
        if self.learning_rate > 0.05:
            self.learning_rate *= 0.85
