import numpy as np

from controlplane import controller_config as cfg
from controlplane.decision_making.qtables.incremental_split_qtable_base import IncrementalSplitQTableBase

# Actions are configured as (direction, factor) pairs. A factor of 4 with
# WEIGHT_STEP=5 means a ±20-bucket update.
INCREMENTAL_SPLIT_ACTIONS = cfg.INCREMENTAL_SPLIT_ACTIONS


class IncrementalSplitQTable(IncrementalSplitQTableBase):
    def __init__(self, two_port_mode: bool = True, weight_learning: bool = True):
        super().__init__(two_port_mode=two_port_mode, weight_learning=weight_learning)

        self.action_values = []
        for direction, factor in INCREMENTAL_SPLIT_ACTIONS:
            if direction == "no_change":
                self.action_values.append("no_change")
            else:
                self.action_values.append(f"{direction}_{factor}x")

        if self.weight_learning:
            shape = (
                len(self.action_values),
                self.state_bins,
                self.state_bins,
                len(self.weight_bins),
            )
        else:
            shape = (len(self.action_values), self.state_bins, self.state_bins)

        self.qtable = np.zeros(shape, dtype=float)

    def select_action(self, h, ports, weights) -> int:
        vals = list(ports.values())
        q0 = self._state(vals[0].last_known_queue)
        q1 = self._state(vals[1].last_known_queue)

        if np.random.random() < h.epsilon_value:
            return int(np.random.randint(len(self.action_values)))

        if self.weight_learning:
            w_idx = tuple(weights.get_qtable_weights_index())
            return int(self.qtable[(slice(None), q0, q1) + w_idx].argmax())
        return int(self.qtable[:, q0, q1].argmax())