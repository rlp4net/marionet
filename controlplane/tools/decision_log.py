from datetime import datetime
from typing import Dict
import numpy as np

from controlplane import controller_config as cfg
from controlplane.custom_objects.enumerations import Bound
from controlplane.custom_objects import PortInfo

_SNAP: Dict[int, float] = {}

def _slice(qtable, ports, learner):
    """Retourne tuple (vec_all_actions, q_before_scalar) APRES update."""
    p0, p1 = ports
    
    state = getattr(qtable, "_state", None) or getattr(qtable, "_bin_q", None)
    if state is None:
        state = lambda q: learner.port_info_map[p0].rescaled_queue_length(cfg.PORT_MAX_Q_STATE)

    q0 = state(learner.port_info_map[p0].last_known_queue)
    q1 = state(learner.port_info_map[p1].last_known_queue)

    # Keep slices within the actual Q-table dimensions.
    max_q0 = qtable.qtable.shape[1] - 1
    max_q1 = qtable.qtable.shape[2] - 1
    q0 = 0 if q0 < 0 else max_q0 if q0 > max_q0 else q0
    q1 = 0 if q1 < 0 else max_q1 if q1 > max_q1 else q1


    w_idx = ()
    if getattr(qtable, "weight_learning", False):
        w_idx = tuple(learner.new_ecmp_weights.get_qtable_weights_index())
    vec = qtable.qtable[(slice(None), q0, q1, *w_idx)].astype(float)
    return vec

# ------------------------------------------------------------------ #
def dlog_pre_update(learner, selected_action: int) -> None:
    vec = _slice(learner.qtable, learner.switch_obj.get_ecmp_ports(), learner)
    _SNAP[id(learner)] = vec.copy()
# ------------------------------------------------------------------ #
def dlog_post_update(learner, selected_action: int) -> None:
    vec_before = _SNAP.pop(id(learner))           # 1‑D array of Qs before
    q_before   = float(vec_before[selected_action])

    vec      = _slice(learner.qtable, learner.switch_obj.get_ecmp_ports(), learner)
    q_after  = float(vec[selected_action])
    stats    = learner.qtable.progress()  # {'index','old','new','delta','ema_delta','updates'}

    # -------- bloc lisible ----------------------------------------
    logger = learner.csv_logger
    sid    = learner.switch_obj.sid
    ports  = list(learner.switch_obj.get_ecmp_ports())
    p0, p1 = ports

    def _width(w, pid):
        up = w.ecmp_data[pid][Bound.UPPER_BOUND.value]
        lo = w.ecmp_data[pid][Bound.LOWER_BOUND.value]
        return int(up - lo)

    def _line(pid, opi: PortInfo, npi: PortInfo, first):
        sat = "Y" if npi.last_known_queue >= 0.9*cfg.MAX_QUEUE_LENGTH else "N"
        prefix = "Ports    : " if first else "           "
        delta_q = npi.last_known_queue - opi.last_known_queue
        return (f"{prefix}p{pid} smp={opi.packet_diff_count} "
                f"queue_before={opi.last_known_queue} queue_after={npi.last_known_queue} "
                f"delta_queue={delta_q:+} w {_width(learner.old_ecmp_weights,pid)}→{_width(learner.new_ecmp_weights,pid)} "
                f"sat={sat}")

    split_old = int(learner.old_ecmp_weights.ecmp_data[p1][Bound.LOWER_BOUND.value])
    split_new = int(learner.new_ecmp_weights.ecmp_data[p1][Bound.LOWER_BOUND.value])

    policy = "absolute" if hasattr(learner.qtable, "action_values") else "incremental"
    eps    = learner.hyperparams.epsilon_value

    greedy_idx = int(vec_before.argmax())
    mode = "greedy" if selected_action == greedy_idx else "explore"

    _span = int(getattr(cfg, "STOP_LEARNING", {}).get("EMA_SPAN", 50))
    dq = stats.get("delta", None)
    dq_ema = stats.get("ema_delta", None)

    if policy == "incremental":
        names = ["inc_dec", "dec_inc", "no_change"]
        qtxt1 = f"[SELECTED] {names[selected_action]} {q_before:+.2f}->{q_after:+.2f}"
        others = [i for i in np.argsort(vec)[::-1] if i != selected_action][:2]
        qtxt2  = " ".join(f"{names[i]} {vec[i]:+.2f}" for i in others)
        qtxt   = qtxt1 + (" | " + qtxt2 if qtxt2 else "")
    else:
        w = learner.qtable.action_values[selected_action]
        qtxt1 = f"w={w} {q_before:+.2f}->{q_after:+.2f}"
        others = [i for i in np.argsort(vec)[::-1] if i != selected_action][:2]
        qtxt2  = " ".join(f"{learner.qtable.action_values[i]}:{vec[i]:+.2f}" for i in others)
        qtxt   = qtxt1 + (" | " + qtxt2 if qtxt2 else "")

    lines = [
        f"=== Decision {logger._decision_count[sid]+1} | switch {sid} | {datetime.now().isoformat()}",
        f"Policy {policy} | eps={eps:.2f} | mode={mode}",
        _line(p0, learner.old_port_info_map[p0], learner.port_info_map[p0], True),
        _line(p1, learner.old_port_info_map[p1], learner.port_info_map[p1], False),
        f"Split    : {split_old}->{split_new}",
        f"Q-table  : {qtxt}",
        f"Learn    : ΔQ={'' if dq is None else f'{dq:+.3e}'} | EMA{_span}(|ΔQ|)={'' if dq_ema is None else f'{dq_ema:.3e}'}",
        f"Reward   : {learner.current_reward:.3f} fn={learner.reward_fn.__class__.__name__}",
        f"Ref      : pkt={learner.packet_number}",
    ]
    logger.log_decision_block(sid, lines)
    logger.log_qtable_update(sid, learner.packet_number,
                             stats.get("index"), stats.get("old"),
                             stats.get("new"), stats.get("delta"),
                             stats.get("ema_delta"), stats.get("updates"))