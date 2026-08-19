import discord
from discord import ui
from discord.ext import commands

from utils.economy import game_container
from utils.ratelimit import limited_edit

CATEGORIES = [
    ("economy", "💰 Economy", ["Economy"], discord.Color.gold()),
    ("earn", "💼 Earn Money", ["Hustle", "Cooldowns"], discord.Color.green()),
    ("bank", "🏦 Bank", ["Bank"], discord.Color.teal()),
    ("shop", "🛒 Shop & Inventory", ["Shop"], discord.Color.orange()),
    ("trade", "🤝 Trading", ["Trade"], discord.Color.blurple()),
    ("marriage", "💍 Marriage", ["Marriage"], discord.Color.fuchsia()),
    ("lottery", "🎟️ Lottery", ["Lottery"], discord.Color.purple()),
    ("stats", "📊 Statistics", ["Profile"], discord.Color.blue()),
    ("games", "🎰 Casino Games", [
        "Blackjack", "Mines", "Hilo", "Plinko", "Limbo", "Keno", "Slots", "Roulette", "Dice", "Coinflip",
        "Scratchcard", "HorseRace", "Baccarat", "Crash",
    ], discord.Color.red()),
    ("rpg_character", "⚔️ RPG: Character", ["RPGCharacter"], discord.Color.dark_green()),
    ("rpg_dungeon", "🗺️ RPG: Dungeons", ["RPGDungeon"], discord.Color.dark_gold()),
    ("rpg_shop", "🛡️ RPG: Equipment", ["RPGShop"], discord.Color.dark_teal()),
    ("rpg_arena", "🏆 RPG: Arena", ["RPGArena"], discord.Color.dark_red()),
    ("settings", "🛠️ Server Settings", ["Settings"], discord.Color.greyple()),
    ("admin", "🔧 Admin", ["Admin"], discord.Color.dark_grey()),
]

SECTIONS = [
    ("💵 Economy & Social", ["economy", "earn", "bank", "shop", "trade", "marriage", "lottery", "stats"]),
    ("🎰 Casino Games", ["games"]),
    ("⚔️ RPG", ["rpg_character", "rpg_dungeon", "rpg_shop", "rpg_arena"]),
    ("🔧 Server & Admin", ["settings", "admin"]),
]

OVERVIEW_COLOR = discord.Color.blurple()


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
        for key, label, cog_names, _color in CATEGORIES:
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

        self.container, self.text = game_container("📖 Command Overview", self._overview_body(), color=OVERVIEW_COLOR)
        self.select = CategorySelect(bot)
        row = ui.ActionRow()
        row.add_item(self.select)
        self.container.add_item(row)
        self.add_item(self.container)

    def _overview_body(self) -> str:
        by_key = {key: (label, cog_names) for key, label, cog_names, _color in CATEGORIES}
        total = sum(len(_category_commands(self.bot, cogs)) for _, _, cogs, _color in CATEGORIES)

        lines = [f"**{total} commands** — pick a category from the dropdown below.", ""]
        for section_title, keys in SECTIONS:
            section_lines = []
            for key in keys:
                label, cog_names = by_key[key]
                count = len(_category_commands(self.bot, cog_names))
                if count:
                    section_lines.append(f"{label} — {count}")
            if section_lines:
                lines.append(f"**{section_title}**")
                lines.extend(section_lines)
                lines.append("")

        lines.append("-# All commands also work as slash commands (e.g. `/balance`).")
        return "\n".join(lines)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Run `/help` yourself to browse commands.", ephemeral=True)
            return False
        return True

    async def show_category(self, interaction: discord.Interaction, key: str):
        label, cog_names, color = next((label, cogs, color) for k, label, cogs, color in CATEGORIES if k == key)
        cmds = _category_commands(self.bot, cog_names)

        entries = [f"`{self.bot.prefix}{c.name}` — {c.description or c.help or '—'}" for c in cmds]
        body = "\n".join(entries) if entries else "No commands in this category."
        body += "\n\n-# All commands also work as slash commands (e.g. `/balance`)."

        self.text.content = f"## {label}\n{body}"
        self.container.accent_colour = color
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
