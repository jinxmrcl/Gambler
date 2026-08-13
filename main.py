import asyncio
import importlib
import json
import logging
import os
import signal
import sys
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

HOT_RELOAD = os.getenv("HOT_RELOAD", "true").lower() not in ("0", "false", "no")
HOT_RELOAD_DIRS = ("commands", "events", "rpg", "utils", "database")
HOT_RELOAD_POLL_SECONDS = 1.5


def _scan_source_mtimes() -> dict[Path, float]:
    result = {}
    for folder in HOT_RELOAD_DIRS:
        for file in (BASE_DIR / folder).rglob("*.py"):
            try:
                result[file] = file.stat().st_mtime
            except OSError:
                pass
    return result


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

        if HOT_RELOAD:
            self._hot_reload_task = asyncio.create_task(self._hot_reload_loop())
            log.info("Hot reload enabled — watching %s for changes.", ", ".join(HOT_RELOAD_DIRS))

    async def _hot_reload_loop(self) -> None:
        """Polls source files for changes and reloads them live, so local dev
        iteration doesn't require restarting (and re-authing) the whole bot.

        Plain modules (rpg/, utils/, database/) are reloaded via importlib
        first so cogs pick up their fresh code, then every loaded cog
        extension is reloaded so its own top-level imports re-run against
        that fresh code, then the command tree is re-synced in case any
        signatures or descriptions changed."""
        mtimes = _scan_source_mtimes()
        while True:
            await asyncio.sleep(HOT_RELOAD_POLL_SECONDS)
            try:
                current = _scan_source_mtimes()
            except Exception:
                continue
            changed = {f for f, t in current.items() if mtimes.get(f) != t}
            removed = mtimes.keys() - current.keys()
            mtimes = current
            if not changed and not removed:
                continue

            changed_names = ", ".join(f.name for f in changed) or "(file removed)"
            log.info("[hot-reload] change detected: %s", changed_names)

            for modname, mod in list(sys.modules.items()):
                modfile = getattr(mod, "__file__", None)
                if not modfile:
                    continue
                try:
                    modpath = Path(modfile).resolve()
                except OSError:
                    continue
                if any(
                    modpath.is_relative_to((BASE_DIR / folder).resolve())
                    for folder in ("rpg", "utils", "database")
                ):
                    try:
                        importlib.reload(mod)
                    except Exception:
                        log.exception("[hot-reload] failed to reload module %s", modname)

            for extension in list(self.extensions):
                try:
                    await self.reload_extension(extension)
                except Exception:
                    log.exception("[hot-reload] failed to reload extension %s", extension)
                else:
                    log.info("[hot-reload] reloaded %s", extension)

            try:
                synced = await self.tree.sync()
                log.info("[hot-reload] re-synced %d slash commands", len(synced))
            except Exception:
                log.exception("[hot-reload] failed to sync commands")

    async def close(self) -> None:
        task = getattr(self, "_hot_reload_task", None)
        if task:
            task.cancel()
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
