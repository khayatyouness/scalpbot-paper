# -*- coding: utf-8 -*-
"""Selecteur de strategie : retourne le module exposant l'interface commune
(warmup / precompute / signal_at / opposite_at)."""
from . import strategy, strategy_smc

_STRATS = {
    "momentum": strategy,
    "smc": strategy_smc,
}


def get(cfg):
    name = getattr(cfg, "strategy", "momentum")
    if name not in _STRATS:
        raise KeyError(f"Strategie inconnue: {name}. Connues: {', '.join(_STRATS)}")
    return _STRATS[name]
