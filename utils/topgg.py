import logging

import aiohttp

log = logging.getLogger("gambler")

_session: aiohttp.ClientSession | None = None


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def close_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


async def has_voted(bot_id: str, token: str, user_id: int) -> bool:
    url = f"https://top.gg/api/bots/{bot_id}/check"
    headers = {"Authorization": token}
    try:
        session = _get_session()
        async with session.get(url, headers=headers, params={"userId": user_id}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                log.warning("[topgg] check returned status %d for user %d", resp.status, user_id)
                return False
            data = await resp.json()
            return bool(data.get("voted"))
    except Exception:
        log.exception("[topgg] failed to check vote status for user %d", user_id)
        return False
