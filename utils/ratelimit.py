import asyncio
import time
from collections import defaultdict


class RateLimiter:

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


_EDIT_RATE = 3
_EDIT_PER = 5.0
_channel_limiters: dict[int, RateLimiter] = defaultdict(lambda: RateLimiter(_EDIT_RATE, _EDIT_PER))


async def limited_edit(message, **kwargs) -> None:
    await _channel_limiters[message.channel.id].acquire()
    await message.edit(**kwargs)
