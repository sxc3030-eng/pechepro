# pechepro

App Windows gratuite de pêche en Amérique du Nord avec recommandations personnalisées par espèce, région et conditions (météo, pression baro, lune, soleil, solunar).

**Status :** Spec v0.1 (révisée v2 après découverte infra i5) — implémentation à venir
**Spec design :** [docs/superpowers/specs/2026-05-09-pechepro-design.md](docs/superpowers/specs/2026-05-09-pechepro-design.md)
**API publique :** `https://peche.genia.social` (V0.1)

## Architecture rapide

- **Backend** Python FastAPI + PostgreSQL (DB `pechepro` dans l'instance Postgres existante de `optimus`/i5), service systemd `pechepro-api` sur port 8440, Nginx vhost rate-limited, exposé via Cloudflare tunnel `pechepro` sur `peche.genia.social`
- **App Windows** Python + PyWebView + cache local SQLite (clone read-only), .exe + installer Inno Setup, offline-capable
- **Données** curées manuellement (15 espèces NA prioritaires, ≥300 tips, ≥120 entrées color_visibility) + APIs gratuites (Open-Meteo, USGS, ECCC)
- **Monétisation** widget Expedia Affiliate Banners leaderboard 728×90 (camref `1101l5IQud` réutilisé du stack GeniA, pubref `pechepro-tips`)

## Espèces MVP (15)

Achigan G/B + P/B · Doré jaune + noir · Brochet · Maskinongé · Truite mouchetée + arc-en-ciel + brune · Touladi · Saumon atlantique · Ouananiche · Perchaude · Crapet-soleil · Barbue de rivière

## Structure

```
backend/        FastAPI + PostgreSQL (asyncpg) + services solunar/baro/recommender + Alembic
frontend/       PyWebView + Flask local + HTML/CSS/JS + cache local SQLite
data/curated/   CSVs sources de vérité (species, regions, lures, tips, color_visibility)
deploy/i5/      setup-i5.sh + uninstall-i5.sh + systemd units + nginx vhost + cloudflared config
deploy/windows/ Inno Setup + PyInstaller build
docs/           Specs + plans superpowers
```
