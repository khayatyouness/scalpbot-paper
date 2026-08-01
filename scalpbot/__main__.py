# -*- coding: utf-8 -*-
"""CLI du scalpbot.

Exemples :
  python -m scalpbot backtest --symbol GC=F
  python -m scalpbot backtest --symbol BTC-USD --interval 5m
  python -m scalpbot live --symbol BTC-USD
  python -m scalpbot live --symbol GC=F --once     (une seule iteration)
  python -m scalpbot params                          (affiche la config)
"""
import argparse
import json
import os
import sys

from .config import Settings, INSTRUMENTS, PRESETS, apply_preset
from . import backtest, engine, optimize


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scalpbot")
    sub = ap.add_subparsers(dest="cmd", required=True)

    STRATS = ["momentum", "smc"]

    b = sub.add_parser("backtest", help="rejoue la strategie sur l'historique")
    b.add_argument("--symbol", default="GC=F", choices=list(INSTRUMENTS))
    b.add_argument("--strategy", default=None, choices=STRATS)
    b.add_argument("--interval", default=None)
    b.add_argument("--range", default=None, help="plage Yahoo (5d, 1mo, ...)")
    b.add_argument("--preset", default=None, choices=list(PRESETS))
    b.add_argument("--source", default=None, choices=["yahoo", "oanda"],
                   help="source de donnees (oanda = historique profond)")
    b.add_argument("--years", type=float, default=None, help="annees d'historique (OANDA)")
    b.add_argument("--verbose", action="store_true")

    l = sub.add_parser("live", help="boucle paper trading temps reel")
    l.add_argument("--symbol", default="GC=F", choices=list(INSTRUMENTS))
    l.add_argument("--strategy", default=None, choices=STRATS)
    l.add_argument("--interval", default=None)
    l.add_argument("--preset", default=None, choices=list(PRESETS))
    l.add_argument("--once", action="store_true", help="une seule iteration")

    o = sub.add_parser("optimize", help="grid-search des meilleurs parametres")
    o.add_argument("--symbol", default="GC=F", choices=list(INSTRUMENTS))
    o.add_argument("--strategy", default=None, choices=STRATS)
    o.add_argument("--source", default=None, choices=["yahoo", "oanda"])
    o.add_argument("--years", type=float, default=None)
    o.add_argument("--top", type=int, default=15)

    v = sub.add_parser("validate", help="validation hors-echantillon (holdout)")
    v.add_argument("--symbol", default="GC=F", choices=list(INSTRUMENTS))
    v.add_argument("--strategy", default=None, choices=STRATS)
    v.add_argument("--interval", default="15m")
    v.add_argument("--source", default=None, choices=["yahoo", "oanda"])
    v.add_argument("--years", type=float, default=None)
    v.add_argument("--split", type=float, default=0.65)

    n = sub.add_parser("init", help="initialise un etat paper vierge ancre a maintenant")
    n.add_argument("--symbol", default="GC=F", choices=list(INSTRUMENTS))
    n.add_argument("--preset", default=None, choices=list(PRESETS))
    n.add_argument("--force", action="store_true", help="ecrase un etat existant")

    r = sub.add_parser("report", help="envoie un resume de statut sur Telegram")
    r.add_argument("--symbol", default="GC=F", choices=list(INSTRUMENTS))
    r.add_argument("--preset", default=None, choices=list(PRESETS))

    sub.add_parser("params", help="affiche la configuration effective")

    args = ap.parse_args(argv)
    # source de donnees (OANDA = historique profond) via env, lue par data.py
    if getattr(args, "source", None):
        os.environ["DATA_SOURCE"] = args.source
    if getattr(args, "years", None) is not None:
        os.environ["OANDA_YEARS"] = str(args.years)
    cfg = Settings()
    if getattr(args, "strategy", None):
        cfg.strategy = args.strategy

    if args.cmd == "backtest":
        if args.preset:
            apply_preset(cfg, args.preset)
        if args.interval:
            cfg.interval = args.interval
        s = backtest.run(args.symbol, cfg, rng=args.range, verbose=args.verbose)
        print(backtest.format_report(s))
        return 0

    if args.cmd == "live":
        if args.preset:
            apply_preset(cfg, args.preset)
        if args.interval:
            cfg.interval = args.interval
        engine.run_live(args.symbol, cfg, once=args.once)
        return 0

    if args.cmd == "optimize":
        res = optimize.run(args.symbol, cfg, top=args.top)
        print(optimize.format_table(args.symbol, res))
        return 0

    if args.cmd == "validate":
        params, ins, oos = optimize.validate(
            args.symbol, args.interval, cfg, split=args.split)
        print(optimize.format_validate(args.symbol, args.interval, params, ins, oos))
        return 0

    if args.cmd == "init":
        if args.preset:
            apply_preset(cfg, args.preset)
        engine.init_state(args.symbol, cfg, force=args.force)
        return 0

    if args.cmd == "report":
        if args.preset:
            apply_preset(cfg, args.preset)
        engine.send_report(args.symbol, cfg)
        return 0

    if args.cmd == "params":
        print(json.dumps(cfg.__dict__, indent=2, default=str))
        return 0

    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, KeyError) as e:
        print(f"Erreur: {e}", file=sys.stderr)
        sys.exit(1)
