import asyncio
import time
from collections import defaultdict


class RateLimiter:

    def __init__(self, rate: float, per: float, *, min_rate_fraction: float = 0.3):
        self._base_rate = rate
        self._per = per
        self._min_rate_fraction = min_rate_fraction
        self._tokens = rate
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()
        self._waiters = 0

    def _effective_rate(self) -> float:
        if self._waiters <= 1:
            return self._base_rate
        scale = max(self._min_rate_fraction, 1 / self._waiters)
        return self._base_rate * scale

    async def acquire(self) -> None:
        self._waiters += 1
        try:
            async with self._lock:
                while True:
                    rate = self._effective_rate()
                    now = time.monotonic()
                    elapsed = now - self._updated_at
                    self._updated_at = now
                    self._tokens = min(rate, self._tokens + elapsed * (rate / self._per))
                    if self._tokens >= 1:
                        self._tokens -= 1
                        return
                    await asyncio.sleep((1 - self._tokens) * (self._per / rate))
        finally:
            self._waiters -= 1


_EDIT_RATE = 3
_EDIT_PER = 5.0
_channel_limiters: dict[int, RateLimiter] = defaultdict(lambda: RateLimiter(_EDIT_RATE, _EDIT_PER))

_GLOBAL_RATE = 45
_GLOBAL_PER = 1.0
_global_limiter = RateLimiter(_GLOBAL_RATE, _GLOBAL_PER)


async def limited_edit(message, **kwargs) -> None:
    await _global_limiter.acquire()
    await _channel_limiters[message.channel.id].acquire()
    await message.edit(**kwargs)


async def limited_send(sendable, **kwargs):
    await _global_limiter.acquire()
    return await sendable.send(**kwargs)
