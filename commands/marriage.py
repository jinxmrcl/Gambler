import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.economy import StaticView, game_container


class AcceptButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Accept 💍", emoji="✅")

    async def callback(self, interaction: discord.Interaction):
        await self.view.accept(interaction)


class DeclineButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="Decline", emoji="❌")

    async def callback(self, interaction: discord.Interaction):
        await self.view.decline(interaction)


class ProposalView(ui.LayoutView):
    def __init__(self, cog: "Marriage", proposer: discord.abc.User, target: discord.abc.User):
        super().__init__(timeout=120)
        self.cog = cog
        self.proposer = proposer
        self.target = target
        self.finished = False
        self.message: discord.Message | None = None

        self.container, self.text = game_container(
            "💍 Marriage Proposal",
            f"{proposer.mention} is proposing to {target.mention}!\n{target.mention}, do you accept?",
        )
        self.accept_button = AcceptButton()
        self.decline_button = DeclineButton()
        row = ui.ActionRow()
        row.add_item(self.accept_button)
        row.add_item(self.decline_button)
        self.container.add_item(row)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Only the person being proposed to can respond.", ephemeral=True)
            return False
        return True

    def _disable_buttons(self):
        self.accept_button.disabled = True
        self.decline_button.disabled = True

    async def accept(self, interaction: discord.Interaction):
        if self.finished:
            return
        self.finished = True
        self._disable_buttons()

        if await self.cog.bot.db.get_marriage(self.proposer.id) is not None:
            self.text.content = f"## 💍 Marriage Proposal\n⚠️ {self.proposer.mention} is already married."
            self.container.accent_colour = discord.Color.red()
            await interaction.response.edit_message(view=self)
            self.stop()
            return

        if await self.cog.bot.db.get_marriage(self.target.id) is not None:
            self.text.content = "## 💍 Marriage Proposal\n⚠️ You're already married."
            self.container.accent_colour = discord.Color.red()
            await interaction.response.edit_message(view=self)
            self.stop()
            return

        await self.cog.bot.db.marry(self.proposer.id, self.target.id)
        self.text.content = f"## 💍 Marriage Proposal\n🎉 {self.proposer.mention} and {self.target.mention} are now married!"
        self.container.accent_colour = discord.Color.green()
        await interaction.response.edit_message(view=self)
        self.stop()

    async def decline(self, interaction: discord.Interaction):
        self.finished = True
        self._disable_buttons()
        self.text.content = f"## 💍 Marriage Proposal\n{self.target.mention} declined the proposal."
        self.container.accent_colour = discord.Color.greyple()
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        self._disable_buttons()
        if self.message:
            self.text.content = f"## 💍 Marriage Proposal\n⏱️ {self.target.mention} didn't respond in time."
            self.container.accent_colour = discord.Color.greyple()
            await self.message.edit(view=self)


class Marriage(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="marry", description="Propose marriage to another player.")
    @app_commands.describe(user="Who to propose to")
    async def marry(self, ctx: commands.Context, user: discord.User):
        if user.bot or user.id == ctx.author.id:
            await ctx.send("⚠️ Invalid proposal target.")
            return

        if await self.bot.db.get_marriage(ctx.author.id) is not None:
            await ctx.send("⚠️ You're already married. Use `/divorce` first.")
            return
        if await self.bot.db.get_marriage(user.id) is not None:
            await ctx.send(f"⚠️ {user.mention} is already married.")
            return

        view = ProposalView(self, ctx.author, user)
        message = await ctx.send(view=view)
        view.message = message

    @commands.hybrid_command(name="divorce", description="End your marriage.")
    async def divorce(self, ctx: commands.Context):
        partner_id = await self.bot.db.divorce(ctx.author.id)
        if partner_id is None:
            await ctx.send("⚠️ You're not married.")
            return

        view = StaticView("💔 Divorce", f"{ctx.author.mention} and <@{partner_id}> are no longer married.")
        await ctx.send(view=view)

    @commands.hybrid_command(name="marriage", description="Shows a player's marriage status.")
    @app_commands.describe(user="Optional: check another user's marriage status")
    async def marriage(self, ctx: commands.Context, user: discord.User | None = None):
        target = user or ctx.author
        partner_id = await self.bot.db.get_marriage(target.id)

        if partner_id is None:
            text = f"{target.mention} is not married."
        else:
            text = f"{target.mention} is married to <@{partner_id}>. 💍"

        view = StaticView("💍 Marriage Status", text)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Marriage(bot))
