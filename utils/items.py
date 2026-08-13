import datetime

SHIELD_DURATION = datetime.timedelta(hours=2)

ITEMS = {
    "shield": {
        "name": "🛡️ Rob Shield",
        "description": f"Protects you from `rob` for {int(SHIELD_DURATION.total_seconds() // 3600)} hours.",
        "price": 750,
    },
    "cooldown_reset": {
        "name": "⏩ Cooldown Reset",
        "description": "Instantly resets the cooldowns of work/crime/slut/rob.",
        "price": 1000,
    },
}
