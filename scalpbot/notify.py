# -*- coding: utf-8 -*-
"""Notifications Telegram (optionnelles). Reutilise les creds du bot existant.

Actif seulement si TELEGRAM_TOKEN et TELEGRAM_CHAT_ID sont definis.
"""
import os
import sys
import urllib.request
import urllib.parse


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send(text):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    body = urllib.parse.urlencode({
        "chat_id": chat, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
        return True
    except Exception as e:
        print(f"[notify] Telegram KO: {e}", file=sys.stderr)
        return False


def trade_open(short, sig, qty):
    arrow = "🟢 LONG" if sig.side == "long" else "🔴 SHORT"
    send(f"<b>[{_esc(short)}] {arrow} (paper)</b>\n"
         f"Entree ~{sig.price:.2f} | Qty {qty}\n"
         f"SL {sig.stop:.2f} | TP {sig.target:.2f}\n"
         f"<i>{_esc(sig.reason)}</i>")


def trade_close(short, tr, equity):
    emo = "✅" if tr.pnl >= 0 else "❌"
    send(f"<b>[{_esc(short)}] {emo} Cloture (paper)</b>\n"
         f"{_esc(tr.exit_reason)} @ {tr.exit:.2f}\n"
         f"PnL <b>{tr.pnl:+.2f}$</b> | Equity {equity:.2f}$")


def status(short, snap, start_equity):
    """Resume periodique (equity, position, perf globale)."""
    eq = snap["equity_mtm"]
    ret = (eq / start_equity - 1) * 100 if start_equity else 0.0
    pos = snap["open_position"]
    if pos:
        pl = "🟢 LONG" if pos["side"] == "long" else "🔴 SHORT"
        posline = (f"Position : {pl} @ {pos['entry']:.2f} "
                   f"(SL {pos['stop']:.2f} / TP {pos['target']:.2f})")
    else:
        posline = "Position : aucune (flat)"
    send(f"<b>[{_esc(short)}] 📊 Statut (paper)</b>\n"
         f"Equity : <b>{eq:.2f}$</b> ({ret:+.2f}%)\n"
         f"{posline}\n"
         f"Trades cloturees : {snap['n_trades']} | Frais : {snap['fees_paid']:.2f}$")
