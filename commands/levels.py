import datetime
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.economy import StaticView, fmt
from utils.level_badges import level_badge
from utils.level_math import level_from_total_xp, MAX_LEVEL
from utils.role_blacklist import is_blacklisted

log = logging.getLogger("gambler")

XP_MIN_PER_MESSAGE = 15
XP_MAX_PER_MESSAGE = 25
XP_MESSAGE_COOLDOWN = datetime.timedelta(seconds=60)

VOICE_TICK_MINUTES = 1
VOICE_XP_MIN_PER_TICK = 6
VOICE_XP_MAX_PER_TICK = 10

LEVEL_UP_GOLD_PER_LEVEL = 500


def _is_eligible(member: discord.Member) -> bool:
    return not is_blacklisted(member)


def _progress_bar(current: int, total: int, length: int = 12) -> str:
    if total <= 0:
        filled = length
    else:
        filled = max(0, min(length, round(length * current / total)))
    return "█" * filled + "░" * (length - filled)


def _format_duration(seconds: int) -> str:
    hours, rem = divmod(int(seconds), 3600)
    minutes = rem // 60
    return f"{hours}h {minutes}m"


def _eligible_voice_members(guild: discord.Guild) -> list[discord.Member]:
    eligible = []
    for channel in guild.voice_channels:
        if channel == guild.afk_channel:
            continue
        members = [m for m in channel.members if not m.bot and _is_eligible(m)]
        if len(members) < 2:
            continue
        for member in members:
            state = member.voice
            if state is None or state.self_deaf or state.deaf:
                continue
            eligible.append(member)
    return eligible


class LevelSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_tick_loop.start()

    def cog_unload(self):
        self.voice_tick_loop.cancel()

    async def _get_multiplier(self, guild_id: int, now: datetime.datetime) -> float:
        boost = await self.bot.db.get_level_boost(guild_id)
        if boost is None:
            return 1.0
        multiplier, expires_at = boost
        if now >= expires_at:
            return 1.0
        return multiplier

    @tasks.loop(minutes=VOICE_TICK_MINUTES)
    async def voice_tick_loop(self):
        try:
            await self._voice_tick()
        except Exception:
            log.exception("[level-system] voice tick failed")

    @voice_tick_loop.before_loop
    async def before_voice_tick_loop(self):
        await self.bot.wait_until_ready()

    async def _voice_tick(self):
        seconds = VOICE_TICK_MINUTES * 60
        now = datetime.datetime.utcnow()
        for guild in self.bot.guilds:
            multiplier = await self._get_multiplier(guild.id, now)
            for member in _eligible_voice_members(guild):
                gained = round(random.randint(VOICE_XP_MIN_PER_TICK, VOICE_XP_MAX_PER_TICK) * multiplier)
                after_xp = await self.bot.db.add_level_voice(guild.id, member.id, gained, seconds)
                before_level, _, _ = level_from_total_xp(after_xp - gained)
                after_level, _, _ = level_from_total_xp(after_xp)

                if after_level > before_level:
                    await self._handle_level_up(member, after_level)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if not _is_eligible(message.author):
            return

        guild_id = message.guild.id
        user_id = message.author.id
        now = datetime.datetime.utcnow()

        last_at = await self.bot.db.get_level_last_xp_at(guild_id, user_id)
        if last_at is not None and now - last_at < XP_MESSAGE_COOLDOWN:
            return

        multiplier = await self._get_multiplier(guild_id, now)
        gained = round(random.randint(XP_MIN_PER_MESSAGE, XP_MAX_PER_MESSAGE) * multiplier)
        after_xp = await self.bot.db.add_level_xp(guild_id, user_id, gained, now)
        before_level, _, _ = level_from_total_xp(after_xp - gained)
        after_level, _, _ = level_from_total_xp(after_xp)

        if after_level > before_level:
            await self._handle_level_up(message.author, after_level, channel=message.channel)

    async def _handle_level_up(
        self, member: discord.Member, new_level: int,
        channel: discord.abc.Messageable | None = None,
    ) -> None:
        if member.bot:
            return

        gold = LEVEL_UP_GOLD_PER_LEVEL * new_level
        try:
            await self.bot.db.ensure_user(member.id, self.bot.starting_balance)
            await self.bot.db.update_balance(member.id, gold)
        except Exception:
            log.exception("[level-system] failed to pay level-up gold to %s", member.id)
            gold = 0

        if channel is not None:
            badge = level_badge(new_level)
            body = f"{member.mention} reached **Level {new_level}**! {badge}".rstrip()
            if gold:
                body += f" +{fmt(gold)}"
            try:
                await channel.send(view=StaticView("⬆️ Level Up!", body, color=discord.Color.gold()))
            except discord.HTTPException:
                log.exception("[level-system] failed to announce level-up for %s", member.id)

    @app_commands.command(name="level", description="Shows your (or another member's) level and XP.")
    @app_commands.describe(user="Optional: check another member's level")
    async def level(self, interaction: discord.Interaction, user: discord.Member | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("This only works in a server.", ephemeral=True)
            return
        if user is not None and user.bot:
            await interaction.response.send_message("Bots don't earn levels.", ephemeral=True)
            return

        target = user or interaction.user
        xp = await self.bot.db.get_level_xp(interaction.guild.id, target.id)
        lvl, into_level, needed = level_from_total_xp(xp)
        bar = _progress_bar(into_level, needed)
        progress_line = "**Max level reached!**" if lvl >= MAX_LEVEL else f"{bar}  {into_level}/{needed} XP to next level"
        badge = level_badge(lvl)
        level_line = f"**Level {lvl}**" + (f" {badge}" if badge else "")

        body = f"{level_line}\n{progress_line}\nTotal XP: {xp:,}"
        await interaction.response.send_message(view=StaticView(f"📈 {target.display_name}'s Level", body))

    @app_commands.command(name="stats", description="Shows all-time level stats: XP breakdown and voice activity.")
    @app_commands.describe(user="Optional: check another member's stats")
    async def stats(self, interaction: discord.Interaction, user: discord.Member | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("This only works in a server.", ephemeral=True)
            return
        if user is not None and user.bot:
            await interaction.response.send_message("Bots don't have stats.", ephemeral=True)
            return

        target = user or interaction.user
        data = await self.bot.db.get_level_stats(interaction.guild.id, target.id)
        lvl, into_level, needed = level_from_total_xp(data["xp"])
        progress_line = "Max level reached!" if lvl >= MAX_LEVEL else f"{into_level:,}/{needed:,} XP to next level"
        badge = level_badge(lvl)
        level_line = f"**Level:** {lvl}" + (f" {badge}" if badge else "")

        body = (
            f"{level_line}  ({progress_line})\n"
            f"**Total XP:** {data['xp']:,}\n"
            f"**From messages:** {data['message_xp']:,} XP\n"
            f"**From voice:** {data['voice_xp']:,} XP\n"
            f"**Active VC time:** {_format_duration(data['vc_seconds'])}"
        )
        await interaction.response.send_message(view=StaticView(f"📊 {target.display_name}'s Stats", body))

    @app_commands.command(name="level-leaderboard", description="Shows the top members by level/XP in this server.")
    async def level_leaderboard(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("This only works in a server.", ephemeral=True)
            return

        rows = await self.bot.db.get_level_leaderboard(interaction.guild.id, limit=10)
        if not rows:
            await interaction.response.send_message("No one has earned any XP yet.")
            return

        lines = []
        for i, (user_id, xp) in enumerate(rows, start=1):
            lvl, _, _ = level_from_total_xp(xp)
            badge = level_badge(lvl)
            level_part = f"Level {lvl}" + (f" {badge}" if badge else "")
            lines.append(f"**#{i}** <@{user_id}> — {level_part} ({xp:,} XP)")

        body = "\n".join(lines)
        await interaction.response.send_message(view=StaticView("🏆 Level Leaderboard", body))

    @app_commands.command(name="level-givexp", description="[Admin] Give a member XP directly (can be negative to remove).")
    @app_commands.describe(user="Target member", amount="Amount of XP to grant (negative to remove)")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_givexp(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: app_commands.Range[int, -1_000_000, 1_000_000],
    ):
        if interaction.guild is None:
            await interaction.response.send_message("This only works in a server.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("Bots don't earn levels.", ephemeral=True)
            return

        before_xp = await self.bot.db.get_level_xp(interaction.guild.id, user.id)
        before_level, _, _ = level_from_total_xp(before_xp)

        after_xp = await self.bot.db.add_level_admin_xp(interaction.guild.id, user.id, amount)
        after_level, into_level, needed = level_from_total_xp(after_xp)

        if after_level > before_level:
            await self._handle_level_up(user, after_level, channel=interaction.channel)

        badge = level_badge(after_level)
        level_line = f"**Level {after_level}**" + (f" {badge}" if badge else "")
        progress_line = "Max level reached!" if after_level >= MAX_LEVEL else f"{into_level:,}/{needed:,} XP to next level"

        body = (
            f"Gave {user.mention} **{amount:,}** XP.\n"
            f"{level_line} ({progress_line})\nTotal XP: {after_xp:,}"
        )
        await interaction.response.send_message(
            view=StaticView("🛠️ XP Granted", body, color=discord.Color.blue())
        )

    @app_commands.command(name="level-boost", description="[Admin] Temporarily multiply XP gains for this server.")
    @app_commands.describe(multiplier="e.g. 1.5 for +50% XP", days="How many days the boost lasts")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_boost(
        self, interaction: discord.Interaction,
        multiplier: app_commands.Range[float, 0.1, 10.0], days: app_commands.Range[float, 0.05, 30.0],
    ):
        if interaction.guild is None:
            await interaction.response.send_message("This only works in a server.", ephemeral=True)
            return
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=days)
        await self.bot.db.set_level_boost(interaction.guild.id, multiplier, expires_at)
        await interaction.response.send_message(
            f"✅ XP gain is now **{multiplier}x** for the next **{days:g}** day(s) "
            f"(until {expires_at.strftime('%Y-%m-%d %H:%M UTC')})."
        )

    @app_commands.command(name="level-boost-clear", description="[Admin] End this server's active XP boost early.")
    @app_commands.checks.has_permissions(administrator=True)
    async def level_boost_clear(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("This only works in a server.", ephemeral=True)
            return
        cleared = await self.bot.db.clear_level_boost(interaction.guild.id)
        if cleared:
            await interaction.response.send_message("✅ XP boost cleared — back to normal rates.")
        else:
            await interaction.response.send_message("⚠️ There's no active XP boost.")

    @app_commands.command(name="level-badges", description="Previews the badge progression (every 10 levels).")
    async def level_badges(self, interaction: discord.Interaction):
        lines = []
        for lvl in range(10, MAX_LEVEL + 1, 10):
            badge = level_badge(lvl)
            lines.append(f"**Level {lvl}** {badge}".rstrip())
        body = "Every level from 1-150 has its own unique badge — here's a preview:\n\n" + "\n".join(lines)
        await interaction.response.send_message(view=StaticView("🎖️ Level Badges", body))


async def setup(bot: commands.Bot):
    await bot.add_cog(LevelSystem(bot))
