import datetime

import discord
from discord.ext import commands

from utils import topgg
from utils.economy import StaticView, fmt

VOTE_COOLDOWN = datetime.timedelta(hours=12)


class Vote(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="vote", description="Vote for the bot on top.gg for a reward.")
    async def vote(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("⚠️ This command is only available in a server.")
            return

        if not self.bot.topgg_bot_id or not self.bot.topgg_token:
            await ctx.send("⚠️ Voting isn't set up yet — check back later!")
            return

        vote_url = f"https://top.gg/bot/{self.bot.topgg_bot_id}/vote"
        db = await self.bot.db.get(ctx.guild.id)
        await db.ensure_user(ctx.author.id, self.bot.starting_balance)

        voted = await topgg.has_voted(self.bot.topgg_bot_id, self.bot.topgg_token, ctx.author.id)
        if not voted:
            await ctx.send(
                f"🗳️ You haven't voted recently. Vote here for a reward: {vote_url}"
            )
            return

        now = datetime.datetime.utcnow()
        new_balance = await db.claim_vote_reward(
            ctx.author.id, self.bot.vote_reward_amount, now, VOTE_COOLDOWN
        )
        if new_balance is None:
            last = await db.get_last_vote_claim(ctx.author.id)
            next_claim = last + VOTE_COOLDOWN if last else now
            await ctx.send(
                f"⏳ You already claimed this vote's reward. Come back "
                f"<t:{int(next_claim.timestamp())}:R>."
            )
            return

        body = f"Thanks for voting! You received {fmt(self.bot.vote_reward_amount)}.\n"
        body += f"New balance: {fmt(new_balance)}\n\nVote again in 12h: {vote_url}"
        view = StaticView("🗳️ Vote Reward", body, color=discord.Color.green())
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Vote(bot))
