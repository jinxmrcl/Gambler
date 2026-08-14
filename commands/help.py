import discord
from discord import ui
from discord.ext import commands

from utils.economy import game_container
from utils.ratelimit import limited_edit

CATEGORIES = [
    ("economy", "💰 Economy", ["Economy"]),
    ("earn", "💼 Earn Money", ["Hustle", "Cooldowns"]),
    ("bank", "🏦 Bank", ["Bank"]),
    ("shop", "🛒 Shop & Inventory", ["Shop"]),
    ("trade", "🤝 Trading", ["Trade"]),
    ("marriage", "💍 Marriage", ["Marriage"]),
    ("lottery", "🎟️ Lottery", ["Lottery"]),
    ("stats", "📊 Statistics", ["Profile"]),
    ("games", "🎰 Casino Games", [
        "Blackjack", "Mines", "Hilo", "Plinko", "Limbo", "Keno", "Slots", "Roulette", "Dice", "Coinflip",
        "Scratchcard", "HorseRace", "Baccarat",
    ]),
    ("rpg_character", "⚔️ RPG: Character", ["RPGCharacter"]),
    ("rpg_dungeon", "🗺️ RPG: Dungeons", ["RPGDungeon"]),
    ("rpg_shop", "🛡️ RPG: Equipment", ["RPGShop"]),
    ("rpg_arena", "🏆 RPG: Arena", ["RPGArena"]),
    ("settings", "🛠️ Server Settings", ["Settings"]),
    ("admin", "🔧 Admin", ["Admin"]),
]


def _category_commands(bot: commands.Bot, cog_names: list[str]) -> list[commands.Command]:
    result = []
    for cog_name in cog_names:
        cog = bot.get_cog(cog_name)
        if cog:
            result.extend(cog.get_commands())
    return result


class CategorySelect(ui.Select):
    def __init__(self, bot: commands.Bot):
        options = []
        for key, label, cog_names in CATEGORIES:
            count = len(_category_commands(bot, cog_names))
            if count:
                options.append(discord.SelectOption(label=label, value=key, description=f"{count} command(s)"))

        super().__init__(placeholder="Choose a category...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_category(interaction, self.values[0])


class HelpView(ui.LayoutView):
    def __init__(self, bot: commands.Bot, author_id: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.author_id = author_id
        self.message: discord.Message | None = None

        self.container, self.text = game_container("📖 Command Overview", self._overview_body())
        self.select = CategorySelect(bot)
        row = ui.ActionRow()
        row.add_item(self.select)
        self.container.add_item(row)
        self.add_item(self.container)

    def _overview_body(self) -> str:
        lines = ["Pick a category from the dropdown below to see its commands.", ""]
        for key, label, cog_names in CATEGORIES:
            count = len(_category_commands(self.bot, cog_names))
            if count:
                lines.append(f"{label} — {count} command(s)")
        lines.append("")
        lines.append("-# All commands also work as slash commands (e.g. `/balance`).")
        return "\n".join(lines)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Run `/help` yourself to browse commands.", ephemeral=True)
            return False
        return True

    async def show_category(self, interaction: discord.Interaction, key: str):
        label, cog_names = next((label, cogs) for k, label, cogs in CATEGORIES if k == key)
        cmds = _category_commands(self.bot, cog_names)

        entries = [f"`{self.bot.prefix}{c.name}` — {c.description or c.help or '—'}" for c in cmds]
        body = "\n".join(entries) if entries else "No commands in this category."
        body += "\n\n-# All commands also work as slash commands (e.g. `/balance`)."

        self.text.content = f"## {label}\n{body}"
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        self.select.disabled = True
        if self.message:
            await limited_edit(self.message, view=self)


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Shows all available commands.")
    async def help(self, ctx: commands.Context):
        view = HelpView(self.bot, ctx.author.id)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
