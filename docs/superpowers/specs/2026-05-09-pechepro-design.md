# pechepro — Design Spec v0.1

**Date :** 2026-05-09 (v3 — pivot Option A : app auto-suffisante, zéro backend)
**Auteur :** bul4 + Master
**Status :** Draft v3, en attente d'approbation
**Repo :** `D:\pechepro\`
**Modèle :** Application Windows desktop standalone, distribution .exe direct

> **Note historique :** Les v1 (SQLite + i5 quick-tunnel) et v2 (PostgreSQL + Nginx + i5 partagé) ont été évaluées puis écartées. Master a tranché : **on ne touche pas au i5** (existing GeniA stack reste isolé). Pivot vers une architecture pure desktop sans serveur central — voir §2.

## 1. Problème et objectifs

Les pêcheurs nord-américains manquent d'une app **personnalisée et contextuelle** qui combine en un seul endroit : conditions météo locales, pression barométrique, phases de lune (solunar major/minor), lever/coucher de soleil, et **astuces ciblées par espèce × région × conditions** (couleurs de leurres selon turbidité, profondeur, présentation, structure).

Apps existantes : génériques (météo seule), payantes (Fishbrain), ou trop techniques (Solunar Pro). Aucune ne donne des recommandations actionnables en français pour le marché québécois et nord-américain.

**Objectif v0.1 :** App Windows desktop **gratuite et auto-suffisante** (revenu pub Expedia, camref `1101l5IQud` réutilisé du compte affilié de Master). Tout tourne dans le .exe : DB SQLite embarquée + données curées + APIs externes appelées directement par l'app + soleil/lune calculé localement. **Zéro backend, zéro serveur, zéro maintenance.** 15 espèces NA prioritaires, FR + EN, offline-capable.

**Critères de succès :**
- App lance en moins de 3 sec, recommandation en moins de 2 sec
- Fonctionne 100% offline pour les fonctions de base (cache local + soleil/lune calculé localement)
- Astuces traçables (chaque tip a une source citée)
- Build .exe + installer Inno Setup, sous 60 MB
- Mises à jour des données curées sans réinstaller l'app (sync GitHub raw au lancement, optionnel)
- Distribution un-clic : Master donne un lien `.exe` à un user → install → utilisable en 60 sec

## 2. Architecture

```
┌────────────────────────────────────────────────────────────┐
│  Windows .exe (auto-suffisant)                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  PyWebView shell (fenêtre native Windows)            │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  Flask local (port dynamique 127.0.0.1)        │  │  │
│  │  │  ├─ Templates Jinja2 (Home, Conditions, Tips)  │  │  │
│  │  │  ├─ Static (CSS, JS, images leurres)           │  │  │
│  │  │  └─ Widget Expedia (HTML embarqué)             │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Services Python (in-process)                        │  │
│  │  ├─ recommender (ranking tips)                       │  │
│  │  ├─ solunar (major/minor periods, calculé local)     │  │
│  │  ├─ baro_analyzer (tendance, score activité)         │  │
│  │  ├─ astral (soleil + lune, no network)               │  │
│  │  └─ data_sync (CSVs depuis GitHub raw au launch)     │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLite local (data/pechepro.db)                     │  │
│  │  ├─ 8 tables curées (seed initial dans le .exe)      │  │
│  │  ├─ weather_cache (TTL 1h)                           │  │
│  │  └─ user_prefs (langue, dernière localisation)       │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬───────────────────────────────────┘
                         │ HTTPS direct (no backend proxy)
        ┌────────────────┼────────────────┬────────────────────┐
        ▼                ▼                ▼                    ▼
  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
  │ Open-    │  │ USGS Water   │  │ ECCC Canada  │  │ GitHub raw       │
  │ Meteo    │  │ Data API     │  │ Climate API  │  │ (CSVs updates)   │
  │ (météo + │  │ (US water    │  │ (CA water    │  │ raw.githubuser-  │
  │  baro)   │  │  temp)       │  │  temp)       │  │ content.com      │
  │ no key   │  │ no key       │  │ no key       │  │ no key           │
  └──────────┘  └──────────────┘  └──────────────┘  └──────────────────┘
```

**Pourquoi cette architecture :**
- **Zéro infra serveur** : pas de cloud, pas de VPS, pas de tunnel Cloudflare, pas de DB hébergée. Master livre le `.exe` et oublie.
- **Privacy by default** : aucune donnée user n'est uploadée nulle part (sauf fetch direct vers Open-Meteo qui ne stocke rien)
- **Offline-first natif** : seul Open-Meteo et la sync GitHub demandent du réseau. Tout le reste (recommender, soleil/lune, tips, color_visibility) fonctionne hors ligne avec la DB SQLite embarquée.
- **Mises à jour des tips** : Master commit dans `data/curated/*.csv` sur GitHub → app fetch via `raw.githubusercontent.com` au lancement (cache 24h). Pas besoin de rebuilder l'app pour ajouter des astuces.
- **i5 préservé** : aucun touch sur le stack GeniA existant
- **Coût récurrent : 0 $** : Master peut donner ou vendre le .exe sans inquiétude

## 3. Composants

Tout vit dans un seul package Python, livré comme un `.exe` PyInstaller. Pas de séparation backend/frontend — c'est une app desktop.

### 3.1 Shell PyWebView (`app/shell.py`)

- Entry point du `.exe`. Lance Flask local en thread, ouvre fenêtre PyWebView pointant vers `http://127.0.0.1:<port>`.
- Bind native Windows (icône taskbar, dimensions 1100×750, redimensionnable, min 900×600)
- Gère lifecycle : démarrage Flask → splash 1 sec → ouverture fenêtre → close = arrêt clean Flask

### 3.2 Serveur Flask local (`app/server.py`)

- Port choisi dynamiquement (port 0, OS assigne)
- Routes :
  - `GET /` → écran Home
  - `GET /conditions?lat=&lon=&species=&water=` → écran Conditions (HTML render avec données live)
  - `POST /api/recommend` → JSON pour le frontend JS
  - `GET /api/species` → liste pour dropdowns
  - `GET /api/regions` → liste régions (auto-détectée par GPS)
  - `GET /api/sun-moon?lat=&lon=&date=` → calcul local via `astral`
  - `GET /api/weather?lat=&lon=` → wrapper Open-Meteo + cache SQLite 1h
- Templates Jinja2 dans `app/templates/`
- Static dans `app/static/` (CSS, JS, images leurres + icons)

### 3.3 Services Python (`app/services/`)

- `recommender.py` — query SQLite tips + ranking par match conditions (species_id, region, water_type, baro_trend, moon_phase, season, time_of_day) + fallback générique si pas de match exact
- `solunar.py` — algorithme major/minor periods (lune transit ± 1h pour major, opposite ± 1h pour minor) ; renvoie windows du jour avec scores qualité
- `baro_analyzer.py` — analyse tendance baro 6h/24h depuis Open-Meteo, score activité par espèce via table `baro_rules`
- `astral_calc.py` — wrapper `astral` 3.x : soleil lever/coucher + crépuscules civil/nautique + lune phase + transits ; tout calculé localement, no network
- `openmeteo_client.py` — async fetch avec `httpx`, cache résultats dans table `weather_cache` (TTL 1h)
- `usgs_client.py` — fetch température eau depuis USGS Water Services (US only, lat/lon → station la plus proche)
- `eccc_client.py` — fetch température eau depuis ECCC pour régions canadiennes (couverture limitée mais gratuite)
- `data_sync.py` — au launch, fetch CSVs depuis `raw.githubusercontent.com/sxc3030-eng/pechepro/main/data/curated/*.csv` (cache 24h) et applique upserts dans SQLite. Si offline, skip silencieusement.
- `geolocation.py` — wrapper Windows Location API (`winsdk.windows.devices.geolocation`) + fallback IP via `ipapi.co` (gratuit no key, 1k req/jour)

### 3.4 Base de données locale (`app/db/`)

- `schema.sql` — DDL des 8 tables (voir §4) — exécuté au premier launch si `pechepro.db` n'existe pas
- `migrations/` — fichiers SQL versionnés (V001, V002, …) appliqués séquentiellement
- `seed_initial.sql` — données curées embarquées dans le .exe (snapshot du repo au build time) — chargées si DB vide

DB locale stockée à `%LOCALAPPDATA%\pechepro\pechepro.db` (pas dans le folder de l'app — survit aux mises à jour).

### 3.5 Données curées (`data/curated/`)

CSVs versionnés git, **double rôle** :
1. Bundlés dans le .exe au build (seed initial)
2. Servis via GitHub raw pour mises à jour live (`raw.githubusercontent.com/sxc3030-eng/pechepro/main/data/curated/*.csv`)

Fichiers :
- `species.csv` — 15 espèces NA (voir §6)
- `regions.csv` — provinces canadiennes + états US (~65 lignes)
- `water_types.csv` — 5 types
- `lures.csv` — ~30 leurres avec catégories
- `color_visibility.csv` — matrice turbidité × luminosité × couleur (~120 lignes)
- `tips.csv` — astuces granulaires (~300-500 lignes pour MVP, sources citées colonne `source_url`)
- `solunar_rules.csv` — règles algorithmique major/minor
- `baro_rules.csv` — règles activité par espèce × tendance baro

Chaque tip a : `species_id, region_id (nullable, null=global NA), water_type_id, season, baro_trend, moon_phase, temp_water_range, time_of_day, tip_text_fr, tip_text_en, source_url, confidence (1-5)`.

**Sources des tips MVP** (à citer dans `source_url`) :
- Sépaq · Quebec Pêche · Pêches et Océans Canada
- In-Fisherman · Bassmaster · Field & Stream
- Livres référence : "Multi-Species Angler" (Lindner), "Critical Concepts" (In-Fisherman)
- INFOpêche

### 3.6 Build & distribution (`deploy/windows/`)

- `installer.iss` — Inno Setup script : installe dans `%LOCALAPPDATA%\Programs\pechepro\`, crée raccourci Desktop + Start Menu, uninstaller propre
- `build.ps1` — orchestre : `pyinstaller app/shell.py --windowed --onefile --icon=app/static/img/logo.ico --add-data="data/curated;data/curated" --add-data="app/db/schema.sql;app/db" --add-data="app/db/seed_initial.sql;app/db"` → `dist/pechepro.exe` → Inno Setup → `dist/pechepro-setup.exe`
- `sign.ps1` — signature signtool (V0.2 quand certificat acquis ; pour V0.1 SmartScreen warning acceptable)
- GitHub Actions workflow `.github/workflows/release.yml` — déclenché sur tag `v*`, build sur runner windows-latest, upload artifact `pechepro-setup.exe` à la release GitHub

## 4. Schéma de base de données (SQLite local)

```sql
CREATE TABLE species (
    id INTEGER PRIMARY KEY,
    common_name_fr TEXT NOT NULL,
    common_name_en TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    family TEXT,
    typical_habitat TEXT,
    image_url TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE regions (
    id INTEGER PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL,
    country TEXT NOT NULL CHECK(country IN ('CA','US','MX')),
    iso_code TEXT NOT NULL,
    bbox_lat_min REAL,
    bbox_lat_max REAL,
    bbox_lon_min REAL,
    bbox_lon_max REAL
);
CREATE INDEX idx_regions_iso ON regions(country, iso_code);

CREATE TABLE water_types (
    id INTEGER PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL
);

CREATE TABLE lures (
    id INTEGER PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL,
    category TEXT NOT NULL,
    image_url TEXT
);

CREATE TABLE color_visibility (
    id INTEGER PRIMARY KEY,
    water_clarity TEXT NOT NULL CHECK(water_clarity IN ('clear','stained','muddy')),
    light_level TEXT NOT NULL CHECK(light_level IN ('bright','overcast','dawn_dusk','night')),
    color TEXT NOT NULL,
    visibility_score INTEGER NOT NULL CHECK(visibility_score BETWEEN 1 AND 10),
    notes_fr TEXT,
    notes_en TEXT
);
CREATE INDEX idx_color_visibility_lookup ON color_visibility(water_clarity, light_level);

CREATE TABLE tips (
    id INTEGER PRIMARY KEY,
    species_id INTEGER NOT NULL REFERENCES species(id),
    region_id INTEGER REFERENCES regions(id),
    water_type_id INTEGER REFERENCES water_types(id),
    season TEXT CHECK(season IN ('spring','summer','fall','winter','any')) DEFAULT 'any',
    baro_trend TEXT CHECK(baro_trend IN ('rising','falling','steady','any')) DEFAULT 'any',
    moon_phase TEXT CHECK(moon_phase IN ('new','waxing','full','waning','any')) DEFAULT 'any',
    temp_water_min_c REAL,
    temp_water_max_c REAL,
    time_of_day TEXT CHECK(time_of_day IN ('dawn','morning','midday','afternoon','dusk','night','any')) DEFAULT 'any',
    tip_text_fr TEXT NOT NULL,
    tip_text_en TEXT NOT NULL,
    source_url TEXT,
    confidence INTEGER CHECK(confidence BETWEEN 1 AND 5),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_tips_species ON tips(species_id);
CREATE INDEX idx_tips_lookup ON tips(species_id, region_id, water_type_id, season);

CREATE TABLE solunar_rules (
    id INTEGER PRIMARY KEY,
    period_type TEXT NOT NULL CHECK(period_type IN ('major','minor')),
    duration_minutes INTEGER NOT NULL,
    weight REAL NOT NULL CHECK(weight BETWEEN 0.0 AND 1.0)
);

CREATE TABLE baro_rules (
    id INTEGER PRIMARY KEY,
    species_id INTEGER NOT NULL REFERENCES species(id),
    baro_trend TEXT NOT NULL CHECK(baro_trend IN ('rising','falling','steady')),
    activity_score INTEGER NOT NULL CHECK(activity_score BETWEEN 1 AND 10),
    notes_fr TEXT,
    notes_en TEXT
);

-- Tables runtime (créées au launch, pas dans le seed)
CREATE TABLE weather_cache (
    cache_key TEXT PRIMARY KEY,  -- "lat_round,lon_round"
    payload_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE user_prefs (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
-- ex : ('language', 'fr'), ('last_lat', '46.81'), ('last_lon', '-71.21'), ('last_species_id', '3')

CREATE TABLE data_sync_meta (
    table_name TEXT PRIMARY KEY,
    last_synced_at TEXT,
    last_etag TEXT,
    row_count INTEGER
);
```

## 5. Flux de données

### 5.1 Recommandation principale (flux critique, 100% in-process)

```
1. User → Home : species=walleye, water_type=lake, GPS=46.81,-71.21 (Lévis QC)
2. Flask local /conditions :
   a. → astral_calc.py : lever/coucher soleil + phase lune + transits (no network)
   b. → openmeteo_client.py : météo + baro + forecast (HTTPS direct, cache 1h)
   c. → solunar.py : major/minor periods du jour
   d. → baro_analyzer.py : tendance baro 6h, score activité walleye
   e. → recommender.py : query SQLite tips matching walleye × QC × lake × baro_trend × moon_phase
   f. → ranking : score chaque tip par nb conditions matchées + confidence
3. Flask render template /conditions avec : weather, baro_trend, sun_moon, solunar_periods, tips_ranked[], lures_recommended[]
4. PyWebView affiche le HTML
5. Footer charge widget Expedia (async, n'altère pas le rendering)
```

### 5.2 Sync curated data depuis GitHub (au launch, optionnel)

```
1. App start → data_sync.py
2. Pour chaque table syncable (species, regions, lures, tips, color_visibility, solunar_rules, baro_rules) :
   a. Check data_sync_meta.last_synced_at < 24h ago → sinon skip
   b. → GET https://raw.githubusercontent.com/sxc3030-eng/pechepro/main/data/curated/<table>.csv
      avec If-None-Match header (etag)
   c. Si 304 → update last_synced_at seulement
   d. Si 200 → parse CSV, upsert dans SQLite (DELETE + INSERT, simple pour MVP)
   e. Update data_sync_meta avec nouveau etag + row_count
3. Si offline ou erreur réseau : log warn, continue avec DB locale existante
```

**Avantage :** Master peut commit un PR `data: add 50 walleye tips` sur GitHub → tous les users existants auront les nouveaux tips au prochain launch, sans réinstaller.

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
| Open-Meteo timeout (5s) | Utilise cache local si <2h, sinon affiche bandeau "météo indisponible — astuces basées sur les conditions de référence" et continue avec les tips génériques |
| GPS Windows refusé | Demande sélection manuelle de région (dropdown 65 régions NA) |
| GitHub raw HS (sync curated) | Log warn, continue avec DB locale, ré-essaie au prochain launch |
| DB SQLite corrompue | Suppression `pechepro.db` + reseed depuis `seed_initial.sql` embarqué (perd weather_cache + user_prefs, regénérés au runtime) |
| USGS / ECCC HS (water temp) | Champ vide ou demande user de saisir manuellement (slider) |
| Aucun tip matchant les conditions exactes | Fallback hierarchy : (a) même species + region match + any baro/moon ; (b) même species + region=null ; (c) tips génériques par species. UI affiche niveau de confiance. |
| Widget Expedia bloqué (uBlock) | Le rendering continue normalement, slot reste vide. Pas de message d'erreur (UX positive) |

## 8. Stratégie de tests

**App :**
- Unit (pytest) : services solunar, baro_analyzer, recommender, astral_calc, openmeteo_client (mocked httpx), data_sync (mocked GitHub)
- Integration : DB seed + Flask routes (Flask test client)
- Coverage cible : ≥80% lignes
- Smoke test E2E : `pytest -k smoke` lance l'app en mode headless (PyWebView headless flag) + tape `GET /conditions?species=3&water=1&lat=46.81&lon=-71.21` → vérif HTML contient le mot "Doré" ou "Walleye"

**Build :**
- `build.ps1` doit produire un .exe testable (smoke launch + close)
- GitHub Actions runs sur push `main` : tests + build .exe artifact (pas release sauf tag)

## 9. Monétisation

**Widget Expedia Affiliate Banners** — snippet exact porté depuis `optimus:/srv/omnipost/ads_preview.html` (lecture seule, pas de modif sur i5) :

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

**Layouts disponibles :**
- `leaderboard` 728×90 — footer écran Astuces (recommandé MVP)
- `medium-rectangle` 300×250 — sidebar si layout 3 colonnes
- `half-page` 300×600 — alternative sidebar verticale

**Tracking pubref :** `pechepro-tips` pour identifier les conversions venant de cette app (séparé du trafic omnipost). Master peut ajouter d'autres `pubref` par écran en V0.2 (`pechepro-conditions`, `pechepro-onboarding`).

**Camref `1101l5IQud`** = compte affilié Expedia Creator de Master, déjà actif.

**Pas de paywall** dans v0.1. Pas d'achats in-app. Pas de subscription. Le widget se charge async dans le PyWebView et n'impacte pas le launch time.

## 10. Hors scope (Phase 2+)

- **Phase 2 (post-MVP) :** API publique (si Master veut exposer la base de connaissances comme service tiers), web scraper pour enrichir tips automatiquement, journal de pêche personnel, partage de spots, photos catch
- **Phase 3 :** Espèces sud-américaines (dorado, peacock bass, surubi), app Android/iOS, mode multi-utilisateurs, sync cloud des préférences
- **Phase 4 :** Premium tier (météo radar, prédictions IA, communauté), Microsoft Store, App Store mobile, certificat code signing pour éliminer le SmartScreen warning

## 11. Risques et mitigations

| Risque | Mitigation |
|---|---|
| **Open-Meteo rate-limit** (10k calls/jour, no key requise) | Cache SQLite 1h par lat/lon arrondi à 0.01° (~1 km) → ~24 calls/user actif/jour, supporte ~400 users actifs simultanés sans dépasser le quota |
| **GitHub raw rate-limit** (60 req/h non-authentifié) | Sync 1×/24h max par user, ETag pour 304s, cache local de 24h avant retry. Suffit pour ~60 lancements/h tous users confondus, largement assez pour V0.1 |
| **Données curées incomplètes** (combinaisons rares manquantes) | Fallback hierarchy dans recommender (§7), UI honnête sur niveau de confiance |
| **Légalité scraping Phase 2** | Phase 1 = curation manuelle uniquement, sources citées. Phase 2 fera robots.txt + ToS-compliant (allowlist) |
| **SmartScreen warning** (.exe non signé) | V0.1 acceptable (user clique "Run anyway"). V0.2 acquérir certificat Code Signing (~$70-200/an) si volume utilisateur le justifie |
| **PyInstaller false-positive antivirus** | Build dans GitHub Actions windows-latest (réputation propre) ; si problème : V0.2 utilise Nuitka (compile en C natif, moins de false positives) |
| **DB locale écrasée à l'update de l'app** | Stockée à `%LOCALAPPDATA%\pechepro\` (séparé du folder `Program Files`), survit aux mises à jour |
| **User a une vieille version sans nouveaux tips** | Sync GitHub raw au launch garantit qu'un user lance l'app aujourd'hui aura les tips à jour, même sur une vieille version d'app (data sync découplée du build) |

## 12. Décomposition implémentation (preview pour writing-plans)

**4 plans parallèles** à dispatcher (vs 5 dans v2 — backend supprimé) :

1. **plan-1-app-core** — PyWebView shell + Flask local + SQLite init/seed + routes templates Home/Conditions/Tips + design system CSS (palette pêche, fonts Inter + JetBrains Mono) + i18n FR/EN gettext
2. **plan-2-services** — recommender, solunar, baro_analyzer, astral_calc, openmeteo_client, usgs_client, eccc_client, data_sync, geolocation — tous testés isolément avec mocks
3. **plan-3-data-curation** — CSVs `species.csv`, `regions.csv`, `water_types.csv`, `lures.csv`, `color_visibility.csv`, `tips.csv` (~300 tips MVP avec sources), `solunar_rules.csv`, `baro_rules.csv`
4. **plan-4-build-deploy** — `build.ps1` + Inno Setup + GitHub Actions release workflow + smoke checklist 20 scénarios

Chaque plan = un agent worktree isolé, executor pattern. Merge sur `main` après code-review.

## 13. Critères "done" pour v0.1

- [ ] App Windows .exe + installer Inno Setup, installable, taille <60 MB
- [ ] Smoke launch : install → ouvrir → Home → sélectionner walleye + Lévis QC + lac → écran Conditions affiché en <3 sec → tips visibles
- [ ] App fonctionne 100% offline (kill réseau, app continue à servir tips + soleil/lune ; météo/baro affiche "indisponible" gracefully)
- [ ] DB SQLite seedée : ≥300 tips, ≥120 entrées color_visibility, 15 species, 65 regions
- [ ] Sync GitHub raw fonctionne : commit `tips.csv` modifié sur main → relancer app → nouveaux tips visibles
- [ ] Widget Expedia leaderboard visible et tracké avec `pubref=pechepro-tips`
- [ ] FR + EN complets pour species, tips, UI strings (i18n via `gettext`)
- [ ] Tests verts : ≥80% coverage pytest, smoke E2E pass
- [ ] README install : étapes user pour installer + screenshots des 3 écrans
- [ ] CHANGELOG.md v0.1.0 daté
- [ ] GitHub release v0.1.0 avec asset `pechepro-setup.exe` téléchargeable
- [ ] Aucun touch sur i5 / GeniA stack (vérifié par diff `before/after` du share `\\10.0.0.81\optimus\`)
