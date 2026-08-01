# -*- coding: utf-8 -*-
"""Strategie scalping / momentum.

Logique (sur bougies cloturees) :
  - Direction : EMA rapide vs EMA lente (momentum de fond).
  - Filtre tendance (optionnel) : sens d'une EMA longue -> pas de contre-tendance.
  - Declencheur : cassure du plus haut/bas recent (breakout de structure).
  - Filtre : RSI pas en surachat/survente extreme (evite d'acheter le sommet).
  - Sortie : SL/TP bases sur l'ATR (volatilite), + sortie temps + signal inverse.

Le calcul est fait via des SERIES precalculees (precompute) partagees entre le
live et le backtest -> une seule source de verite, et un backtest en O(n).
"""
from dataclasses import dataclass
from . import indicators as ind


@dataclass
class Signal:
    side: str          # "long" ou "short"
    price: float       # prix de reference (close de la bougie signal)
    stop: float        # niveau de stop-loss
    target: float      # niveau de take-profit
    atr: float         # ATR au moment du signal (pour trailing / logs)
    reason: str        # explication lisible


def warmup(cfg):
    """Nombre de bougies necessaires avant de pouvoir generer un signal."""
    base = max(cfg.ema_slow, cfg.atr_period, cfg.breakout_lookback,
               cfg.rsi_period, cfg.trend_ema)
    if cfg.use_ichimoku:
        base = max(base, cfg.ichi_span_b + cfg.ichi_shift)
    return base + 2


def precompute(bars, cfg):
    """Precalcule toutes les series d'indicateurs une seule fois."""
    closes = [b.c for b in bars]
    hi, lo = ind.rolling_high_low_series(bars, cfg.breakout_lookback)
    pre = {
        "ef": ind.ema_series(closes, cfg.ema_fast),
        "es": ind.ema_series(closes, cfg.ema_slow),
        "te": ind.ema_series(closes, cfg.trend_ema) if cfg.trend_ema > 0 else None,
        "rsi": ind.rsi_series(closes, cfg.rsi_period),
        "atr": ind.atr_series(bars, cfg.atr_period),
        "hi": hi, "lo": lo,
        "ichi": None,
    }
    if cfg.use_ichimoku:
        tk, kj, ct, cb = ind.ichimoku(bars, cfg.ichi_tenkan, cfg.ichi_kijun,
                                      cfg.ichi_span_b, cfg.ichi_shift)
        pre["ichi"] = {"tk": tk, "kj": kj, "ct": ct, "cb": cb}
    return pre


def signal_at(pre, i, bars, cfg):
    """Signal a l'indice i a partir des series precalculees, ou None."""
    rsi = pre["rsi"][i]
    a = pre["atr"][i]
    hi = pre["hi"][i]
    lo = pre["lo"][i]
    if None in (rsi, a, hi, lo) or a <= 0:
        return None

    c = bars[i].c
    up = pre["ef"][i] > pre["es"][i]
    dn = pre["ef"][i] < pre["es"][i]
    if pre["te"] is not None:
        te = pre["te"][i]
        up = up and c > te
        dn = dn and c < te

    # Filtre Ichimoku (confirmation) : prix au-dessus/en-dessous du nuage (Kumo)
    # + Tenkan/Kijun aligne dans le sens du trade.
    if pre["ichi"] is not None:
        ic = pre["ichi"]
        ct, cb, tk, kj = ic["ct"][i], ic["cb"][i], ic["tk"][i], ic["kj"][i]
        if None in (ct, cb, tk, kj):
            return None
        up = up and c > ct and tk > kj
        dn = dn and c < cb and tk < kj

    if up and c > hi and rsi < cfg.rsi_long_max:
        return Signal("long", c, c - cfg.sl_atr * a, c + cfg.tp_atr * a, a,
                      f"EMA{cfg.ema_fast}>EMA{cfg.ema_slow}, cassure {hi:.2f}, "
                      f"RSI {rsi:.0f}")
    if dn and c < lo and rsi > cfg.rsi_short_min:
        return Signal("short", c, c + cfg.sl_atr * a, c - cfg.tp_atr * a, a,
                      f"EMA{cfg.ema_fast}<EMA{cfg.ema_slow}, cassure {lo:.2f}, "
                      f"RSI {rsi:.0f}")
    return None


def opposite_at(pre, i, side):
    """True si le momentum EMA s'est inverse contre la position ouverte."""
    if pre["ef"][i] is None or pre["es"][i] is None:
        return False
    if side == "long":
        return pre["ef"][i] < pre["es"][i]
    return pre["ef"][i] > pre["es"][i]


# ---- chemin LIVE : appele une fois par nouvelle bougie ----
def generate(bars, cfg):
    """Genere un Signal a partir des bougies cloturees, ou None."""
    if len(bars) < warmup(cfg):
        return None
    pre = precompute(bars, cfg)
    return signal_at(pre, len(bars) - 1, bars, cfg)


def opposite_exit(side, bars, cfg):
    """True si le momentum s'est inverse (chemin live)."""
    if len(bars) < cfg.ema_slow + 1:
        return False
    pre = precompute(bars, cfg)
    return opposite_at(pre, len(bars) - 1, side)
