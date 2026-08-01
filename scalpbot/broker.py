# -*- coding: utf-8 -*-
"""Broker PAPER (simule) : positions, fills realistes, PnL, equity.

AUCUN ordre reel n'est passe. On simule :
  - le spread bid/ask (on achete a l'ask, on vend au bid),
  - le slippage sur ordre marche,
  - les frais (en points de base sur le notionnel),
  - le declenchement intra-bougie du stop-loss / take-profit.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Position:
    side: str            # "long" / "short"
    qty: float
    entry: float         # prix d'entree effectif (apres spread/slippage)
    stop: float
    target: float
    atr: float
    opened_ts: int
    opened_bars: int = 0     # nb de bougies depuis l'ouverture (sortie temps)
    reason: str = ""

    def unrealized(self, price):
        d = price - self.entry
        return d * self.qty if self.side == "long" else -d * self.qty


@dataclass
class Trade:
    """Une operation fermee (pour le journal / stats)."""
    side: str
    qty: float
    entry: float
    exit: float
    pnl: float
    fees: float
    opened_ts: int
    closed_ts: int
    exit_reason: str


@dataclass
class PaperBroker:
    instrument: object              # config.Instrument
    equity: float = 10000.0
    position: Optional[Position] = None
    realized: float = 0.0
    fees_paid: float = 0.0
    trades: list = field(default_factory=list)

    # --- helpers microstructure ---
    def _fee(self, notional):
        return abs(notional) * self.instrument.fee_bps / 10000.0

    def _buy_price(self, mid):
        return mid + self.instrument.spread / 2.0 + self.instrument.slippage

    def _sell_price(self, mid):
        return mid - self.instrument.spread / 2.0 - self.instrument.slippage

    # --- cycle de vie d'une position ---
    def open(self, side, qty, mid, stop, target, atr, ts, reason=""):
        if self.position is not None:
            return False
        entry = self._buy_price(mid) if side == "long" else self._sell_price(mid)
        fee = self._fee(entry * qty)
        self.fees_paid += fee
        self.realized -= fee
        self.equity -= fee
        self.position = Position(side, qty, entry, stop, target, atr, ts,
                                 reason=reason)
        return True

    def close(self, mid, ts, reason):
        p = self.position
        if p is None:
            return None
        exit_px = self._sell_price(mid) if p.side == "long" else self._buy_price(mid)
        gross = ((exit_px - p.entry) if p.side == "long"
                 else (p.entry - exit_px)) * p.qty
        fee = self._fee(exit_px * p.qty)
        self.fees_paid += fee
        pnl = gross - fee
        self.realized += pnl
        self.equity += pnl
        tr = Trade(p.side, p.qty, p.entry, exit_px, pnl, fee,
                   p.opened_ts, ts, reason)
        self.trades.append(tr)
        self.position = None
        return tr

    def check_exit(self, bar):
        """Verifie si le SL/TP est touche a l'interieur de la bougie.

        Convention prudente : si les deux sont touches dans la meme bougie,
        on considere le STOP en premier (pire cas).
        Retourne (mid_de_sortie, raison) ou None.
        """
        p = self.position
        if p is None:
            return None
        if p.side == "long":
            if bar.l <= p.stop:
                return p.stop, "stop-loss"
            if bar.h >= p.target:
                return p.target, "take-profit"
        else:
            if bar.h >= p.stop:
                return p.stop, "stop-loss"
            if bar.l <= p.target:
                return p.target, "take-profit"
        return None

    def apply_trailing(self, price, trail_atr):
        """Remonte le stop en faveur de la position (trailing stop ATR)."""
        p = self.position
        if p is None or trail_atr <= 0:
            return
        dist = trail_atr * p.atr
        if p.side == "long":
            p.stop = max(p.stop, price - dist)
        else:
            p.stop = min(p.stop, price - (-dist))

    def snapshot(self, price=None):
        eq = self.equity
        if self.position and price is not None:
            eq += self.position.unrealized(price)
        return dict(equity=round(self.equity, 2),
                    equity_mtm=round(eq, 2),
                    realized=round(self.realized, 2),
                    fees_paid=round(self.fees_paid, 2),
                    open_position=asdict(self.position) if self.position else None,
                    n_trades=len(self.trades))
