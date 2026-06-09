from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class MetricsSink(Protocol):
    def emit(self, *, event: dict[str, Any]) -> None: ...


@dataclass
class JSONLinesMetricsSink:
    out_path: Path

    def __post_init__(self) -> None:
        self.out_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, *, event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with self.out_path.open("a", encoding="utf-8", errors="replace") as f:
            f.write(line + "\n")
