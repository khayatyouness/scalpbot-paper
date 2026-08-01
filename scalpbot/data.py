# -*- coding: utf-8 -*-
"""Recuperation des bougies intraday depuis l'endpoint public Yahoo.

Reutilise l'approche du bot d'alertes existant (100% stdlib, pas de yfinance
qui est bloque depuis les IP datacenter).
"""
import json
import urllib.request
from dataclasses import dataclass

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# Plages Yahoo autorisees par intervalle intraday.
_DEFAULT_RANGE = {
    "1m": "5d", "2m": "5d", "5m": "1mo", "15m": "1mo",
    "30m": "1mo", "60m": "3mo", "90m": "3mo",
}


@dataclass
class Bar:
    ts: int      # timestamp epoch (secondes, UTC)
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_bars(symbol, interval="1m", rng=None):
    """Retourne (bars, live_price).

    bars : liste de Bar triee par ts croissant, valeurs completes uniquement.
    live_price : dernier prix de marche (regularMarketPrice) ou None.
    """
    rng = rng or _DEFAULT_RANGE.get(interval, "5d")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?range={rng}&interval={interval}&includePrePost=false")
    data = json.loads(_get(url))
    res = data["chart"]["result"][0]
    meta = res.get("meta", {})
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    o, h, l, c = q.get("open"), q.get("high"), q.get("low"), q.get("close")
    v = q.get("volume") or [None] * len(ts)
    bars = []
    for i in range(len(ts)):
        if None in (o[i], h[i], l[i], c[i]):
            continue
        bars.append(Bar(ts[i], o[i], h[i], l[i], c[i], v[i] or 0.0))
    return bars, meta.get("regularMarketPrice")
