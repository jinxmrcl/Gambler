from discord.ext import commands

from utils.economy import StaticView

TRACKED_COMMANDS = ("work", "crime", "slut", "rob")


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
        hustle = self.bot.get_cog("Hustle")
        lines = []

        if hustle:
            for cmd_name in TRACKED_COMMANDS:
                cmd = getattr(hustle, cmd_name, None)
                if not cmd:
                    continue
                retry_after = cmd.get_cooldown_retry_after(ctx)
                if retry_after > 0:
                    lines.append(f"`{cmd_name}` — ready in {format_duration(retry_after)}")
                else:
                    lines.append(f"`{cmd_name}` — ✅ ready now")

        view = StaticView("⏱️ Your Cooldowns", "\n".join(lines) or "No cooldown-based commands found.")
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Cooldowns(bot))
