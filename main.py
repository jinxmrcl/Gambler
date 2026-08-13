import asyncio
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from database import Database

load_dotenv()

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
log = logging.getLogger("gambler")

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")

BASE_DIR = Path(__file__).parent


class GamblerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned_or(PREFIX), intents=intents, help_command=None
        )

        self.prefix = PREFIX
        self.starting_balance = int(os.getenv("STARTING_BALANCE", "1000"))
        self.daily_amount = int(os.getenv("DAILY_AMOUNT", "500"))

        self.db = Database(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            db=os.getenv("DB_NAME", "gambler"),
        )

    async def setup_hook(self) -> None:
        await self.db.connect()
        log.info("Connected to MySQL database.")

        for folder in ("events", "commands"):
            folder_path = BASE_DIR / folder
            for file in sorted(folder_path.glob("*.py")):
                if file.name.startswith("_"):
                    continue
                extension = f"{folder}.{file.stem}"
                try:
                    await self.load_extension(extension)
                    log.info("Loaded cog: %s", extension)
                except Exception:
                    log.exception("Failed to load cog: %s", extension)

        synced = await self.tree.sync()
        log.info("Synced %d slash commands.", len(synced))

    async def close(self) -> None:
        await self.db.close()
        await super().close()


async def main():
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Please check your .env file.")

    bot = GamblerBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
