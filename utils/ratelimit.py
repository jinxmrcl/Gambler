import asyncio
import time


class RateLimiter:
    """A token-bucket limiter for our own outgoing Discord API calls.

    discord.py already queues and retries requests against Discord's per-route
    buckets, so a 429 here wouldn't crash anything — but under concurrent load
    (e.g. many players spinning an animated game at once) that just means
    requests silently stall waiting on Discord's backoff. Throttling
    proactively on our side keeps request bursts (like a multi-frame spin
    animation) well under Discord's global limit instead of relying on
    Discord to tell us to slow down.
    """

    def __init__(self, rate: float, per: float):
        self._rate = rate
        self._per = per
        self._tokens = rate
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._updated_at
                self._updated_at = now
                self._tokens = min(self._rate, self._tokens + elapsed * (self._rate / self._per))
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await asyncio.sleep((1 - self._tokens) * (self._per / self._rate))


# Discord's global limit is 50 requests/second bot-wide. Staying well under it
# leaves headroom for everything else the bot is doing (commands, other
# messages) alongside bursty edit sequences like game animations.
global_limiter = RateLimiter(rate=35, per=1.0)


async def limited_edit(message, **kwargs) -> None:
    """Edits a message through the shared global limiter."""
    await global_limiter.acquire()
    await message.edit(**kwargs)
