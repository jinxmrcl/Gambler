import logging

import discord
from discord.ext import commands

log = logging.getLogger("gambler")

AUDITED_COGS = {"Admin", "Settings"}


class AuditLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
        await self.bot._send_to_servers_log(
            title="📥 Joined a server",
            description=f"**{guild.name}** (`{guild.id}`)\n{guild.member_count} members",
            color=0x57F287,
        )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        log.info("[guilds] removed from %s (%s)", guild.name, guild.id)
        await self.bot._send_to_servers_log(
            title="📤 Left a server",
            description=f"**{guild.name}** (`{guild.id}`)",
            color=0xED4245,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AuditLog(bot))
