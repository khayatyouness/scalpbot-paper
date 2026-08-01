# -*- coding: utf-8 -*-
"""Indicateurs techniques (pure python, aucune dependance)."""


def ema_series(vals, n):
    """Serie EMA complete (meme longueur que vals)."""
    if not vals:
        return []
    k = 2.0 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(closes, period=14):
    """RSI de Wilder sur la derniere valeur. None si pas assez de donnees."""
    if len(closes) <= period:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def atr(bars, period=14):
    """ATR de Wilder. `bars` = liste d'objets avec .h .l .c. None si trop court."""
    if len(bars) <= period:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i].h, bars[i].l, bars[i - 1].c
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    a = sum(trs[:period]) / period
    for t in trs[period:]:
        a = (a * (period - 1) + t) / period
    return a


def rsi_series(closes, period=14):
    """Serie RSI de Wilder (meme longueur que closes ; None avant amorcage)."""
    n = len(closes)
    out = [None] * n
    if n <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / period, losses / period
    out[period] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    for i in range(period + 1, n):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


def atr_series(bars, period=14):
    """Serie ATR de Wilder alignee sur bars (None avant amorcage)."""
    n = len(bars)
    out = [None] * n
    if n <= period:
        return out
    trs = [0.0]
    for i in range(1, n):
        h, l, pc = bars[i].h, bars[i].l, bars[i - 1].c
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    a = sum(trs[1:period + 1]) / period
    out[period] = a
    for i in range(period + 1, n):
        a = (a * (period - 1) + trs[i]) / period
        out[i] = a
    return out


def rolling_high_low_series(bars, lookback):
    """Series (highs, lows) : a l'indice i, extremes des `lookback` bougies
    PRECEDANT i (exclut i). None avant d'avoir assez d'historique."""
    n = len(bars)
    highs = [None] * n
    lows = [None] * n
    for i in range(lookback, n):
        window = bars[i - lookback:i]
        highs[i] = max(b.h for b in window)
        lows[i] = min(b.l for b in window)
    return highs, lows


def ichimoku(bars, tenkan_p=9, kijun_p=26, span_b_p=52, shift=26):
    """Ichimoku Kinko Hyo. Retourne des series alignees sur bars :
        tenkan, kijun, cloud_top, cloud_bottom
    Le nuage (cloud) a la bougie i est deja decale correctement : il utilise
    les spans Senkou calcules `shift` periodes plus tot (projection avant).
    None tant que l'amorcage n'est pas atteint.
    """
    n = len(bars)
    tenkan = [None] * n
    kijun = [None] * n
    span_a_raw = [None] * n
    span_b_raw = [None] * n

    def mid(t, p):
        if t < p - 1:
            return None
        seg = bars[t - p + 1:t + 1]
        return (max(b.h for b in seg) + min(b.l for b in seg)) / 2.0

    for t in range(n):
        tenkan[t] = mid(t, tenkan_p)
        kijun[t] = mid(t, kijun_p)
        if tenkan[t] is not None and kijun[t] is not None:
            span_a_raw[t] = (tenkan[t] + kijun[t]) / 2.0
        span_b_raw[t] = mid(t, span_b_p)

    cloud_top = [None] * n
    cloud_bottom = [None] * n
    for i in range(n):
        j = i - shift
        if j >= 0 and span_a_raw[j] is not None and span_b_raw[j] is not None:
            cloud_top[i] = max(span_a_raw[j], span_b_raw[j])
            cloud_bottom[i] = min(span_a_raw[j], span_b_raw[j])
    return tenkan, kijun, cloud_top, cloud_bottom


def recent_high_low(bars, lookback):
    """Plus haut / plus bas des `lookback` bougies precedant la derniere.

    On EXCLUT la derniere bougie (celle qui declenche potentiellement le
    breakout) pour comparer a la structure anterieure.
    """
    window = bars[-(lookback + 1):-1]
    if not window:
        return None, None
    return max(b.h for b in window), min(b.l for b in window)
