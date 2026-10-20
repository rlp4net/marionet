from typing import Dict, Optional
import threading

from .abstract_learner import Learner, SwitchLearnerBase
from controlplane.decision_making.hyperparams import HyperParams
from controlplane.custom_objects.enumerations import Bound
from controlplane.custom_objects.ecmp_weights import EcmpWeights
from controlplane.custom_objects.telemetry_buffers import TelemetryBuffers
from controlplane.network import QSwitch
from controlplane.network.network_interpreter import NetworkInterpreter


class AbsoluteSplitSwitchLearner(SwitchLearnerBase):
    def __init__(self,
                 sw: QSwitch,
                 hp: HyperParams,
                 qtable_csv_path: Optional[str] = None,
                 run_mode: str = "auto"):
        super().__init__(sw, hp, qtable_csv_path=qtable_csv_path, run_mode=run_mode)

    def _apply_selected_action(self) -> None:
        w = self.qtable.action_to_weight(self.selected_action)
        ports = self.switch_obj.get_ecmp_ports()
        self.old_ecmp_weights = EcmpWeights.clone(self.new_ecmp_weights)
        self.new_ecmp_weights.set_bound_weight(ports[0], Bound.UPPER_BOUND.value, w)
        self.new_ecmp_weights.set_bound_weight(ports[1], Bound.LOWER_BOUND.value, w)


class AbsoluteSplitLearner(Learner):
    def __init__(self,
                 sw_map: Dict[int, QSwitch],
                 hp: HyperParams,
                 qtable_csv_path: Optional[str] = None,
                 run_mode: str = "auto"):
        super().__init__()
        self.switch_map = sw_map
        self.hyperparams = hp
        self.sw_learners = {
            sid: AbsoluteSplitSwitchLearner(sw, hp, qtable_csv_path=qtable_csv_path, run_mode=run_mode)
            for sid, sw in sw_map.items()
        }

    def learn(self, switch_id: int, stop_evt: threading.Event, net: NetworkInterpreter, telebuf: TelemetryBuffers):
        print("LEARN switch id " + str(switch_id))
        self.sw_learners[switch_id].learn_from_data(stop_evt, net, telebuf)