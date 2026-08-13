from dataclasses import dataclass

# Percentage bonuses (not flat) so gear stays meaningful across the whole
# 1-1500 level range instead of being trivial once base stats outgrow it.
# tier: (badge, atk/def/hp %, price)
TIERS = [
    ("common", "⚪", 0.03, 200),
    ("rare", "🔵", 0.07, 800),
    ("epic", "🟣", 0.14, 2500),
    ("legendary", "🟠", 0.24, 7000),
    ("mythic", "🔴", 0.38, 20_000),
    ("ancient", "🌈", 0.55, 60_000),
]

WEAPON_NAMES = {
    "common": ("wooden_sword", "🗡️ Wooden Sword"),
    "rare": ("iron_sword", "⚔️ Iron Sword"),
    "epic": ("flame_blade", "🔥 Flame Blade"),
    "legendary": ("dragon_fang", "🐉 Dragon Fang"),
    "mythic": ("void_reaver", "🌌 Void Reaver"),
    "ancient": ("worldbreaker", "☄️ Worldbreaker"),
}
ARMOR_NAMES = {
    "common": ("leather_armor", "🥋 Leather Armor"),
    "rare": ("chainmail", "⛓️ Chainmail"),
    "epic": ("plate_armor", "🛡️ Plate Armor"),
    "legendary": ("dragonscale_armor", "🐲 Dragonscale Armor"),
    "mythic": ("void_plate", "🌌 Void Plate"),
    "ancient": ("worldguard", "☄️ Worldguard Aegis"),
}


@dataclass(frozen=True)
class EquipmentDef:
    key: str
    name: str
    slot: str  # "weapon" or "armor"
    tier: str
    price: int
    atk_pct: float = 0.0
    def_pct: float = 0.0
    hp_pct: float = 0.0


def _build() -> dict[str, EquipmentDef]:
    items: dict[str, EquipmentDef] = {}
    for tier, badge, pct, price in TIERS:
        w_key, w_name = WEAPON_NAMES[tier]
        items[w_key] = EquipmentDef(w_key, f"{badge} {w_name}", "weapon", tier, price, atk_pct=pct)
        a_key, a_name = ARMOR_NAMES[tier]
        items[a_key] = EquipmentDef(a_key, f"{badge} {a_name}", "armor", tier, price, def_pct=pct * 0.7, hp_pct=pct)
    return items


EQUIPMENT: dict[str, EquipmentDef] = _build()


def equipment_multipliers(weapon_key: str | None, armor_key: str | None) -> dict:
    atk_pct = def_pct = hp_pct = 0.0
    for key in (weapon_key, armor_key):
        item = EQUIPMENT.get(key) if key else None
        if item:
            atk_pct += item.atk_pct
            def_pct += item.def_pct
            hp_pct += item.hp_pct
    return {"atk": 1 + atk_pct, "def": 1 + def_pct, "hp": 1 + hp_pct}
