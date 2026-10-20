from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
from controlplane import controller_config as cfg

class QTable(ABC):
    def __init__(self) -> None:
        self._last_update: Optional[Tuple[tuple, float, float, float]] = None
        self._ema_abs_delta: Optional[float] = None
        self._ema_abs_q: Optional[float] = None
        self._num_updates: int = 0
        self._learning_stopped: bool = False

    @abstractmethod
    def update(self, hyperparams, port_info, ecmp_weights, reward, action):
        pass

    @abstractmethod
    def select_action(self, hyperparams, port_info, ecmp_weights):
        pass

    def update_with_transition(self, hyperparams,
                               prev_ports, prev_weights,
                               reward,
                               next_ports, next_weights,
                               prev_action):
        if hasattr(self, "_compute_update"):
            idx, old_v, new_v = self._compute_update(hyperparams, prev_ports, prev_weights,
                                                     reward, next_ports, next_weights, prev_action)
            self._record_update(idx, old_v, new_v)
            self.qtable[idx] = new_v
            return idx, old_v, new_v
        return self.update(hyperparams, next_ports, next_weights, reward, prev_action)

    def compute_update_with_transition(self, hyperparams,
                                       prev_ports, prev_weights,
                                       reward,
                                       next_ports, next_weights,
                                       prev_action):
        if not hasattr(self, "_compute_update"):
            raise NotImplementedError
        idx, old_v, new_v = self._compute_update(hyperparams, prev_ports, prev_weights,
                                                 reward, next_ports, next_weights, prev_action)
        self._record_update(idx, old_v, new_v)
        return idx, old_v, new_v

    def apply_computed_update(self, index, new_value):
        self.qtable[index] = new_value

    def _record_update(self, index: tuple, old_value: float, new_value: float) -> None:
        delta = abs(float(new_value) - float(old_value))
        span = int(getattr(cfg, "STOP_LEARNING", {}).get("EMA_SPAN", 50))
        alpha = 2.0 / (float(span) + 1.0)
        self._ema_abs_delta = delta if self._ema_abs_delta is None else alpha * delta + (1.0 - alpha) * self._ema_abs_delta
        abs_q = abs(float(new_value))
        self._ema_abs_q = abs_q if self._ema_abs_q is None else alpha * abs_q + (1.0 - alpha) * self._ema_abs_q
        self._last_update = (index, float(old_value), float(new_value), delta)
        self._num_updates += 1

    def progress(self) -> Dict[str, Any]:
        idx, old_v, new_v, d = (None, None, None, None)
        if self._last_update is not None:
            idx, old_v, new_v, d = self._last_update
        return {
            "index": idx,
            "old": old_v,
            "new": new_v,
            "delta": d,
            "ema_delta": self._ema_abs_delta,
            "updates": self._num_updates,
        }

    def should_learn(self) -> tuple[bool, Optional[str]]:
        sl = getattr(cfg, "STOP_LEARNING", {})
        if not bool(sl.get("ENABLED", False)):
            return True, None
        if self._ema_abs_delta is None or self._ema_abs_q is None:
            return True, None

        thr = float(sl.get("RATIO_MIN", 1e-2))
        r_k = float(sl.get("RESUME_K", 5.0))

        stop_cond = self._ema_abs_delta < thr * self._ema_abs_q
        resume_cond = self._ema_abs_delta > r_k * thr * self._ema_abs_q

        if self._learning_stopped:
            if resume_cond:
                self._learning_stopped = False
                return True, (f"[RESUME-LEARNING] EMA(|ΔQ|)={self._ema_abs_delta:.3e} > "
                              f"{r_k:.1f}*thr*EMA(|Q|)={(r_k*thr*self._ema_abs_q):.3e}")
            return False, None
        else:
            if stop_cond:
                self._learning_stopped = True
                return False, (f"[STOP-LEARNING]   EMA(|ΔQ|)={self._ema_abs_delta:.3e} < "
                               f"thr*EMA(|Q|)={(thr*self._ema_abs_q):.3e}")
            return True, None