import numpy as np

from controlplane.controller_config import MAX_QUEUE_LENGTH, WEIGHT_MAX_Q_STATE
from controlplane.decision_making.qtables.abstract_qtable import QTable
from controlplane.custom_objects.enumerations import TwoPortsActions
class IncrementalSplitQTableBase(QTable):
    def __init__(self, two_port_mode: bool = True, weight_learning: bool = True):
        super().__init__()
        self.two_port_mode = two_port_mode
        self.weight_learning = weight_learning

        self.state_bins = 6
        self.action_values = [a.name.lower() for a in TwoPortsActions]
        if self.weight_learning:
            self.weight_bins = list(range(WEIGHT_MAX_Q_STATE + 1))

        if not two_port_mode:
            raise NotImplementedError("IncrementalSplitQTableBase supports only 2 ports.")

        if weight_learning:
            shape = (len(TwoPortsActions), self.state_bins, self.state_bins, WEIGHT_MAX_Q_STATE + 1)
        else:
            shape = (len(TwoPortsActions), self.state_bins, self.state_bins)

        self.qtable = np.zeros(shape, dtype=float)

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

    def update(self, h, ports, weights, r, a):
        vals = list(ports.values())
        q0 = self._state(vals[0].last_known_queue)
        q1 = self._state(vals[1].last_known_queue)
        if self.weight_learning:
            w = tuple(weights.get_qtable_weights_index())
            idx = (a, q0, q1) + w
            v = float(self.qtable[idx])
            fut = float(self.qtable[(slice(None), q0, q1) + w].max())
        else:
            idx = (a, q0, q1)
            v = float(self.qtable[idx])
            fut = float(self.qtable[:, q0, q1].max())
        new_v = (1 - h.learning_rate) * v + h.learning_rate * (r + h.discount_factor * fut)
        new_v = round(new_v, 3)
        self._record_update(idx, v, new_v)
        self.qtable[idx] = new_v

    def _compute_update(self, h,
                        prev_ports, prev_weights,
                        reward,
                        next_ports, next_weights,
                        prev_action):
        """Return the Q-learning update for one transition.

        The caller may apply the returned value immediately or only use it to
        monitor convergence when learning is paused.
        """

        vals_prev = list(prev_ports.values())
        q0p = self._state(vals_prev[0].last_known_queue)
        q1p = self._state(vals_prev[1].last_known_queue)

        vals_next = list(next_ports.values())
        q0n = self._state(vals_next[0].last_known_queue)
        q1n = self._state(vals_next[1].last_known_queue)

        if self.weight_learning:
            w_prev = tuple(prev_weights.get_qtable_weights_index())
            w_next = tuple(next_weights.get_qtable_weights_index())

            idx_prev = (prev_action, q0p, q1p) + w_prev
            q_sa = float(self.qtable[idx_prev])

            max_next = float(self.qtable[(slice(None), q0n, q1n) + w_next].max())
        else:
            idx_prev = (prev_action, q0p, q1p)
            q_sa = float(self.qtable[idx_prev])
            max_next = float(self.qtable[:, q0n, q1n].max())

        new_v = (1 - h.learning_rate) * q_sa + h.learning_rate * (reward + h.discount_factor * max_next)
        new_v = round(new_v, 3)
        return idx_prev, q_sa, new_v

    def update_with_transition(self, h,
                               prev_ports, prev_weights,
                               reward,
                               next_ports, next_weights,
                               prev_action):
        return super().update_with_transition(h, prev_ports, prev_weights, reward, next_ports, next_weights, prev_action)

    def select_action(self, h, ports, weights):
        vals = list(ports.values())
        q0 = self._state(vals[0].last_known_queue)
        q1 = self._state(vals[1].last_known_queue)

        if np.random.random() < h.epsilon_value:
            return np.random.choice([
                TwoPortsActions.ACTION_INCREASE_DECREASE.value,
                TwoPortsActions.ACTION_DECREASE_INCREASE.value,
                TwoPortsActions.ACTION_NO_CHANGE.value,
            ])

        if self.weight_learning:
            w_idx = tuple(weights.get_qtable_weights_index())
            return int(self.qtable[(slice(None), q0, q1) + w_idx].argmax())
        return int(self.qtable[:, q0, q1].argmax())