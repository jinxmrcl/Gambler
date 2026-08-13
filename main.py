import asyncio
import json
import logging
import os
import signal
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from database import Database
from utils.checks import gamble_channel_check

load_dotenv()

log = logging.getLogger("gambler")

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")
_raw_restart_channel = os.getenv("RESTART_LOG_CHANNEL_ID", "")
RESTART_LOG_CHANNEL_ID = int(_raw_restart_channel) if _raw_restart_channel.isdigit() else None

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
RESTART_STATE_PATH = DATA_DIR / "restart_state.json"


def setup_discord_logger(log_filename: str = "bot_debug.log") -> None:
    """File-based debug logging, in addition to the console output used
    during local runs.

    `log_filename` gets everything DEBUG+ from this run only (truncated on
    every restart). `debug.log` accumulates ERROR+ across restarts — since it
    appends rather than truncates, it survives the process dying and is what
    a startup-state check could tail to report what killed the last run."""
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    debug_file_handler = logging.FileHandler(log_filename, mode="w", encoding="utf-8")
    debug_file_handler.setLevel(logging.DEBUG)
    debug_file_handler.setFormatter(formatter)
    root.addHandler(debug_file_handler)

    error_handler = logging.FileHandler("debug.log", encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)

    for noisy in ("discord", "discord.gateway", "discord.client", "discord.http", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.INFO)


def _recent_error_lines(limit: int = 8) -> str:
    path = Path("debug.log")
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(lines[-limit:])
    except Exception:
        return ""


def _read_restart_state() -> dict:
    try:
        return json.loads(RESTART_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_restart_state(status: str, **extra) -> None:
    try:
        payload = {"status": status, "at": datetime.now(timezone.utc).isoformat(), **extra}
        RESTART_STATE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


class GamblerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned_or(PREFIX), intents=intents, help_command=None
        )
        self.add_check(gamble_channel_check)

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

        self._startup_reported = False

    async def _send_to_restart_channel(self, **kwargs) -> None:
        if not RESTART_LOG_CHANNEL_ID:
            return
        channel = self.get_channel(RESTART_LOG_CHANNEL_ID)
        if not channel:
            try:
                channel = await self.fetch_channel(RESTART_LOG_CHANNEL_ID)
            except Exception:
                return
        try:
            await channel.send(embed=discord.Embed(**kwargs))
        except Exception:
            pass

    async def report_startup_state(self) -> None:
        """Announces to RESTART_LOG_CHANNEL_ID whether the previous run shut
        down cleanly or crashed. Guarded so it only fires once per process,
        since on_ready can refire on gateway reconnects."""
        if self._startup_reported:
            return
        self._startup_reported = True

        prev = _read_restart_state()
        status = prev.get("status")
        if status == "clean_shutdown":
            await self._send_to_restart_channel(
                title="✅ Restart complete",
                description="The bot shut down cleanly and is back online.",
                color=0x57F287,
            )
        elif status == "running":
            tail = _recent_error_lines()
            desc = (
                "The bot came back online, but the previous run did not exit "
                "cleanly (crash, OOM kill, or a forced stop)."
            )
            if tail:
                desc += f"\n```\n{tail}\n```"
            await self._send_to_restart_channel(
                title="⚠️ Restarted after an unclean shutdown", description=desc, color=0xFEE75C
            )
        _write_restart_state("running")

    async def graceful_shutdown(self) -> None:
        if self.is_ready():
            await self._send_to_restart_channel(
                title="🔁 Restarting",
                description="A restart was requested. The bot is shutting down cleanly and will be back shortly.",
                color=0xFEE75C,
            )
        _write_restart_state("clean_shutdown")
        await self.close()

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

    async def on_command(self, ctx: commands.Context) -> None:
        log.info(
            "[DIAG] command=%s invoked via=%s message_id=%s interaction_id=%s",
            ctx.command.qualified_name,
            "interaction" if ctx.interaction else "message",
            getattr(ctx.message, "id", None),
            getattr(ctx.interaction, "id", None),
        )

    async def close(self) -> None:
        await self.db.close()
        await super().close()


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, bot: GamblerBot) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(bot.graceful_shutdown()))
        except (NotImplementedError, AttributeError):
            # Not supported on Windows; deployments that need graceful-shutdown
            # announcements should run this under a Unix-like environment.
            pass


async def main():
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Please check your .env file.")

    setup_discord_logger()

    bot = GamblerBot()
    _install_signal_handlers(asyncio.get_running_loop(), bot)
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
