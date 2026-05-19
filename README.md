# pechepro

> App Windows **standalone** gratuite de pêche en Amérique du Nord avec recommandations personnalisées par espèce, région et conditions (météo, pression baro, lune, soleil, solunar).

![Status](https://img.shields.io/badge/status-v0.1.0%20alpha-brightgreen)
![Python](https://img.shields.io/badge/python-3.13-blue)
![Tests](https://img.shields.io/badge/tests-311%20passing-success)
![Coverage](https://img.shields.io/badge/coverage-~96%25-success)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

**Status :** v0.1.0 alpha shipped (2026-05-12) — Windows desktop app live · 15 espèces · 65 régions · 310 tips curés · FR + EN
**Distribution :** `.exe` Windows installable directement, aucun service à déployer
**Spec design :** [docs/superpowers/specs/2026-05-09-pechepro-design.md](docs/superpowers/specs/2026-05-09-pechepro-design.md)

## Architecture rapide

App auto-suffisante :
- **PyWebView shell** + **Flask local** (port dynamique 127.0.0.1) + **SQLite locale** (`%LOCALAPPDATA%\pechepro\pechepro.db`)
- **Services in-process** : recommender, solunar, baro_analyzer, astral (soleil/lune), openmeteo client, usgs/eccc water-temp clients, data_sync depuis GitHub raw
- **Données curées** bundlées au build + sync 1×/24h depuis `raw.githubusercontent.com/sxc3030-eng/pechepro/main/data/curated/*.csv`
- **APIs externes** appelées directement par l'app (no proxy, no backend) : Open-Meteo (météo + baro), USGS Water Data (US), ECCC (Canada)
- **Monétisation** widget Expedia Affiliate Banners leaderboard 728×90 (camref `1101l5IQud`, pubref `pechepro-tips`)

**Zéro infra :** pas de cloud, pas de VPS, pas de tunnel, pas de DB hébergée. Master livre le `.exe` et oublie.

## Espèces MVP (15)

Achigan G/B + P/B · Doré jaune + noir · Brochet · Maskinongé · Truite mouchetée + arc-en-ciel + brune · Touladi · Saumon atlantique · Ouananiche · Perchaude · Crapet-soleil · Barbue de rivière

## Structure

```
app/                  Tout le code applicatif Python
  ├─ shell.py        Entry point PyWebView (le .exe lance ça)
  ├─ server.py       Flask local
  ├─ services/       recommender, solunar, baro, astral, openmeteo, usgs, eccc, data_sync, geolocation
  ├─ db/             schema.sql, migrations, seed_initial.sql
  ├─ templates/      Jinja2 (home, conditions, tips)
  └─ static/         CSS, JS, images leurres + icons

data/curated/        CSVs sources de vérité (species, regions, lures, tips, color_visibility, solunar_rules, baro_rules)
                     Bundlés dans le .exe + servis via GitHub raw pour mises à jour live

deploy/windows/      build.ps1 + installer.iss (Inno Setup) + sign.ps1
.github/workflows/   release.yml (build .exe sur tag v*)
docs/                Specs + plans superpowers
tests/               pytest (services + Flask routes + smoke E2E)
```

## Install

**Download** the latest installer from [GitHub Releases](https://github.com/sxc3030-eng/pechepro/releases/latest) :

- `pechepro-setup.exe` — full Windows installer (recommended)
- `pechepro.exe` — single-file portable executable (no install needed)

**Run** `pechepro-setup.exe`, accept the SmartScreen warning ("More info" → "Run anyway" — V0.2 will be code-signed), and follow the wizard.

**First launch :**
1. App opens to the Home screen
2. Allow Windows Location access (or pick a region manually)
3. Pick a species + water type
4. View Conditions + Tips

**Uninstall :** Settings → Apps → Pechepro → Uninstall.

**Manual data refresh :** the app auto-syncs curated tips from GitHub raw every 24h. To force a refresh, delete `%LOCALAPPDATA%\pechepro\pechepro.db` and relaunch.

## Tech stack

- **Python 3.13** · **PyWebView 5.4** · **Flask 3.0.3** · SQLite stdlib
- **311 pytest tests** · ~96 % coverage on services layer
- Build pipeline : PyInstaller 6.11.1 + Inno Setup 6 + GitHub Actions (windows-latest)
- Astral (sun/moon), Open-Meteo (weather + baro), USGS Water Data (US), ECCC (Canada)

## Screenshots

_To be added in V0.2_ — coming soon.
