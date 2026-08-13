import datetime

from discord.ext import commands

from utils.economy import StaticView

TRACKED_COMMANDS = ("work", "crime", "slut", "rob", "dungeon")


def format_duration(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


class Cooldowns(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="cooldowns", description="Shows your remaining cooldowns.")
    async def cooldowns(self, ctx: commands.Context):
        now = datetime.datetime.utcnow()
        lines = []

        for cmd_name in TRACKED_COMMANDS:
            until = await self.bot.db.get_cooldown(ctx.author.id, cmd_name)
            if until and until > now:
                lines.append(f"`{cmd_name}` — ready in {format_duration((until - now).total_seconds())}")
            else:
                lines.append(f"`{cmd_name}` — ✅ ready now")

        view = StaticView("⏱️ Your Cooldowns", "\n".join(lines) or "No cooldown-based commands found.")
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Cooldowns(bot))
