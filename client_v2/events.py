from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable


@dataclass(slots=True)
class CheckEvent:
    event: str
    module: str
    message: str
    level: str = "info"
    progress: int = 0
    timestamp: str = ""
    title: str = ""
    value: str = ""
    status: str = ""
    current: int = 0
    total: int = 0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


EventSink = Callable[[CheckEvent], None]


def emit(sink: EventSink | None, event: str, module: str, message: str, *, level: str = "info", progress: int = 0) -> CheckEvent:
    item = CheckEvent(event, module, message, level, progress)
    if sink:
        sink(item)
    return item
