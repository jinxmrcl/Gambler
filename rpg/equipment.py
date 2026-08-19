from dataclasses import dataclass

SHIELD_CLASS_KEY = "paladin"

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

SHIELD_DR = {
    "common": 0.03,
    "rare": 0.05,
    "epic": 0.08,
    "legendary": 0.12,
    "mythic": 0.16,
    "ancient": 0.20,
}
SHIELD_BLOCK = {
    "common": 0.02,
    "rare": 0.04,
    "epic": 0.06,
    "legendary": 0.09,
    "mythic": 0.12,
    "ancient": 0.15,
}

TIER_LEVEL_THRESHOLDS = [
    (55, "ancient"),
    (35, "mythic"),
    (25, "legendary"),
    (16, "epic"),
    (8, "rare"),
    (1, "common"),
]


def recommended_tier_for_level(level: int) -> str:
    for threshold, tier in TIER_LEVEL_THRESHOLDS:
        if level >= threshold:
            return tier
    return "common"

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
SHIELD_NAMES = {
    "common": ("wooden_shield", "🪵 Wooden Shield"),
    "rare": ("iron_shield", "🔩 Iron Shield"),
    "epic": ("tower_shield", "🏰 Tower Shield"),
    "legendary": ("dragonbone_shield", "🐉 Dragonbone Shield"),
    "mythic": ("void_aegis", "🌌 Void Aegis"),
    "ancient": ("worldwarden", "☄️ Worldwarden"),
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
    dr_pct: float = 0.0
    block_pct: float = 0.0


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
        s_key, s_name = SHIELD_NAMES[tier]
        items[s_key] = EquipmentDef(
            s_key, f"{badge} {s_name}", "shield", tier, price,
            dr_pct=SHIELD_DR[tier], block_pct=SHIELD_BLOCK[tier],
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
    shield_key: str | None = None,
    shield_enchant: int = 0,
) -> dict:
    atk_pct = def_pct = hp_pct = crit_pct = dr_pct = block_pct = 0.0
    for key, enchant in (
        (weapon_key, weapon_enchant),
        (armor_key, armor_enchant),
        (accessory_key, accessory_enchant),
        (shield_key, shield_enchant),
    ):
        item = EQUIPMENT.get(key) if key else None
        if not item:
            continue
        bonus_add = ENCHANT_PCT_PER_LEVEL * enchant
        atk_pct += item.atk_pct + (bonus_add if item.atk_pct else 0)
        def_pct += item.def_pct + (bonus_add if item.def_pct else 0)
        hp_pct += item.hp_pct + (bonus_add if item.hp_pct else 0)
        crit_pct += item.crit_pct + (bonus_add if item.crit_pct else 0)
        dr_pct += item.dr_pct + (bonus_add if item.dr_pct else 0)
        block_pct += item.block_pct + (bonus_add if item.block_pct else 0)
    return {
        "atk": 1 + atk_pct, "def": 1 + def_pct, "hp": 1 + hp_pct, "crit_add": crit_pct,
        "dr_pct": dr_pct, "block_pct": block_pct,
    }
