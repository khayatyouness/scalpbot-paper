# -*- coding: utf-8 -*-
"""Gestion du risque : sizing par risque fixe, garde-fous journaliers."""


def position_size(equity, entry, stop, cfg, instrument):
    """Quantite telle que la perte au stop = risk_per_trade x equity.

    Retourne 0 si la distance de stop est nulle ou la taille sous le minimum.
    """
    risk_amount = equity * cfg.risk_per_trade
    stop_dist = abs(entry - stop)
    if stop_dist <= 0:
        return 0.0
    qty = risk_amount / stop_dist
    # arrondi a la granularite de quantite de l'instrument
    step = instrument.min_qty
    qty = (int(qty / step)) * step if step > 0 else qty
    if qty < instrument.min_qty:
        return 0.0
    return round(qty, 8)


class DayGuard:
    """Bloque le trading si la perte du jour depasse le seuil."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.day = None
        self.start_equity = None
        self.locked = False

    def update(self, equity, day_key):
        if day_key != self.day:
            self.day = day_key
            self.start_equity = equity
            self.locked = False
        if self.start_equity:
            dd = (equity - self.start_equity) / self.start_equity
            if dd <= -self.cfg.max_daily_loss:
                self.locked = True
        return self.locked

    def can_trade(self):
        return not self.locked
