#!/usr/bin/env python3
"""Check the package's metadata, command reference, and event reader contract.

These are the useful product assertions from the retired release campaign.
Publication approval is a maintainer decision, not a state machine in this tool.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

from tenkz_ctan import read_release
from tenkz_language import current_reference_entries, load_registry
from tenkzlib import tnlog

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "tex/tenkz/tenkz-language-registry.tex"
REFERENCE = "docs/tenkz/chapters2/generated-language-reference.tex"
KIND_BLOCK = re.compile(
    r"^```toml[ \t]+tenkz-event-kinds-v1[ \t]*\n(.*?)^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def check(root: Path = ROOT) -> None:
    """Raise on missing, malformed, or inconsistent product evidence."""
    # Reuse the archive parser: cardinality, version syntax, and calendar date.
    read_release(root / "tex/tenkz/tenkz.sty")
    commands = {e.fields[0] for e in current_reference_entries(load_registry(root / REGISTRY))
                if e.kind == "command"}
    if not commands:
        raise ValueError("registry contains no command declarations")
    reference = (root / REFERENCE).read_text()
    missing = sorted(
        name
        for name in commands
        if f"\\texttt{{\\textbackslash {name}}}" not in reference
    )
    if missing:
        raise ValueError(f"generated reference omits commands: {missing}")

    blocks = KIND_BLOCK.findall((root / "docs/tenkz/TNLOG.md").read_text())
    if len(blocks) != 1:
        raise ValueError("TNLOG.md must contain exactly one event-kind declaration")
    declaration = tomllib.loads(blocks[0])
    schema = declaration.get("schema")
    if not isinstance(schema, int) or isinstance(schema, bool) or schema != 1:
        raise ValueError("event-kind declaration must use schema 1")
    kinds = declaration.get("reader_table")
    if not isinstance(kinds, list) or not all(isinstance(kind, str) for kind in kinds):
        raise ValueError("event-kind declaration needs a list of reader kinds")
    if sorted(kinds) != sorted(tnlog.FIELD_VALIDATORS):
        raise ValueError("declared event kinds differ from the canonical reader")

    findings: list[str] = []
    stream = (
        "picture|id=k1|lang=kernel|later-minor-field=value\n"
        "atom|id=atom-1|addr=(1,1)|kind=tn|another-later-field=value\n"
        "kernel-boundary|signature=open:w\n"
    )
    parsed = tnlog.parse_log(
        stream,
        hard=lambda rule, where, message: findings.append(f"{rule}: {message}"),
    )
    if findings or len(parsed.valid_events) != 3:
        raise ValueError(f"reader rejected unknown optional fields: {findings}")


def main() -> int:
    try:
        check()
    except (OSError, ValueError, SystemExit) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: package version, command reference, and event reader contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
