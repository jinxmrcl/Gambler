import datetime
import json
import os
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from rpg.consumables import CONSUMABLES
from rpg.equipment import EQUIPMENT
from rpg.leveling import MAX_LEVEL, apply_xp, xp_for_level
from rpg.primordial import PRIMORDIAL_BASES, describe_affixes, generate_primordial_drop
from utils.checks import admin_only, app_admin_only
from utils.economy import StaticView, fmt
from utils.ratelimit import get_status as ratelimit_status, limited_send

PrimordialSlotKey = Literal["weapon", "armor", "accessory"]

RPGITEM_AUTOCOMPLETE_LIMIT = 25


def _rpgitem_name(key: str) -> str:
    if key in EQUIPMENT:
        return EQUIPMENT[key].name
    if key in CONSUMABLES:
        return CONSUMABLES[key].name
    return key


async def _rpgitem_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    current = current.lower()
    keys = list(EQUIPMENT.keys()) + list(CONSUMABLES.keys())
    matches = [k for k in keys if current in k.lower() or current in _rpgitem_name(k).lower()]
    return [app_commands.Choice(name=_rpgitem_name(k), value=k) for k in matches[:RPGITEM_AUTOCOMPLETE_LIMIT]]

_raw_updates_channel = os.getenv("UPDATES_CHANNEL_ID", "1538079078186229760")
UPDATES_CHANNEL_ID = int(_raw_updates_channel) if _raw_updates_channel.isdigit() else None

PERMANENT_SHIELD_UNTIL = datetime.datetime(9999, 1, 1)


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="addmoney", description="[Admin] Add or remove balance.")
    @app_commands.describe(user="Target user", amount="Amount (negative to remove)")
    @admin_only()
    async def addmoney(self, ctx: commands.Context, user: discord.User, amount: int):
        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)
        new_balance = await self.bot.db.update_balance(user.id, amount)

        view = StaticView(
            "🛠️ Balance Changed",
            f"{fmt(amount)} applied to {user.mention}.\nNew balance: {fmt(new_balance)}",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="setbalance", description="[Admin] Set a user's balance exactly.")
    @app_commands.describe(user="Target user", amount="New balance")
    @admin_only()
    async def setbalance(self, ctx: commands.Context, user: discord.User, amount: commands.Range[int, 0]):
        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)
        await self.bot.db.set_balance(user.id, amount)

        view = StaticView(
            "🛠️ Balance Set",
            f"Set {user.mention}'s balance to {fmt(amount)}.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="giveall", description="[Admin] Give (or take) balance from every player at once.")
    @app_commands.describe(amount="Amount to give every player (negative to remove, floored at 0)")
    @admin_only()
    async def giveall(self, ctx: commands.Context, amount: int):
        count = await self.bot.db.give_all_users(amount)

        view = StaticView(
            "🛠️ Balance Given to Everyone",
            f"{fmt(amount)} applied to **{count}** player(s).",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="resetuser", description="[Admin] Clear a user's bank savings in this server.")
    @app_commands.describe(user="Target user")
    @admin_only()
    async def resetuser(self, ctx: commands.Context, user: discord.User):
        if ctx.guild is None:
            await ctx.send("⚠️ This command is available only in a server.")
            return

        await self.bot.db.reset_guild_bank(ctx.guild.id, user.id)

        view = StaticView(
            "🛠️ Server Bank Reset",
            f"{user.mention}'s bank savings were cleared for this server only.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="permcooldown", description="[Admin] Toggle a permanent cooldown bypass for a user."
    )
    @app_commands.describe(user="Target user", enabled="Enable or disable the bypass")
    @admin_only()
    async def permcooldown(self, ctx: commands.Context, user: discord.User, enabled: bool):
        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)
        await self.bot.db.set_cooldown_bypass(user.id, enabled)
        if enabled:
            await self.bot.db.clear_cooldowns(user.id, ("work", "crime", "slut", "rob", "duel"))

        state = "enabled" if enabled else "disabled"
        view = StaticView(
            "🛠️ Cooldown Bypass Toggled",
            f"Permanent cooldown bypass is now **{state}** for {user.mention}.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="permshield", description="[Admin] Toggle a permanent rob shield for a user."
    )
    @app_commands.describe(user="Target user", enabled="Enable or disable the shield")
    @admin_only()
    async def permshield(self, ctx: commands.Context, user: discord.User, enabled: bool):
        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)

        if enabled:
            await self.bot.db.set_protected_until(user.id, PERMANENT_SHIELD_UNTIL)
        else:
            current = await self.bot.db.get_protected_until(user.id)
            if current == PERMANENT_SHIELD_UNTIL:
                await self.bot.db.set_protected_until(user.id, None)

        state = "enabled" if enabled else "disabled"
        view = StaticView(
            "🛠️ Permanent Shield Toggled",
            f"Permanent rob shield is now **{state}** for {user.mention}.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="botstatus", description="[Admin] Shows gateway latency and rate-limit health.")
    @admin_only()
    async def botstatus(self, ctx: commands.Context):
        rl = ratelimit_status()
        lines = [
            f"**Gateway latency:** {self.bot.latency * 1000:.0f}ms",
            f"**Gateway rate-limited:** {'⚠️ yes' if self.bot.is_ws_ratelimited() else '✅ no'}",
            f"**Edit budget:** {rl['edit_tokens']} / {rl['edit_rate']} tokens",
            f"**Send budget:** {rl['send_tokens']} / {rl['send_rate']} tokens",
            f"**Tracked channels / messages:** {rl['tracked_channels']} / {rl['tracked_messages']}",
        ]
        view = StaticView("📡 Bot Status", "\n".join(lines), color=discord.Color.blue())
        await ctx.send(view=view)

    @commands.hybrid_command(name="restart", description="[Admin] Restart the bot process.")
    @admin_only()
    async def restart(self, ctx: commands.Context):
        view = StaticView(
            "<:restart:1537866127835799572> Restarting",
            "Restarting the bot now — back online in a few seconds.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)
        await self.bot.graceful_shutdown()

    @commands.hybrid_command(name="announce", description="[Admin] Post an announcement to the updates channel.")
    @app_commands.describe(message="The announcement text")
    @admin_only()
    async def announce(self, ctx: commands.Context, *, message: str):
        if not UPDATES_CHANNEL_ID:
            await ctx.send("⚠️ UPDATES_CHANNEL_ID is not configured.")
            return

        channel = self.bot.get_channel(UPDATES_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(UPDATES_CHANNEL_ID)
            except discord.HTTPException:
                await ctx.send("⚠️ Couldn't find the updates channel.")
                return

        view = StaticView("📢 Announcement", message, color=discord.Color.blurple())
        await limited_send(channel, view=view)

        await ctx.send("✅ Announcement posted.")

    @app_commands.command(name="rpgsetlevel", description="[Admin] Set a player's RPG level (and optionally XP).")
    @app_commands.describe(user="Target user", level="New level (1-1500)", xp="XP toward the next level (default: 0)")
    @app_admin_only()
    async def rpgsetlevel(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        level: app_commands.Range[int, 1, MAX_LEVEL],
        xp: app_commands.Range[int, 0] = 0,
    ):
        character = await self.bot.db.get_character(user.id)
        if not character:
            await interaction.response.send_message(f"⚠️ {user.mention} doesn't have a character yet.")
            return

        capped_xp = min(xp, max(xp_for_level(level) - 1, 0)) if level < MAX_LEVEL else 0
        await self.bot.db.set_character_level(user.id, level, capped_xp)

        view = StaticView(
            "🛠️ Level Set",
            f"Set {user.mention}'s RPG level to **{level}** (XP: {capped_xp}).",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(
        name="rpggivexp", description="[Admin] Give a player XP directly, applying level-ups automatically."
    )
    @app_commands.describe(user="Target user", amount="Amount of XP to grant")
    @app_admin_only()
    async def rpggivexp(self, interaction: discord.Interaction, user: discord.User, amount: app_commands.Range[int, 1]):
        character = await self.bot.db.get_character(user.id)
        if not character:
            await interaction.response.send_message(f"⚠️ {user.mention} doesn't have a character yet.")
            return

        new_level, new_xp, levels_gained = apply_xp(character["level"], character["xp"], amount)
        await self.bot.db.set_character_level(user.id, new_level, new_xp)

        level_note = f" — **{levels_gained}** level-up{'s' if levels_gained != 1 else ''}! 🎉" if levels_gained else ""
        xp_line = f"XP: {new_xp} / {xp_for_level(new_level)}" if new_level < MAX_LEVEL else "MAX LEVEL"

        view = StaticView(
            "🛠️ XP Granted",
            f"Gave {user.mention} **{amount:,}** XP{level_note}\nNow **Level {new_level}** — {xp_line}",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpggive", description="[Admin] Give a player a piece of equipment for free.")
    @app_commands.describe(user="Target user", item="Which item to give", quantity="How many (default: 1)")
    @app_commands.autocomplete(item=_rpgitem_autocomplete)
    @app_admin_only()
    async def rpggive(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        item: str,
        quantity: app_commands.Range[int, 1, 99] = 1,
    ):
        if item not in EQUIPMENT and item not in CONSUMABLES:
            await interaction.response.send_message(f"⚠️ Unknown item `{item}`.")
            return

        character = await self.bot.db.get_character(user.id)
        if not character:
            await interaction.response.send_message(f"⚠️ {user.mention} doesn't have a character yet.")
            return

        await self.bot.db.add_rpg_item(user.id, item, quantity)
        info = EQUIPMENT.get(item) or CONSUMABLES[item]
        followup = f"They can equip it with `/rpgequip {item}`." if item in EQUIPMENT else f"They can use it with `/rpguse {item}`."

        view = StaticView(
            "🛠️ Equipment Given",
            f"Gave {quantity}x {info.name} to {user.mention}.\n{followup}",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpggiveprimordial", description="[Admin] Spawn a ✨ Primordial item with freshly rolled affixes for a player.")
    @app_commands.describe(user="Target user", slot="Which slot to spawn a Primordial item for")
    @app_admin_only()
    async def rpggiveprimordial(self, interaction: discord.Interaction, user: discord.User, slot: PrimordialSlotKey):
        character = await self.bot.db.get_character(user.id)
        if not character:
            await interaction.response.send_message(f"⚠️ {user.mention} doesn't have a character yet.")
            return

        affixes = generate_primordial_drop(slot)
        item_id = await self.bot.db.add_primordial_item(user.id, slot, json.dumps(affixes))
        base_name = PRIMORDIAL_BASES[slot].name

        view = StaticView(
            "🛠️ Primordial Item Spawned",
            f"Gave {user.mention} a {base_name} (`#{item_id}`) — {describe_affixes(affixes)}.\n"
            f"They can equip it with `/rpgequipprimordial {item_id}`.",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
