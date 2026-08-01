# -*- coding: utf-8 -*-
"""Configuration des instruments et parametres par defaut.

Tout est surchargeable par variables d'environnement pour deployer
facilement (GitHub Actions, VPS, cron local) sans toucher au code.
"""
import os
from dataclasses import dataclass, field


def _f(name, default):
    return float(os.environ.get(name, default))


def _i(name, default):
    return int(os.environ.get(name, default))


@dataclass
class Instrument:
    """Un actif tradable : symbole Yahoo + microstructure simulee."""
    symbol: str          # symbole Yahoo (GC=F, BTC-USD, ...)
    name: str            # nom lisible
    short: str           # code court (GOLD, BTC)
    # cout par unite de prix, exprime en $ par 1$ de mouvement / unite :
    spread: float        # spread bid/ask simule (en $ de prix)
    slippage: float      # slippage moyen sur ordre marche (en $ de prix)
    fee_bps: float       # frais aller-retour en points de base (0.01% = 1 bp)
    tick: float          # granularite minimale du prix
    min_qty: float       # quantite minimale
    session_24h: bool    # True = 24/7 (crypto), False = suit une session


# Catalogue des instruments supportes.
INSTRUMENTS = {
    "GC=F": Instrument(
        symbol="GC=F", name="GOLD (XAU/USD)", short="GOLD",
        spread=0.30, slippage=0.10, fee_bps=0.5, tick=0.1,
        min_qty=0.01, session_24h=False,
    ),
    "BTC-USD": Instrument(
        symbol="BTC-USD", name="BITCOIN (BTC/USD)", short="BTC",
        spread=8.0, slippage=4.0, fee_bps=6.0, tick=0.5,
        min_qty=0.0001, session_24h=True,
    ),
}


@dataclass
class Settings:
    """Parametres globaux du moteur (surchargables par env)."""
    # --- capital / risque ---
    start_equity: float = field(default_factory=lambda: _f("START_EQUITY", 10000))
    risk_per_trade: float = field(default_factory=lambda: _f("RISK_PER_TRADE", 0.005))  # 0.5%
    max_daily_loss: float = field(default_factory=lambda: _f("MAX_DAILY_LOSS", 0.03))   # 3%
    max_positions: int = field(default_factory=lambda: _i("MAX_POSITIONS", 1))          # par instrument

    # --- strategie ---
    strategy: str = field(default_factory=lambda: os.environ.get("STRATEGY", "momentum"))  # momentum | smc
    interval: str = field(default_factory=lambda: os.environ.get("INTERVAL", "1m"))
    ema_fast: int = field(default_factory=lambda: _i("EMA_FAST", 9))
    ema_slow: int = field(default_factory=lambda: _i("EMA_SLOW", 21))
    rsi_period: int = field(default_factory=lambda: _i("RSI_PERIOD", 14))
    rsi_long_max: float = field(default_factory=lambda: _f("RSI_LONG_MAX", 75))   # pas d'achat si surachat extreme
    rsi_short_min: float = field(default_factory=lambda: _f("RSI_SHORT_MIN", 25)) # pas de vente si survente extreme
    atr_period: int = field(default_factory=lambda: _i("ATR_PERIOD", 14))
    trend_ema: int = field(default_factory=lambda: _i("TREND_EMA", 0))   # 0 = filtre off
    breakout_lookback: int = field(default_factory=lambda: _i("BREAKOUT_LOOKBACK", 15))
    # --- filtre Ichimoku (confirmation du momentum) ---
    use_ichimoku: int = field(default_factory=lambda: _i("USE_ICHIMOKU", 0))   # 1 = active
    ichi_tenkan: int = field(default_factory=lambda: _i("ICHI_TENKAN", 9))
    ichi_kijun: int = field(default_factory=lambda: _i("ICHI_KIJUN", 26))
    ichi_span_b: int = field(default_factory=lambda: _i("ICHI_SPAN_B", 52))
    ichi_shift: int = field(default_factory=lambda: _i("ICHI_SHIFT", 26))
    sl_atr: float = field(default_factory=lambda: _f("SL_ATR", 1.2))   # stop = 1.2 x ATR
    tp_atr: float = field(default_factory=lambda: _f("TP_ATR", 1.8))   # cible = 1.8 x ATR (R:R ~1.5)
    trail_atr: float = field(default_factory=lambda: _f("TRAIL_ATR", 0.0))  # 0 = pas de trailing
    max_hold_bars: int = field(default_factory=lambda: _i("MAX_HOLD_BARS", 30))  # sortie temps

    # --- strategie SMC / ICT ---
    smc_swing: int = field(default_factory=lambda: _i("SMC_SWING", 2))          # largeur fractale (gauche/droite)
    smc_lookback: int = field(default_factory=lambda: _i("SMC_LOOKBACK", 20))   # duree de validite d'une zone FVG
    smc_fvg_min_atr: float = field(default_factory=lambda: _f("SMC_FVG_MIN_ATR", 0.25))  # taille min du gap (x ATR)
    smc_rr: float = field(default_factory=lambda: _f("SMC_RR", 2.0))            # reward:risk
    smc_sl_buffer_atr: float = field(default_factory=lambda: _f("SMC_SL_BUFFER_ATR", 0.1))  # marge sous le gap
    smc_require_sweep: int = field(default_factory=lambda: _i("SMC_REQUIRE_SWEEP", 0))  # 1 = exiger prise de liquidite avant le FVG
    smc_killzone: int = field(default_factory=lambda: _i("SMC_KILLZONE", 0))    # 1 = trader seulement en killzones Londres/NY

    # --- boucle live ---
    poll_seconds: int = field(default_factory=lambda: _i("POLL_SECONDS", 30))
    cooldown_bars: int = field(default_factory=lambda: _i("COOLDOWN_BARS", 3))  # apres une perte

    # --- horaires (Europe/Paris) : ne trade que dans la plage ---
    hour_start: int = field(default_factory=lambda: _i("HOUR_START", 0))
    hour_end: int = field(default_factory=lambda: _i("HOUR_END", 23))


# Presets valides par backtest + holdout out-of-sample (2026-08-01).
# GOLD_15M : edge confirme hors-echantillon (PF ~2 en OOS).
# ⚠️ Un preset validе sur une fenetre passee n'est PAS une garantie future :
#    revalider regulierement (`scalpbot validate`).
PRESETS = {
    # Momentum GOLD 15m + filtre Ichimoku : edge confirme hors-echantillon
    # (OOS : PF 3.8, +5.1%, DD 1.1% -> meilleur sur toutes les metriques que
    #  sans Ichimoku). RECOMMANDE.
    "gold15m": dict(
        strategy="momentum",
        interval="15m", ema_fast=9, ema_slow=21,
        sl_atr=2.5, tp_atr=4.0, trend_ema=100, trail_atr=0.0,
        use_ichimoku=1, ichi_tenkan=9, ichi_kijun=26, ichi_span_b=52, ichi_shift=26,
    ),
    # SMC/ICT GOLD (FVG + prise de liquidite) : EXPERIMENTAL. L'edge existe
    # mais est faible et sur trop peu de trades pour etre fiable -> a surveiller,
    # pas a privilegier. Voir README.
    "smc_gold": dict(
        strategy="smc",
        interval="15m", smc_swing=2, smc_lookback=12,
        smc_fvg_min_atr=0.15, smc_rr=3.0, max_hold_bars=20,
        smc_require_sweep=1, smc_killzone=0,
    ),
}


def apply_preset(cfg, name):
    if name not in PRESETS:
        raise KeyError(f"Preset inconnu: {name}. Connus: {', '.join(PRESETS)}")
    for k, v in PRESETS[name].items():
        setattr(cfg, k, v)
    return cfg


def get_instrument(symbol):
    if symbol in INSTRUMENTS:
        return INSTRUMENTS[symbol]
    raise KeyError(
        f"Instrument inconnu: {symbol}. Connus: {', '.join(INSTRUMENTS)}")
