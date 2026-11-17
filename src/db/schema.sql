-- ============================================================================
-- UAE Pizza Price Intelligence - SQLite Schema
-- ============================================================================
-- Enforces data integrity, historical price preservation, source evidence,
-- UAE emirates coverage, and multi-channel ordering methods.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1. COMPETITORS
-- Master record of pizza brands being tracked (e.g. Pizza Hut UAE benchmark, Domino's, etc.)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS competitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    website_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- 2. EMIRATES
-- The seven UAE emirates: Dubai, Abu Dhabi, Sharjah, Ajman, RAK, Fujairah, UAQ.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS emirates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name_en TEXT NOT NULL UNIQUE,
    name_ar TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- ----------------------------------------------------------------------------
-- 3. LOCATIONS AND BRANCHES
-- Physical store locations across the 7 emirates for branch-specific pricing.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_id INTEGER NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    emirate_id INTEGER NOT NULL REFERENCES emirates(id) ON DELETE RESTRICT,
    branch_name TEXT NOT NULL,
    area TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    phone TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- 4. ORDERING CHANNELS
-- The 4 required ordering channels:
--  - Direct delivery
--  - Direct pickup / takeaway
--  - Dine-in
--  - Third-party delivery apps
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ordering_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE CHECK (code IN ('direct_delivery', 'direct_pickup', 'dine_in', 'third_party_delivery')),
    name TEXT NOT NULL,
    description TEXT
);

-- ----------------------------------------------------------------------------
-- 5. ORDERING PLATFORMS
-- Specific ordering interfaces (Direct Website, Talabat, Careem, Deliveroo, Noon Food)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ordering_platforms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    channel_id INTEGER NOT NULL REFERENCES ordering_channels(id) ON DELETE RESTRICT,
    platform_type TEXT NOT NULL CHECK (platform_type IN ('direct_web', 'direct_app', 'aggregator', 'in_store')),
    base_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- ----------------------------------------------------------------------------
-- 6. PRODUCT CATEGORIES
-- Groupings (e.g. Pizzas, Sides, Desserts, Beverages, Meal Deals)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0
);

-- ----------------------------------------------------------------------------
-- 7. PRODUCTS
-- Specific menu items belonging to a competitor.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_id INTEGER NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    normalized_name TEXT,
    description TEXT,
    is_vegetarian INTEGER NOT NULL DEFAULT 0 CHECK (is_vegetarian IN (0, 1)),
    is_spicy INTEGER NOT NULL DEFAULT 0 CHECK (is_spicy IN (0, 1)),
    image_url TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- 8. PRODUCT SIZES AND VARIANTS
-- Exact size/crust specifications for accurate cross-brand matching.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product_variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    size_name TEXT NOT NULL,
    normalized_size TEXT NOT NULL CHECK (normalized_size IN ('personal', 'small', 'medium', 'large', 'xlarge', 'other')),
    crust_type TEXT NOT NULL DEFAULT 'Standard',
    diameter_inches REAL,
    slices_count INTEGER,
    serves_count INTEGER,
    sku TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- 9. RESEARCH RUNS
-- Audit log of research sessions, automated scrapes, and collection status.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uuid TEXT NOT NULL UNIQUE,
    competitor_id INTEGER REFERENCES competitors(id) ON DELETE SET NULL,
    platform_id INTEGER REFERENCES ordering_platforms(id) ON DELETE SET NULL,
    channel_id INTEGER REFERENCES ordering_channels(id) ON DELETE SET NULL,
    emirate_id INTEGER REFERENCES emirates(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'started' CHECK (status IN ('started', 'running', 'completed', 'failed', 'partial')),
    items_extracted INTEGER NOT NULL DEFAULT 0,
    items_verified INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    error_message TEXT,
    notes TEXT
);

-- ----------------------------------------------------------------------------
-- 10. EVIDENCE RECORDS
-- Verifiable proof of captured prices (screenshots, HTML snapshots, JSON payloads).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES research_runs(id) ON DELETE SET NULL,
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('screenshot', 'html_snapshot', 'json_payload', 'url_log', 'api_response')),
    source_url TEXT NOT NULL,
    file_path TEXT,
    file_hash_sha256 TEXT,
    http_status INTEGER,
    captured_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT
);

-- ----------------------------------------------------------------------------
-- 11. HISTORICAL PRICE OBSERVATIONS
-- Core price audit log. NEVER stores fake data.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS price_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES research_runs(id) ON DELETE SET NULL,
    competitor_id INTEGER NOT NULL REFERENCES competitors(id) ON DELETE RESTRICT,
    product_variant_id INTEGER NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    emirate_id INTEGER NOT NULL REFERENCES emirates(id) ON DELETE RESTRICT,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    channel_id INTEGER NOT NULL REFERENCES ordering_channels(id) ON DELETE RESTRICT,
    platform_id INTEGER NOT NULL REFERENCES ordering_platforms(id) ON DELETE RESTRICT,
    original_price REAL NOT NULL CHECK (original_price >= 0),
    currency TEXT NOT NULL DEFAULT 'AED' CHECK (currency = 'AED'),
    promo_price REAL CHECK (promo_price IS NULL OR promo_price >= 0),
    promo_description TEXT,
    delivery_fee REAL DEFAULT 0.0 CHECK (delivery_fee IS NULL OR delivery_fee >= 0),
    min_order_amount REAL DEFAULT 0.0 CHECK (min_order_amount IS NULL OR min_order_amount >= 0),
    source_url TEXT NOT NULL,
    evidence_id INTEGER REFERENCES evidence_records(id) ON DELETE SET NULL,
    verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN ('verified', 'needs_review', 'unverified', 'unavailable')),
    collected_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT
);

-- ----------------------------------------------------------------------------
-- 12. PROMOTIONS AND DISCOUNTS
-- Deals, vouchers, combos, and time-limited offers with source URLs.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_id INTEGER NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
    platform_id INTEGER REFERENCES ordering_platforms(id) ON DELETE SET NULL,
    emirate_id INTEGER REFERENCES emirates(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT,
    promo_type TEXT NOT NULL CHECK (promo_type IN ('bogo', 'combo', 'percentage_discount', 'flat_discount', 'free_item', 'meal_deal', 'other')),
    discount_amount REAL,
    discount_percentage REAL,
    promo_code TEXT,
    terms_conditions TEXT,
    starts_at TEXT,
    ends_at TEXT,
    source_url TEXT NOT NULL,
    evidence_id INTEGER REFERENCES evidence_records(id) ON DELETE SET NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- INDEXES FOR HIGH-PERFORMANCE ANALYTICS & AUDITING
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_price_observations_competitor_date
    ON price_observations(competitor_id, collected_at);

CREATE INDEX IF NOT EXISTS idx_price_observations_emirate
    ON price_observations(emirate_id);

CREATE INDEX IF NOT EXISTS idx_price_observations_channel_platform
    ON price_observations(channel_id, platform_id);

CREATE INDEX IF NOT EXISTS idx_price_observations_variant
    ON price_observations(product_variant_id);

CREATE INDEX IF NOT EXISTS idx_price_observations_verification
    ON price_observations(verification_status);

CREATE INDEX IF NOT EXISTS idx_locations_competitor_emirate
    ON locations(competitor_id, emirate_id);

CREATE INDEX IF NOT EXISTS idx_product_variants_lookup
    ON product_variants(product_id, normalized_size);

CREATE INDEX IF NOT EXISTS idx_research_runs_uuid
    ON research_runs(run_uuid);

CREATE INDEX IF NOT EXISTS idx_evidence_run
    ON evidence_records(run_id);

CREATE INDEX IF NOT EXISTS idx_promotions_competitor
    ON promotions(competitor_id, is_active);
