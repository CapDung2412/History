from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar, cast

T = TypeVar("T")


@dataclass(slots=True)
class _Flight(Generic[T]):
    event: threading.Event = field(default_factory=threading.Event)
    result: T | None = None
    error: BaseException | None = None


class SingleFlight(Generic[T]):
    """Coalesce same-key work inside the API's documented single process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._flights: dict[str, _Flight[T]] = {}

    def run(self, key: str, action: Callable[[], T]) -> T:
        with self._lock:
            flight = self._flights.get(key)
            leader = flight is None
            if flight is None:
                flight = _Flight()
                self._flights[key] = flight

        if not leader:
            flight.event.wait()
            if flight.error is not None:
                raise flight.error
            return cast(T, flight.result)

        try:
            flight.result = action()
            return flight.result
        except BaseException as exc:
            flight.error = exc
            raise
        finally:
            flight.event.set()
            with self._lock:
                self._flights.pop(key, None)
