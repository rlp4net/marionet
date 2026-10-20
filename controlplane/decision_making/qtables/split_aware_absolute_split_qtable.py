import numpy as np
from controlplane.controller_config import MAX_QUEUE_LENGTH, WEIGHT_MAX_Q_STATE, ECMP_MAX_WEIGHT, WEIGHT_STEP
from controlplane.decision_making.qtables.abstract_qtable import QTable

class SplitAwareAbsoluteSplitQTable(QTable):
    def __init__(self):
        super().__init__()
        self.weight_learning = True 
        self.state_bins = 6
        self.action_values = list(range(0, ECMP_MAX_WEIGHT + 1, WEIGHT_STEP))
        self.weight_bins = [x * WEIGHT_STEP for x in range(WEIGHT_MAX_Q_STATE + 1)]
        self.qtable = np.zeros((len(self.action_values),
                                self.state_bins,
                                self.state_bins,
                                WEIGHT_MAX_Q_STATE + 1), dtype=float)

    def _bin_q(self, q: int) -> int:
        r = q / MAX_QUEUE_LENGTH
        if r < .05: return 0
        if r < .25: return 1
        if r < .5:  return 2
        if r < .75: return 3
        if r < .95: return 4
        return 5

    def _w_idx(self, ecmp_weights) -> tuple:
        return tuple(ecmp_weights.get_qtable_weights_index())

    def _compute_update(self, h,
                        prev_ports, prev_weights,
                        reward,
                        next_ports, next_weights,
                        prev_action):
        """Return the Q-learning update for one transition.

        The caller may apply the returned value immediately or only use it to
        monitor convergence when learning is paused.
        """
        v_prev = list(prev_ports.values())
        q0p = self._bin_q(v_prev[0].last_known_queue)
        q1p = self._bin_q(v_prev[1].last_known_queue)
        wp  = self._w_idx(prev_weights)

        v_next = list(next_ports.values())
        q0n = self._bin_q(v_next[0].last_known_queue)
        q1n = self._bin_q(v_next[1].last_known_queue)
        wn  = self._w_idx(next_weights)

        idx_prev = (prev_action, q0p, q1p) + wp
        q_sa = float(self.qtable[idx_prev])
        max_next = float(self.qtable[(slice(None), q0n, q1n) + wn].max())
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
        vals = list(ports.values())
        q0 = self._bin_q(vals[0].last_known_queue)
        q1 = self._bin_q(vals[1].last_known_queue)
        w  = self._w_idx(weights)
        idx = (a, q0, q1) + w
        v = float(self.qtable[idx])
        fut = float(self.qtable[(slice(None), q0, q1) + w].max())
        new_v = (1 - h.learning_rate) * v + h.learning_rate * (r + h.discount_factor * fut)
        new_v = round(new_v, 3)
        self._record_update(idx, v, new_v)
        self.qtable[idx] = new_v

    def select_action(self, h, ports, weights) -> int:
        vals = list(ports.values())
        q0 = self._bin_q(vals[0].last_known_queue)
        q1 = self._bin_q(vals[1].last_known_queue)
        if np.random.random() < h.epsilon_value:
            return np.random.randint(len(self.action_values))
        w = self._w_idx(weights)
        return int(self.qtable[(slice(None), q0, q1) + w].argmax())

    def action_to_weight(self, a_idx: int) -> int:
        return self.action_values[a_idx]