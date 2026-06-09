from __future__ import annotations

import json
import sys

from runtime.config.rules_loader import RulesLoadError, load_ruleset


def main() -> int:
    try:
        ruleset = load_ruleset()
    except RulesLoadError as e:
        sys.stderr.write(f"rules validation failed: {e}\n")
        return 1

    summary = {
        "execution": ruleset.execution.get("policy_id"),
        "permission": ruleset.permission.get("policy_id"),
        "ownership": ruleset.ownership.get("policy_id"),
        "communication": ruleset.communication.get("policy_id"),
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

