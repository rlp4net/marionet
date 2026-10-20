import math
from typing import Dict

import numpy as np

from controlplane.controller_config import PORT_MAX_Q_STATE
from controlplane.decision_making.hyperparams import HyperParams
from controlplane.custom_objects.enumerations import TwoPortsActions
from controlplane.custom_objects import PortInfo
from controlplane.custom_objects.ecmp_weights import EcmpWeights
from controlplane.decision_making.qtables.abstract_qtable import QTable


class QcmpQTable(QTable):
    """
    QCMP Q-table: 3 actions by 11 by 11 queue states for two ports.

    State is (q0, q1), where q0 and q1 are bins in 0..10 derived from
    PortInfo.rescaled_queue_length(PORT_MAX_Q_STATE). ECMP weights are not
    part of the state, following the QCMP baseline.
    """

    def __init__(self) -> None:
        super().__init__()
        self.weight_learning = False  # expected by qtable_viewer and log tooling
        self.state_bins = PORT_MAX_Q_STATE + 1 # 11 bins (0..10) 
        self.action_values = [a.name.lower() for a in TwoPortsActions]

        # Initialize around zero, matching the QCMP implementation.
        self.qtable = np.random.rand(
            len(self.action_values), self.state_bins, self.state_bins
        ) * 0.1 - 0.05
        self.qtable = np.round(self.qtable, 3)

    def _state_indices(self, port_info_map: Dict[int, PortInfo]) -> tuple[int, int]:
        """
        Return (q0_idx, q1_idx) for the two ECMP ports, ordered
        deterministically by increasing port ID.
        """
        ports = sorted(port_info_map.keys())
        if len(ports) != 2:
            raise ValueError("QcmpQTable supports exactly 2 ECMP ports")

        q0 = port_info_map[ports[0]].rescaled_queue_length(PORT_MAX_Q_STATE)
        q1 = port_info_map[ports[1]].rescaled_queue_length(PORT_MAX_Q_STATE)

        max_idx = self.state_bins - 1
        q0 = max(0, min(max_idx, int(q0)))
        q1 = max(0, min(max_idx, int(q1)))
        return q0, q1

    def _compute_update(
        self,
        h: HyperParams,
        prev_ports: Dict[int, PortInfo],
        prev_weights: EcmpWeights,
        reward: float,
        next_ports: Dict[int, PortInfo],
        next_weights: EcmpWeights,
        prev_action: int,
    ) -> tuple[tuple, float, float]:
        q0p, q1p = self._state_indices(prev_ports)
        q0n, q1n = self._state_indices(next_ports)

        idx_prev = (prev_action, q0p, q1p)
        q_sa = float(self.qtable[idx_prev])
        max_next = float(self.qtable[:, q0n, q1n].max())

        new_v = (1.0 - h.learning_rate) * q_sa + h.learning_rate * (
            reward + h.discount_factor * max_next
        )
        # QCMP bounds Q-values in [-1, 1].
        new_v = max(-1.0, min(1.0, new_v))
        new_v = round(new_v, 3)
        return idx_prev, q_sa, new_v

    # Standard QTable interface. The current learner uses the transition-aware method above.
    def update(
        self,
        h: HyperParams,
        ports: Dict[int, PortInfo],
        weights: EcmpWeights,
        reward: float,
        action: int,
    ) -> None:
        q0, q1 = self._state_indices(ports)
        idx = (action, q0, q1)
        q_sa = float(self.qtable[idx])
        max_next = float(self.qtable[:, q0, q1].max())

        new_v = (1.0 - h.learning_rate) * q_sa + h.learning_rate * (
            reward + h.discount_factor * max_next
        )
        new_v = max(-1.0, min(1.0, new_v))
        new_v = round(new_v, 3)

        self._record_update(idx, q_sa, new_v)
        self.qtable[idx] = new_v

    def select_action(
        self,
        h: HyperParams,
        ports: Dict[int, PortInfo],
        weights: EcmpWeights,
    ) -> int:
        """
        Epsilon-greedy selection over the three QCMP actions: updown, downup, no_change.
        """
        q0, q1 = self._state_indices(ports)

        if np.random.random() < h.epsilon_value:
            return int(np.random.randint(len(self.action_values)))

        return int(self.qtable[:, q0, q1].argmax())