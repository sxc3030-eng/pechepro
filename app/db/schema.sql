-- pechepro local SQLite schema (V0.1)
-- Generated from spec §4 — keep in sync.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS species (
    id INTEGER PRIMARY KEY,
    common_name_fr TEXT NOT NULL,
    common_name_en TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    family TEXT,
    typical_habitat TEXT,
    image_url TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS regions (
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
CREATE INDEX IF NOT EXISTS idx_regions_iso ON regions(country, iso_code);

CREATE TABLE IF NOT EXISTS water_types (
    id INTEGER PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lures (
    id INTEGER PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL,
    category TEXT NOT NULL,
    image_url TEXT
);

CREATE TABLE IF NOT EXISTS color_visibility (
    id INTEGER PRIMARY KEY,
    water_clarity TEXT NOT NULL CHECK(water_clarity IN ('clear','stained','muddy')),
    light_level TEXT NOT NULL CHECK(light_level IN ('bright','overcast','dawn_dusk','night')),
    color TEXT NOT NULL,
    visibility_score INTEGER NOT NULL CHECK(visibility_score BETWEEN 1 AND 10),
    notes_fr TEXT,
    notes_en TEXT
);
CREATE INDEX IF NOT EXISTS idx_color_visibility_lookup ON color_visibility(water_clarity, light_level);

CREATE TABLE IF NOT EXISTS tips (
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
CREATE INDEX IF NOT EXISTS idx_tips_species ON tips(species_id);
CREATE INDEX IF NOT EXISTS idx_tips_lookup ON tips(species_id, region_id, water_type_id, season);

CREATE TABLE IF NOT EXISTS solunar_rules (
    id INTEGER PRIMARY KEY,
    period_type TEXT NOT NULL CHECK(period_type IN ('major','minor')),
    duration_minutes INTEGER NOT NULL,
    weight REAL NOT NULL CHECK(weight BETWEEN 0.0 AND 1.0)
);

CREATE TABLE IF NOT EXISTS baro_rules (
    id INTEGER PRIMARY KEY,
    species_id INTEGER NOT NULL REFERENCES species(id),
    baro_trend TEXT NOT NULL CHECK(baro_trend IN ('rising','falling','steady')),
    activity_score INTEGER NOT NULL CHECK(activity_score BETWEEN 1 AND 10),
    notes_fr TEXT,
    notes_en TEXT
);

-- Runtime tables (créées par schema.sql mais pas dans le seed bundle)
CREATE TABLE IF NOT EXISTS weather_cache (
    cache_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_prefs (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS data_sync_meta (
    table_name TEXT PRIMARY KEY,
    last_synced_at TEXT,
    last_etag TEXT,
    row_count INTEGER
);
