"""Provider chain with explicit degradation and attempt log (M1-T05)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from .catalog import Catalog
from .model import AppRecord


class ResolveError(ValueError):
    """Raised when every provider (and the cache) failed for an appid."""

    def __init__(self, appid: int, attempts: tuple["Attempt", ...]):
        self.appid = appid
        self.attempts = attempts
        detail = "; ".join(
            attempt.provider + "=" + ("ok" if attempt.ok else str(attempt.error))
            for attempt in attempts
        )
        super().__init__("cannot resolve appid " + str(appid) + " -> " + detail)


@dataclass(frozen=True)
class Attempt:
    provider: str
    ok: bool
    error: str | None
    ms: float

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "ok": self.ok,
            "error": self.error,
            "ms": round(self.ms, 3),
        }


@dataclass(frozen=True)
class Resolution:
    appid: int
    record: AppRecord
    used: str
    attempts: tuple[Attempt, ...]

    @property
    def degraded(self) -> bool:
        return any(not attempt.ok for attempt in self.attempts)

    def as_dict(self) -> dict:
        return {
            "appid": self.appid,
            "used": self.used,
            "degraded": self.degraded,
            "attempts": [attempt.as_dict() for attempt in self.attempts],
        }


class Provider(Protocol):
    name: str

    def fetch(self, appid: int) -> AppRecord | None:
        ...


class CallableProvider:
    """Adapter for a plain function, mostly for tests and ad-hoc sources."""

    def __init__(self, name: str, fn: Callable[[int], AppRecord | None]):
        self.name = name
        self._fn = fn

    def fetch(self, appid: int) -> AppRecord | None:
        return self._fn(appid)


class Resolver:
    """Walk providers in priority order, fall back to the catalog cache."""

    def __init__(
        self,
        providers: Iterable[Provider],
        *,
        cache: Catalog | None = None,
        store: bool = True,
        clock: Callable[[], float] = time.perf_counter,
    ):
        self.providers = list(providers)
        self.cache = cache
        self.store = store
        self._clock = clock

    def resolve(self, appid: int) -> Resolution:
        attempts: list[Attempt] = []
        for provider in self.providers:
            started = self._clock()
            try:
                record = provider.fetch(appid)
            except Exception as exc:  # noqa: BLE001 - degradation is the point
                attempts.append(
                    Attempt(
                        provider.name,
                        False,
                        type(exc).__name__ + ": " + str(exc),
                        self._clock() - started,
                    )
                )
                continue
            elapsed = self._clock() - started
            if record is None:
                attempts.append(Attempt(provider.name, False, "no data", elapsed))
                continue
            attempts.append(Attempt(provider.name, True, None, elapsed))
            if self.store and self.cache is not None:
                self.cache.upsert(record)
            return Resolution(appid, record, provider.name, tuple(attempts))

        if self.cache is not None:
            cached = self.cache.query(appid)
            if cached is not None:
                attempts.append(Attempt("cache", True, None, 0.0))
                return Resolution(appid, cached, "cache", tuple(attempts))
        raise ResolveError(appid, tuple(attempts))
