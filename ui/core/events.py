from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, DefaultDict, List


EventCallback = Callable[[Any], None]


class EventBus:
    """Simple publish/subscribe bus for UI events."""

    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, List[EventCallback]] = defaultdict(list)

    def subscribe(self, topic: str, callback: EventCallback) -> Callable[[], None]:
        self._subscribers[topic].append(callback)

        def _unsubscribe() -> None:
            self.unsubscribe(topic, callback)

        return _unsubscribe

    def unsubscribe(self, topic: str, callback: EventCallback) -> None:
        callbacks = self._subscribers.get(topic)
        if not callbacks:
            return
        try:
            callbacks.remove(callback)
        except ValueError:
            return
        if not callbacks:
            self._subscribers.pop(topic, None)

    def emit(self, topic: str, payload: Any | None = None) -> None:
        callbacks = list(self._subscribers.get(topic, ()))
        for callback in callbacks:
            callback(payload)

    def clear(self) -> None:
        self._subscribers.clear()