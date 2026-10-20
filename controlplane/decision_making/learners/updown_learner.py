from typing import Dict, Optional
import threading

from .abstract_learner import Learner, SwitchLearnerBase
from controlplane.decision_making.hyperparams import HyperParams
from controlplane.custom_objects.enumerations import TwoPortsActions, Bound, PortAction
from controlplane.custom_objects.ecmp_weights import EcmpWeights, EcmpGlobalAction
from controlplane.custom_objects.telemetry_buffers import TelemetryBuffers
from controlplane.network import QSwitch
from controlplane.network.network_interpreter import NetworkInterpreter


class UpdownSwitchLearner(SwitchLearnerBase):
    def __init__(self,
                 switch_obj: QSwitch,
                 hyperparams: HyperParams,
                 qtable_csv_path: Optional[str] = None,
                 run_mode: str = "auto") -> None:
        super().__init__(switch_obj, hyperparams, qtable_csv_path=qtable_csv_path, run_mode=run_mode)

        self.selected_action = TwoPortsActions.ACTION_NO_CHANGE.value

    def _apply_selected_action(self) -> None:
        global_action = EcmpGlobalAction()
        ports = self.switch_obj.get_ecmp_ports()

        if self.selected_action == TwoPortsActions.ACTION_INCREASE_DECREASE.value:
            global_action.set_action_for_bound(
                ports[0], Bound.UPPER_BOUND.value, PortAction.INCREASE
            )
            global_action.set_action_for_bound(
                ports[1], Bound.LOWER_BOUND.value, PortAction.INCREASE
            )
        elif self.selected_action == TwoPortsActions.ACTION_DECREASE_INCREASE.value:
            global_action.set_action_for_bound(
                ports[0], Bound.UPPER_BOUND.value, PortAction.DECREASE
            )
            global_action.set_action_for_bound(
                ports[1], Bound.LOWER_BOUND.value, PortAction.DECREASE
            )
        else:
            global_action.set_action_for_bound(
                ports[0], Bound.UPPER_BOUND.value, PortAction.UNCHANGED
            )
            global_action.set_action_for_bound(
                ports[1], Bound.LOWER_BOUND.value, PortAction.UNCHANGED
            )

        self.old_ecmp_weights = EcmpWeights.clone(self.new_ecmp_weights)
        self.new_ecmp_weights.apply_global_action(
            global_action, self.hyperparams.action_weight
        )


class UpdownLearner(Learner):
    def __init__(self,
                 switch_map: Dict[int, QSwitch],
                 hyperparams: HyperParams,
                 qtable_csv_path: Optional[str] = None,
                 run_mode: str = "auto") -> None:
        super().__init__()
        self.switch_map = switch_map
        self.hyperparams = hyperparams
        self.qcmp_switch_learners: Dict[int, UpdownSwitchLearner] = {
            sid: UpdownSwitchLearner(sw, hyperparams, qtable_csv_path=qtable_csv_path, run_mode=run_mode)
            for sid, sw in switch_map.items()
        }

    def learn(
        self,
        switch_id: int,
        stop_evt: threading.Event,
        net_interpreter: NetworkInterpreter,
        telemetry_buffers: TelemetryBuffers,
    ) -> None:
        print("LEARN switch id " + str(switch_id))
        self.qcmp_switch_learners[switch_id].learn_from_data(
            stop_evt, net_interpreter, telemetry_buffers
        )