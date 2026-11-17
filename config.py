"""
Global configuration for UAE Pizza Price Intelligence platform.
"""
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
EVIDENCE_DIR = DATA_DIR / "evidence"
EXPORTS_DIR = DATA_DIR / "exports"
DEFAULT_DB_PATH = DATA_DIR / "pizza_intelligence.db"

# Currency
CURRENCY_CODE = "AED"

# The Seven Emirates of the United Arab Emirates
UAE_EMIRATES = [
    {"code": "DXB", "name_en": "Dubai", "name_ar": "دبي", "display_order": 1},
    {"code": "AUH", "name_en": "Abu Dhabi", "name_ar": "أبوظبي", "display_order": 2},
    {"code": "SHJ", "name_en": "Sharjah", "name_ar": "الشارقة", "display_order": 3},
    {"code": "AJM", "name_en": "Ajman", "name_ar": "عجمان", "display_order": 4},
    {"code": "RAK", "name_en": "Ras Al Khaimah", "name_ar": "رأس الخيمة", "display_order": 5},
    {"code": "FUJ", "name_en": "Fujairah", "name_ar": "الفجيرة", "display_order": 6},
    {"code": "UAQ", "name_en": "Umm Al Quwain", "name_ar": "أم القيوين", "display_order": 7},
]

# The 4 Required Ordering Channels
ORDERING_CHANNELS = [
    {
        "code": "direct_delivery",
        "name": "Direct Delivery",
        "description": "Orders placed directly with the restaurant for home delivery.",
    },
    {
        "code": "direct_pickup",
        "name": "Direct Pickup / Takeaway",
        "description": "Orders placed directly for in-store takeaway or pickup.",
    },
    {
        "code": "dine_in",
        "name": "Dine-in",
        "description": "Menu prices observed for in-restaurant dining.",
    },
    {
        "code": "third_party_delivery",
        "name": "Third-Party Delivery Apps",
        "description": "Orders placed via aggregator platforms (e.g. Talabat, Deliveroo, Careem).",
    },
]

# Ordering Platforms
ORDERING_PLATFORMS = [
    {"code": "direct_web", "name": "Direct Website", "platform_type": "direct_web", "base_url": None},
    {"code": "talabat", "name": "Talabat", "platform_type": "aggregator", "base_url": "https://www.talabat.com/uae"},
    {"code": "deliveroo", "name": "Deliveroo", "platform_type": "aggregator", "base_url": "https://deliveroo.ae"},
    {"code": "careem", "name": "Careem Food", "platform_type": "aggregator", "base_url": "https://www.careem.com"},
    {"code": "noon_food", "name": "Noon Food", "platform_type": "aggregator", "base_url": "https://food.noon.com"},
]

# Key UAE Competitors (Entities only - NEVER insert fake prices)
COMPETITORS = [
    {"code": "pizza_hut", "name": "Pizza Hut UAE", "website_url": "https://www.pizzahut.ae", "notes": "Benchmark brand"},
    {"code": "dominos", "name": "Domino's Pizza UAE", "website_url": "https://www.dominos.ae", "notes": "Primary delivery competitor"},
    {"code": "papa_johns", "name": "Papa John's UAE", "website_url": "https://www.papajohns.ae", "notes": "Major pizza chain"},
    {"code": "freedom_pizza", "name": "Freedom Pizza", "website_url": "https://freedompizza.ae", "notes": "Artisanal / local UAE competitor"},
]

# Verification Statuses
VERIFICATION_STATUSES = [
    "verified",       # Validated against genuine source evidence
    "needs_review",   # Potential anomaly or uncertain attribute match
    "unverified",     # Raw capture pending validation
    "unavailable",    # Item temporarily unavailable or branch out-of-service
]
