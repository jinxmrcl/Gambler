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

_MESSAGE_MIN_INTERVAL = 1.1
_message_limiters: dict[int, RateLimiter] = defaultdict(
    lambda: RateLimiter(1, _MESSAGE_MIN_INTERVAL, min_rate_fraction=1.0)
)

_GLOBAL_EDIT_RATE = 20
_GLOBAL_SEND_RATE = 8
_GLOBAL_PER = 1.0
_global_edit_limiter = RateLimiter(_GLOBAL_EDIT_RATE, _GLOBAL_PER, min_rate_fraction=0.8)
_global_send_limiter = RateLimiter(_GLOBAL_SEND_RATE, _GLOBAL_PER, min_rate_fraction=0.15)

_STALE_ENTRY_SECONDS = 1800.0
_SWEEP_INTERVAL_SECONDS = 600.0
_last_sweep = 0.0


def _sweep_stale_entries() -> None:
    """Drops per-channel/per-message limiters untouched for a while, so these dicts
    don't grow forever as new messages/channels get edited over the bot's uptime."""
    global _last_sweep
    now = time.monotonic()
    if now - _last_sweep < _SWEEP_INTERVAL_SECONDS:
        return
    _last_sweep = now
    cutoff = now - _STALE_ENTRY_SECONDS
    for store in (_message_limiters, _channel_limiters):
        for key, limiter in list(store.items()):
            if limiter._waiters == 0 and limiter._updated_at < cutoff:
                del store[key]


async def limited_edit(message, **kwargs) -> None:
    _sweep_stale_entries()
    await _global_edit_limiter.acquire()
    await _channel_limiters[message.channel.id].acquire()
    await _message_limiters[message.id].acquire()
    await message.edit(**kwargs)


async def limited_send(sendable, **kwargs):
    await _global_send_limiter.acquire()
    return await sendable.send(**kwargs)


def get_status() -> dict:
    return {
        "edit_tokens": round(_global_edit_limiter._tokens, 1),
        "edit_rate": _GLOBAL_EDIT_RATE,
        "send_tokens": round(_global_send_limiter._tokens, 1),
        "send_rate": _GLOBAL_SEND_RATE,
        "tracked_channels": len(_channel_limiters),
        "tracked_messages": len(_message_limiters),
    }
