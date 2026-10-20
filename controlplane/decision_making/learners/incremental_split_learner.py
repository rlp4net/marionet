from typing import Dict, Optional
import threading

from .abstract_learner import Learner
from .updown_learner import UpdownSwitchLearner
from controlplane.decision_making.hyperparams import HyperParams
from controlplane.custom_objects.enumerations import Bound, PortAction
from controlplane.custom_objects.ecmp_weights import EcmpWeights, EcmpGlobalAction
from controlplane.custom_objects.telemetry_buffers import TelemetryBuffers
from controlplane.network import QSwitch
from controlplane.network.network_interpreter import NetworkInterpreter
from controlplane.decision_making.qtables.incremental_split_qtable import INCREMENTAL_SPLIT_ACTIONS


class IncrementalSplitSwitchLearner(UpdownSwitchLearner):
    def __init__(
        self,
        switch_obj: QSwitch,
        hyperparams: HyperParams,
        qtable_csv_path: Optional[str] = None,
        run_mode: str = "auto",
    ) -> None:
        super().__init__(
            switch_obj,
            hyperparams,
            qtable_csv_path=qtable_csv_path,
            run_mode=run_mode,
        )

    def _apply_selected_action(self) -> None:
        ports = self.switch_obj.get_ecmp_ports()
        global_action = EcmpGlobalAction()

        if not 0 <= self.selected_action < len(INCREMENTAL_SPLIT_ACTIONS):
            raise ValueError(f"Invalid incremental split action: {self.selected_action}")

        direction, factor = INCREMENTAL_SPLIT_ACTIONS[self.selected_action]

        if direction == "inc_dec":
            global_action.set_action_for_bound(
                ports[0], Bound.UPPER_BOUND.value, PortAction.INCREASE
            )
            global_action.set_action_for_bound(
                ports[1], Bound.LOWER_BOUND.value, PortAction.INCREASE
            )
        elif direction == "dec_inc":
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
            factor = 0

        step_factor = factor if factor > 0 else 1
        step = self.hyperparams.action_weight * step_factor

        self.old_ecmp_weights = EcmpWeights.clone(self.new_ecmp_weights)
        self.new_ecmp_weights.apply_global_action(global_action, step)


class IncrementalSplitLearner(Learner):
    def __init__(
        self,
        switch_map: Dict[int, QSwitch],
        hp: HyperParams,
        qtable_csv_path: Optional[str] = None,
        run_mode: str = "auto",
    ) -> None:
        super().__init__()
        self.switch_map = switch_map
        self.hyperparams = hp
        self.sw_learners: Dict[int, IncrementalSplitSwitchLearner] = {
            sid: IncrementalSplitSwitchLearner(
                sw,
                hp,
                qtable_csv_path=qtable_csv_path,
                run_mode=run_mode,
            )
            for sid, sw in switch_map.items()
        }

    def learn(
        self,
        switch_id: int,
        stop_evt: threading.Event,
        net_interpreter: NetworkInterpreter,
        telemetry_buffers: TelemetryBuffers,
    ) -> None:
        print("LEARN incremental split switch id " + str(switch_id))
        self.sw_learners[switch_id].learn_from_data(
            stop_evt, net_interpreter, telemetry_buffers
        )