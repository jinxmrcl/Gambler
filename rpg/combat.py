import random
from dataclasses import dataclass

MAX_ROUNDS = 30


@dataclass
class Fighter:
    name: str
    max_hp: int
    atk: int
    defense: int
    crit: float
    skill_key: str | None = None
    hp: int | None = None
    skill_used: bool = False

    def __post_init__(self):
        if self.hp is None:
            self.hp = self.max_hp


def _hit(attacker: Fighter, defender: Fighter) -> tuple[int, bool, str]:
    is_crit = random.random() < attacker.crit
    dmg_mult = 1.0
    pen_mult = 1.0
    note = ""

    if not attacker.skill_used:
        if attacker.skill_key == "arcane_bolt":
            is_crit = True
            attacker.skill_used = True
            note = " ✨*Arcane Bolt!*"
        elif attacker.skill_key == "backstab":
            dmg_mult *= 1.5
            attacker.skill_used = True
            note = " 🗡️*Backstab!*"
        elif attacker.skill_key == "piercing_shot":
            pen_mult = 0.35
            attacker.skill_used = True
            note = " 🏹*Piercing Shot!*"

    if attacker.skill_key == "bloodlust" and attacker.hp / attacker.max_hp < 0.5:
        dmg_mult *= 1.15
        note += " 🪓*Bloodlust!*"

    variance = random.uniform(0.85, 1.15)
    raw = attacker.atk * variance * dmg_mult * (2.0 if is_crit else 1.0)

    defense_mult = 1.0
    if not defender.skill_used and defender.skill_key == "shield_wall":
        defense_mult = 2.0
        defender.skill_used = True
        note += " 🛡️*Shield Wall!*"

    effective_defense = defender.defense * defense_mult * pen_mult
    mitigation = effective_defense / (effective_defense + attacker.atk)
    dmg = max(1, round(raw * (1 - mitigation)))
    defender.hp = max(0, defender.hp - dmg)

    if attacker.skill_key == "life_drain" and not attacker.skill_used:
        healed = dmg * 2 // 3
        attacker.hp = min(attacker.max_hp, attacker.hp + healed)
        attacker.skill_used = True
        note += f" 💀*Life Drain!* (+{healed} HP)"

    return dmg, is_crit, note


def _maybe_heal(fighter: Fighter, log: list[str]) -> None:
    if (
        fighter.skill_key == "lay_on_hands"
        and not fighter.skill_used
        and fighter.hp > 0
        and fighter.hp / fighter.max_hp < 0.3
    ):
        healed = int(fighter.max_hp * 0.2)
        fighter.hp = min(fighter.max_hp, fighter.hp + healed)
        fighter.skill_used = True
        log.append(f"✨ *Lay on Hands!* {fighter.name} heals **{healed}** HP ({fighter.hp}/{fighter.max_hp} HP)")


def simulate(fighter_a: Fighter, fighter_b: Fighter) -> dict:
    log: list[str] = []
    turn = 0
    while fighter_a.hp > 0 and fighter_b.hp > 0 and turn < MAX_ROUNDS * 2:
        attacker, defender = (fighter_a, fighter_b) if turn % 2 == 0 else (fighter_b, fighter_a)
        dmg, crit, note = _hit(attacker, defender)
        marker = "💥" if crit else "⚔️"
        suffix = " **(CRIT!)**" if crit else ""
        log.append(
            f"{marker} {attacker.name} hits {defender.name} for **{dmg}**{suffix}{note} "
            f"({defender.hp}/{defender.max_hp} HP)"
        )
        _maybe_heal(defender, log)
        turn += 1

    if fighter_a.hp > 0 and fighter_b.hp <= 0:
        winner = fighter_a
    elif fighter_b.hp > 0 and fighter_a.hp <= 0:
        winner = fighter_b
    else:
        winner = None

    return {"log": log, "winner": winner, "fighter_a": fighter_a, "fighter_b": fighter_b}
