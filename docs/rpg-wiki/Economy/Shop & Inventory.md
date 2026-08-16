# Shop & Inventory

Two purchasable items (`utils/items.py`):

- **🛡️ Rob Shield** — 750 gold — protects from `/rob` for
  2 hours
- **⏩ Cooldown Reset** — 1000 gold — instantly
  resets [work/crime/slut/rob](Hustle%20%28Work%20Crime%20Rob%29.md) and duel cooldowns

Both items can only be **used** (not bought) up to twice in any rolling 24-hour window,
tracked per item independently — owning more than 2 doesn't bypass the limit, they just
sit in inventory until the window resets.

Commands: `/shop`, `/buy`, `/inventory`, `/use`, `/gift`. See [Economy Overview](Economy%20Overview.md).
