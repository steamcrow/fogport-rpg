"""Fail CI when a Fogport workflow can write to Kanka without manual dispatch."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def audit_workflows(workflows: Path) -> list[str]:
    errors: list[str] = []
    for workflow in sorted(workflows.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        if "KANKA_API_TOKEN" not in text:
            continue
        if "workflow_dispatch:" not in text:
            errors.append(f"{workflow.name}: Kanka writer must require workflow_dispatch.")
        if "\n  push:" in text or "\n  schedule:" in text or "\n  pull_request:" in text:
            errors.append(f"{workflow.name}: Kanka writer must not run on push, schedule, or pull_request.")
        if "contents: write" in text:
            errors.append(f"{workflow.name}: Kanka writer must not have repository write permission.")
    return errors


def main() -> int:
    errors = audit_workflows(WORKFLOWS)
    if errors:
        print("Unsafe Kanka workflow configuration:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print("Kanka workflow safety audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
