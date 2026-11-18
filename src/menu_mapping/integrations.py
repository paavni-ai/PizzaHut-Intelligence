"""Known permitted integration paths; no third-party API calls are made here."""

PLATFORM_ACCESS = {
    "direct_web": {
        "method": "Existing public Pizza Hut UAE collector and source-backed manual imports",
        "status": "Public website collection is implemented in the existing project; source may block or change.",
        "requires_credentials": False,
    },
    "talabat": {
        "method": "Official restaurant Partner API / POS integration",
        "status": "Partner onboarding and credentials are required; this is not a public competitor-menu API.",
        "requires_credentials": True,
        "url": "https://integration.talabat.com/en/documentation/",
    },
    "deliveroo": {
        "method": "Official Partner Platform Menu API",
        "status": "Partner authentication and site/brand access are required; no anonymous competitor endpoint is used.",
        "requires_credentials": True,
        "url": "https://api-docs.deliveroo.com/docs/menu-api-overview",
    },
    "noon_food": {
        "method": "Manual CSV/XLSX import pending an approved partner feed",
        "status": "No suitable public UAE menu API was verified for this implementation.",
        "requires_credentials": True,
    },
}


def integration_for(platform_code: str) -> dict[str, object]:
    return PLATFORM_ACCESS.get(platform_code, {
        "method": "Approved feed, partner API, or manual CSV/XLSX import",
        "status": "No connector is configured for this platform.",
        "requires_credentials": True,
    })
