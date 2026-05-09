# pechepro — Design Spec v0.1

**Date :** 2026-05-09 (révisé après découverte infrastructure i5)
**Auteur :** bul4 + Master
**Status :** Draft v2, en attente d'approbation
**Repo :** `D:\pechepro\`
**Hôte cible :** `optimus.local` (Debian 12, 10.0.0.81) — partagé avec stack GIa Underground / GeniA

## 1. Problème et objectifs

Les pêcheurs nord-américains manquent d'une app **personnalisée et contextuelle** qui combine en un seul endroit : conditions météo locales, pression barométrique, phases de lune (solunar major/minor), lever/coucher de soleil, et **astuces ciblées par espèce × région × conditions** (couleurs de leurres selon turbidité, profondeur, présentation, structure).

Apps existantes : génériques (météo seule), payantes (Fishbrain), ou trop techniques (Solunar Pro). Aucune ne donne des recommandations actionnables en français pour le marché québécois et nord-américain.

**Objectif v0.1 :** App Windows gratuite (revenu pub Expedia, camref `1101l5IQud` réutilisé de `omnipost`), backend public gratuit hébergé sur `optimus` (i5) côte-à-côte avec genia-media et omnipost, exposé via Cloudflare tunnel sur `peche.genia.social`, 15 espèces NA prioritaires, FR + EN, offline-capable.

**Critères de succès :**
- App lance en moins de 3 sec, recommandation en moins de 2 sec
- Fonctionne sans internet (DB clonée localement, météo cachée 7 jours)
- Astuces traçables (chaque tip a une source citée)
- Build distribuable .exe + installer Inno Setup, app <60 MB (PyWebView + Python embedded)
- API publique read-only sans clé pour usage tiers

## 2. Architecture

```
┌──────────────────────────┐         ┌──────────────────────┐
│  App Windows (.exe)      │ HTTPS   │  Cloudflare tunnel   │
│  Python + PyWebView      │────────▶│  pechepro (existing  │
│  - HTML/CSS/JS local     │         │  cloudflared service)│
│  - SQLite cache local    │         └──────────┬───────────┘
│  - Widget Expedia        │                    │ peche.genia.social
└──────────────────────────┘                    ▼
                                     ┌──────────────────────┐
                                     │  Nginx (existing)    │
                                     │  rate-limited proxy  │
                                     └──────────┬───────────┘
                                                │ 127.0.0.1:8440
                                                ▼
                                     ┌──────────────────────┐
                                     │  pechepro-api        │
                                     │  FastAPI uvicorn     │
                                     │  systemd service     │
                                     └──────────┬───────────┘
                                                │
                                ┌───────────────┼─────────────────┐
                                ▼               ▼                 ▼
                       ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
                       │ PostgreSQL   │ │ Open-Meteo   │ │ USGS / ECCC  │
                       │ (existing)   │ │ (no key)     │ │ (water temp) │
                       │ DB: pechepro │ └──────────────┘ └──────────────┘
                       └──────────────┘
```

**Pourquoi cette architecture :**
- **Réutilise l'infra GeniA existante** : PostgreSQL (5432), Nginx, cloudflared, systemd patterns — zéro install de DB ou web server
- **DB séparée `pechepro`** dans la même instance PostgreSQL (pas de pollution avec `genia` DB) — owner dédié `pechepro`
- **Subdomain `peche.genia.social`** : DNS via `cloudflared tunnel route dns` (instantané, gratuit, géré dans le compte Cloudflare existant)
- **Port libre 8440** : hors plage actuellement utilisée (8420 genia-media, 8430 omnipost, 8861/8862 omnipost wrappers)
- **App offline-first** : cache local SQLite (clone read-only de pechepro DB) + soleil/lune calculés localement (lib `astral`)
- **API publique gratuite** : différenciateur, peut servir d'autres apps tierces

## 3. Composants

### 3.1 Backend (`backend/`)

**Stack :** Python 3.13 · FastAPI · PostgreSQL (asyncpg) · uvicorn · pydantic v2 · Alembic (migrations)

**Hôte :** `/opt/pechepro-api/` sur `optimus` (i5), service systemd `pechepro-api.service`, écoute `127.0.0.1:8440`, exposé via Nginx vhost `peche.genia.social` puis Cloudflare tunnel `pechepro` (configuration parallèle au `cloudflared-genia` existant).

**Modules :**
- `app/main.py` — FastAPI bootstrap + CORS + middleware logging structuré (journald)
- `app/db/migrations/` — Alembic versions
- `app/db/models.py` — SQLAlchemy 2.x async models (8 tables, voir §4)
- `app/db/seed.py` — chargement des CSV curés depuis `data/curated/` (idempotent)
- `app/routes/species.py` — `GET /v1/species`, `GET /v1/species/{id}`
- `app/routes/regions.py` — `GET /v1/regions`, `GET /v1/water-types`
- `app/routes/astro.py` — `GET /v1/sun-moon?lat=&lon=&date=` (calculé via `astral` + `skyfield`)
- `app/routes/weather.py` — `GET /v1/weather?lat=&lon=` (proxy Open-Meteo, cache 30 min via `cachetools` ou Redis si dispo)
- `app/routes/recommend.py` — `POST /v1/recommend` (orchestrateur principal)
- `app/routes/health.py` — `GET /v1/health` (uptime + DB connectivity ping)
- `app/services/solunar.py` — algorithme major/minor periods (lune transit ± 1h, opposite ± 1h)
- `app/services/baro_analyzer.py` — tendance baro 6h/24h + score activité par espèce
- `app/services/recommender.py` — query DB tips + ranking par match conditions
- `app/services/openmeteo_client.py` — wrapper httpx async
- `tests/` — pytest + pytest-asyncio + testcontainers-postgres, ≥80% coverage

**Interface publique :** REST JSON, OpenAPI auto-généré (`/docs`), versionné `/v1/`.

**Dépendances :** Open-Meteo (no key, attribution), USGS Water Data (no key, US only), ECCC (Canada, public). `astral` 3.x, `skyfield` 1.x, `httpx`, `fastapi`, `uvicorn[standard]`, `pydantic`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`.

**Setup PostgreSQL (idempotent dans `setup-i5.sh`) :**
```sql
CREATE USER pechepro WITH PASSWORD '<gen>';
CREATE DATABASE pechepro OWNER pechepro;
GRANT ALL PRIVILEGES ON DATABASE pechepro TO pechepro;
```
Password généré aléatoirement, stocké dans `/opt/pechepro-api/.env` (mode 0600, owner `pechepro` user système).

### 3.2 Frontend Windows (`frontend/`)

**Stack :** Python 3.13 · PyWebView · Flask local (port 0, choix dynamique) · HTML5 + CSS3 + vanilla JS · SQLite cache

**Écrans :**
1. **Home** — "Où es-tu ?" (GPS auto via Windows Location API + override manuel par sélecteur région) · "Que pêches-tu ?" (15 espèces dropdown avec photos) · "Type d'eau" (lac/rivière/étang/fleuve/baie)
2. **Conditions** (auto-fetched depuis backend + cache) — météo actuelle, pression baro + tendance, phase lune, lever/coucher soleil, fenêtres solunar (vert/jaune/rouge), température eau (si dispo via USGS/ECCC ou input manuel)
3. **Astuces** — output rangé : couleurs leurres recommandées (avec swatches), profondeur, type de leurre, présentation (vitesse récup), structure à viser, fenêtres horaires optimales du jour. Footer = widget Expedia leaderboard 728×90 (camref `1101l5IQud`, pubref `pechepro-tips`).

**Modules :**
- `src/app.py` — entry point PyWebView, gère window + Flask thread
- `src/server.py` — Flask local servant les templates + API proxy vers backend distant
- `src/sync.py` — sync DB locale ↔ backend (delta quotidien sur `tips`/`species`/`color_visibility`)
- `src/geolocation.py` — wrapper Windows Location API + fallback IP (`ipapi.co`)
- `src/cache.py` — gestion cache offline (météo 7 jours, soleil/lune calculé localement)
- `static/css/style.css` — design system (palette : pêche/eau, fonts Inter + JetBrains Mono)
- `static/js/main.js` — interactions, fetch local Flask
- `templates/{home,conditions,tips}.html` — Jinja2

**Dépendances :** `pywebview` 5.x, `flask` 3.x, `requests`, `astral`, `pyinstaller` (build), `winsdk` (geolocation).

### 3.3 Données curées (`data/curated/`)

CSVs versionnés git, source de vérité pour le seed initial :
- `species.csv` — 15 espèces NA (voir §6)
- `regions.csv` — provinces canadiennes + 50 états US (65 lignes)
- `water_types.csv` — 5 types
- `lures.csv` — ~30 leurres avec catégories
- `color_visibility.csv` — matrice turbidité × luminosité × couleur (~120 lignes)
- `tips.csv` — astuces granulaires (~300-500 lignes pour MVP, sources citées colonne `source_url`)

Chaque tip a : `species_id, region_id (nullable, null=global NA), water_type_id, season, baro_trend (enum), moon_phase (enum), temp_water_range, time_of_day, tip_text_fr, tip_text_en, source_url, confidence (1-5)`.

**Sources des tips MVP** (à citer dans `source_url`) :
- Sépaq · Quebec Pêche · Pêches et Océans Canada
- In-Fisherman · Bassmaster · Field & Stream
- Livres référence : "Multi-Species Angler" (Lindner), "Critical Concepts" (In-Fisherman)
- INFOpêche

### 3.4 Deploy (`deploy/`)

**i5 (Linux Debian 12 — `optimus`) :**
- `deploy/i5/setup-i5.sh` — bash script idempotent inspiré de `setup-tunnel.sh` existant. Étapes : (1) crée user système `pechepro`, (2) clone repo dans `/opt/pechepro-api`, (3) crée venv Python 3.13, (4) installe deps, (5) crée DB Postgres `pechepro` + user, (6) lance Alembic migrations, (7) seed initial depuis `data/curated/`, (8) installe systemd unit `pechepro-api.service` (template fourni), (9) installe Nginx vhost `peche.genia.social` (template fourni), (10) crée tunnel cloudflared `pechepro` + DNS route, (11) start services
- `deploy/i5/pechepro-api.service` — systemd unit (calqué sur `genia-media.service` : User=pechepro, WorkingDirectory=/opt/pechepro-api, ExecStart=`uvicorn`, hardening `NoNewPrivileges`, `ProtectSystem`, `ProtectHome`, `PrivateTmp`)
- `deploy/i5/nginx-peche.conf` — vhost Nginx (calqué sur `media.genia.social` : `proxy_pass http://127.0.0.1:8440`, `limit_req zone=api`, `proxy_cache 5m` sur les endpoints read-only, `client_max_body_size 1M`)
- `deploy/i5/cloudflared-pechepro.yml` — config tunnel (entry ingress `peche.genia.social → http://localhost:80` car Nginx termine le proxy)
- `deploy/i5/cloudflared-pechepro.service` — systemd unit (calqué sur `cloudflared-genia` existant)
- `deploy/i5/uninstall-i5.sh` — script de retrait propre (drop DB, stop services, remove files) pour repartir de zéro si besoin

**Windows (app frontend) :**
- `deploy/windows/installer.iss` — Inno Setup script pour build .exe + installer
- `deploy/windows/build.ps1` — orchestre PyInstaller + Inno Setup
- `deploy/windows/sign.ps1` — signature signtool.exe (V0.2, certificat à acquérir)

## 4. Schéma de base de données (PostgreSQL 15+)

DB : `pechepro` dans l'instance Postgres existante de `optimus` (port 5432, owner `pechepro`). Le client app local utilise SQLite comme **cache read-only** (clone synchronisé via `/v1/sync`).

```sql
CREATE TYPE country_code AS ENUM ('CA','US','MX');
CREATE TYPE water_clarity AS ENUM ('clear','stained','muddy');
CREATE TYPE light_level AS ENUM ('bright','overcast','dawn_dusk','night');
CREATE TYPE season_t AS ENUM ('spring','summer','fall','winter','any');
CREATE TYPE baro_trend_t AS ENUM ('rising','falling','steady','any');
CREATE TYPE moon_phase_t AS ENUM ('new','waxing','full','waning','any');
CREATE TYPE tod_t AS ENUM ('dawn','morning','midday','afternoon','dusk','night','any');
CREATE TYPE period_t AS ENUM ('major','minor');

CREATE TABLE species (
    id SERIAL PRIMARY KEY,
    common_name_fr TEXT NOT NULL,
    common_name_en TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    family TEXT,
    typical_habitat TEXT,
    image_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE regions (
    id SERIAL PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL,
    country country_code NOT NULL,
    iso_code TEXT NOT NULL,  -- ex: 'QC', 'ON', 'NY'
    bbox_lat_min DOUBLE PRECISION,
    bbox_lat_max DOUBLE PRECISION,
    bbox_lon_min DOUBLE PRECISION,
    bbox_lon_max DOUBLE PRECISION
);
CREATE INDEX idx_regions_iso ON regions(country, iso_code);

CREATE TABLE water_types (
    id SERIAL PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL
);

CREATE TABLE lures (
    id SERIAL PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL,
    category TEXT NOT NULL,  -- ex: 'soft_plastic', 'crankbait', 'jig', 'spinnerbait', 'fly'
    image_url TEXT
);

CREATE TABLE color_visibility (
    id SERIAL PRIMARY KEY,
    water_clarity water_clarity NOT NULL,
    light_level light_level NOT NULL,
    color TEXT NOT NULL,
    visibility_score INTEGER NOT NULL CHECK(visibility_score BETWEEN 1 AND 10),
    notes_fr TEXT,
    notes_en TEXT
);
CREATE INDEX idx_color_visibility_lookup ON color_visibility(water_clarity, light_level);

CREATE TABLE tips (
    id SERIAL PRIMARY KEY,
    species_id INTEGER NOT NULL REFERENCES species(id) ON DELETE CASCADE,
    region_id INTEGER REFERENCES regions(id),  -- nullable = applicable partout
    water_type_id INTEGER REFERENCES water_types(id),
    season season_t DEFAULT 'any',
    baro_trend baro_trend_t DEFAULT 'any',
    moon_phase moon_phase_t DEFAULT 'any',
    temp_water_min_c REAL,
    temp_water_max_c REAL,
    time_of_day tod_t DEFAULT 'any',
    tip_text_fr TEXT NOT NULL,
    tip_text_en TEXT NOT NULL,
    source_url TEXT,
    confidence INTEGER CHECK(confidence BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_tips_species ON tips(species_id);
CREATE INDEX idx_tips_lookup ON tips(species_id, region_id, water_type_id, season);

CREATE TABLE solunar_rules (
    id SERIAL PRIMARY KEY,
    period_type period_t NOT NULL,
    duration_minutes INTEGER NOT NULL,
    weight REAL NOT NULL CHECK(weight BETWEEN 0.0 AND 1.0)
);

CREATE TABLE baro_rules (
    id SERIAL PRIMARY KEY,
    species_id INTEGER NOT NULL REFERENCES species(id) ON DELETE CASCADE,
    baro_trend baro_trend_t NOT NULL,
    activity_score INTEGER NOT NULL CHECK(activity_score BETWEEN 1 AND 10),
    notes_fr TEXT,
    notes_en TEXT
);
CREATE INDEX idx_baro_rules_species ON baro_rules(species_id);
```

## 5. Flux de données

### 5.1 Recommandation principale (flux critique)

```
1. User → Home : species_id=walleye, water_type=lake, GPS=46.81,-71.21 (Lévis)
2. App → Backend : POST /v1/recommend {species_id, water_type_id, lat, lon, date}
3. Backend orchestrateur :
   a. → Open-Meteo : météo actuelle + 24h forecast + baro
   b. → astral lib : lever/coucher soleil + phase lune + transits
   c. → solunar.py : calcule major/minor périodes du jour
   d. → recommender.py : query DB tips matching species × region × water × baro_trend × moon_phase
   e. → ranking : score chaque tip par nb de conditions matchées + confidence
4. Backend → App : { weather, baro_trend, sun_moon, solunar_periods, tips_ranked[], lures_recommended[] }
5. App → écran Astuces : render
6. App → cache local : sauvegarde réponse 30 min (clé = species_id + lat/lon arrondi + date)
```

### 5.2 Sync DB locale ↔ backend

Au premier lancement : full clone des tables `species`, `regions`, `water_types`, `lures`, `color_visibility`, `tips`, `solunar_rules`, `baro_rules` (~3 MB).

Quotidien (au lancement si dernier sync >24h) : delta sync via `GET /v1/sync?since=<iso>` → applique upserts.

Si offline : utilise cache local + soleil/lune calculé localement (astral lib embarquée), pas de météo.

## 6. Espèces MVP (15 espèces nord-américaines)

| FR | EN | Scientifique |
|---|---|---|
| Achigan à grande bouche | Largemouth Bass | *Micropterus salmoides* |
| Achigan à petite bouche | Smallmouth Bass | *Micropterus dolomieu* |
| Doré jaune | Walleye | *Sander vitreus* |
| Doré noir | Sauger | *Sander canadensis* |
| Grand brochet | Northern Pike | *Esox lucius* |
| Maskinongé | Muskellunge | *Esox masquinongy* |
| Truite mouchetée | Brook Trout | *Salvelinus fontinalis* |
| Truite arc-en-ciel | Rainbow Trout | *Oncorhynchus mykiss* |
| Truite brune | Brown Trout | *Salmo trutta* |
| Touladi | Lake Trout | *Salvelinus namaycush* |
| Saumon atlantique | Atlantic Salmon | *Salmo salar* |
| Ouananiche | Landlocked Salmon | *Salmo salar (forme dulcicole)* |
| Perchaude | Yellow Perch | *Perca flavescens* |
| Crapet-soleil | Pumpkinseed Sunfish | *Lepomis gibbosus* |
| Barbue de rivière | Channel Catfish | *Ictalurus punctatus* |

## 7. Gestion d'erreurs

| Cas | Comportement |
|---|---|
| Backend HS (timeout 5s) | App utilise cache local, bandeau "mode hors ligne" |
| Open-Meteo HS | Backend retourne météo cachée si <30 min, sinon `null` + UI affiche "météo indisponible" |
| GPS refusé par Windows | App demande sélection manuelle de région |
| Aucun tip matchant les conditions exactes | Fallback : tips `region=null + baro=any + moon=any` (générique espèce) |
| DB locale corrompue | Suppression + re-sync full au prochain lancement |
| Cloudflare tunnel down | Backend i5 inaccessible → app full offline (annonce dans UI) |

## 8. Stratégie de tests

**Backend :**
- Unit (pytest) : services solunar, baro_analyzer, recommender, openmeteo_client (mocked)
- Integration : DB seed + endpoints REST (httpx test client)
- Coverage cible : ≥80% lignes
- Smoke test E2E : `pytest -k smoke` lance uvicorn + tape `/v1/recommend` pour walleye à Lévis QC

**Frontend :**
- Unit pytest : sync.py, cache.py, geolocation.py (mocked)
- Smoke test : lance app PyWebView en headless mode, vérifie HTML render

**E2E intégré :**
- Playwright optional Phase 2 (UI complète)
- Pour MVP : test manuel checklist + smoke automatisé

## 9. Monétisation

**Widget Expedia Affiliate Banners** — snippet exact porté depuis `optimus:/srv/omnipost/ads_preview.html` :

```html
<div class="eg-affiliate-banners"
     data-program="us-expedia"
     data-network="pz"
     data-layout="leaderboard"
     data-image="city"
     data-message="none"
     data-camref="1101l5IQud"
     data-pubref="pechepro-tips"
     data-link="home"></div>
<script class="eg-affiliate-banners-script"
        src="https://creator.expediagroup.com/products/banners/assets/eg-affiliate-banners.js"></script>
```

**Layouts disponibles (choisir selon écran de l'app) :**
- `leaderboard` 728×90 — footer écran Astuces (recommandé)
- `medium-rectangle` 300×250 — sidebar si layout 3 colonnes
- `half-page` 300×600 — alternative sidebar verticale
- `skyscraper` 160×600 — sidebar étroite

**Tracking pubref :** `pechepro-tips` pour identifier les conversions venant de cette app dans le dashboard Expedia (séparé du trafic omnipost). Master pourra ajouter d'autres `pubref` par écran (ex: `pechepro-conditions`, `pechepro-onboarding`) en V0.2.

**Camref `1101l5IQud`** = compte affilié Expedia Creator de Master, déjà actif (utilisé par omnipost).

**Pas de paywall** dans v0.1. Pas d'achats in-app. Pas de subscription. Le widget se charge async et n'impacte pas le launch time.

## 10. Hors scope (Phase 2+)

- **Phase 2 (post-MVP) :** Web scraper pour enrichir tips, journal de pêche personnel, partage de spots, photos catch
- **Phase 3 :** Espèces sud-américaines (dorado, peacock bass, surubi), app Android/iOS, mode multi-utilisateurs
- **Phase 4 :** Premium tier (météo radar, prédictions IA, communauté), Microsoft Store, App Store mobile

## 11. Risques et mitigations

| Risque | Mitigation |
|---|---|
| ~~**i5 SSH bloqué**~~ | ✅ **Résolu** : SSH `optimus@10.0.0.81` avec clé existante `id_ed25519` fonctionne, user `optimus` (Debian 12) |
| ~~**Pas de domaine Cloudflare**~~ | ✅ **Résolu** : `genia.social` actif, sous-domaine `peche.genia.social` créé via `cloudflared tunnel route dns pechepro peche.genia.social` |
| ~~**Pub Expedia rejet/délai compte affilié**~~ | ✅ **Résolu** : compte affilié Expedia Creator déjà actif (camref `1101l5IQud`), widget snippet récupéré, intégration directe |
| **Conflit de port avec services existants** | Port 8440 choisi (libre — hors plage 8420/8430/8861/8862 utilisée) ; vérification automatique dans `setup-i5.sh` |
| **Pollution DB `genia` existante** | DB `pechepro` séparée dans la même instance Postgres ; user dédié `pechepro` avec privilèges limités à sa DB |
| **Open-Meteo rate-limit** (10k calls/jour gratuit) | Cache backend 30 min in-memory + Postgres `weather_cache` table, cache app 1h, suffit pour <2k users actifs/jour |
| **Données curées incomplètes** (tips manquants pour combinaisons rares) | Fallback tips génériques par espèce, message UI honnête "données limitées pour cette combinaison" |
| **Légalité scraping Phase 2** | Phase 1 = curation manuelle uniquement, sources citées. Scraping Phase 2 fait robots.txt + ToS-compliant (allowlist) |
| **Service systemd plante en silence** | Healthcheck via `/v1/health` + cron monitoring ajouté à `genia-status.sh` (3 lignes : ajouter `pechepro-api` et `cloudflared-pechepro` dans la liste des services) |
| **Coexistence avec genia-media** | Hardening systemd identique (NoNewPrivileges, ProtectHome, ReadWritePaths uniquement sur `/opt/pechepro-api`) ; pas d'interférence avec `/srv/genia/` ou `/srv/omnipost/` |

## 12. Décomposition implémentation (preview pour writing-plans)

5 plans parallèles à dispatcher :

1. **plan-1-backend-core** — FastAPI bootstrap, schema DB, seed loader, services (solunar, baro, recommender), routes species/regions/astro, tests
2. **plan-2-data-curation** — CSVs `species.csv`, `regions.csv`, `lures.csv`, `color_visibility.csv`, `tips.csv` (~300 tips MVP avec sources)
3. **plan-3-external-apis** — wrappers Open-Meteo, USGS Water, ECCC, route `/v1/weather`, route `/v1/recommend` (orchestrateur)
4. **plan-4-frontend-app** — PyWebView shell, Flask local, écrans Home/Conditions/Astuces, sync, cache, geolocation, design system CSS
5. **plan-5-deploy** — `setup-i5.sh` bash idempotent (Postgres setup, systemd unit `pechepro-api`, Nginx vhost `peche.genia.social`, cloudflared tunnel `pechepro` + DNS route), `uninstall-i5.sh` propre, Inno Setup installer Windows, build script PyInstaller, smoke checklist E2E

Chaque plan = un agent worktree isolé, executor pattern. Merge sur `main` après code-review.

## 13. Critères "done" pour v0.1

- [ ] Backend déployé sur `optimus`, service `pechepro-api` actif (`systemctl is-active`)
- [ ] Tunnel `cloudflared-pechepro` actif, `peche.genia.social` répond en HTTPS
- [ ] `GET https://peche.genia.social/v1/health` retourne 200 depuis n'importe où
- [ ] `POST /v1/recommend` fonctionne pour les 15 espèces × 5 régions tests (smoke test E2E)
- [ ] DB Postgres `pechepro` seedée : ≥300 tips, ≥120 entrées color_visibility, 15 species, 65 regions
- [ ] App Windows .exe + installer Inno Setup, installable, taille <60 MB
- [ ] App fonctionne offline après 1 sync initial (vérification : kill backend, app continue à servir les tips)
- [ ] Widget Expedia leaderboard visible et tracké avec `pubref=pechepro-tips`
- [ ] FR + EN complets pour species, tips, UI strings (i18n via `gettext` côté Python)
- [ ] Tests verts : backend ≥80% coverage pytest, frontend smoke pytest
- [ ] `genia-status.sh` mis à jour pour inclure `pechepro-api` et `cloudflared-pechepro`
- [ ] README install : étapes user pour installer l'app + screenshots
- [ ] CHANGELOG.md v0.1.0 daté
- [ ] `setup-i5.sh` est idempotent (peut être ré-exécuté sans casser l'état)
- [ ] `uninstall-i5.sh` testé : drop DB + stop services + remove files = état pristine
