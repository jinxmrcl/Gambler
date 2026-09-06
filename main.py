def _bootstrap_venv():
    import os, sys, subprocess
    root = os.path.dirname(os.path.abspath(__file__))
    venv_dir = os.path.join(root, "venv")
    bindir = "Scripts" if os.name == "nt" else "bin"
    vpy = os.path.join(venv_dir, bindir, "python.exe" if os.name == "nt" else "python")

    if os.path.abspath(sys.prefix) == os.path.abspath(venv_dir):
        return
    if os.environ.get("_GAMBLER_BOOTSTRAPPED") == "1" or os.environ.get("GAMBLER_NO_BOOTSTRAP") == "1":
        return

    fresh = not os.path.exists(vpy)
    try:
        if fresh:
            print("[bootstrap] No venv found — creating one…", flush=True)
            subprocess.check_call([sys.executable, "-m", "venv", venv_dir])
        req = os.path.join(root, "requirements.txt")
        if os.path.exists(req) and (fresh or os.environ.get("GAMBLER_INSTALL_DEPS") == "1"):
            print("[bootstrap] Installing requirements…", flush=True)
            subprocess.check_call([vpy, "-m", "pip", "install", "--upgrade", "pip", "-q"])
            subprocess.check_call([vpy, "-m", "pip", "install", "-q", "-r", req])
    except Exception as exc:
        print(f"[bootstrap] setup failed ({exc}); continuing with current interpreter.", flush=True)
        return

    os.environ["_GAMBLER_BOOTSTRAPPED"] = "1"
    cmd = [vpy, os.path.abspath(__file__), *sys.argv[1:]]
    if os.name == "nt":
        print("[bootstrap] Launching inside venv…", flush=True)
        raise SystemExit(subprocess.call(cmd))
    try:
        bindir_path = os.path.dirname(vpy)
        for f in os.listdir(bindir_path):
            fp = os.path.join(bindir_path, f)
            if os.path.isfile(fp):
                os.chmod(fp, 0o755)
    except OSError:
        pass
    print("[bootstrap] Launching inside venv…", flush=True)
    os.execv(vpy, cmd)


_bootstrap_venv()

import asyncio
import importlib
import json
import logging
import os
import random
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

from database import GuildDatabaseManager, SupabaseBackup
from utils.checks import gamble_channel_check
from utils.economy import StaticView
from utils.owners import OWNER_IDS
from utils.ratelimit import limited_send

load_dotenv()

log = logging.getLogger("gambler")


def _resolve_supabase_dsn() -> str | None:
    dsn_file = os.getenv("SUPABASE_DB_URL_FILE")
    if dsn_file:
        return Path(dsn_file).read_text(encoding="utf-8").strip()
    return os.getenv("SUPABASE_DB_URL") or None


TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")


def _channel_id_from_env(name: str) -> int | None:
    raw = os.getenv(name, "")
    return int(raw) if raw.isdigit() else None


RESTART_LOG_CHANNEL_ID = _channel_id_from_env("RESTART_LOG_CHANNEL_ID")
RESTART_GLOBAL_LOG_CHANNEL_ID = _channel_id_from_env("RESTART_GLOBAL_LOG_CHANNEL_ID")
ERROR_LOG_CHANNEL_ID = _channel_id_from_env("ERROR_LOG_CHANNEL_ID")
ACTION_LOG_CHANNEL_ID = _channel_id_from_env("ACTION_LOG_CHANNEL_ID")
INFO_LOG_CHANNEL_ID = _channel_id_from_env("INFO_LOG_CHANNEL_ID")
SERVERS_LOG_CHANNEL_ID = _channel_id_from_env("SERVERS_LOG_CHANNEL_ID")
LOGS_LOG_CHANNEL_ID = _channel_id_from_env("LOGS_LOG_CHANNEL_ID")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
RESTART_STATE_PATH = DATA_DIR / "restart_state.json"
KNOWN_COMMANDS_PATH = DATA_DIR / "known_commands.json"

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

BACKUPS_DIR = BASE_DIR / "backups"
BACKUPS_DIR.mkdir(exist_ok=True)
DB_BACKUP_MIN_INTERVAL_SECONDS = 30 * 60
DB_BACKUP_MAX_INTERVAL_SECONDS = 60 * 60
DB_BACKUP_RETENTION = 48
DAILY_BACKUP_INTERVAL_SECONDS = 24 * 60 * 60

HOT_RELOAD = os.getenv("HOT_RELOAD", "true").lower() not in ("0", "false", "no")
HOT_RELOAD_DIRS = ("commands", "events", "rpg", "utils", "database")
HOT_RELOAD_POLL_SECONDS = 1.5

GIT_WATCH_INTERVAL_SECONDS = 60
GIT_REPO_URL = "https://github.com/jinxmrcl/Gambler.git"


async def _run_git(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=BASE_DIR,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    out, _ = await proc.communicate()
    return proc.returncode, out.decode(errors="ignore").strip()


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
    
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    debug_file_handler = logging.FileHandler(LOGS_DIR / log_filename, mode="w", encoding="utf-8")
    debug_file_handler.setLevel(logging.DEBUG)
    debug_file_handler.setFormatter(formatter)
    root.addHandler(debug_file_handler)

    error_handler = logging.FileHandler(LOGS_DIR / "debug.log", encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)

    for noisy in ("discord", "discord.gateway", "discord.client", "discord.http", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.INFO)


def _recent_error_lines(limit: int = 8) -> str:
    path = LOGS_DIR / "debug.log"
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


def _read_known_commands() -> list[str] | None:
    """Returns None if this is the first run ever (no baseline to diff against yet)."""
    try:
        return json.loads(KNOWN_COMMANDS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_known_commands(names: list[str]) -> None:
    try:
        KNOWN_COMMANDS_PATH.write_text(json.dumps(sorted(names)), encoding="utf-8")
    except Exception:
        pass


class GamblerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned_or(PREFIX),
            intents=intents,
            help_command=None,
            owner_ids=OWNER_IDS,
        )
        self.add_check(gamble_channel_check)

        self.prefix = PREFIX
        self.starting_balance = int(os.getenv("STARTING_BALANCE", "100000"))
        self.daily_amount = int(os.getenv("DAILY_AMOUNT", "500"))

        self.db = GuildDatabaseManager(DATA_DIR / "guilds")
        self.backup: SupabaseBackup | None = None

        self._startup_reported = False
        self._git_watch_last_failed_sha: str | None = None

    async def _send_to_channel(self, channel_id: int, **kwargs) -> None:
        channel = self.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.fetch_channel(channel_id)
            except Exception:
                return
        try:
            await channel.send(embed=discord.Embed(**kwargs))
        except Exception:
            pass

    async def _send_to_restart_channel(self, **kwargs) -> None:
        for channel_id in (RESTART_LOG_CHANNEL_ID, RESTART_GLOBAL_LOG_CHANNEL_ID):
            if channel_id:
                await self._send_to_channel(channel_id, **kwargs)

    async def _send_to_error_log(self, **kwargs) -> None:
        if ERROR_LOG_CHANNEL_ID:
            await self._send_to_channel(ERROR_LOG_CHANNEL_ID, **kwargs)

    async def _send_to_action_log(self, **kwargs) -> None:
        if ACTION_LOG_CHANNEL_ID:
            await self._send_to_channel(ACTION_LOG_CHANNEL_ID, **kwargs)

    async def _send_to_info_log(self, **kwargs) -> None:
        if INFO_LOG_CHANNEL_ID:
            await self._send_to_channel(INFO_LOG_CHANNEL_ID, **kwargs)

    async def _send_to_servers_log(self, **kwargs) -> None:
        if SERVERS_LOG_CHANNEL_ID:
            await self._send_to_channel(SERVERS_LOG_CHANNEL_ID, **kwargs)

    async def _send_to_logs_log(self, **kwargs) -> None:
        if LOGS_LOG_CHANNEL_ID:
            await self._send_to_channel(LOGS_LOG_CHANNEL_ID, **kwargs)

    async def report_startup_state(self) -> None:
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
        await self._announce_new_features()

    async def _announce_new_features(self) -> None:
        app_commands_list = self.tree.get_commands()
        current_names = sorted(c.name for c in app_commands_list)
        descriptions = {c.name: c.description for c in app_commands_list}

        previous_names = _read_known_commands()
        _write_known_commands(current_names)

        if previous_names is None:
            return

        new_names = sorted(set(current_names) - set(previous_names))
        if not new_names:
            return

        lines = [f"`/{name}` — {descriptions.get(name) or '—'}" for name in new_names]
        body = f"This bot was just updated with {len(new_names)} new command(s):\n\n" + "\n".join(lines)

        for guild in self.guilds:
            try:
                guild_db = await self.db.get(guild.id)
                channel_id = await guild_db.get_updates_channel()
            except Exception:
                log.exception("[updates] failed to load updates channel for guild %s", guild.id)
                continue
            if not channel_id:
                continue

            channel = self.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.fetch_channel(channel_id)
                except Exception:
                    continue
            try:
                view = StaticView("🆕 New Features Added", body, color=discord.Color.gold())
                await limited_send(channel, view=view)
            except Exception:
                log.exception("[updates] failed to announce new features in guild %s", guild.id)

    async def graceful_shutdown(self) -> None:
        if self.is_ready():
            await self._send_to_restart_channel(
                title="<:restart:1537866127835799572> Restarting",
                description="A restart was requested. The bot is shutting down cleanly and will be back shortly.",
                color=0xFEE75C,
            )
        _write_restart_state("clean_shutdown")
        await self.close()

    async def setup_hook(self) -> None:
        log.info("Per-guild SQLite databases will be created under %s as guilds are seen.", DATA_DIR / "guilds")

        dsn = _resolve_supabase_dsn()
        if dsn:
            try:
                backup = SupabaseBackup(dsn)
                await backup.connect()
                self.backup = backup
                log.info("Connected to Supabase — guild data will be backed up there periodically.")
            except Exception:
                log.exception("[supabase-backup] could not connect; continuing without off-site backup.")

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

        self._db_backup_task = asyncio.create_task(self._db_backup_loop())
        log.info("DB backup enabled — snapshotting every 30-60 min to %s.", BACKUPS_DIR)

        self._daily_backup_task = asyncio.create_task(self._daily_backup_loop())
        log.info("Daily Supabase backup enabled — pushing a dated snapshot every 24h.")

        if (BASE_DIR / ".git").exists():
            self._git_watch_task = asyncio.create_task(self._git_watch_loop())
            log.info("Git watch enabled — checking %s every %ds.", GIT_REPO_URL, GIT_WATCH_INTERVAL_SECONDS)

    async def _db_backup_loop(self) -> None:
        while True:
            await asyncio.sleep(random.uniform(DB_BACKUP_MIN_INTERVAL_SECONDS, DB_BACKUP_MAX_INTERVAL_SECONDS))
            try:
                await self._run_db_backup()
            except Exception:
                log.exception("[db-backup] backup failed")

    async def _run_db_backup(self) -> None:
        guild_ids = set(self.db.loaded_guild_ids())
        guild_ids.update(self.db.known_guild_ids())
        guild_ids.update(g.id for g in self.guilds)

        data: dict[str, dict] = {}
        for guild_id in guild_ids:
            guild_db = await self.db.get(guild_id)
            dump = await guild_db.dump_all_tables()
            data[str(guild_id)] = dump
            if self.backup is not None:
                try:
                    await self.backup.push_guild_snapshot(guild_id, dump)
                except Exception:
                    log.exception("[supabase-backup] failed to push snapshot for guild %s", guild_id)

        if self.backup is not None:
            try:
                await self.backup.push_global_snapshot(data)
            except Exception:
                log.exception("[supabase-backup] failed to push global snapshot")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = BACKUPS_DIR / f"backup_{timestamp}.json"
        await asyncio.to_thread(path.write_text, json.dumps(data, default=str), encoding="utf-8")
        log.info("[db-backup] wrote %s (%d guild(s))", path.name, len(data))
        await self._send_to_logs_log(
            title="💾 DB backup",
            description=f"Wrote `{path.name}` ({len(data)} guild(s)).",
            color=0x5865F2,
        )

    async def _daily_backup_loop(self) -> None:
        while True:
            await asyncio.sleep(DAILY_BACKUP_INTERVAL_SECONDS)
            try:
                await self._run_daily_backup()
            except Exception:
                log.exception("[daily-backup] backup failed")

    async def _run_daily_backup(self) -> None:
        if self.backup is None:
            return

        guild_ids = set(self.db.loaded_guild_ids())
        guild_ids.update(self.db.known_guild_ids())
        guild_ids.update(g.id for g in self.guilds)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        count = 0
        for guild_id in guild_ids:
            guild_db = await self.db.get(guild_id)
            dump = await guild_db.dump_all_tables()
            try:
                await self.backup.push_guild_daily_snapshot(guild_id, today, dump)
                count += 1
            except Exception:
                log.exception("[daily-backup] failed to push snapshot for guild %s", guild_id)

        try:
            await self.backup.prune_daily_backups()
        except Exception:
            log.exception("[daily-backup] failed to prune old snapshots")

        log.info("[daily-backup] pushed daily snapshot for %d guild(s) (%s)", count, today)
        await self._send_to_logs_log(
            title="🗓️ Daily Supabase backup",
            description=f"Pushed a dated snapshot for **{count}** guild(s) ({today}).",
            color=0x5865F2,
        )

        backups = sorted(BACKUPS_DIR.glob("backup_*.json"))
        for old in backups[: max(0, len(backups) - DB_BACKUP_RETENTION)]:
            old.unlink(missing_ok=True)

    async def _git_watch_loop(self) -> None:
        while True:
            await asyncio.sleep(GIT_WATCH_INTERVAL_SECONDS)
            try:
                await self._git_watch_check()
            except Exception:
                log.exception("[git-watch] check failed")

    async def _git_watch_check(self) -> None:
        code, _ = await _run_git("remote", "set-url", "origin", GIT_REPO_URL)
        if code != 0:
            await _run_git("remote", "add", "origin", GIT_REPO_URL)

        code, branch = await _run_git("rev-parse", "--abbrev-ref", "HEAD")
        if code != 0 or not branch or branch == "HEAD":
            return

        code, _ = await _run_git("fetch", "--quiet", "origin", branch)
        if code != 0:
            return

        code, local_sha = await _run_git("rev-parse", "HEAD")
        if code != 0:
            return
        code, remote_sha = await _run_git("rev-parse", f"origin/{branch}")
        if code != 0:
            return
        if local_sha == remote_sha:
            return

        code, _ = await _run_git("merge", "--quiet", "--ff-only", f"origin/{branch}")
        if code == 0:
            log.info("[git-watch] pulled new commits (%s -> %s)", local_sha[:7], remote_sha[:7])
            await self._send_to_restart_channel(
                title="📦 New update pulled",
                description="New commits were pulled from the repo. Run `/restart` to apply them.",
                color=0x5865F2,
            )
        elif self._git_watch_last_failed_sha != remote_sha:
            self._git_watch_last_failed_sha = remote_sha
            log.warning("[git-watch] pull failed for %s (local changes on disk?)", remote_sha[:7])
            await self._send_to_restart_channel(
                title="⚠️ Update available but auto-pull failed",
                description="Likely local changes on the server conflicting with the update. "
                "Check `git status` on the VPS.",
                color=0xED4245,
            )

    async def _hot_reload_loop(self) -> None:
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

            shared_dirs_touched = any(
                f.resolve().is_relative_to((BASE_DIR / folder).resolve())
                for f in (changed | removed)
                for folder in ("rpg", "utils", "database")
            )

            if shared_dirs_touched:
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

            await self._send_to_info_log(
                title="🔁 Hot reload",
                description=f"Changed: `{changed_names}`",
                color=0x5865F2,
            )

    async def close(self) -> None:
        for attr in ("_hot_reload_task", "_git_watch_task", "_db_backup_task", "_daily_backup_task"):
            task = getattr(self, attr, None)
            if task:
                task.cancel()
        for name in list(self.cogs.keys()):
            try:
                await self.remove_cog(name)
            except Exception:
                log.exception("[shutdown] failed to unload cog %s", name)
        await self.db.close_all()
        if self.backup is not None:
            await self.backup.close()
        await super().close()


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, bot: GamblerBot) -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(bot.graceful_shutdown()))
        except (NotImplementedError, AttributeError):
            pass


def _handle_loop_exception(_loop: asyncio.AbstractEventLoop, context: dict) -> None:
    exc = context.get("exception")
    message = context.get("message", "Unhandled exception in event loop")
    log.error("[event-loop] %s", message, exc_info=exc)


GATEWAY_STARTUP_RETRY_DELAYS = (5, 15, 30, 60, 60)


async def main():
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Please check your .env file.")

    setup_discord_logger()

    delays = (*GATEWAY_STARTUP_RETRY_DELAYS, None)
    for attempt, delay in enumerate(delays, start=1):
        bot = GamblerBot()
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(_handle_loop_exception)
        _install_signal_handlers(loop, bot)
        try:
            async with bot:
                await bot.start(TOKEN)
            return
        except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as exc:
            if delay is None:
                log.error("[startup] gateway connection failed after %d attempts, giving up: %s", attempt, exc)
                raise
            log.warning(
                "[startup] gateway connection failed (attempt %d/%d): %s — retrying in %ds",
                attempt, len(delays), exc, delay,
            )
            await asyncio.sleep(delay)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down.")
