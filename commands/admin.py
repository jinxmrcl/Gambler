import datetime
import json
from pathlib import Path
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from events.audit_log import invite_for
from rpg.consumables import CONSUMABLES
from rpg.equipment import EQUIPMENT
from rpg.leveling import MAX_LEVEL, apply_xp, xp_for_level
from rpg.primordial import PRIMORDIAL_BASES, describe_affixes, generate_primordial_drop
from utils.checks import admin_only, app_admin_only
from utils.economy import StaticView, fmt, game_container
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

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PERMANENT_SHIELD_UNTIL = datetime.datetime(9999, 1, 1)


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024


class AnnounceConfirmView(discord.ui.LayoutView):
    def __init__(self, author_id: int, targets: list[tuple[discord.Guild, discord.abc.Messageable]], message: str):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.targets = targets
        self.message_text = message
        self.done = False

        names = "\n".join(f"• {g.name}" for g, _c in targets) or "*none*"
        self.container, self.text = game_container(
            "📢 Confirm Announcement",
            f"{message}\n\n-# Will post to **{len(targets)}** server(s):\n{names}",
        )
        self.confirm_button = discord.ui.Button(style=discord.ButtonStyle.success, label="Send", emoji="✅")
        self.cancel_button = discord.ui.Button(style=discord.ButtonStyle.danger, label="Cancel", emoji="❌")
        self.confirm_button.callback = self.confirm
        self.cancel_button.callback = self.cancel
        row = discord.ui.ActionRow()
        row.add_item(self.confirm_button)
        row.add_item(self.cancel_button)
        self.container.add_item(row)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the person who ran this command can confirm it.", ephemeral=True)
            return False
        return True

    async def confirm(self, interaction: discord.Interaction):
        if self.done:
            return
        self.done = True
        self.confirm_button.disabled = True
        self.cancel_button.disabled = True
        self.text.content = "## 📢 Confirm Announcement\n📤 Sending..."
        await interaction.response.edit_message(view=self)

        sent = 0
        for _guild, channel in self.targets:
            try:
                view = StaticView("📢 Announcement", self.message_text, color=discord.Color.blurple())
                await limited_send(channel, view=view)
                sent += 1
            except (discord.HTTPException, discord.Forbidden):
                pass

        self.text.content = f"## 📢 Confirm Announcement\n✅ Sent to **{sent}**/{len(self.targets)} server(s)."
        await interaction.message.edit(view=self)
        self.stop()

    async def cancel(self, interaction: discord.Interaction):
        if self.done:
            return
        self.done = True
        self.confirm_button.disabled = True
        self.cancel_button.disabled = True
        self.text.content = "## 📢 Confirm Announcement\n❌ Cancelled — nothing was sent."
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        if self.done:
            return
        self.done = True
        self.confirm_button.disabled = True
        self.cancel_button.disabled = True


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="addmoney", description="[Admin] Add or remove balance.")
    @app_commands.describe(user="Target user", amount="Amount (negative to remove)")
    @admin_only()
    async def addmoney(self, ctx: commands.Context, user: discord.User, amount: int):
        if ctx.guild is None:
            await ctx.send("⚠️ This command is only available in a server.")
            return
        db = await self.bot.db.get(ctx.guild.id)
        await db.ensure_user(user.id, self.bot.starting_balance)
        new_balance = await db.update_balance(user.id, amount)

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
        if ctx.guild is None:
            await ctx.send("⚠️ This command is only available in a server.")
            return
        db = await self.bot.db.get(ctx.guild.id)
        await db.ensure_user(user.id, self.bot.starting_balance)
        await db.set_balance(user.id, amount)

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
        if ctx.guild is None:
            await ctx.send("⚠️ This command is only available in a server.")
            return
        db = await self.bot.db.get(ctx.guild.id)
        count = await db.give_all_users(amount)

        view = StaticView(
            "🛠️ Balance Given to Everyone",
            f"{fmt(amount)} applied to **{count}** player(s).",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="resetuser", description="[Admin] Fully reset a user's data in this server.")
    @app_commands.describe(user="Target user")
    @admin_only()
    async def resetuser(self, ctx: commands.Context, user: discord.User):
        if ctx.guild is None:
            await ctx.send("⚠️ This command is available only in a server.")
            return

        db = await self.bot.db.get(ctx.guild.id)
        await db.ensure_user(user.id, self.bot.starting_balance)
        await db.reset_user(user.id, self.bot.starting_balance)

        view = StaticView(
            "🛠️ User Reset",
            f"{user.mention} was reset to {fmt(self.bot.starting_balance)} in this server "
            f"(bank, inventory, and statistics cleared).",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="permcooldown", description="[Admin] Toggle a permanent cooldown bypass for a user."
    )
    @app_commands.describe(user="Target user", enabled="Enable or disable the bypass")
    @admin_only()
    async def permcooldown(self, ctx: commands.Context, user: discord.User, enabled: bool):
        if ctx.guild is None:
            await ctx.send("⚠️ This command is only available in a server.")
            return
        db = await self.bot.db.get(ctx.guild.id)
        await db.ensure_user(user.id, self.bot.starting_balance)
        await db.set_cooldown_bypass(user.id, enabled)
        if enabled:
            await db.clear_cooldowns(user.id, ("work", "crime", "slut", "rob", "duel"))

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
        if ctx.guild is None:
            await ctx.send("⚠️ This command is only available in a server.")
            return
        db = await self.bot.db.get(ctx.guild.id)
        await db.ensure_user(user.id, self.bot.starting_balance)

        if enabled:
            await db.set_protected_until(user.id, PERMANENT_SHIELD_UNTIL)
        else:
            current = await db.get_protected_until(user.id)
            if current == PERMANENT_SHIELD_UNTIL:
                await db.set_protected_until(user.id, None)

        state = "enabled" if enabled else "disabled"
        view = StaticView(
            "🛠️ Permanent Shield Toggled",
            f"Permanent rob shield is now **{state}** for {user.mention}.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.command(name="botstatus", hidden=True)
    @commands.is_owner()
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

    @commands.command(name="servers", hidden=True)
    @commands.is_owner()
    async def servers(self, ctx: commands.Context):
        lines = []
        for guild in self.bot.guilds:
            invite_url = await invite_for(guild)
            invite_text = invite_url or "*(no invite - missing permission)*"
            lines.append(f"**{guild.name}** (`{guild.id}`) — {guild.member_count} members\n{invite_text}")

        body = "\n\n".join(lines) if lines else "*Not in any servers.*"
        for chunk_start in range(0, len(body), 3800):
            chunk = body[chunk_start : chunk_start + 3800]
            await ctx.send(view=StaticView(f"🌐 Servers ({len(self.bot.guilds)})", chunk, color=discord.Color.blue()))

    @commands.command(name="restart", hidden=True)
    @commands.is_owner()
    async def restart(self, ctx: commands.Context):
        view = StaticView(
            "<:restart:1537866127835799572> Restarting",
            "Restarting the bot now — back online in a few seconds.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)
        await self.bot.graceful_shutdown()

    @commands.command(name="announce", hidden=True)
    @commands.is_owner()
    async def announce(self, ctx: commands.Context, *, message: str):
        targets: list[tuple[discord.Guild, discord.abc.Messageable]] = []
        for guild in self.bot.guilds:
            db = await self.bot.db.get(guild.id)
            channel_id = await db.get_updates_channel()
            if not channel_id:
                continue
            channel = guild.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except (discord.HTTPException, discord.Forbidden):
                    continue
            targets.append((guild, channel))

        if not targets:
            await ctx.send("⚠️ No server has an updates channel configured (`/set-updateschannel`).")
            return

        view = AnnounceConfirmView(ctx.author.id, targets, message)
        await ctx.send(view=view)

    @commands.command(name="guildinfo", hidden=True)
    @commands.is_owner()
    async def guildinfo(self, ctx: commands.Context, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(guild_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                await ctx.send(f"⚠️ Couldn't find/fetch guild `{guild_id}`.")
                return

        owner_text = f"`{guild.owner_id}`"
        if guild.owner_id:
            try:
                owner_user = self.bot.get_user(guild.owner_id) or await self.bot.fetch_user(guild.owner_id)
                owner_text = f"{owner_user} (`{guild.owner_id}`)"
            except discord.HTTPException:
                pass

        lines = [
            f"**ID:** `{guild.id}`",
            f"**Owner:** {owner_text}",
            f"**Members:** {guild.member_count}",
            f"**Created:** {discord.utils.format_dt(guild.created_at, 'F')}",
        ]
        view = StaticView(f"🌐 {guild.name}", "\n".join(lines), color=discord.Color.blue())
        await ctx.send(view=view)

    @commands.command(name="sync", hidden=True)
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        synced = await self.bot.tree.sync()
        await ctx.send(f"✅ Synced {len(synced)} slash command(s).")

    @commands.command(name="dbsize", hidden=True)
    @commands.is_owner()
    async def dbsize(self, ctx: commands.Context):
        guilds_dir = DATA_DIR / "guilds"
        if not guilds_dir.exists():
            await ctx.send("⚠️ No guild databases found yet.")
            return

        entries = sorted(
            ((f.stem, f.stat().st_size) for f in guilds_dir.glob("*.db")),
            key=lambda e: e[1],
            reverse=True,
        )
        lines = [f"`{guild_id}`: {_fmt_size(size)}" for guild_id, size in entries]
        total = sum(size for _guild_id, size in entries)
        data_total = sum(f.stat().st_size for f in DATA_DIR.rglob("*") if f.is_file())
        lines.append(f"\n**Total (guild DBs):** {_fmt_size(total)}")
        lines.append(f"**Total (data/ folder):** {_fmt_size(data_total)}")

        body = "\n".join(lines) if entries else "*No guild databases found.*"
        view = StaticView("💾 Database Sizes", body, color=discord.Color.blue())
        await ctx.send(view=view)

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
        if interaction.guild is None:
            await interaction.response.send_message("⚠️ This command is only available in a server.")
            return
        db = await self.bot.db.get(interaction.guild.id)
        character = await db.get_character(user.id)
        if not character:
            await interaction.response.send_message(f"⚠️ {user.mention} doesn't have a character yet.")
            return

        capped_xp = min(xp, max(xp_for_level(level) - 1, 0)) if level < MAX_LEVEL else 0
        await db.set_character_level(user.id, level, capped_xp)

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
        if interaction.guild is None:
            await interaction.response.send_message("⚠️ This command is only available in a server.")
            return
        db = await self.bot.db.get(interaction.guild.id)
        character = await db.get_character(user.id)
        if not character:
            await interaction.response.send_message(f"⚠️ {user.mention} doesn't have a character yet.")
            return

        new_level, new_xp, levels_gained = apply_xp(character["level"], character["xp"], amount)
        await db.set_character_level(user.id, new_level, new_xp)

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
        if interaction.guild is None:
            await interaction.response.send_message("⚠️ This command is only available in a server.")
            return

        db = await self.bot.db.get(interaction.guild.id)
        character = await db.get_character(user.id)
        if not character:
            await interaction.response.send_message(f"⚠️ {user.mention} doesn't have a character yet.")
            return

        await db.add_rpg_item(user.id, item, quantity)
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
        if interaction.guild is None:
            await interaction.response.send_message("⚠️ This command is only available in a server.")
            return
        db = await self.bot.db.get(interaction.guild.id)
        character = await db.get_character(user.id)
        if not character:
            await interaction.response.send_message(f"⚠️ {user.mention} doesn't have a character yet.")
            return

        affixes = generate_primordial_drop(slot)
        item_id = await db.add_primordial_item(user.id, slot, json.dumps(affixes))
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
