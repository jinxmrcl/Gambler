from dataclasses import dataclass


@dataclass(frozen=True)
class ConsumableDef:
    key: str
    name: str
    price: int
    heal_pct: float


CONSUMABLES: dict[str, ConsumableDef] = {
    "minor_potion": ConsumableDef("minor_potion", "🧪 Minor Potion", 400, 0.25),
    "greater_potion": ConsumableDef("greater_potion", "⚗️ Greater Potion", 4_000, 0.55),
    "superior_potion": ConsumableDef("superior_potion", "💠 Superior Potion", 18_000, 1.0),
}
