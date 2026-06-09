from __future__ import annotations

import json
import sys

from runtime.orchestrator import Orchestrator, OrchestratorError


def main() -> int:
    orch = Orchestrator.load()
    try:
        result = orch.run_demo_task(instruction="创建一个可审查的最小变更，并产出 artifact")
    except OrchestratorError as e:
        sys.stderr.write(f"demo failed: {e}\n")
        return 1
    if not bool(result.get("ok", True)):
        sys.stderr.write(json.dumps(result.get("failure") or {}, ensure_ascii=False, indent=2) + "\n")
        return 1

    sys.stdout.write(json.dumps(result["result"], ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
