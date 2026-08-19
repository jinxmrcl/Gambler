import random
from dataclasses import dataclass

MAX_ROUNDS = 30
DIVINE_SHIELD_PCT = 0.20


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
    lifesteal_pct: float = 0.0
    crit_dmg_bonus: float = 0.0
    reflect_pct: float = 0.0
    shield_hp: int = 0
    damage_reduction_pct: float = 0.0
    block_chance: float = 0.0

    def __post_init__(self):
        if self.hp is None:
            self.hp = self.max_hp
        if self.skill_key == "divine_shield":
            self.shield_hp = int(self.max_hp * DIVINE_SHIELD_PCT)


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
            dmg_mult *= 1.7
            attacker.skill_used = True
            note = " 🗡️*Backstab!*"
        elif attacker.skill_key == "piercing_shot":
            pen_mult = 0.15
            attacker.skill_used = True
            note = " 🏹*Piercing Shot!*"

    if attacker.skill_key == "bloodlust" and attacker.hp / attacker.max_hp < 0.5:
        dmg_mult *= 1.15
        note += " 🪓*Bloodlust!*"

    if attacker.skill_key == "enrage" and attacker.hp / attacker.max_hp < 0.25:
        dmg_mult *= 1.5
        if not attacker.skill_used:
            attacker.skill_used = True
            note += " 😡*Enraged!*"

    if attacker.skill_key == "double_strike" and random.random() < 0.3:
        dmg_mult *= 2.0
        note += " ⚡*Double Strike!*"

    variance = random.uniform(0.85, 1.15)
    crit_mult = 2.0 + attacker.crit_dmg_bonus
    raw = attacker.atk * variance * dmg_mult * (crit_mult if is_crit else 1.0)

    defense_mult = 1.0
    if not defender.skill_used and defender.skill_key == "shield_wall":
        defense_mult = 2.0
        defender.skill_used = True
        note += " 🛡️*Shield Wall!*"

    effective_defense = defender.defense * defense_mult * pen_mult
    mitigation = effective_defense / (effective_defense + attacker.atk)
    dmg = max(1, round(raw * (1 - mitigation)))

    if defender.block_chance > 0 and random.random() < defender.block_chance:
        dmg = 0
        note += " 🛡️*Blocked!*"
    elif defender.damage_reduction_pct:
        dmg = max(1, round(dmg * (1 - defender.damage_reduction_pct)))

    if defender.shield_hp > 0:
        absorbed = min(defender.shield_hp, dmg)
        defender.shield_hp -= absorbed
        remaining = dmg - absorbed
        defender.hp = max(0, defender.hp - remaining)
        if absorbed:
            note += f" 🔵*Shield absorbs {absorbed}!*" + (" *(shattered)*" if defender.shield_hp == 0 else "")
    else:
        defender.hp = max(0, defender.hp - dmg)

    if attacker.skill_key == "life_drain" and not attacker.skill_used:
        healed = dmg * 2 // 3
        attacker.hp = min(attacker.max_hp, attacker.hp + healed)
        attacker.skill_used = True
        note += f" 💀*Life Drain!* (+{healed} HP)"

    if attacker.lifesteal_pct:
        healed = int(dmg * attacker.lifesteal_pct)
        if healed:
            attacker.hp = min(attacker.max_hp, attacker.hp + healed)
            note += f" 🩸*Lifesteal!* (+{healed} HP)"

    if defender.reflect_pct:
        reflected = int(dmg * defender.reflect_pct)
        if reflected:
            attacker.hp = max(0, attacker.hp - reflected)
            note += f" 🔮*Reflect!* ({reflected} dmg back)"

    if defender.skill_key == "counterstrike" and defender.hp > 0 and random.random() < 0.25:
        counter_variance = random.uniform(0.85, 1.15)
        counter_raw = defender.atk * counter_variance * 0.5
        counter_mitigation = attacker.defense / (attacker.defense + defender.atk)
        counter_dmg = max(1, round(counter_raw * (1 - counter_mitigation)))
        attacker.hp = max(0, attacker.hp - counter_dmg)
        note += f" 🥋*Counterstrike!* ({counter_dmg} dmg back)"

    return dmg, is_crit, note


def _maybe_heal(fighter: Fighter, log: list[str]) -> None:
    if (
        fighter.skill_key == "divine_shield"
        and not fighter.skill_used
        and fighter.hp > 0
        and fighter.hp / fighter.max_hp < 0.3
    ):
        healed = int(fighter.max_hp * 0.15)
        fighter.hp = min(fighter.max_hp, fighter.hp + healed)
        fighter.skill_used = True
        log.append(f"✨ *Lay on Hands!* {fighter.name} heals **{healed}** HP ({fighter.hp}/{fighter.max_hp} HP)")

    if fighter.skill_key == "regrowth" and fighter.hp > 0:
        missing = fighter.max_hp - fighter.hp
        healed = int(missing * 0.04)
        if healed:
            fighter.hp = min(fighter.max_hp, fighter.hp + healed)
            log.append(f"🌿 *Regrowth!* {fighter.name} recovers **{healed}** HP ({fighter.hp}/{fighter.max_hp} HP)")


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

    timed_out = winner is None and fighter_a.hp > 0 and fighter_b.hp > 0
    return {
        "log": log, "winner": winner, "fighter_a": fighter_a, "fighter_b": fighter_b, "timed_out": timed_out,
    }


def simulate_team(party: list[Fighter], monster: Fighter) -> dict:
    log: list[str] = []
    round_num = 0

    def alive(fighters: list[Fighter]) -> list[Fighter]:
        return [f for f in fighters if f.hp > 0]

    while alive(party) and monster.hp > 0 and round_num < MAX_ROUNDS:
        for member in alive(party):
            if monster.hp <= 0:
                break
            dmg, crit, note = _hit(member, monster)
            marker = "💥" if crit else "⚔️"
            suffix = " **(CRIT!)**" if crit else ""
            log.append(
                f"{marker} {member.name} hits {monster.name} for **{dmg}**{suffix}{note} "
                f"({monster.hp}/{monster.max_hp} HP)"
            )
        if monster.hp <= 0:
            break

        living = alive(party)
        if not living:
            break
        target = random.choice(living)
        dmg, crit, note = _hit(monster, target)
        marker = "💥" if crit else "⚔️"
        suffix = " **(CRIT!)**" if crit else ""
        log.append(
            f"{marker} {monster.name} hits {target.name} for **{dmg}**{suffix}{note} "
            f"({target.hp}/{target.max_hp} HP)"
        )
        _maybe_heal(target, log)

        round_num += 1

    won = monster.hp <= 0
    timed_out = not won and bool(alive(party))
    return {"log": log, "won": won, "party": party, "monster": monster, "timed_out": timed_out}
