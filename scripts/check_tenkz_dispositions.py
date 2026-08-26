#!/usr/bin/env python3
"""Verify that the tenkz migration ledger matches the tracked TeX sources."""

from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tenkzlib.texcase import (
    Construct,
    TeXEnvironmentNestingError,
    following_group,
    following_group_span,
    match_group,
    scan_constructs,
    strip_comments,
    top_level_options,
)
from tenkz_language import load_registry, tombstone_rows, tombstone_shape


DOCUMENT = ROOT / "docs/tenkz/DISPOSITIONS.md"
BLUEPRINT_ROOT = Path(
    os.environ.get("TENKZ_BLUEPRINT_ROOT", ROOT / "blueprint/src/chapter")
)
FIXTURE_ROOT = ROOT / "tests/tenkz"
ENVIRONMENT = re.compile(
    r"\\begin\s*\{\s*(tenkz(?:eq|free|cd|lattice|planes)?)\s*\}"
)
COMMAND = re.compile(r"\\(tnpic|tntree)\b")
TENKZEQ_TOKEN = re.compile(r"\\(begin|end)\{tenkzeq\}")
SETUP_COMMAND = re.compile(r"\\(?:tnset|tndeclare(?:atom)?|tenkzkernel)\b")
DISPOSITIONS = ("preserve", "codemod", "redraw")
DISPOSITION_FAMILY = {"P": "preserve", "C": "codemod", "R": "redraw"}
# Counter equality reads a missing label as a zero, so the rows standing at
# zero -- the ratchets that say a retired construct has not come back -- could
# be deleted without any total moving.  Their labels are pinned here, so
# removing one is an edit to this checker and gets read.
BLUEPRINT_RAW_LABELS = frozenset({"tenkz", "tenkzcd", "tenkzplanes", "tnpic", "tntree"})
FIXTURE_RAW_LABELS = frozenset({"tenkz", "tenkzeq", "tnpic", "tntree"})
MIGRATION_CODES: frozenset[str] = frozenset()
# Retired spellings, read from the registry's tombstone rows: a command row
# names a command that no longer exists, a `key=value` row a word struck from
# a live key's alphabet.  Retiring a spelling is one registry edit, and this
# audit follows it rather than keeping a second list of the same knowledge.
#
# `\tnprose` has no row.  It sets a sentence where a picture would stand, puts
# no ink on the page, and is a live registry command; calling it dead was this
# file disagreeing with the registry about one spelling.
_TOMBSTONE_ROWS = tombstone_rows(load_registry())


def _retired_values(
    rows: list[tuple[str, str, str]],
) -> dict[str, set[str]]:
    """Group the alphabet words a ledger buries under the key that held them."""
    retired: dict[str, set[str]] = {}
    for scope, spelling, _migration in rows:
        if tombstone_shape(scope, spelling) != "value":
            continue
        key, _separator, value = spelling.partition("=")
        retired.setdefault(key.strip(), set()).add(value.strip())
    return retired


DEAD_COMMANDS = tuple(
    sorted(
        spelling.removeprefix("\\")
        for scope, spelling, _migration in _TOMBSTONE_ROWS
        if tombstone_shape(scope, spelling) == "command"
    )
)
# Retired alphabet words, keyed by the key that used to accept them.  `prose`
# has no row either: it is a word of the live `form=` alphabet.
RETIRED_VALUES = _retired_values(_TOMBSTONE_ROWS)
DEAD_KEYS = (
    "out",
    "in",
    "label shift",
    "col vector",
    "row vector",
    "sheet vector",
    "maps",
    "polygon",
    "radius",
    "tensor style",
    "wiring",
    "trace style",
    "via",
    "bend",
    "weight",
    "nudge",
    "inset",
    "slot",
    "check",
    "chain axis",
    "legs at",
    "boundary legs",
    "label at",
    "poly",
    "bond dir",
    "up",
    "down",
)
SUGAR_COMMANDS = (
    "tnX",
    "tnbond",
    "tnstring",
    "tnfuse",
    "tnspan",
    "tndots",
    "tnskip",
)
# Sugar commands the kernel tier binds to their signed expansions.  Under
# `\tenkzkernel` these owe no migration work, exactly as a key with a signed
# `kernel-` registry row owes none: the surface switch reads them as their
# ledger expansions where they stand.
KERNEL_SUGAR_COMMANDS = frozenset({"tnbond", "tnfuse"})
BARE_DEAD_FLAGS = ("boundary legs", "maps")
SIGNED_KEYS_BY_SCOPE = {
    scope: {
        entry.fields[1].replace("~", " ")
        for entry in load_registry()
        if entry.kind == "key" and entry.fields[0] == f"kernel-{scope}"
    }
    for scope in ("picture", "atom", "wire", "mark", "setup", "declare")
}
COMPATIBILITY_KEYS = {
    "picture": {
        "inline",
        "compact",
        "fused",
        "periodic",
        "west label",
        "east label",
        "north label",
        "south label",
        "bond label",
        "planes",
        *BARE_DEAD_FLAGS,
    },
    "atom": {
        "box",
        "dot",
        "pill",
        "mpo",
        "ring",
        "no legs",
        "circle",
        "boundary",
        "removed",
        "enclosure",
        "tri",
        "combined",
        "span",
        "up at",
        "down at",
        "west at",
        "east at",
        *DEAD_KEYS,
    },
    "wire": {"none", "bond dir", *DEAD_KEYS},
    "mark": {"brace above", "brace below", *DEAD_KEYS},
    "setup": {"species"},
    "declare": set(),
}
OPTION_SCOPES = {
    "tn": "atom",
    "tnX": "atom",
    "tnfuse": "atom",
    "tntree": "atom",
    "tnwire": "wire",
    "tnbond": "wire",
    "tnstring": "wire",
    "tnmark": "mark",
    "tngroup": "picture",
    "tnspan": "mark",
    "tnpic": "picture",
    "tnput": "atom",
    "tnsite": "atom",
    "tnghost": "atom",
    "tnjoin": "wire",
    "tnedge": "wire",
    "tnarrow": "wire",
    "tncut": "mark",
    "tnregion": "mark",
}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def occurrences(path: Path) -> list[tuple[int, str]]:
    """Return every public picture construct in a comment-stripped TeX file."""
    source = strip_comments(path.read_text(errors="replace"))
    matches = [
        (match.start(), match.group(1))
        for pattern in (ENVIRONMENT, COMMAND)
        for match in pattern.finditer(source)
    ]
    return [
        (source.count("\n", 0, offset) + 1, name)
        for offset, name in sorted(matches)
    ]


def normalized_environment_spacing(source: str) -> str:
    """Normalize tenkz tokens without changing source length or line count."""
    pattern = re.compile(
        r"\\(begin|end)(\s*)\{(\s*)"
        r"(tenkz(?:eq|free|cd|lattice|planes)?)(\s*)\}"
    )

    def replace(match: re.Match[str]) -> str:
        whitespace = match.group(2) + match.group(3) + match.group(5)
        return rf"\{match.group(1)}{{{match.group(4)}}}" + whitespace

    return pattern.sub(replace, source)


def encountered_option_groups(source: str) -> list[tuple[str, str]]:
    """Return every public option group with its signed registry scope."""
    groups: list[tuple[str, str]] = []
    for match in ENVIRONMENT.finditer(source):
        options = following_group(source, match.end(), "[", "]")
        if options is not None:
            groups.append(("picture", options))
    commands = "|".join(sorted(OPTION_SCOPES, key=len, reverse=True))
    for match in re.finditer(rf"\\({commands})\*?(?![A-Za-z])", source):
        options = following_group(source, match.end(), "[", "]")
        if options is not None:
            groups.append((OPTION_SCOPES[match.group(1)], options))
    for match in re.finditer(r"\\tnset\b", source):
        options = following_group(source, match.end(), "{", "}")
        if options is not None:
            groups.append(("setup", options))
    for match in re.finditer(r"\\tndeclare\b", source):
        position = match.end()
        arguments: list[str] = []
        for _ in range(3):
            group = following_group_span(source, position, "{", "}")
            if group is None:
                break
            argument, position = group
            arguments.append(argument)
        if len(arguments) == 3:
            groups.append(("declare", arguments[2]))
    for match in re.finditer(r"\\tndeclareatom\b", source):
        position = match.end()
        arguments: list[str] = []
        for _ in range(2):
            group = following_group_span(source, position, "{", "}")
            if group is None:
                break
            argument, position = group
            arguments.append(argument)
        if len(arguments) == 2:
            groups.append(("atom", arguments[1]))
    return groups


def encountered_options(source: str) -> list[tuple[str, str, str | None]]:
    """Return parsed public options as scope, key, and optional value."""
    return [
        (scope, key, value)
        for scope, group in encountered_option_groups(source)
        for key, value in top_level_options(group)
    ]


def unrecognized_option_keys(source: str) -> set[str]:
    """Find option keys outside the signed 1.0 grammar and classified sugar."""
    unknown: set[str] = set()

    def check(options: str, scope: str) -> None:
        allowed = SIGNED_KEYS_BY_SCOPE[scope] | COMPATIBILITY_KEYS[scope]
        unknown.update(
            key for key, _value in top_level_options(options) if key not in allowed
        )

    for scope, options in encountered_option_groups(source):
        check(options, scope)
    return unknown


def scan_inventory_constructs(source: str) -> list[Construct]:
    """Scan picture constructs plus the non-picture `tenkzeq` wrapper."""
    constructs = scan_constructs(source)
    for match in re.finditer(r"\\begin\{tenkzeq\}", source):
        depth = 1
        end_match: re.Match[str] | None = None
        for token in TENKZEQ_TOKEN.finditer(source, match.end()):
            depth += 1 if token.group(1) == "begin" else -1
            if depth == 0:
                end_match = token
                break
        end = end_match.end() if end_match else len(source)
        body_start = match.end()
        if source[body_start : body_start + 1] == "[":
            closed = match_group(source, body_start, "[", "]")
            if closed != -1:
                body_start = closed
        body_end = end_match.start() if end_match else len(source)
        constructs.append(
            Construct(
                "tenkzeq",
                match.start(),
                end,
                source[body_start:body_end],
                source.count("\n", 0, match.start()) + 1,
                body_start,
            )
        )
    constructs.sort(key=lambda construct: construct.start)
    return constructs


def construct_sources(
    path: Path,
) -> dict[tuple[str, int, str], list[tuple[str, bool]]]:
    """Return each construct's source slice and whether the kernel reaches it.

    Since the S4 surface swap the package binds the kernel surface at load,
    so the kernel reaches every construct; a document's own `\\tenkzkernel`
    call rebinds the same meanings and is inert.
    """
    source = normalized_environment_spacing(
        strip_comments(path.read_text(errors="replace"))
    )
    result: dict[tuple[str, int, str], list[tuple[str, bool]]] = defaultdict(list)
    for construct in scan_inventory_constructs(source):
        key = (path.name, construct.line, construct.name)
        result[key].append(
            (source[construct.start : construct.end], True)
        )
    return result


def expanded_source(path: Path, stack: tuple[Path, ...] = ()) -> str:
    """Expand local input files so fixture disposition includes dependencies."""
    path = path.resolve()
    if path in stack:
        fail(f"recursive fixture input: {' -> '.join(map(str, stack + (path,)))}")
    source = strip_comments(path.read_text(errors="replace"))

    def replace(match: re.Match[str]) -> str:
        dependency = (path.parent / (match.group(1) or match.group(2))).resolve()
        if not dependency.suffix:
            dependency = dependency.with_suffix(".tex")
        if not dependency.is_file():
            return match.group(0)
        return expanded_source(dependency, stack + (path,))

    return re.sub(
        r"\\(?:input|include)\s*(?:\{\s*([^}]+?)\s*\}|([^\s%{}]+))",
        replace,
        source,
    )


def fragment_target_codes(source: str, kernel: bool = False) -> frozenset[str]:
    r"""Classify one construct or construct-free source fragment.

    `kernel` says the `\tenkzkernel` switch reaches this fragment, so its keys
    already carry their 1.0 meaning. A key with a signed `kernel-` registry
    row then owes no migration work, whether the row is kernel or sugar: the
    surface switch leaves it spelled exactly as it stands. The same key on a
    0.7 picture still owes one, because the two tiers read several of these
    keys differently — 0.7 `boundary=` sets all four sides where the kernel
    sets west and east, and 0.7 `physical=` is a row topology where the
    kernel's is a per-cell port policy.
    """
    public_commands = (
        "tn",
        "tnwire",
        "tnmark",
        "tngroup",
        "tnset",
        "tndeclare",
        "tndeclareatom",
        "tenkzkernel",
        # `\tnprose` sets a sentence where a picture would stand and puts no
        # ink on the page.  It is a live registry command, so it makes a
        # fragment public without making its record dead.
        "tnprose",
        *DEAD_COMMANDS,
        *SUGAR_COMMANDS,
    )
    public = bool(
        ENVIRONMENT.search(source)
        or COMMAND.search(source)
        or any(re.search(rf"\\{name}\b", source) for name in public_commands)
    )
    if not public:
        return frozenset({"P-none"})

    codes: set[str] = set()
    environments = set(ENVIRONMENT.findall(source))
    environment_codes = {
        "tenkzfree": "R-free",
        "tenkzcd": "R-cd",
        "tenkzlattice": "R-lattice",
        "tenkzplanes": "R-plane",
    }
    codes.update(
        environment_codes[name] for name in environments if name in environment_codes
    )

    options = encountered_options(source)
    keys = {key for _scope, key, _value in options}
    keys_by_scope = {
        scope: {key for option_scope, key, _value in options if option_scope == scope}
        for scope in SIGNED_KEYS_BY_SCOPE
    }
    migrating_by_scope = {
        scope: scope_keys - SIGNED_KEYS_BY_SCOPE[scope] if kernel else scope_keys
        for scope, scope_keys in keys_by_scope.items()
    }
    migrating = set().union(*migrating_by_scope.values())
    tn_options: list[tuple[str, str | None]] = []
    for match in re.finditer(r"\\tn\*?(?![A-Za-z])", source):
        group = following_group(source, match.end(), "[", "]")
        if group is not None:
            tn_options.extend(top_level_options(group))
    tn_keys = {key for key, _value in tn_options}
    bare_tn_keys = {key for key, value in tn_options if value is None}

    def values(key: str) -> list[str]:
        return [
            value.lstrip("{").strip()
            for _scope, option_key, value in options
            if option_key == key and value is not None
        ]

    dead_record = any(re.search(rf"\\{name}\b", source) for name in DEAD_COMMANDS)
    dead_record |= bool(keys & set(DEAD_KEYS))
    dead_record |= bool(
        keys
        & {
            "inline",
            "compact",
            "fused",
            "none",
            "brace above",
            "brace below",
            *BARE_DEAD_FLAGS,
        }
    )
    dead_record |= any(
        re.match(r"(?:hv|vh|curve|drop|hug)\b", value)
        for value in values("route")
    )
    dead_record |= any(
        re.match(r"vertical\b|(?:rotate|matrix)\s*=", value)
        for value in values("frame")
    )
    dead_record |= any(":" in value for value in values("rows"))
    for key, retired in RETIRED_VALUES.items():
        # a value may arrive braced against a comma, and only its first word
        # names the alphabet entry
        dead_record |= any(
            value.strip("{} ").split(" ")[0] in retired for value in values(key)
        )
    dead_record |= any(
        re.match(r"(?:cluster|enclosure)\b", value) for value in values("skin")
    )
    dead_record |= any(
        re.match(r"string\b", value) for value in values("weight")
    )
    dead_record |= any(
        re.search(
            r"\bleg\s+(?:north|south|east|west)\s+of\b"
            r"|\b(?:north|south|east|west)\s+outside\b",
            value,
        )
        for _scope, _key, value in options
        if value is not None
    )
    # A subtracted selector term is kernel grammar (#5565): a mark states a
    # staircase or a complement in the language itself, so the spelling is
    # preserved rather than redrawn.
    unknown_keys = unrecognized_option_keys(source)
    dead_record |= bool(unknown_keys) and not any(
        code.startswith("R-") for code in codes
    )
    dead_record |= bool(
        bare_tn_keys & {"circle", "boundary", "removed", "cluster", "enclosure"}
    )
    dead_record |= "tri" in tn_keys
    if tn_keys & {"box", "dot", "pill", "mpo", "ring", "no legs"}:
        codes.add("C-record")
    if "cluster" in migrating_by_scope["atom"] and any(
        key == "cluster" and value is not None for key, value in tn_options
    ):
        codes.add("C-record")
    if dead_record:
        codes.add("R-record")

    if COMMAND.search(source) and re.search(r"\\tnpic\b", source):
        codes.add("C-picture")
    if re.search(r"\\tntree\b", source):
        codes.add("C-tree")
    # The kernel side grammar takes `cup={m}` itself; `tail=` has no kernel row.
    labelled_side = r"tail" if kernel else r"(?:cup|tail)"
    if "physical" in migrating or migrating_by_scope["picture"] & {
        "boundary",
        "west label",
        "east label",
        "north label",
        "south label",
        "bond label",
        "sandwich",
        "periodic",
    } or any(
        re.match(labelled_side + r"\s*=", value.lstrip("{").strip())
        for scope, key, value in options
        if scope == "picture"
        and key in {"west", "east", "north", "south"}
        and value is not None
    ):
        codes.add("C-policy")
    if migrating_by_scope["picture"] & {
        "lattice",
        "ring",
        "surface",
        "cluster",
        "planes",
    }:
        codes.add("C-frame")
    if any(
        re.search(rf"\\{name}\b", source)
        for name in SUGAR_COMMANDS
        if not (kernel and name in KERNEL_SUGAR_COMMANDS)
    ):
        codes.add("C-record")
    if re.search(r"\\tn\*", source):
        codes.add("C-record")
    if migrating_by_scope["atom"] & {
        "combined",
        "span",
        "up at",
        "down at",
        "west at",
        "east at",
        "up",
        "down",
    }:
        codes.add("C-record")
    if "role" in migrating:
        codes.add("C-species")
    if "species" in migrating_by_scope["setup"]:
        codes.add("C-declare")
    if re.search(r"\\tndeclareatom\b", source):
        codes.add("C-declare")
    if re.search(r"\\tenkzkernel\b", source):
        codes.add("C-switch")

    redraw = {code for code in codes if code.startswith("R-")}
    if redraw:
        return frozenset(codes)
    if codes:
        return frozenset(codes)
    return frozenset({"P-grid"})


def source_target_codes(source: str) -> frozenset[str]:
    """Derive exact migration targets, preserving mixed-construct workloads.

    The kernel is passed as reaching every construct: since the S4 surface
    swap the package binds the kernel surface at load.
    """
    source = normalized_environment_spacing(source)
    constructs = scan_inventory_constructs(source)
    codes: set[str] = set()
    masked = list(source)
    for construct in constructs:
        codes.update(
            fragment_target_codes(
                source[construct.start : construct.end],
                True,
            )
        )
        for index in range(construct.start, construct.end):
            if masked[index] != "\n":
                masked[index] = " "
    codes.update(fragment_target_codes("".join(masked), True))
    if any(not code.startswith("P-") for code in codes):
        codes = {code for code in codes if not code.startswith("P-")}
    elif "P-grid" in codes:
        codes.discard("P-none")
    return frozenset(codes)


def uses_tombstone(source: str) -> bool:
    """Return whether source uses a spelling tombstoned by LANGUAGE-1.0 §10."""
    return any(code.startswith("R-") for code in source_target_codes(source))


def migration_codes(text: str) -> frozenset[str]:
    """The codes the document's own migration table defines."""
    body = section(text, "### Migration target codes", "## ")
    rows: list[str] = []
    for line in body.splitlines():
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        if re.match(r"\|\s*Code\s*\|\s*Required 1\.0 target\s*\|$", line):
            continue
        # A malformed definition is unreferenced today and would disappear
        # unnoticed, taking the code it should have defined with it.
        match = re.match(r"\| `([A-Za-z]+-[a-z]+)` \|", line)
        if match is None:
            fail(f"the migration table has a row it cannot read: {line!r}")
        rows.append(match.group(1))
    repeated = sorted({code for code in rows if rows.count(code) > 1})
    if repeated:
        fail(f"the migration table defines a code more than once: {repeated}")
    codes = frozenset(rows)
    # `target_disposition` reads the family letter, and everything that is
    # neither C nor R falls to preserve, so a family it does not know would
    # be filed as preserve without anyone saying so.  Three families exist.
    stray = sorted(code for code in codes if code.split("-", 1)[0] not in DISPOSITION_FAMILY)
    if stray:
        fail(f"the migration table defines codes outside P/C/R: {stray}")
    return codes


def target_disposition(codes: frozenset[str]) -> str:
    """Return the workload disposition implied by a target-code set."""
    if any(code.startswith("R-") for code in codes):
        return "redraw"
    if any(code.startswith("C-") for code in codes):
        return "codemod"
    return "preserve"


def section(text: str, heading: str, next_heading: str | None = None) -> str:
    try:
        result = text.split(heading, 1)[1]
    except IndexError:
        fail(f"missing document heading: {heading}")
    if next_heading is not None:
        result = result.split(next_heading, 1)[0]
    return result


def parse_counter_table(text: str, heading: str) -> tuple[Counter[str], int]:
    result: Counter[str] = Counter()
    total: int | None = None
    started = False
    seen_header = False
    for row in section(text, heading).splitlines():
        if started and not row.strip():
            break
        if not row.startswith("|"):
            continue
        # The table's own header and its rule are the only exempt rows.  Every
        # other row must be readable, including one standing before the first
        # valid entry: skipping it would leave the counter and the total where
        # they were and the table would still add up.
        if not seen_header:
            seen_header = True
            continue
        if set(row) <= set("|-: "):
            continue
        match = re.match(r"\| `?([^|`]+?)`? \| \**([0-9]+)\** \|$", row)
        if match is None:
            fail(f"counter table below {heading} has a row it cannot read: {row!r}")
        started |= bool(match)
        label = match.group(1).strip().strip("*") if match else ""
        if match and label.lower() == "total":
            if total is not None:
                fail(f"counter table below {heading} lists more than one Total row")
            total = int(match.group(2))
        elif match:
            # A repeated label would overwrite its earlier row and, with the
            # total left alone, the table would still add up.
            if label in result:
                fail(f"counter table below {heading} lists {label!r} more than once")
            result[label] = int(match.group(2))
    if not result:
        fail(f"could not parse counter table below {heading}")
    if total is None or total != sum(result.values()):
        fail(f"invalid total below {heading}: {total} != {sum(result.values())}")
    return result, total


def parse_fixture_table(text: str) -> tuple[Counter[str], int]:
    body = section(text, "| Disposition | Fixtures |")
    body = body.split("\n\n", 1)[0]
    files: Counter[str] = Counter()
    total: int | None = None
    for row in body.splitlines():
        total_match = re.match(r"\| \*\*Total\*\* \| \*\*([0-9]+)\*\* \|$", row)
        if total_match:
            if total is not None:
                fail("standalone fixture table lists more than one Total row")
            total = int(total_match.group(1))
            continue
        if not row.startswith("|") or set(row) <= set("|-: "):
            continue
        if re.match(r"\|\s*Disposition\s*\|\s*Fixtures\s*\|$", row):
            continue
        # The first cell is read as written, not filtered to the words already
        # known: a row spelt `BOGUS` or `bogus-value` must reach the unknown
        # check below rather than be skipped by the pattern (LionSR/tenkz#6).
        match = re.match(r"\| ([^|]+) \| ([0-9]+) \|$", row)
        if match is None:
            fail(f"standalone fixture table has a row it cannot read: {row!r}")
        label = match.group(1).strip()
        if label in files:
            fail(f"standalone fixture table lists {label!r} more than once")
        files[label] = int(match.group(2))
    # Since the S4 surface swap every codemod and redraw fixture has left the
    # corpus, so the table may carry the preserve row alone.
    if not files:
        fail("could not parse standalone fixture reconciliation table")
    unknown = sorted(set(files) - set(DISPOSITIONS))
    if unknown:
        fail(f"standalone fixture table names unknown dispositions: {unknown}")
    if total is None or total != sum(files.values()):
        fail(f"invalid standalone fixture total: {total} != {sum(files.values())}")
    return files, total


def documented_blueprint(
    text: str,
) -> tuple[
    Counter[tuple[str, int, str]],
    Counter[str],
    dict[tuple[str, int, str], str],
    dict[tuple[str, int, str], frozenset[str]],
]:
    body = section(text, "## Blueprint inventory", "### Blueprint reconciliation")
    listed: Counter[tuple[str, int, str]] = Counter()
    dispositions: Counter[str] = Counter()
    disposition_by_occurrence: dict[tuple[str, int, str], str] = {}
    targets_by_occurrence: dict[tuple[str, int, str], frozenset[str]] = {}
    started = False
    for row in body.splitlines():
        if not row.startswith("|"):
            if started:
                break
            continue
        cells = [cell.strip() for cell in row.split("|")[1:-1]]
        if set(row) <= set("|-: ") or cells[:1] == ["Source"]:
            continue
        # A row the grammar cannot read is refused rather than skipped: a
        # mistyped source name would otherwise drop its occurrences from the
        # inventory and the totals could be lowered to agree.
        if len(cells) != 4 or not re.fullmatch(r"`[^`]+\.tex`", cells[0]):
            fail(f"blueprint inventory has a row it cannot read: {row!r}")
        started = True
        filename = cells[0].strip("`")
        for disposition, cell in zip(DISPOSITIONS, cells[1:]):
            # The grammar must consume the whole cell: a second occurrence
            # written any other way would otherwise be skipped while every
            # counter stayed where it was.
            residue = re.sub(
                r"L([1-9][0-9]*(?:, [1-9][0-9]*)*) `([^`]+)` → `([^`]+)`", "", cell
            ).strip(" ;,")
            if cell.strip() != "—" and residue:
                fail(
                    f"{filename}: {disposition} cell has text the occurrence "
                    f"grammar does not read: {residue!r}"
                )
            # Source lines are one-based, so `L0` names nothing and must not
            # read as a location.
            for use in re.finditer(
                r"L([1-9][0-9]*(?:, [1-9][0-9]*)*) `([^`]+)` → `([^`]+)`",
                cell,
            ):
                for line in map(int, use.group(1).split(", ")):
                    key = (filename, line, use.group(2))
                    listed[key] += 1
                    dispositions[disposition] += 1
                    disposition_by_occurrence[key] = disposition
                    targets_by_occurrence[key] = frozenset(
                        use.group(3).split("+")
                    )
    return (
        listed,
        dispositions,
        disposition_by_occurrence,
        targets_by_occurrence,
    )


def documented_fixtures(text: str) -> dict[str, tuple[str, frozenset[str]]]:
    result: dict[str, tuple[str, frozenset[str]]] = {}
    target_codes = set(re.findall(r"^\| `([PCR]-[^`]+)` \|", text, re.MULTILINE))
    for disposition in DISPOSITIONS:
        heading = rf"### {disposition.capitalize()} fixtures \(([0-9]+)\)\n"
        ending = r"(?=\n### |\nThe preserved list|\n\nThree corrections)"
        match = re.search(
            heading + r"(.*?)" + ending,
            text,
            flags=re.DOTALL,
        )
        if not match:
            # Since the S4 surface swap the codemod and redraw groups are
            # empty and their lists have left the document.
            if disposition in ("codemod", "redraw"):
                continue
            fail(f"missing {disposition} fixture list")
        names: list[str] = []
        for row in match.group(2).splitlines():
            item = re.match(r"- `([^`]+)`: (.+)", row)
            if not item:
                continue
            codes = frozenset(item.group(1).split("+"))
            unknown = codes - target_codes
            if unknown:
                fail(f"unknown target codes for {disposition}: {sorted(unknown)}")
            if disposition == "preserve" and any(not code.startswith("P-") for code in codes):
                fail(f"non-preserve target in preserve fixture group: {sorted(codes)}")
            if disposition == "codemod" and (
                not any(code.startswith("C-") for code in codes)
                or any(code.startswith("R-") for code in codes)
            ):
                fail(f"invalid codemod target set: {sorted(codes)}")
            if disposition == "redraw" and not any(
                code.startswith("R-") for code in codes
            ):
                fail(f"redraw target set lacks a redraw code: {sorted(codes)}")
            row_names = re.findall(r"`([^`]+\.tex)`", item.group(2))
            names.extend(row_names)
            for name in row_names:
                if name in result:
                    fail(f"fixture is listed more than once: {name}")
                result[name] = (disposition, codes)
        if len(names) != int(match.group(1)):
            fail(
                f"{disposition} heading says {match.group(1)} fixtures, "
                f"but lists {len(names)}"
            )
    return result


def main() -> int:
    text = DOCUMENT.read_text()
    global MIGRATION_CODES
    MIGRATION_CODES = migration_codes(text)
    if not MIGRATION_CODES:
        fail("the migration target-code table is empty or unreadable")

    # The blueprint's two counter tables and their shared total are checked
    # from the document alone.  Reconciling them against the chapter sources
    # needs the TNLean blueprint tree, which this repository does not carry
    # (LionSR/tenkz#6): with TENKZ_BLUEPRINT_ROOT unset that half is reported
    # as not run rather than folded into a pass.
    (
        listed_blueprint,
        blueprint_dispositions,
        blueprint_occurrence_dispositions,
        blueprint_occurrence_targets,
    ) = documented_blueprint(text)
    documented_blueprint_raw, blueprint_total = parse_counter_table(
        text, "| Raw construct | Occurrences |"
    )
    documented_blueprint_dispositions, disposition_total = parse_counter_table(
        text, "| Disposition | Occurrences |"
    )
    if blueprint_total != disposition_total:
        fail("blueprint reconciliation tables have different totals")
    if sum(listed_blueprint.values()) != blueprint_total:
        fail(
            f"blueprint inventory lists {sum(listed_blueprint.values())} "
            f"occurrences but the raw-count table totals {blueprint_total}"
        )
    if blueprint_dispositions != documented_blueprint_dispositions:
        fail("blueprint disposition totals do not match the line inventory")
    # Counter equality reads a missing label as a zero, so a deleted row and a
    # row reading 0 compare the same and the documented zero ratchets could be
    # dropped in silence.  The labels are compared as well as the counts.
    if set(documented_blueprint_dispositions) != set(DISPOSITIONS):
        fail(
            "blueprint disposition table must carry every disposition row: "
            f"{sorted(documented_blueprint_dispositions)}"
        )
    # The totals agreeing is not the per-construct counts agreeing: moving one
    # occurrence from `tenkz` to `tntree` leaves every total where it was.
    listed_raw: Counter[str] = Counter()
    for (_file, _line, construct), count in listed_blueprint.items():
        listed_raw[construct] += count
    if set(documented_blueprint_raw) != BLUEPRINT_RAW_LABELS:
        fail(
            "blueprint raw-count table must carry every tracked construct row: "
            f"{sorted(documented_blueprint_raw)} against "
            f"{sorted(BLUEPRINT_RAW_LABELS)}"
        )
    if listed_raw != documented_blueprint_raw:
        fail(
            "blueprint raw-count table does not match the line inventory: "
            f"table={dict(sorted(documented_blueprint_raw.items()))}, "
            f"inventory={dict(sorted(listed_raw.items()))}"
        )
    repeated = sorted(key for key, count in listed_blueprint.items() if count != 1)
    if repeated:
        fail(f"blueprint inventory lists one occurrence more than once: {repeated}")
    # A target code is a row of the migration table, and its family decides
    # the disposition the entry is filed under; both are readable without the
    # chapter sources.
    for key, codes in blueprint_occurrence_targets.items():
        unknown_codes = sorted(code for code in codes if code not in MIGRATION_CODES)
        if unknown_codes:
            fail(f"{key[0]}:{key[1]} {key[2]} names unknown target code(s): {unknown_codes}")
        # `source_target_codes` drops every preserve code as soon as a
        # non-preserve one is present, so a set holding both is one no source
        # could produce -- and reading only the strongest family would file it
        # as if the preserve half were not written.
        families = {code.split("-", 1)[0] for code in codes}
        if "P" in families and families - {"P"}:
            fail(
                f"{key[0]}:{key[1]} {key[2]} mixes preserve and non-preserve "
                f"targets {sorted(codes)}, which the source classifier never "
                "produces"
            )
        implied = target_disposition(codes)
        if implied != blueprint_occurrence_dispositions[key]:
            fail(
                f"{key[0]}:{key[1]} {key[2]} is filed under "
                f"{blueprint_occurrence_dispositions[key]} but its targets "
                f"{sorted(codes)} imply {implied}"
            )
    blueprint_reconciled = BLUEPRINT_ROOT.is_dir()

    if blueprint_reconciled:
        blueprint_occurrences: Counter[tuple[str, int, str]] = Counter()
        blueprint_raw: Counter[str] = Counter()
        blueprint_sources: dict[tuple[str, int, str], list[tuple[str, bool]]] = {}
        for path in sorted(BLUEPRINT_ROOT.glob("*.tex")):
            blueprint_sources.update(construct_sources(path))
            for line, name in occurrences(path):
                blueprint_occurrences[(path.name, line, name)] += 1
                blueprint_raw[name] += 1

        if blueprint_occurrences != listed_blueprint:
            fail(
                "blueprint inventory mismatch: "
                f"missing={blueprint_occurrences - listed_blueprint}, "
                f"extra={listed_blueprint - blueprint_occurrences}"
            )
        if blueprint_raw != documented_blueprint_raw:
            fail("blueprint raw-count table does not match the source inventory")
        for key, documented_disposition in blueprint_occurrence_dispositions.items():
            actual_targets = frozenset().union(
                *(
                    fragment_target_codes(source, kernel)
                    for source, kernel in blueprint_sources[key]
                )
            )
            if actual_targets != blueprint_occurrence_targets[key]:
                fail(
                    f"{key[0]}:{key[1]} {key[2]} target mismatch: "
                    f"documented={sorted(blueprint_occurrence_targets[key])}, "
                    f"actual={sorted(actual_targets)}"
                )
            actual_disposition = target_disposition(actual_targets)
            if actual_disposition != documented_disposition:
                fail(
                    f"{key[0]}:{key[1]} {key[2]} disposition mismatch: "
                    f"documented={documented_disposition}, actual={actual_disposition}"
                )
    else:
        print(
            "NOT RUN: blueprint source reconciliation; "
            f"{BLUEPRINT_ROOT} is absent (the chapters live in LionSR/TNLean; "
            "set TENKZ_BLUEPRINT_ROOT to reconcile them)",
            file=sys.stderr,
        )

    fixtures = documented_fixtures(text)
    expected_fixtures = {path.name for path in FIXTURE_ROOT.glob("*.tex")}
    if set(fixtures) != expected_fixtures:
        fail(
            "fixture inventory mismatch: "
            f"missing={sorted(expected_fixtures - set(fixtures))}, "
            f"extra={sorted(set(fixtures) - expected_fixtures)}"
        )

    fixture_raw: Counter[str] = Counter()
    fixture_files: Counter[str] = Counter(
        disposition for disposition, _ in fixtures.values()
    )
    environment_files = 0
    command_only_files = 0
    setup_only_files = 0
    no_surface_files = 0
    for path in sorted(FIXTURE_ROOT.glob("*.tex")):
        uses = occurrences(path)
        names = Counter(name for _, name in uses)
        fixture_raw.update(names)
        expanded = expanded_source(path)
        expanded_names = [
            match.group(1)
            for pattern in (ENVIRONMENT, COMMAND)
            for match in pattern.finditer(expanded)
        ]
        has_environment = any(name.startswith("tenkz") for name in expanded_names)
        has_command = any(name in {"tnpic", "tntree"} for name in expanded_names)
        has_setup = SETUP_COMMAND.search(expanded) is not None
        environment_files += has_environment
        command_only_files += has_command and not has_environment
        setup_only_files += has_setup and not has_environment and not has_command
        no_surface_files += not has_environment and not has_command and not has_setup
        disposition, _ = fixtures[path.name]
        _, documented_targets = fixtures[path.name]
        actual_targets = source_target_codes(expanded)
        if actual_targets != documented_targets:
            fail(
                f"{path.name} target mismatch: "
                f"documented={sorted(documented_targets)}, "
                f"actual={sorted(actual_targets)}"
            )
        actual_disposition = target_disposition(actual_targets)
        if actual_disposition != disposition:
            fail(
                f"{path.name} disposition mismatch: "
                f"documented={disposition}, actual={actual_disposition}"
            )

    documented_files, _fixture_total = parse_fixture_table(text)
    if fixture_files != documented_files:
        fail("fixture disposition totals do not match the fixture lists")
    fixture_heading = "### Fixture raw-count reconciliation"
    documented_fixture_raw, _fixture_raw_total = parse_counter_table(
        text, fixture_heading
    )
    if set(documented_fixture_raw) != FIXTURE_RAW_LABELS:
        fail(
            "fixture raw-count table must carry every tracked construct row: "
            f"{sorted(documented_fixture_raw)} against {sorted(FIXTURE_RAW_LABELS)}"
        )
    if fixture_raw != documented_fixture_raw:
        fail("fixture raw-count table does not match the source inventory")

    census = re.search(
        r"Of the ([0-9]+) top-level fixtures, ([0-9]+) open the \(kernel\) "
        r"tenkz environment and ([0-9]+)\n"
        r"contain no tenkz public-surface construct\.",
        text,
    )
    actual_census = (
        len(expected_fixtures),
        environment_files,
        no_surface_files,
    )
    if command_only_files or setup_only_files:
        fail(
            "fixture consumer census has command-only or setup-only "
            f"consumers the document does not state: {command_only_files}, "
            f"{setup_only_files}"
        )
    if not census or tuple(map(int, census.groups())) != actual_census:
        fail(f"fixture consumer census does not match {actual_census}")

    blueprint_status = (
        f"{blueprint_total} blueprint occurrences reconcile exactly with their sources"
        if blueprint_reconciled
        else f"{blueprint_total} documented blueprint occurrences are internally "
        "consistent (sources not reconciled)"
    )
    print(
        f"PASS: {blueprint_status}; "
        f"{len(expected_fixtures)} standalone fixtures reconcile exactly"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TeXEnvironmentNestingError as error:
        fail(f"malformed TeX environment nesting: {error}")
