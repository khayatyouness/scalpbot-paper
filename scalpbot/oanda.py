# -*- coding: utf-8 -*-
"""Adaptateur de donnees OANDA v20 (API REST) — historique intraday profond.

Yahoo plafonne l'intraday a ~1 mois (15m) / ~7 jours (1m). OANDA fournit
plusieurs ANNEES de bougies intraday, gratuitement via un compte DEMO
(practice). Ideal pour backtester serieusement.

100% stdlib (urllib). Necessite un token OANDA (compte practice gratuit) :
    OANDA_TOKEN     : token API (obligatoire)
    OANDA_ENV       : "practice" (defaut) ou "live"
    OANDA_YEARS     : profondeur d'historique en annees (defaut 2)

Utilisation transparente : `DATA_SOURCE=oanda` fait basculer data.fetch_bars
vers cet adaptateur (voir data.py). Symboles mappes automatiquement
(GC=F -> XAU_USD, BTC-USD -> BTC_USD).
"""
import os
import time
import json
import calendar
import urllib.request
import urllib.parse

from .data import Bar

# mapping symbole interne -> instrument OANDA
_SYMBOL_MAP = {
    "GC=F": "XAU_USD",
    "XAUUSD": "XAU_USD",
    "XAU_USD": "XAU_USD",
    "BTC-USD": "BTC_USD",
    "BTC_USD": "BTC_USD",
}

# mapping intervalle interne -> granularite OANDA
_GRAN_MAP = {
    "1m": "M1", "2m": "M2", "5m": "M5", "15m": "M15", "30m": "M30",
    "60m": "H1", "1h": "H1", "4h": "H4", "1d": "D",
}

_MAX_COUNT = 5000   # limite OANDA par requete


def _base_url():
    env = os.environ.get("OANDA_ENV", "practice").lower()
    return ("https://api-fxtrade.oanda.com" if env == "live"
            else "https://api-fxpractice.oanda.com")


def _instrument(symbol):
    if symbol in _SYMBOL_MAP:
        return _SYMBOL_MAP[symbol]
    raise KeyError(f"Symbole non mappe pour OANDA: {symbol}. "
                   f"Connus: {', '.join(sorted(set(_SYMBOL_MAP)))}")


def _granularity(interval):
    if interval in _GRAN_MAP:
        return _GRAN_MAP[interval]
    raise KeyError(f"Intervalle non mappe pour OANDA: {interval}. "
                   f"Connus: {', '.join(_GRAN_MAP)}")


def _parse_time(s):
    """RFC3339 OANDA ('2024-01-02T09:00:00.000000000Z') -> epoch UTC."""
    return calendar.timegm(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))


def _get(url, token, timeout=30):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _fetch_chunk(instrument, gran, from_epoch, token, count=_MAX_COUNT):
    from_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(from_epoch))
    q = urllib.parse.urlencode({
        "granularity": gran, "price": "M", "count": count,
        "from": from_str, "includeFirst": "true",
    })
    url = f"{_base_url()}/v3/instruments/{instrument}/candles?{q}"
    data = _get(url, token)
    out = []
    for c in data.get("candles", []):
        if not c.get("complete", False):
            continue                       # ignore la bougie en formation
        m = c["mid"]
        out.append(Bar(_parse_time(c["time"]),
                       float(m["o"]), float(m["h"]), float(m["l"]),
                       float(m["c"]), float(c.get("volume", 0))))
    return out


def fetch_bars(symbol, interval="15m", years=None):
    """Retourne (bars, live_price) — meme signature que data.fetch_bars.

    Pagine en avant depuis (maintenant - years) jusqu'a aujourd'hui.
    """
    token = os.environ.get("OANDA_TOKEN")
    if not token:
        raise RuntimeError(
            "OANDA_TOKEN manquant. Cree un compte practice gratuit sur "
            "oanda.com, genere un token API, puis exporte OANDA_TOKEN.")
    years = years if years is not None else float(os.environ.get("OANDA_YEARS", 2))
    instrument = _instrument(symbol)
    gran = _granularity(interval)

    now = int(time.time())
    cur = now - int(years * 365 * 24 * 3600)
    bars, seen = [], set()
    while cur < now:
        chunk = _fetch_chunk(instrument, gran, cur, token)
        if not chunk:
            break
        added = 0
        for b in chunk:
            if b.ts in seen:
                continue
            seen.add(b.ts)
            bars.append(b)
            added += 1
        last_ts = chunk[-1].ts
        if added == 0 or last_ts <= cur:
            break                          # plus de progression
        cur = last_ts + 1
        time.sleep(0.1)                    # courtoisie API
    bars.sort(key=lambda b: b.ts)
    live = bars[-1].c if bars else None
    return bars, live
