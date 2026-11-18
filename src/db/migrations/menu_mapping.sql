-- Additive Menu Mapping & Price Comparison schema.
-- Existing observations, products, promotions, evidence and runs are untouched.
CREATE TABLE IF NOT EXISTS platform_menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_id INTEGER NOT NULL REFERENCES competitors(id) ON DELETE RESTRICT,
    platform_id INTEGER NOT NULL REFERENCES ordering_platforms(id) ON DELETE RESTRICT,
    emirate_id INTEGER NOT NULL REFERENCES emirates(id) ON DELETE RESTRICT,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    source_item_key TEXT NOT NULL,
    item_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    description TEXT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    size_name TEXT NOT NULL,
    normalized_size TEXT NOT NULL CHECK (normalized_size IN ('personal','small','medium','large','xlarge','other')),
    crust_type TEXT,
    ingredients TEXT,
    availability TEXT NOT NULL DEFAULT 'unknown' CHECK (availability IN ('available','unavailable','unknown')),
    source_url TEXT NOT NULL,
    evidence_id INTEGER REFERENCES evidence_records(id) ON DELETE SET NULL,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (competitor_id, platform_id, emirate_id, source_item_key)
);

CREATE TABLE IF NOT EXISTS menu_item_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_menu_item_id INTEGER NOT NULL REFERENCES platform_menu_items(id) ON DELETE CASCADE,
    product_variant_id INTEGER NOT NULL REFERENCES product_variants(id) ON DELETE RESTRICT,
    confidence_score REAL NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
    status TEXT NOT NULL DEFAULT 'suggested' CHECK (status IN ('suggested','approved','rejected')),
    matching_details TEXT,
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (platform_menu_item_id, product_variant_id)
);

CREATE TABLE IF NOT EXISTS menu_import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    research_run_id INTEGER NOT NULL UNIQUE REFERENCES research_runs(id) ON DELETE RESTRICT,
    file_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    file_content BLOB NOT NULL,
    imported_rows INTEGER NOT NULL DEFAULT 0 CHECK (imported_rows >= 0),
    imported_at TEXT NOT NULL,
    imported_by TEXT
);

CREATE TABLE IF NOT EXISTS menu_item_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_menu_item_id INTEGER NOT NULL REFERENCES platform_menu_items(id) ON DELETE RESTRICT,
    research_run_id INTEGER NOT NULL REFERENCES research_runs(id) ON DELETE RESTRICT,
    import_batch_id INTEGER REFERENCES menu_import_batches(id) ON DELETE SET NULL,
    price REAL CHECK (price IS NULL OR price >= 0),
    currency TEXT NOT NULL DEFAULT 'AED' CHECK (currency = 'AED'),
    availability TEXT NOT NULL CHECK (availability IN ('available','unavailable','unknown')),
    observed_at TEXT NOT NULL,
    source_url TEXT NOT NULL,
    evidence_id INTEGER REFERENCES evidence_records(id) ON DELETE SET NULL,
    verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN ('verified','needs_review','unverified','unavailable')),
    verified_by TEXT,
    verified_at TEXT,
    CHECK (availability <> 'available' OR price IS NOT NULL),
    UNIQUE (platform_menu_item_id, research_run_id)
);

CREATE TABLE IF NOT EXISTS menu_fee_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_id INTEGER NOT NULL REFERENCES competitors(id) ON DELETE RESTRICT,
    platform_id INTEGER NOT NULL REFERENCES ordering_platforms(id) ON DELETE RESTRICT,
    emirate_id INTEGER NOT NULL REFERENCES emirates(id) ON DELETE RESTRICT,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    research_run_id INTEGER NOT NULL REFERENCES research_runs(id) ON DELETE RESTRICT,
    delivery_fee REAL CHECK (delivery_fee IS NULL OR delivery_fee >= 0),
    service_fee REAL CHECK (service_fee IS NULL OR service_fee >= 0),
    small_order_fee REAL CHECK (small_order_fee IS NULL OR small_order_fee >= 0),
    packaging_fee REAL CHECK (packaging_fee IS NULL OR packaging_fee >= 0),
    other_fee REAL CHECK (other_fee IS NULL OR other_fee >= 0),
    minimum_order_amount REAL CHECK (minimum_order_amount IS NULL OR minimum_order_amount >= 0),
    observed_at TEXT NOT NULL,
    source_url TEXT NOT NULL,
    evidence_id INTEGER REFERENCES evidence_records(id) ON DELETE SET NULL,
    verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN ('verified','needs_review','unverified')),
    verified_by TEXT
);

CREATE TABLE IF NOT EXISTS promotion_terms (
    promotion_id INTEGER PRIMARY KEY REFERENCES promotions(id) ON DELETE CASCADE,
    promotion_type TEXT NOT NULL DEFAULT 'other' CHECK (promotion_type IN ('percentage_discount','fixed_discount','bogo','free_delivery','pizza_deal','meal_deal','combo_offer','platform_discount','minimum_spend','first_order','loyalty','other')),
    minimum_order_value REAL CHECK (minimum_order_value IS NULL OR minimum_order_value >= 0),
    maximum_discount REAL CHECK (maximum_discount IS NULL OR maximum_discount >= 0),
    last_verified_at TEXT,
    verified_by TEXT,
    verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN ('verified','needs_review','unverified')),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS promotion_weekdays (
    promotion_id INTEGER NOT NULL REFERENCES promotions(id) ON DELETE CASCADE,
    weekday INTEGER NOT NULL CHECK (weekday >= 0 AND weekday <= 6),
    starts_local_time TEXT,
    ends_local_time TEXT,
    PRIMARY KEY (promotion_id, weekday)
);

CREATE TABLE IF NOT EXISTS promotion_item_eligibility (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    promotion_id INTEGER NOT NULL REFERENCES promotions(id) ON DELETE CASCADE,
    product_variant_id INTEGER REFERENCES product_variants(id) ON DELETE CASCADE,
    platform_menu_item_id INTEGER REFERENCES platform_menu_items(id) ON DELETE CASCADE,
    CHECK ((product_variant_id IS NOT NULL AND platform_menu_item_id IS NULL) OR
           (product_variant_id IS NULL AND platform_menu_item_id IS NOT NULL)),
    UNIQUE (promotion_id, product_variant_id, platform_menu_item_id)
);

CREATE TABLE IF NOT EXISTS cart_comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor_id INTEGER NOT NULL REFERENCES competitors(id) ON DELETE RESTRICT,
    emirate_id INTEGER NOT NULL REFERENCES emirates(id) ON DELETE RESTRICT,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS cart_comparison_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comparison_id INTEGER NOT NULL REFERENCES cart_comparisons(id) ON DELETE CASCADE,
    product_variant_id INTEGER NOT NULL REFERENCES product_variants(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    customization_notes TEXT,
    customization_amount REAL NOT NULL DEFAULT 0 CHECK (customization_amount >= 0),
    UNIQUE (comparison_id, product_variant_id, customization_notes)
);

CREATE TABLE IF NOT EXISTS cart_platform_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comparison_id INTEGER NOT NULL REFERENCES cart_comparisons(id) ON DELETE CASCADE,
    platform_id INTEGER NOT NULL REFERENCES ordering_platforms(id) ON DELETE RESTRICT,
    quote_status TEXT NOT NULL CHECK (quote_status IN ('verified_checkout','estimate','unavailable','incomplete')),
    item_subtotal REAL CHECK (item_subtotal IS NULL OR item_subtotal >= 0),
    customization_total REAL CHECK (customization_total IS NULL OR customization_total >= 0),
    promotion_discount REAL CHECK (promotion_discount IS NULL OR promotion_discount >= 0),
    delivery_fee REAL CHECK (delivery_fee IS NULL OR delivery_fee >= 0),
    service_fee REAL CHECK (service_fee IS NULL OR service_fee >= 0),
    small_order_fee REAL CHECK (small_order_fee IS NULL OR small_order_fee >= 0),
    packaging_fee REAL CHECK (packaging_fee IS NULL OR packaging_fee >= 0),
    other_fee REAL CHECK (other_fee IS NULL OR other_fee >= 0),
    minimum_order_amount REAL CHECK (minimum_order_amount IS NULL OR minimum_order_amount >= 0),
    final_total REAL CHECK (final_total IS NULL OR final_total >= 0),
    observed_at TEXT NOT NULL,
    source_url TEXT,
    evidence_id INTEGER REFERENCES evidence_records(id) ON DELETE SET NULL,
    notes TEXT,
    UNIQUE (comparison_id, platform_id)
);

CREATE TABLE IF NOT EXISTS cart_quote_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id INTEGER NOT NULL REFERENCES cart_platform_quotes(id) ON DELETE CASCADE,
    comparison_item_id INTEGER NOT NULL REFERENCES cart_comparison_items(id) ON DELETE RESTRICT,
    platform_menu_item_id INTEGER REFERENCES platform_menu_items(id) ON DELETE SET NULL,
    unit_price REAL CHECK (unit_price IS NULL OR unit_price >= 0),
    customization_amount REAL NOT NULL DEFAULT 0 CHECK (customization_amount >= 0),
    promotion_discount REAL NOT NULL DEFAULT 0 CHECK (promotion_discount >= 0),
    availability TEXT NOT NULL CHECK (availability IN ('available','unavailable','unknown')),
    UNIQUE (quote_id, comparison_item_id)
);

CREATE INDEX IF NOT EXISTS idx_platform_menu_location ON platform_menu_items(competitor_id, platform_id, emirate_id, normalized_size);
CREATE INDEX IF NOT EXISTS idx_menu_matches_review ON menu_item_matches(status, platform_menu_item_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_menu_matches_one_approved ON menu_item_matches(platform_menu_item_id) WHERE status = 'approved';
CREATE INDEX IF NOT EXISTS idx_menu_prices_latest ON menu_item_prices(platform_menu_item_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_menu_fees_latest ON menu_fee_observations(competitor_id, platform_id, emirate_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_promotion_terms_status ON promotion_terms(verification_status, last_verified_at);
CREATE INDEX IF NOT EXISTS idx_cart_comparison_created ON cart_comparisons(competitor_id, created_at);
