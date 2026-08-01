# -*- coding: utf-8 -*-
"""Strategie SMC / ICT (Smart Money Concepts / Inner Circle Trader).

Modele d'entree implemente (le plus backtestable et fidele a ICT) :

  1. STRUCTURE   : swings fractals -> plus haut/bas de structure.
  2. DISPLACEMENT + FVG : une bougie impulsive casse la structure (BOS) et
     laisse un Fair Value Gap (imbalance a 3 bougies).
       - FVG haussier a l'indice j : low[j] > high[j-2]  -> zone (high[j-2], low[j])
       - FVG baissier a l'indice j : high[j] < low[j-2]  -> zone (high[j], low[j-2])
  3. ENTREE      : le prix revient dans le FVG (mitigation de l'imbalance /
     logique Order Block), dans le sens du BOS.
  4. SL / TP     : SL au bord oppose du gap (+ marge ATR), TP en reward:risk fixe.
  5. INVALIDATION: la zone meurt si le prix cloture au-dela du gap, ou apres
     smc_lookback bougies.

Aucune fuite d'information future : un swing fractal de largeur w n'est
"connu" qu'a la bougie s+w ; on ne l'utilise jamais avant.

Interface identique a strategy.py (warmup/precompute/signal_at/opposite_at)
pour etre interchangeable dans le backtest et le live.
"""
import datetime as dt
from . import indicators as ind
from .strategy import Signal

# Killzones ICT (heures UTC) : Londres open + New York AM.
_KILLZONE_HOURS = {7, 8, 9, 12, 13, 14, 15}


def warmup(cfg):
    return cfg.smc_lookback + 2 * cfg.smc_swing + cfg.atr_period + 5


def _swings(bars, w):
    """Indices des swings fractals confirmes.

    swing high a s : high[s] est le max de [s-w, s+w]. Confirme a s+w.
    Retourne (highs, lows) = listes d'indices s (l'info est disponible des s+w).
    """
    n = len(bars)
    highs, lows = [], []
    for s in range(w, n - w):
        seg = bars[s - w:s + w + 1]
        if bars[s].h == max(b.h for b in seg):
            highs.append(s)
        if bars[s].l == min(b.l for b in seg):
            lows.append(s)
    return highs, lows


def _fvgs(bars, atr, cfg):
    """Liste des FVG : (j, side, gap_lo, gap_hi). j = indice de la 3e bougie."""
    out = []
    for j in range(2, len(bars)):
        a = atr[j]
        if a is None or a <= 0:
            continue
        # haussier : gap entre high[j-2] et low[j]
        if bars[j].l > bars[j - 2].h:
            lo, hi = bars[j - 2].h, bars[j].l
            if (hi - lo) >= cfg.smc_fvg_min_atr * a:
                out.append((j, "long", lo, hi))
        # baissier : gap entre high[j] et low[j-2]
        elif bars[j].h < bars[j - 2].l:
            lo, hi = bars[j].h, bars[j - 2].l
            if (hi - lo) >= cfg.smc_fvg_min_atr * a:
                out.append((j, "short", lo, hi))
    return out


def precompute(bars, cfg):
    atr = ind.atr_series(bars, cfg.atr_period)
    sh, sl = _swings(bars, cfg.smc_swing)
    fvgs = _fvgs(bars, atr, cfg)
    return {"atr": atr, "sh": sh, "sl": sl, "fvgs": fvgs, "w": cfg.smc_swing}


def _last_swing_before(swings, idx, conf_delay, limit):
    """Dernier swing (indice) strictement avant idx, confirme a idx, dans limit."""
    best = None
    for s in swings:
        if s >= idx or s + conf_delay > idx:   # non confirme a idx
            continue
        if idx - s > limit:
            continue
        best = s
    return best


def _bos_up(bars, j, sh, w, lookback):
    """La bougie j a-t-elle casse un swing high anterieur (BOS haussier) ?"""
    s = _last_swing_before(sh, j, w, lookback)
    return s is not None and bars[j].c > bars[s].h


def _bos_down(bars, j, sl, w, lookback):
    s = _last_swing_before(sl, j, w, lookback)
    return s is not None and bars[j].c < bars[s].l


def _swept_liquidity(bars, j, swings, w, lookback, side):
    """Prise de liquidite avant le displacement (modele ICT 2022).

    LONG : dans la fenetre avant j, le prix a casse SOUS un swing low
    anterieur (sell-side liquidity grab) avant de repartir a la hausse.
    SHORT : symetrique au-dessus d'un swing high.
    """
    ref = _last_swing_before(swings, j - 2, w, 3 * lookback)
    if ref is None:
        return False
    level = bars[ref].l if side == "long" else bars[ref].h
    for k in range(ref + 1, j + 1):
        if side == "long" and bars[k].l < level:
            return True
        if side == "short" and bars[k].h > level:
            return True
    return False


def _in_killzone(ts):
    return dt.datetime.utcfromtimestamp(ts).hour in _KILLZONE_HOURS


def _zone_valid(bars, j, i, side, gap_lo, gap_hi):
    """La zone FVG creee en j est-elle toujours valide a i (pas invalidee) ?"""
    for k in range(j + 1, i):
        if side == "long" and bars[k].c < gap_lo:
            return False
        if side == "short" and bars[k].c > gap_hi:
            return False
    return True


def signal_at(pre, i, bars, cfg):
    """Signal ICT a la bougie i : retour du prix dans un FVG valide + BOS."""
    a = pre["atr"][i]
    if a is None or a <= 0:
        return None
    w, lb = pre["w"], cfg.smc_lookback
    bar = bars[i]

    # filtre killzone (heures Londres/NY)
    if cfg.smc_killzone and not _in_killzone(bar.ts):
        return None

    # on cherche le FVG valide le plus recent que la bougie i vient mitiger
    for (j, side, lo, hi) in reversed(pre["fvgs"]):
        if j >= i or (i - j) > lb:
            if j < i - lb:
                break          # trop vieux (liste triee par j) -> stop
            continue
        # BOS dans le sens du FVG (displacement qui casse la structure)
        if side == "long" and not _bos_up(bars, j, pre["sh"], w, lb):
            continue
        if side == "short" and not _bos_down(bars, j, pre["sl"], w, lb):
            continue
        # prise de liquidite avant le displacement (modele ICT 2022)
        if cfg.smc_require_sweep:
            swings = pre["sl"] if side == "long" else pre["sh"]
            if not _swept_liquidity(bars, j, swings, w, lb, side):
                continue
        if not _zone_valid(bars, j, i, side, lo, hi):
            continue

        if side == "long":
            # le prix redescend dans le gap sans le cloturer sous le bas
            if bar.l <= hi and bar.c > lo:
                entry = bar.c
                stop = lo - cfg.smc_sl_buffer_atr * a
                risk = entry - stop
                if risk <= 0:
                    continue
                target = entry + cfg.smc_rr * risk
                return Signal("long", entry, stop, target, a,
                              f"ICT: BOS haussier + retour FVG [{lo:.2f}-{hi:.2f}]")
        else:
            if bar.h >= lo and bar.c < hi:
                entry = bar.c
                stop = hi + cfg.smc_sl_buffer_atr * a
                risk = stop - entry
                if risk <= 0:
                    continue
                target = entry - cfg.smc_rr * risk
                return Signal("short", entry, stop, target, a,
                              f"ICT: BOS baissier + retour FVG [{lo:.2f}-{hi:.2f}]")
    return None


def opposite_at(pre, i, side):
    """SMC gere la sortie par SL/TP (+ timeout) : pas de sortie 'signal inverse'."""
    return False
