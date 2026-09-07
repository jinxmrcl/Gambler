import json
import logging
from pathlib import Path

import discord
from discord.ext import commands

log = logging.getLogger("gambler")

AUDITED_COGS = {"Admin", "Settings"}

LOGGED_GUILDS_PATH = Path(__file__).resolve().parent.parent / "data" / "logged_guild_invites.json"


def _read_logged_guild_ids() -> set[int]:
    try:
        return set(json.loads(LOGGED_GUILDS_PATH.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _write_logged_guild_ids(ids: set[int]) -> None:
    try:
        LOGGED_GUILDS_PATH.write_text(json.dumps(sorted(ids)), encoding="utf-8")
    except Exception:
        pass


async def invite_for(guild: discord.Guild) -> str | None:
    channel = guild.system_channel
    if channel is None or not channel.permissions_for(guild.me).create_instant_invite:
        channel = next(
            (c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite),
            None,
        )
    if channel is None:
        return None
    try:
        invite = await channel.create_invite(max_age=0, max_uses=0, unique=False, reason="Server log entry")
        return invite.url
    except (discord.Forbidden, discord.HTTPException):
        return None


class AuditLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._backfill_done = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self._backfill_done:
            return
        self._backfill_done = True

        logged = _read_logged_guild_ids()
        newly_logged = set()
        for guild in self.bot.guilds:
            if guild.id in logged:
                continue
            invite_url = await invite_for(guild)
            invite_text = f"\n{invite_url}" if invite_url else "\n*(no invite - missing permission)*"
            await self.bot._send_to_servers_log(
                title="📥 Server",
                description=f"**{guild.name}** (`{guild.id}`)\n{guild.member_count} members{invite_text}",
                color=0x57F287,
            )
            newly_logged.add(guild.id)

        if newly_logged:
            _write_logged_guild_ids(logged | newly_logged)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if not ctx.cog or ctx.cog.qualified_name not in AUDITED_COGS:
            return
        args_text = ", ".join(f"{k}={v}" for k, v in ctx.kwargs.items()) or "—"
        guild_text = f"{ctx.guild.name} (`{ctx.guild.id}`)" if ctx.guild else "DM"
        await self.bot._send_to_action_log(
            title="🛠️ Admin action",
            description=(
                f"**Command:** `{ctx.command.qualified_name}`\n"
                f"**By:** {ctx.author} (`{ctx.author.id}`)\n"
                f"**Server:** {guild_text}\n"
                f"**Args:** {args_text}"
            ),
            color=0x5865F2,
        )

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        log.info("[guilds] joined %s (%s) - %d members", guild.name, guild.id, guild.member_count)
        invite_url = await invite_for(guild)
        invite_text = f"\n{invite_url}" if invite_url else "\n*(no invite - missing permission)*"
        await self.bot._send_to_servers_log(
            title="📥 Joined a server",
            description=f"**{guild.name}** (`{guild.id}`)\n{guild.member_count} members{invite_text}",
            color=0x57F287,
        )
        logged = _read_logged_guild_ids()
        logged.add(guild.id)
        _write_logged_guild_ids(logged)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        log.info("[guilds] removed from %s (%s)", guild.name, guild.id)
        await self.bot._send_to_servers_log(
            title="📤 Left a server",
            description=f"**{guild.name}** (`{guild.id}`)",
            color=0xED4245,
        )
        logged = _read_logged_guild_ids()
        logged.discard(guild.id)
        _write_logged_guild_ids(logged)


async def setup(bot: commands.Bot):
    await bot.add_cog(AuditLog(bot))
