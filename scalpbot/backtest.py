# -*- coding: utf-8 -*-
"""Backtest : rejoue la strategie sur l'historique intraday.

A lancer AVANT tout live : valide que la strategie est (ou non) rentable,
mesure win-rate, profit factor, drawdown. Un backtest positif ne garantit
rien en live (frais/slippage reels, regime de marche), mais un backtest
negatif est un stop net.
"""
import datetime as dt
from . import data, risk, select
from .broker import PaperBroker
from .config import get_instrument


def run(symbol, cfg, rng=None, verbose=False, bars=None):
    """Backtest. `bars` peut etre pre-charge (utile pour le grid-search)."""
    inst = get_instrument(symbol)
    strat = select.get(cfg)
    if bars is None:
        bars, _ = data.fetch_bars(symbol, cfg.interval, rng)
    need = strat.warmup(cfg)
    if len(bars) < need + 5:
        raise RuntimeError(f"Pas assez de bougies ({len(bars)}) pour backtester.")

    bk = PaperBroker(instrument=inst, equity=cfg.start_equity)
    guard = risk.DayGuard(cfg)
    cooldown = 0
    peak = bk.equity
    max_dd = 0.0
    pre = strat.precompute(bars, cfg)      # series calculees UNE fois -> O(n)

    for i in range(need, len(bars)):
        bar = bars[i]
        day_key = dt.datetime.utcfromtimestamp(bar.ts).date()
        guard.update(bk.equity, day_key)

        # 1) gestion de la position ouverte
        if bk.position is not None:
            bk.position.opened_bars += 1
            bk.apply_trailing(bar.c, cfg.trail_atr)
            hit = bk.check_exit(bar)
            if hit:
                px, reason = hit
                tr = bk.close(px, bar.ts, reason)
                if tr.pnl < 0:
                    cooldown = cfg.cooldown_bars
            elif bk.position.opened_bars >= cfg.max_hold_bars:
                bk.close(bar.c, bar.ts, "timeout")
            elif strat.opposite_at(pre, i, bk.position.side):
                bk.close(bar.c, bar.ts, "signal-inverse")

        # 2) nouvelle entree
        if bk.position is None and guard.can_trade():
            if cooldown > 0:
                cooldown -= 1
            else:
                sig = strat.signal_at(pre, i, bars, cfg)
                if sig:
                    qty = risk.position_size(bk.equity, sig.price, sig.stop,
                                             cfg, inst)
                    if qty > 0:
                        bk.open(sig.side, qty, bar.c, sig.stop, sig.target,
                                sig.atr, bar.ts, sig.reason)
                        if verbose:
                            print(f"  OPEN {sig.side} @ {bar.c:.2f} qty={qty} "
                                  f"({sig.reason})")

        eq = bk.equity + (bk.position.unrealized(bar.c) if bk.position else 0)
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak if peak else 0)

    # cloture finale eventuelle
    if bk.position is not None:
        bk.close(bars[-1].c, bars[-1].ts, "fin-backtest")

    return _stats(bk, cfg, symbol, len(bars), max_dd)


def _stats(bk, cfg, symbol, n_bars, max_dd):
    trades = bk.trades
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    ret = (bk.equity / cfg.start_equity - 1) * 100
    return dict(
        symbol=symbol,
        bars=n_bars,
        n_trades=len(trades),
        win_rate=round(100 * len(wins) / len(trades), 1) if trades else 0.0,
        profit_factor=round(pf, 2) if pf != float("inf") else "inf",
        net_pnl=round(bk.realized, 2),
        fees_paid=round(bk.fees_paid, 2),
        return_pct=round(ret, 2),
        max_drawdown_pct=round(max_dd * 100, 2),
        final_equity=round(bk.equity, 2),
    )


def format_report(s):
    return (
        f"=== BACKTEST {s['symbol']} ({s['bars']} bougies) ===\n"
        f"Trades          : {s['n_trades']}\n"
        f"Win rate        : {s['win_rate']}%\n"
        f"Profit factor   : {s['profit_factor']}\n"
        f"PnL net         : {s['net_pnl']:+.2f}$  (frais {s['fees_paid']:.2f}$)\n"
        f"Rendement       : {s['return_pct']:+.2f}%\n"
        f"Max drawdown    : {s['max_drawdown_pct']}%\n"
        f"Equity finale   : {s['final_equity']:.2f}$\n"
    )
