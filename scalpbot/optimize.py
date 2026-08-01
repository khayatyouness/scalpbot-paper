# -*- coding: utf-8 -*-
"""Grid-search : cherche les meilleurs parametres par backtest.

⚠️ Attention a l'over-fitting : optimiser sur UNE fenetre de donnees trouve
des parametres qui collaient au passe, pas forcement au futur. On limite le
risque en (1) exigeant un nombre minimum de trades, (2) classant par un score
robuste (profit factor penalise par le drawdown), (3) affichant tout le
classement pour reperer les plateaux stables plutot qu'un pic isole.

Les donnees sont chargees UNE fois par (symbole, intervalle) puis reutilisees
pour toutes les combinaisons -> pas de matraquage de Yahoo.
"""
import itertools
from dataclasses import replace

from . import data, backtest
from .config import Settings

# Espaces de recherche par strategie.
GRID_MOMENTUM = {
    "interval": ["5m", "15m", "60m"],
    "ema_fast": [9, 12],
    "ema_slow": [21, 34, 50],
    "sl_atr": [1.2, 1.8, 2.5],
    "tp_atr": [1.8, 3.0, 4.0],
    "trend_ema": [0, 100, 200],
    "trail_atr": [0.0, 1.5],
    "use_ichimoku": [0, 1],
}

GRID_SMC = {
    "interval": ["5m", "15m", "60m"],
    "smc_swing": [2, 3],
    "smc_lookback": [12, 20, 30],
    "smc_fvg_min_atr": [0.15, 0.3, 0.5],
    "smc_rr": [1.5, 2.0, 3.0],
    "max_hold_bars": [20, 40],
    "smc_require_sweep": [0, 1],
    "smc_killzone": [0, 1],
}

GRID = GRID_MOMENTUM   # retro-compat


def grid_for(cfg):
    return GRID_SMC if getattr(cfg, "strategy", "momentum") == "smc" else GRID_MOMENTUM

MIN_TRADES = 10          # en dessous, resultat non significatif
DD_PENALTY = 3.0         # poids du drawdown dans le score


def _score(stats):
    """Score robuste : rendement ajuste du risque, nul si trop peu de trades."""
    if stats["n_trades"] < MIN_TRADES:
        return -1e9
    pf = stats["profit_factor"]
    pf = 5.0 if pf == "inf" else float(pf)
    dd = stats["max_drawdown_pct"] / 100.0
    # rendement penalise par le drawdown, bonus leger si PF > 1
    return stats["return_pct"] - DD_PENALTY * dd * 100 + (pf - 1) * 5


def build_grid(overrides=None, base_grid=None):
    g = dict(base_grid or GRID)
    if overrides:
        g.update(overrides)
    keys = list(g)
    for combo in itertools.product(*(g[k] for k in keys)):
        params = dict(zip(keys, combo))
        # contrainte momentum : EMA rapide < EMA lente
        if "ema_fast" in params and params["ema_fast"] >= params["ema_slow"]:
            continue
        yield params


def run(symbol, base_cfg=None, overrides=None, top=15):
    base_cfg = base_cfg or Settings()
    grid = grid_for(base_cfg)
    # pre-charge les donnees par intervalle
    intervals = set((overrides or grid).get("interval", grid["interval"]))
    cache = {}
    for iv in intervals:
        try:
            cache[iv], _ = data.fetch_bars(symbol, iv)
        except Exception as e:
            print(f"[optimize] fetch {iv} KO: {e}")

    results = []
    for params in build_grid(overrides, grid):
        bars = cache.get(params["interval"])
        if not bars:
            continue
        cfg = replace(base_cfg, **params)
        try:
            s = backtest.run(symbol, cfg, bars=bars)
        except Exception:
            continue
        s = dict(s, _params=params, _score=round(_score(s), 2))
        results.append(s)

    results.sort(key=lambda r: r["_score"], reverse=True)
    return results[:top]


def validate(symbol, interval, base_cfg=None, split=0.65, top=8):
    """Validation hors-echantillon (holdout).

    Optimise sur les premiers `split`% des donnees (in-sample), puis teste la
    meilleure config sur le reste (out-of-sample = jamais vu par le grid).
    Si l'edge tient en OOS, il est bien plus credible.
    """
    base_cfg = base_cfg or Settings()
    bars, _ = data.fetch_bars(symbol, interval)
    cut = int(len(bars) * split)
    ins, oos = bars[:cut], bars[cut:]
    if len(oos) < 200:
        raise RuntimeError("Pas assez de donnees pour un holdout fiable.")

    from dataclasses import replace
    grid = grid_for(base_cfg)
    best = None
    ov = {"interval": [interval]}
    for params in build_grid(ov, grid):
        cfg = replace(base_cfg, **params)
        try:
            s = backtest.run(symbol, cfg, bars=ins)
        except Exception:
            continue
        sc = _score(s)
        if best is None or sc > best[0]:
            best = (sc, params, s)
    if best is None:
        raise RuntimeError("Aucune config valide en in-sample.")

    _, params, ins_stats = best
    cfg = replace(base_cfg, **params)
    oos_stats = backtest.run(symbol, cfg, bars=oos)
    return params, ins_stats, oos_stats


def _pstr(params):
    return " ".join(f"{k}={v}" for k, v in params.items())


def format_validate(symbol, interval, params, ins, oos):
    pstr = _pstr(params)
    def line(tag, s):
        return (f"{tag:>12} : ret {s['return_pct']:>6}%  PF {str(s['profit_factor']):>5}  "
                f"DD {s['max_drawdown_pct']:>5}%  trades {s['n_trades']}")
    return "\n".join([
        f"=== VALIDATION HOLDOUT — {symbol} {interval} ===",
        f"Meilleure config in-sample : {pstr}",
        line("IN-SAMPLE", ins),
        line("OUT-SAMPLE", oos),
        "",
        ("✅ L'edge TIENT hors echantillon." if oos["return_pct"] > 0
         and oos["profit_factor"] not in ("inf",) and float(oos["profit_factor"]) > 1
         else "⚠️ L'edge NE tient PAS hors echantillon (sur-apprentissage probable)."),
    ])


def format_table(symbol, results):
    lines = [f"=== TOP configs — {symbol} ===",
             f"{'score':>7} {'ret%':>7} {'PF':>5} {'DD%':>6} {'trades':>6}  params"]
    for r in results:
        lines.append(f"{r['_score']:>7} {r['return_pct']:>7} "
                     f"{str(r['profit_factor']):>5} {r['max_drawdown_pct']:>6} "
                     f"{r['n_trades']:>6}  {_pstr(r['_params'])}")
    return "\n".join(lines)
