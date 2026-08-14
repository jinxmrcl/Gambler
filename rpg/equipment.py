from dataclasses import dataclass

TIERS = [
    ("common", "⚪", 0.03, 200),
    ("rare", "🔵", 0.07, 800),
    ("epic", "🟣", 0.14, 2500),
    ("legendary", "🟠", 0.24, 7000),
    ("mythic", "🔴", 0.38, 20_000),
    ("ancient", "🌈", 0.55, 60_000),
]

ACCESSORY_CRIT = {
    "common": 0.02,
    "rare": 0.04,
    "epic": 0.07,
    "legendary": 0.10,
    "mythic": 0.14,
    "ancient": 0.20,
}

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
ACCESSORY_NAMES = {
    "common": ("lucky_charm", "🍀 Lucky Charm"),
    "rare": ("hawk_eye_ring", "💍 Hawk-Eye Ring"),
    "epic": ("assassins_pendant", "📿 Assassin's Pendant"),
    "legendary": ("phoenix_feather", "🪶 Phoenix Feather"),
    "mythic": ("void_sigil", "🌌 Void Sigil"),
    "ancient": ("crown_of_fate", "👑 Crown of Fate"),
}


@dataclass(frozen=True)
class EquipmentDef:
    key: str
    name: str
    slot: str
    tier: str
    price: int
    atk_pct: float = 0.0
    def_pct: float = 0.0
    hp_pct: float = 0.0
    crit_pct: float = 0.0


def _build() -> dict[str, EquipmentDef]:
    items: dict[str, EquipmentDef] = {}
    for tier, badge, pct, price in TIERS:
        w_key, w_name = WEAPON_NAMES[tier]
        items[w_key] = EquipmentDef(w_key, f"{badge} {w_name}", "weapon", tier, price, atk_pct=pct)
        a_key, a_name = ARMOR_NAMES[tier]
        items[a_key] = EquipmentDef(a_key, f"{badge} {a_name}", "armor", tier, price, def_pct=pct * 0.7, hp_pct=pct)
        acc_key, acc_name = ACCESSORY_NAMES[tier]
        items[acc_key] = EquipmentDef(
            acc_key, f"{badge} {acc_name}", "accessory", tier, price, crit_pct=ACCESSORY_CRIT[tier]
        )
    return items


EQUIPMENT: dict[str, EquipmentDef] = _build()

ENCHANT_MAX_LEVEL = 10
ENCHANT_PCT_PER_LEVEL = 0.01  # each level adds a flat +1 percentage point to that slot's stat(s)


def enchant_cost(item_key: str, current_level: int) -> int:
    """Gold cost to go from `current_level` to `current_level + 1` on this item."""
    item = EQUIPMENT[item_key]
    return int(item.price * 0.15 * (current_level + 1))


def equipment_multipliers(
    weapon_key: str | None,
    armor_key: str | None,
    accessory_key: str | None = None,
    weapon_enchant: int = 0,
    armor_enchant: int = 0,
    accessory_enchant: int = 0,
) -> dict:
    atk_pct = def_pct = hp_pct = crit_pct = 0.0
    for key, enchant in (
        (weapon_key, weapon_enchant),
        (armor_key, armor_enchant),
        (accessory_key, accessory_enchant),
    ):
        item = EQUIPMENT.get(key) if key else None
        if not item:
            continue
        bonus_add = ENCHANT_PCT_PER_LEVEL * enchant
        atk_pct += item.atk_pct + (bonus_add if item.atk_pct else 0)
        def_pct += item.def_pct + (bonus_add if item.def_pct else 0)
        hp_pct += item.hp_pct + (bonus_add if item.hp_pct else 0)
        crit_pct += item.crit_pct + (bonus_add if item.crit_pct else 0)
    return {"atk": 1 + atk_pct, "def": 1 + def_pct, "hp": 1 + hp_pct, "crit_add": crit_pct}
