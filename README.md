# scalpbot — scalping / momentum en PAPER TRADING

Moteur de trading automatisé **simulé** pour **XAUUSD** (`GC=F`) et **BTCUSD**
(`BTC-USD`). 100% stdlib Python (aucun `pip`), dans l'esprit du bot Telegram
existant.

> ⚠️ **Ce n'est PAS du vrai HFT** et ça ne passe **aucun ordre réel**. Les
> exécutions sont simulées (spread, slippage, frais) sur des prix live réels
> (Yahoo Finance). Outil d'apprentissage et de validation de stratégie.
> Le trading comporte un risque de perte. Ceci n'est pas un conseil
> d'investissement.

## Installation

Rien à installer. Python 3.9+ suffit.

## Utilisation

Backtest (à faire AVANT tout live) :

```bash
python -m scalpbot backtest --symbol BTC-USD
python -m scalpbot backtest --symbol GC=F --interval 5m --verbose
```

Optimiser (grid-search) puis valider hors-échantillon :

```bash
python -m scalpbot optimize --symbol GC=F          # cherche les meilleurs params
python -m scalpbot validate --symbol GC=F --interval 15m   # test out-of-sample
```

### Backtest sur plusieurs années (source OANDA)

Yahoo plafonne l'intraday à ~1 mois (15m). Pour backtester sur **2-3 ans**,
utilise l'API OANDA (compte **practice gratuit**) :

1. Crée un compte démo sur [oanda.com](https://www.oanda.com), génère un
   **token API** (Manage API Access).
2. Exporte-le puis lance avec `--source oanda` :

```bash
export OANDA_TOKEN="ton_token"
python -m scalpbot backtest --symbol GC=F --preset gold15m --source oanda --years 3
python -m scalpbot validate --symbol GC=F --interval 15m --source oanda --years 3
python -m scalpbot optimize --symbol GC=F --source oanda --years 3
```

Symboles mappés automatiquement (`GC=F`→`XAU_USD`, `BTC-USD`→`BTC_USD`).
`OANDA_ENV=live` pour un compte réel (déconseillé pour du backtest).

Boucle paper trading temps réel (avec la config validée) :

```bash
python -m scalpbot live --symbol GC=F --preset gold15m
python -m scalpbot backtest --symbol GC=F --preset gold15m
python -m scalpbot live --symbol GC=F --once   # une seule itération (test/cron)
```

Voir la config effective :

```bash
python -m scalpbot params
```

## Déploiement paper live (GitHub Actions + Telegram)

Le bot tourne **sans machine allumée** : GitHub Actions exécute un tick toutes
les 15 min, envoie les trades sur Telegram et recommite l'état dans le repo.
Modèle idéal pour une stratégie 15 min (pas de boucle 24/7).

> ⚠️ **PAPER TRADING** — aucun ordre réel. Track record démarré à 10 000$ fictifs
> au moment du déploiement (`init` ancre l'état à « maintenant »).

**Étapes :**

1. **Créer un bot Telegram dédié** : sur Telegram, parler à `@BotFather` →
   `/newbot` → récupérer le **token**. Puis faire `/start` sur ton nouveau bot.
2. **Récupérer ton chat_id** : ouvrir
   `https://api.telegram.org/bot<TOKEN>/getUpdates` après avoir écrit au bot,
   lire `chat.id`.
3. **Créer le repo GitHub** et pousser ce dossier :
   ```bash
   cd scalping-bot
   git init && git add -A && git commit -m "scalpbot paper live"
   gh repo create scalpbot-paper --public --source=. --push
   ```
4. **Configurer les secrets** (repo → Settings → Secrets, ou en CLI) :
   ```bash
   gh secret set TELEGRAM_TOKEN --body "<ton_token>"
   gh secret set TELEGRAM_CHAT_ID --body "<ton_chat_id>"
   ```
5. **Vérifier** : onglet *Actions* → *scalp-gold* → *Run workflow* (lancement
   manuel). Le 1er run initialise l'état ; les trades arrivent sur Telegram.

Le workflow `scalp-report.yml` envoie en plus un **résumé quotidien** (equity,
position, perf). Repo **public** recommandé (minutes Actions illimitées ;
aucun secret dans le code).

## Configuration (variables d'environnement)

| Var | Défaut | Rôle |
|-----|--------|------|
| `START_EQUITY` | 10000 | capital de départ (fictif) |
| `RISK_PER_TRADE` | 0.005 | risque par trade (0.5% de l'equity) |
| `MAX_DAILY_LOSS` | 0.03 | stop journalier (bloque à -3%) |
| `INTERVAL` | 1m | timeframe (`1m`,`5m`,`15m`…) |
| `EMA_FAST`/`EMA_SLOW` | 9 / 21 | momentum de fond |
| `RSI_PERIOD` | 14 | filtre RSI |
| `ATR_PERIOD` | 14 | volatilité (sizing SL/TP) |
| `BREAKOUT_LOOKBACK` | 15 | fenêtre de cassure |
| `SL_ATR` / `TP_ATR` | 1.2 / 1.8 | stop / cible en multiples d'ATR |
| `TRAIL_ATR` | 0 | trailing stop (0 = off) |
| `MAX_HOLD_BARS` | 30 | sortie temps |
| `COOLDOWN_BARS` | 3 | pause après une perte |
| `POLL_SECONDS` | 30 | fréquence de la boucle live |
| `HOUR_START`/`HOUR_END` | 0 / 23 | plage horaire Europe/Paris |
| `SCALPBOT_STATE_DIR` | `.` | dossier des fichiers d'état JSON |
| `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` | — | notifs Telegram (optionnel) |

## Architecture

```
scalpbot/
  config.py       instruments + paramètres
  data.py         fetch bougies intraday (Yahoo)
  indicators.py   EMA / RSI / ATR
  strategy.py     signal scalping/momentum + niveaux SL/TP
  broker.py       broker simulé : fills, spread, slippage, frais, PnL
  risk.py         sizing par risque fixe + garde-fous journaliers
  engine.py       boucle live + persistance d'état
  backtest.py     rejeu historique + statistiques
  __main__.py     CLI
```

## Stratégies disponibles

Sélection via `--strategy momentum|smc` (ou `STRATEGY=`).

**`momentum`** (défaut) — direction via croisement EMA, entrée sur cassure du
plus haut/bas récent, filtre RSI anti-extrêmes, filtre de tendance EMA longue,
**filtre Ichimoku** optionnel (prix vs nuage Kumo + Tenkan/Kijun ; activé par
`USE_ICHIMOKU=1`), sortie SL/TP en ATR + sortie temps + signal inverse.

**`smc`** — Smart Money Concepts / ICT. Structure (swings fractals) → BOS
(break of structure) → displacement laissant un **Fair Value Gap** → entrée sur
retour du prix dans le FVG (mitigation). Filtres ICT optionnels : **prise de
liquidité** avant le displacement (`smc_require_sweep`, modèle 2022) et
**killzones** Londres/NY (`smc_killzone`). SL au bord opposé du gap, TP en
reward:risk fixe.

## Résultats d'optimisation (2026-08-01)

Le premier jet (scalping 1m) **perdait** : les frais/slippage mangeaient
l'edge (coût relatif ≈ `frais / (SL_ATR × ATR)`, énorme quand l'ATR est
minuscule sur 1m). Le grid-search + la validation hors-échantillon donnent :

| Actif | Config | In-sample | **Out-of-sample** | Verdict |
|-------|--------|-----------|-------------------|---------|
| **GOLD** | `gold15m` | +4,4% / PF 1,81 | **+3,1% / PF 2,13** | ✅ edge confirmé |
| **BTC** | 60m tuné | +7,2% / PF 1,77 | **−0,45% / PF 1,10** | ⚠️ sur-appris |

→ **GOLD 15m** garde son edge sur des données jamais vues (preset `gold15m`).
**BTC** s'effondre hors-échantillon : pas d'edge exploitable avec cette
stratégie sur cette fenêtre. Ne pas trader BTC sur la foi du backtest seul.

### Filtre Ichimoku (2026-08-01)

Ajout d'un filtre Ichimoku (9/26/52, décalage Senkou correct) au momentum :
n'entre que si le prix est du bon côté du **nuage (Kumo)** avec Tenkan/Kijun
alignés. Comparaison tête-à-tête sur la même fenêtre out-of-sample :

| OOS (gold15m) | Sans Ichimoku | **Avec Ichimoku** |
|---------------|---------------|-------------------|
| Rendement | +3,7% | **+5,1%** |
| Profit factor | 2,2 | **3,8** |
| Max drawdown | 1,6% | **1,1%** |

→ Ichimoku améliore **toutes** les métriques hors-échantillon → intégré au
preset `gold15m` (recommandé).

### Stratégie SMC / ICT (2026-08-01)

Modèle ICT mécanisé (BOS + FVG + retour dans le gap), puis ajout des deux
filtres qui définissent vraiment ICT : **prise de liquidité** et **killzones**.

- La prise de liquidité (`smc_require_sweep=1`) **améliore nettement** la
  qualité (profit factor ~1,1 → ~2,0) : le concept ICT a un fondement réel.
- **MAIS** la stratégie est très sélective (10-20 trades sur la fenêtre),
  l'edge net reste faible (~+4,7% in-sample, ~flat en OOS sur 10 trades) et
  l'échantillon est trop petit pour être statistiquement fiable.
- **Conclusion honnête** : sur ces données, le **momentum reste supérieur et
  plus robuste** que SMC. Le preset `smc_gold` est fourni comme
  **expérimental** (à surveiller en paper, pas à privilégier).

Pistes pour donner plus de chances à SMC : biais HTF (H4/D1), ciblage explicite
de la liquidité opposée comme TP, plus de données historiques pour un
échantillon significatif.

> ⚠️ Un backtest/holdout positif sur UNE fenêtre passée **ne garantit rien**
> pour le futur (régime de marché, over-fitting résiduel). Revalider
> régulièrement (`scalpbot validate`) et n'engager du réel qu'après une
> longue période de paper trading concluante.

## Pistes d'amélioration

- Walk-forward complet (ré-optimisation glissante) au lieu d'un seul holdout.
- Filtre de tendance multi-timeframe réel (fetch H1 séparé).
- Filtre de volatilité / de session (éviter les heures mortes).
- Trailing stop (`TRAIL_ATR`), break-even, sorties partielles.
- Brancher un vrai broker paper (OANDA practice, Binance testnet) en
  remplaçant `broker.py` par un adaptateur API.
