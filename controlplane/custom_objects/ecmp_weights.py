from typing import Dict, List
from controlplane.controller_config import ECMP_MAX_WEIGHT, WEIGHT_STEP
from .enumerations import Bound, PortAction
from .port_info import PortInfo

class EcmpGlobalAction:
    """
    Describes the action for each port (and which bound to move up/down).
    """

    def __init__(self) -> None:
        self.per_port_actions: Dict[int, Dict[int, PortAction]] = {}

    def set_action_for_bound(self, port_id: int, bound_type: int, action: PortAction) -> 'EcmpGlobalAction':
        if port_id not in self.per_port_actions:
            self.per_port_actions[port_id] = {}
        self.per_port_actions[port_id][bound_type] = action
        return self

class EcmpWeights:
    """
    Manages the lower/upper weight bounds for each port.
    """

    def __init__(self, ecmp_port_list: List[int]) -> None:
        portion = int(ECMP_MAX_WEIGHT / len(ecmp_port_list))
        self.ecmp_data: Dict[int, Dict[int, int]] = {}
        for idx, port_id in enumerate(ecmp_port_list):
            self.ecmp_data[port_id] = {
                0: portion * idx,
                1: portion * (idx + 1)
            }
            if idx == len(ecmp_port_list) - 1:
                self.ecmp_data[port_id][1] = ECMP_MAX_WEIGHT

    @classmethod
    def clone(cls, existing: 'EcmpWeights') -> 'EcmpWeights':
        new_obj = cls(list(existing.ecmp_data.keys()))
        for port_id, bounds_map in existing.ecmp_data.items():
            for b_idx, val in bounds_map.items():
                new_obj.ecmp_data[port_id][b_idx] = val
        return new_obj

    def set_bound_weight(self, port_id: int, bound_type: int, new_weight: int) -> None:
        if new_weight < 0:
            new_weight = 0
        if new_weight > ECMP_MAX_WEIGHT:
            new_weight = ECMP_MAX_WEIGHT
        self.ecmp_data[port_id][bound_type] = new_weight

    def apply_global_action(self, global_action: EcmpGlobalAction, action_weight: int) -> None:
        for port_id, bound_map in global_action.per_port_actions.items():
            for b_idx, action_val in bound_map.items():
                if action_val == PortAction.INCREASE:
                    self.set_bound_weight(port_id,
                                          b_idx,
                                          self.ecmp_data[port_id][b_idx] + action_weight)
                elif action_val == PortAction.DECREASE:
                    self.set_bound_weight(port_id,
                                          b_idx,
                                          self.ecmp_data[port_id][b_idx] - action_weight)

    def get_port_weights(self) -> Dict[int, int]:
        output = {}
        for port_id, b_map in self.ecmp_data.items():
            up_bound = b_map[Bound.UPPER_BOUND.value]
            low_bound = b_map[Bound.LOWER_BOUND.value]
            output[port_id] = up_bound - low_bound
        return output

    def get_qtable_weights_index(self) -> List[int]:
        port_ids = list(self.ecmp_data.keys())
        idx_list: List[int] = []
        for p in port_ids[:-1]:
            up_bound = self.ecmp_data[p][Bound.UPPER_BOUND.value]
            low_bound = self.ecmp_data[p][Bound.LOWER_BOUND.value]
            idx_list.append((up_bound - low_bound) // WEIGHT_STEP)
        return idx_list

    def weighted_average_queue(self,
                               port_info_map: Dict[int, PortInfo],
                               ignore_mean: bool = False) -> float:
        total_weight = 0
        total_queues = 0
        for pid, b_map in self.ecmp_data.items():
            w = b_map[Bound.UPPER_BOUND.value] - b_map[Bound.LOWER_BOUND.value]
            total_weight += w
            total_queues += w * port_info_map[pid].last_known_queue
        if total_weight == 0:
            total_weight = 1
        if ignore_mean:
            return float(total_queues)
        return float(total_queues) / float(total_weight)

    def difference_term(self,
                        port_info_map: Dict[int, PortInfo],
                        difference_constant: float) -> float:
        min_val = float('inf')
        max_val = -1.0
        for pid in self.ecmp_data:
            q = port_info_map[pid].last_known_queue
            if q < min_val:
                min_val = q
            if q > max_val:
                max_val = q
        return difference_constant - abs(max_val - min_val)

    def estimate_state_value(self,
                             port_info_map: Dict[int, PortInfo],
                             difference_constant: float) -> float:
        return (self.weighted_average_queue(port_info_map)
                + self.difference_term(port_info_map, difference_constant))
