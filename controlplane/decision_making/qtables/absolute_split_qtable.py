import numpy as np
from controlplane.controller_config import MAX_QUEUE_LENGTH, ECMP_MAX_WEIGHT, WEIGHT_STEP
from controlplane.decision_making.qtables.abstract_qtable import QTable
from typing import Tuple

class AbsoluteSplitQTable(QTable):
    def __init__(self):
        super().__init__()
        self.state_bins = 6
        self.action_values = list(range(0, ECMP_MAX_WEIGHT + 1, WEIGHT_STEP))
        self.qtable = np.zeros((len(self.action_values), self.state_bins, self.state_bins), dtype=float)

    def _state(self, q):
        r = q / MAX_QUEUE_LENGTH
        if r < .05:
            return 0
        if r < .25:
            return 1
        if r < .5:
            return 2
        if r < .75:
            return 3
        if r < .95:
            return 4
        return 5

    def _compute_update(self, h,
                        prev_ports, prev_weights,
                        reward,
                        next_ports, next_weights,
                        prev_action) -> Tuple[tuple, float, float]:
        """Return the Q-learning update for one transition.

        The caller may apply the returned value immediately or only use it to
        monitor convergence when learning is paused.
        """
        v_prev = list(prev_ports.values())
        q0p = self._state(v_prev[0].last_known_queue)
        q1p = self._state(v_prev[1].last_known_queue)
        v_next = list(next_ports.values())
        q0n = self._state(v_next[0].last_known_queue)
        q1n = self._state(v_next[1].last_known_queue)
        idx_prev = (prev_action, q0p, q1p)
        q_sa = float(self.qtable[idx_prev])
        max_next = float(self.qtable[(slice(None), q0n, q1n)].max())
        new_v = (1 - h.learning_rate) * q_sa + h.learning_rate * (reward + h.discount_factor * max_next)
        new_v = round(new_v, 3)
        return idx_prev, q_sa, new_v

    def update_with_transition(self, h,
                               prev_ports, prev_weights,
                               reward,
                               next_ports, next_weights,
                               prev_action):
        return super().update_with_transition(h, prev_ports, prev_weights, reward, next_ports, next_weights, prev_action)

    def update(self, h, ports, weights, r, a):
        q0 = self._state(list(ports.values())[0].last_known_queue)
        q1 = self._state(list(ports.values())[1].last_known_queue)
        idx = (a, q0, q1)
        v = float(self.qtable[idx])
        new_v = v + h.learning_rate * (r + h.discount_factor * float(self.qtable[:, q0, q1].max()) - v)
        new_v = round(new_v, 3)
        self._record_update(idx, v, new_v)
        self.qtable[idx] = new_v

    def select_action(self, h, ports, weights):
        q0 = self._state(list(ports.values())[0].last_known_queue)
        q1 = self._state(list(ports.values())[1].last_known_queue)
        if np.random.random() < h.epsilon_value:
            return np.random.randint(len(self.action_values))
        return int(self.qtable[:, q0, q1].argmax())

    def action_to_weight(self, a):
        return self.action_values[a]
