from discord.ext import commands

from utils.economy import StaticView

COG_TITLES = {
    "Economy": "💰 Economy",
    "Hustle": "💼 Earn Money",
    "Bank": "🏦 Bank",
    "Shop": "🛒 Shop & Inventory",
    "Trade": "🤝 Trading",
    "Marriage": "💍 Marriage",
    "Lottery": "🎟️ Lottery",
    "Profile": "📊 Statistics",
    "Cooldowns": "⏱️ Cooldowns",
    "Blackjack": "🃏 Blackjack",
    "Mines": "💣 Mines",
    "Hilo": "🎴 Hilo",
    "Plinko": "🔴 Plinko",
    "Limbo": "🚀 Limbo",
    "Keno": "🔢 Keno",
    "Slots": "🎰 Slots",
    "Roulette": "🎡 Roulette",
    "Dice": "🎲 Dice",
    "Coinflip": "🪙 Coinflip",
    "RPGCharacter": "⚔️ RPG: Character",
    "RPGDungeon": "🗺️ RPG: Dungeons",
    "RPGShop": "🛒 RPG: Equipment",
    "RPGArena": "🏆 RPG: Arena",
    "Settings": "🛠️ Server Settings",
    "Admin": "🛠️ Admin",
}


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Shows all available commands.")
    async def help(self, ctx: commands.Context):
        sections = []
        for cog_name, title in COG_TITLES.items():
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            entries = [
                f"`{self.bot.prefix}{c.name}` — {c.description or c.help or '—'}" for c in cog.get_commands()
            ]
            if entries:
                sections.append(f"**{title}**\n" + "\n".join(entries))

        body = (
            "\n\n".join(sections)
            + "\n\n-# All commands also work as slash commands (e.g. `/balance`)."
        )
        view = StaticView("📖 Command Overview", body)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
