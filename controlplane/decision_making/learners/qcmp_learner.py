from typing import Dict, Optional
import threading

from controlplane.decision_making.hyperparams import HyperParams
from controlplane.custom_objects.telemetry_buffers import TelemetryBuffers
from controlplane.network import QSwitch
from controlplane.network.network_interpreter import NetworkInterpreter

from .abstract_learner import Learner
from .updown_learner import UpdownSwitchLearner


class QcmpSwitchLearner(UpdownSwitchLearner):
    """
    Per-switch learner for the QCMP baseline.

    The implementation reuses the three-action Up/Down learner. The QCMP
    behavior is defined by the configured `(QcmpQTable, QcmpReward)` pair,
    while this class keeps a separate extension point for QCMP-specific changes.
    """
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


class QcmpLearner(Learner):
    """Global QCMP learner: one QcmpSwitchLearner per switch."""

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
        self.qcmp_switch_learners: Dict[int, QcmpSwitchLearner] = {
            sid: QcmpSwitchLearner(
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
        print("LEARN QCMP switch id " + str(switch_id))
        self.qcmp_switch_learners[switch_id].learn_from_data(
            stop_evt, net_interpreter, telemetry_buffers
        )