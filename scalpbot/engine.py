# -*- coding: utf-8 -*-
"""Moteur LIVE en paper trading : boucle temps reel + persistance d'etat.

Ne travaille QUE sur des bougies CLOTUREES (on ignore la bougie en cours de
formation) pour eviter les faux signaux. L'etat (equity, position, trades) est
sauvegarde en JSON pour survivre a un redemarrage.
"""
import os
import sys
import json
import time
import datetime as dt

from . import data, risk, notify, select
from .broker import PaperBroker, Position, Trade
from .config import get_instrument, Settings

TZ_NAME = "Europe/Paris"


def paris_hour():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(TZ_NAME)).hour
    except Exception:
        return None


# ---------------- persistance ----------------
def state_path(symbol):
    base = os.environ.get("SCALPBOT_STATE_DIR", ".")
    safe = symbol.replace("=", "_").replace("/", "_")
    return os.path.join(base, f"state_{safe}.json")


def save_state(path, bk, last_ts, cooldown, guard):
    st = {
        "equity": bk.equity,
        "realized": bk.realized,
        "fees_paid": bk.fees_paid,
        "position": _pos_to_dict(bk.position),
        "trades": [t.__dict__ for t in bk.trades],
        "last_ts": last_ts,
        "cooldown": cooldown,
        "guard_day": str(guard.day) if guard.day else None,
        "guard_start_equity": guard.start_equity,
        "guard_locked": guard.locked,
    }
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=2, default=str)
    os.replace(tmp, path)


def load_state(path, bk, guard):
    if not os.path.exists(path):
        return 0, 0
    with open(path) as f:
        st = json.load(f)
    bk.equity = st.get("equity", bk.equity)
    bk.realized = st.get("realized", 0.0)
    bk.fees_paid = st.get("fees_paid", 0.0)
    bk.position = _pos_from_dict(st.get("position"))
    bk.trades = [Trade(**t) for t in st.get("trades", [])]
    guard.day = st.get("guard_day")
    guard.start_equity = st.get("guard_start_equity")
    guard.locked = st.get("guard_locked", False)
    return st.get("last_ts", 0), st.get("cooldown", 0)


def _pos_to_dict(p):
    return p.__dict__ if p else None


def _pos_from_dict(d):
    return Position(**d) if d else None


def _paris_hour_of(ts):
    """Heure Europe/Paris d'un timestamp (gere ete/hiver), ou None."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.fromtimestamp(ts, ZoneInfo(TZ_NAME)).hour
    except Exception:
        return None


def _process_bar(bk, cfg, inst, strat, pre, bars, i, cooldown, guard):
    """Traite UNE bougie deja cloturee (indice i). Retourne (cooldown, events)."""
    events = []
    bar = bars[i]
    guard.update(bk.equity, dt.datetime.utcfromtimestamp(bar.ts).date())

    # 1) gestion de la position ouverte
    if bk.position is not None:
        bk.position.opened_bars += 1
        bk.apply_trailing(bar.c, cfg.trail_atr)
        hit = bk.check_exit(bar)
        if hit:
            px, reason = hit
            tr = bk.close(px, bar.ts, reason)
            events.append(("close", tr))
            if tr.pnl < 0:
                cooldown = cfg.cooldown_bars
        elif bk.position.opened_bars >= cfg.max_hold_bars:
            events.append(("close", bk.close(bar.c, bar.ts, "timeout")))
        elif strat.opposite_at(pre, i, bk.position.side):
            events.append(("close", bk.close(bar.c, bar.ts, "signal-inverse")))

    # 2) nouvelle entree (horaires bougie, cooldown, day guard)
    h = _paris_hour_of(bar.ts)
    in_hours = h is None or (cfg.hour_start <= h <= cfg.hour_end)
    if bk.position is None and guard.can_trade() and in_hours:
        if cooldown > 0:
            cooldown -= 1
        else:
            sig = strat.signal_at(pre, i, bars, cfg)
            if sig:
                qty = risk.position_size(bk.equity, sig.price, sig.stop, cfg, inst)
                if qty > 0:
                    bk.open(sig.side, qty, bar.c, sig.stop, sig.target,
                            sig.atr, bar.ts, sig.reason)
                    events.append(("open", sig, qty))
    return cooldown, events


def advance(bk, cfg, inst, closed_bars, last_ts, cooldown, guard):
    """Rattrape TOUTES les bougies cloturees depuis last_ts (robuste au jitter
    du cron : on ne saute jamais une bougie, donc jamais un SL/TP).

    Retourne (last_ts, cooldown, events).
    """
    all_events = []
    strat = select.get(cfg)
    need = strat.warmup(cfg)
    if len(closed_bars) < need:
        return last_ts, cooldown, all_events
    pre = strat.precompute(closed_bars, cfg)   # series calculees UNE fois
    for i in range(need, len(closed_bars)):
        if closed_bars[i].ts <= last_ts:
            continue                            # deja traitee
        cooldown, events = _process_bar(
            bk, cfg, inst, strat, pre, closed_bars, i, cooldown, guard)
        all_events.extend(events)
        last_ts = closed_bars[i].ts
    return last_ts, cooldown, all_events


def run_live(symbol, cfg=None, once=False):
    cfg = cfg or Settings()
    inst = get_instrument(symbol)
    bk = PaperBroker(instrument=inst, equity=cfg.start_equity)
    guard = risk.DayGuard(cfg)
    path = state_path(symbol)
    last_ts, cooldown = load_state(path, bk, guard)

    print(f"[scalpbot] LIVE PAPER {inst.name} | interval={cfg.interval} "
          f"| equity={bk.equity:.2f}$ | state={path}")
    print("[scalpbot] ⚠️  PAPER TRADING — aucun ordre reel n'est passe.")

    while True:
        try:
            bars, live = data.fetch_bars(symbol, cfg.interval)
            closed = bars[:-1]                       # ignore la bougie en cours
            last_ts, cooldown, events = advance(
                bk, cfg, inst, closed, last_ts, cooldown, guard)
            for ev in events:
                _report_event(inst, bk, ev)
            save_state(path, bk, last_ts, cooldown, guard)
            snap = bk.snapshot(live)
            pos = "flat" if not snap["open_position"] else snap["open_position"]["side"]
            print(f"[{dt.datetime.utcnow():%H:%M:%S}] px={live} "
                  f"equity_mtm={snap['equity_mtm']}$ pos={pos} "
                  f"trades={snap['n_trades']}")
        except Exception as e:
            print(f"[scalpbot] erreur boucle: {type(e).__name__}: {e}",
                  file=sys.stderr)
        if once:
            break
        time.sleep(cfg.poll_seconds)


def init_state(symbol, cfg=None, force=False):
    """Initialise un etat paper VIERGE ancre a maintenant (ne rejoue pas le
    passe). A lancer UNE fois au deploiement pour demarrer le track record a
    start_equity depuis la bougie courante."""
    cfg = cfg or Settings()
    inst = get_instrument(symbol)
    path = state_path(symbol)
    if os.path.exists(path) and not force:
        print(f"[scalpbot] etat deja present ({path}). --force pour reinitialiser.")
        return False
    bars, _ = data.fetch_bars(symbol, cfg.interval)
    last_ts = bars[-2].ts if len(bars) >= 2 else 0    # derniere bougie cloturee
    bk = PaperBroker(instrument=inst, equity=cfg.start_equity)
    guard = risk.DayGuard(cfg)
    save_state(path, bk, last_ts, 0, guard)
    print(f"[scalpbot] etat initialise : equity={cfg.start_equity:.2f}$ "
          f"ancre a last_ts={last_ts} ({path})")
    return True


def send_report(symbol, cfg=None):
    """Envoie un resume de statut sur Telegram (pour un cron quotidien)."""
    cfg = cfg or Settings()
    inst = get_instrument(symbol)
    bk = PaperBroker(instrument=inst, equity=cfg.start_equity)
    guard = risk.DayGuard(cfg)
    load_state(state_path(symbol), bk, guard)
    live = None
    try:
        _, live = data.fetch_bars(symbol, cfg.interval)
    except Exception:
        pass
    snap = bk.snapshot(live)
    notify.status(inst.short, snap, cfg.start_equity)
    print(f"[scalpbot] rapport envoye : equity_mtm={snap['equity_mtm']}$ "
          f"trades={snap['n_trades']}")


def _report_event(inst, bk, ev):
    if ev[0] == "open":
        _, sig, qty = ev
        print(f"  >>> OPEN {sig.side.upper()} {inst.short} @~{sig.price:.2f} "
              f"qty={qty} SL={sig.stop:.2f} TP={sig.target:.2f}")
        notify.trade_open(inst.short, sig, qty)
    elif ev[0] == "close":
        tr = ev[1]
        print(f"  <<< CLOSE {inst.short} {tr.exit_reason} @ {tr.exit:.2f} "
              f"PnL={tr.pnl:+.2f}$ equity={bk.equity:.2f}$")
        notify.trade_close(inst.short, tr, bk.equity)
