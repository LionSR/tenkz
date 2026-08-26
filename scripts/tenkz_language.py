#!/usr/bin/env python3
"""Generate and verify the public tenkz language registry.

The TeX registry is executable by the package and parseable here.  This tool
is the common source for the manual reference, lint aliases, and API census.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from tenkzlib.texcase import strip_comments

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "tex/tenkz/tenkz-language-registry.tex"
REFERENCE = ROOT / "docs/tenkz/chapters2/generated-language-reference.tex"
ALIASES = ROOT / "docs/tenkz/chapters2/generated-language-aliases.tex"
CONTRACT = ROOT / "docs/tenkz/LANGUAGE-1.0.md"
KERNEL = ROOT / "tex/tenkz/tenkz-kernel.code.tex"

# The closed alphabets of LANGUAGE-1.0 section 2.8, each paired with the one
# place that accepts its words.  Three are kernel parsers whose \str_case
# branches are the alphabet; the fourth is the registry's own enum.  The
# census meters count keys, not the words inside a closed alphabet (issue
# LionSR/tenkz#7), so this check is what keeps the contract's table and the
# implementation from drifting apart in either direction.
ALPHABET_PARSERS = {
    "side policy": "__tenkz_kernel_side_policy:nn",
    "routes": "__tenkz_kernel_route:n",
    "default skins": "__tenkz_kernel_skin_base_aux:nN",
}
ALPHABET_CHOICES = {"mark forms": ("tenkz-kernel-mark", "form")}
# A parser's branches are the accepted alphabet only while the parser is what
# the surface reaches.  Each entry names the text that must still carry a call
# to it: the key binding for a directly wired parser, the installing helper's
# body for the others.  This proves the one link that the rest of the gate
# rests on, not the whole runtime path.
# The side words are installed on the picture scope by a helper, so the
# generated keys are what a later block would rebind; each is checked in
# addition to the installer.
SIDE_KEYS = ("west", "east", "north", "south")
ALPHABET_REACHED_FROM = {
    "routes": ("key", "__tenkz_kernel_route:n", ("tenkz-kernel-wire", "route")),
    "side policy": (
        "macro", "__tenkz_kernel_side_policy:nn", "__tenkz_kernel_side:nn",
    ),
    "default skins": (
        "macro", "__tenkz_kernel_skin_base_aux:nN", "__tenkz_kernel_skin_base:nN",
    ),
}
# The helper that installs a choice table must still install a *choice* table:
# rewritten to an unrestricted `.code:n` handler it would accept anything,
# while its call site and word list read unchanged.
CHOICE_HELPER = "__tenkz_kernel_choice:nnnn"
# The helpers whose calls this gate already reads: the choice helper's word
# lists, and the side installer, which is checked to bind its key and call its
# parser.  A call to any other key-installing helper is a binding this gate
# has not accounted for.
# Each sanctioned installer is sanctioned only for the scope and keys this
# gate already reads it for.  The same helper aimed elsewhere -- the side
# installer at `tenkz-kernel-mark:form`, say -- is an override like any other.
SANCTIONED_INSTALLERS = {
    "__tenkz_kernel_choice:nnnn": (("tenkz-kernel-mark", "form"),),
    "__tenkz_kernel_side:nn": tuple(
        ("tenkz-kernel-picture", word) for word in ("west", "east", "north", "south")
    ),
}
# l3keys properties that decorate a key without installing the code that
# accepts its value.  Everything else replaces the handler.
ORTHOGONAL_PROPERTIES = frozenset({
    "default", "initial", "value_required", "value_forbidden", "groups", "usage",
})
# Each choice-table alphabet is also a registry enum row, and the two must
# name the same words: the registry is what the documents and tools read,
# the choice table is what the parser accepts.
ALPHABET_ENUMS = {"mark forms": ("kernel-mark", "form")}
# The contract's table holds the words that put ink on the page; `prose`
# is the recording row the sugar ledger keeps (SHRINK 2026-08-11) and is
# subtracted here, the one place the difference is spelled.
ALPHABET_RECORDING_WORDS = {"mark forms": {"prose"}}


@dataclass(frozen=True)
class Entry:
    kind: str
    fields: tuple[str, ...]


ARITIES = {
    "environment": 4,
    "command": 5,
    "key": 6,
    "alias": 4,
    "example": 3,
    "prelude": 3,
    "tombstone": 3,
}

BASELINE = ROOT / "tests/tenkz/census-baseline.json"

# The two-ledger vocabulary of the shrink gate (docs/tenkz/SHRINK.md).
# kernel: the load-bearing surface, hard one-in-one-out budget.
# sugar(<expansion>): expands mechanically into kernel spellings.
# alias(<replacement>; sunset=<milestone>): read-old-documents only.
# escape: sanctioned raw-geometry leak, metered by the escape census.
_LEDGERS = ("kernel", "sugar", "alias", "escape")
MILESTONES = ("0.8", "0.9", "1.0")
_PARSER_FAMILY_SCOPE = {
    # the surviving pgfkeys families (the dialect families died with their
    # front ends; the S4 surface swap removed the last, grid)
    "tree": "object",
    "declare atom": "atom-declaration",
    # the 1.0 kernel trees (l3keys); scopes mirror LANGUAGE-1.0.md section 2
    "kernel-picture": "kernel-picture",
    "kernel-frame": "kernel-frame",
    "kernel-atom": "kernel-atom",
    "kernel-wire": "kernel-wire",
    "kernel-mark": "kernel-mark",
    "kernel-setup": "kernel-setup",
    "kernel-declare": "kernel-declare",
    "kernel-declare-atom": "atom-declaration",
}
# The tree's `pitch=` rescopes the kernel-setup metric door for one tree,
# so the parser leaf collapses onto the kernel-setup registry row.  (The
# 0.7 dialects' broader setup forwarding left with the grid front end.)
_SETUP_FORWARDS: dict[str, set[str]] = {
    "tree": {"pitch"},
}


def parse_status(status: str) -> tuple[str, str]:
    """Return (ledger, payload); raise ValueError on unknown vocabulary."""
    if status in ("kernel", "escape"):
        return status, ""
    for ledger in ("sugar", "alias"):
        if status.startswith(ledger + "(") and status.endswith(")"):
            return ledger, status[len(ledger) + 1 : -1]
    raise ValueError(f"unknown ledger status {status!r}")


def parse_alias_payload(payload: str) -> tuple[str, str]:
    """Return an alias replacement and its supported sunset milestone."""
    match = re.fullmatch(r"(.+?)\s*;\s*sunset=([^;\s]+)", payload)
    if match is None:
        raise ValueError(
            "alias payload must be '<replacement>; sunset=<milestone>'"
        )
    replacement, sunset = match.groups()
    if sunset not in MILESTONES:
        raise ValueError(
            f"unsupported alias sunset {sunset!r}; expected one of "
            + ", ".join(MILESTONES)
        )
    return replacement.strip(), sunset


def parse_value_alias_sunset(meaning: str) -> str:
    """Return the milestone carried by a value-alias description."""
    match = re.search(r"(?:^|\s)Sunset\s+([^.\s]+(?:\.[^.\s]+)?)\.\s*$", meaning)
    if match is None:
        raise ValueError("value alias description carries no final 'Sunset M.'")
    sunset = match.group(1)
    if sunset not in MILESTONES:
        raise ValueError(
            f"unsupported value-alias sunset {sunset!r}; expected one of "
            + ", ".join(MILESTONES)
        )
    return sunset


def ledger_split(entries: list[Entry]) -> dict[str, list[tuple[str, ...]]]:
    split: dict[str, list[tuple[str, ...]]] = {ledger: [] for ledger in _LEDGERS}
    for entry in entries:
        if entry.kind != "key":
            continue
        ledger, _payload = parse_status(entry.fields[4])
        split[ledger].append(entry.fields)
    return split


def public_census(entries: list[Entry]) -> dict[str, int]:
    """Registry surface counted by M1, including commands and environments."""
    split = ledger_split(entries)
    return {
        **{ledger: len(split[ledger]) for ledger in _LEDGERS},
        "commands": sum(entry.kind == "command" for entry in entries),
        "environments": sum(entry.kind == "environment" for entry in entries),
    }


def _split_top_level_commas(text: str) -> list[str]:
    """Split a registry expression without cutting commas inside braces."""
    parts: list[str] = []
    start = 0
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char in "{[(":
            depth += 1
        elif char in "}])":
            depth -= 1
            if depth < 0:
                raise ValueError(f"unbalanced registry expression {text!r}")
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
        index += 1
    if depth:
        raise ValueError(f"unbalanced registry expression {text!r}")
    parts.append(text[start:].strip())
    return parts


def parse_key_expression(expression: str) -> list[tuple[str, str | None]]:
    """Parse a complete comma-separated key or key=value expression."""
    parsed: list[tuple[str, str | None]] = []
    for fragment in _split_top_level_commas(expression):
        match = re.fullmatch(r"([a-z][a-z ~]*?)(?:\s*=(.*))?", fragment)
        if match is None:
            raise ValueError(f"invalid key-expression fragment {fragment!r}")
        name, value = match.groups()
        parsed.append((name.replace("~", " ").strip(), value))
    if not parsed:
        raise ValueError("empty key expression")
    return parsed


def _enum_value_error(
    target: str,
    value: str | None,
    target_record: tuple[str, str],
) -> str | None:
    """Describe an invalid explicit enum value in a registry rewrite."""
    if value is None:
        return None
    value_type = target_record[1]
    enum = re.fullmatch(r"enum\(([^)]*)\)", value_type)
    if enum is not None and value not in enum.group(1).split("|"):
        return f"replacement value {value!r} for {target!r} is not in {value_type}"
    return None


def _group(text: str, start: int) -> tuple[str, int]:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != "{":
        raise ValueError(f"expected '{{' at registry offset {start}")
    depth = 1
    out: list[str] = []
    i = start + 1
    while i < len(text) and depth:
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            out.extend((char, text[i + 1]))
            i += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return "".join(out).strip(), i + 1
        out.append(char)
        i += 1
    raise ValueError(f"unclosed registry group at offset {start}")


def load_registry() -> list[Entry]:
    # A record the file comments out does not run, so the tools may not read
    # it either; otherwise the registry means one thing to TeX and another to
    # everything that checks it.  The shared reader blanks a comment in place,
    # so every offset below is the offset in the file.
    text = strip_comments(REGISTRY.read_text(encoding="utf-8"))
    pattern = re.compile(
        r"\\__tenkz_language_registry_"
        r"(environment|command|key|alias|example|prelude|tombstone):[n]+"
    )
    entries: list[Entry] = []
    for match in pattern.finditer(text):
        kind = match.group(1)
        pos = match.end()
        fields: list[str] = []
        for _ in range(ARITIES[kind]):
            field, pos = _group(text, pos)
            fields.append(field)
        entries.append(Entry(kind, tuple(fields)))
    return entries


def _declared_api() -> tuple[set[str], set[str]]:
    commands: set[str] = {"tnset"}
    environments: set[str] = set()
    for path in (ROOT / "tex/tenkz").glob("*.code.tex"):
        text = path.read_text(encoding="utf-8")
        commands.update(re.findall(r"\\NewDocumentCommand\s+\\([A-Za-z]+)", text))
        commands.update(
            public
            for public, implementation in re.findall(
                r"\\cs_set_eq:NN\s+\\([A-Za-z]+)"
                r"\s+\\(__tenkz_kernel_[A-Za-z_]+_cmd)",
                text,
            )
            if "_env_" not in implementation
        )
        environments.update(
            re.findall(r"\\NewDocumentEnvironment\s*\{\s*([A-Za-z]+)", text)
        )
    return commands, environments


def _parser_leaf_keys_from_texts(texts: Iterable[str]) -> set[tuple[str, str]]:
    """Collect public leaf-key spellings from TeX parser source texts."""
    leaves: set[tuple[str, str]] = set()
    leaf = re.compile(
        r"/tenkz/([^/,{]+?)/([^/,{]+?)/\.(?:code|store~in|is~choice)"
        r"(?=\s*[,=])"
    )
    root_leaf = re.compile(
        r"/tenkz/([^/,{]+?)/\.(?:code|store~in|is~choice)(?=\s*[,=])"
    )
    forwards = re.compile(
        r"(?m)^\\tenkz_install_core_forwards:nn\s*\{[^}]+\}\s*\{([^}]+)\}"
    )
    for text in texts:
        for match in leaf.finditer(text):
            family = match.group(1).replace("~", " ").strip()
            name = match.group(2).replace("~", " ").strip()
            if family not in {"#1", "tensor style"} and name != ".unknown":
                leaves.add((family, name))
        for match in forwards.finditer(text):
            family_match = re.search(r"\{([^}]+)\}", match.group(0))
            assert family_match is not None
            family = family_match.group(1).replace("~", " ").strip()
            leaves.update(
                (family, item.replace("~", " ").strip())
                for item in match.group(1).split(",")
            )
        for match in root_leaf.finditer(text):
            name = match.group(1).replace("~", " ").strip()
            # `pitch` is the internal metric door the kernel-setup pitch row
            # delegates to (tenkz-language.code.tex); since the S4 surface
            # swap no public spelling reaches the /tenkz root directly, so
            # the door is plumbing, not a census leaf.
            if name not in {"", "declare atom", "pitch"}:
                leaves.add(("setup", name))
    return leaves


# Extension-gate: #4687; Census-correction: #4753 includes hyphenated
# kernel families in the parser-path census.
_KERNEL_HELPER = re.compile(
    r"\\__tenkz_kernel_"
    r"(?:value:nnn|choice:nnnn|flag:nnn|positive_integer:nnnnnn|side:nn"
    r"|label_pos:nn)\s*"
    r"\{\s*tenkz-kernel-([a-z]+(?:-[a-z]+)*)\s*\}\s*\{\s*([^}]+?)\s*\}"
)
_KERNEL_BLOCK = re.compile(
    r"\\keys_define:nn\s*\{\s*tenkz-kernel-([a-z]+(?:-[a-z]+)*)\s*\}"
)
_KERNEL_LINE = re.compile(
    r"^\s*([a-z][a-z ~-]*?)\s*\.(?:code:n|meta:n|choices:nn)\s*="
)


def _kernel_leaf_keys_from_texts(texts) -> set[tuple[str, str]]:
    """Collect l3keys leaves installed by the kernel language stage."""
    leaves: set[tuple[str, str]] = set()
    for text in texts:
        for match in _KERNEL_HELPER.finditer(text):
            leaves.add((f"kernel-{match.group(1)}",
                        match.group(2).replace("~", " ").strip()))
        family = None
        depth = 0
        for line in text.splitlines():
            if family is None:
                block = _KERNEL_BLOCK.search(line)
                if block:
                    family = f"kernel-{block.group(1)}"
                    depth = line.count("{") - line.count("}")
                continue
            depth += line.count("{") - line.count("}")
            key = _KERNEL_LINE.match(line)
            if key and key.group(1).strip() != "unknown":
                leaves.add((family, key.group(1).replace("~", " ").strip()))
            if depth <= 0:
                family = None
    return leaves


# A word struck from a live key's alphabet stays installed as a branch that
# refuses the spelling and states the migration.  Reading those branches is
# what lets the language check hold the registry's tombstone ledger and the
# parser to one list; the lookahead skips the helper's own definition, whose
# next token is a parameter rather than an argument group.
_KERNEL_TOMBSTONE = re.compile(r"\\__tenkz_kernel_tombstone:nnnn\s*(?=\{)")


def _sentence(text: str) -> str:
    """Read an expl3 argument as the sentence a reader is shown."""
    return " ".join(text.replace("~", " ").split())


def tombstone_shape(scope: str, spelling: str) -> str:
    """Which kind of dead spelling a row states.

    `command` and `environment` are named by the scope they take, since a
    retired environment's spelling is an ordinary word.  `value` is a word
    struck from a live key's alphabet and `key` a key that no longer exists.
    `malformed` is a row that states no spelling at all: an empty one, or a
    key with an equals sign and nothing after it, which would otherwise pass
    as a bare key and ban a live word.
    """
    if not spelling:
        return "malformed"
    if spelling.startswith("\\"):
        return "command"
    if scope == "environment":
        return "environment"
    key, separator, value = spelling.partition("=")
    if not key.strip() or (separator and not value.strip()):
        return "malformed"
    return "value" if separator else "key"


def _kernel_tombstones_from_texts(texts: Iterable[str]) -> dict[tuple[str, str], str]:
    """Collect the spellings the kernel parser refuses by name and their migrations."""
    tombstones: dict[tuple[str, str], str] = {}
    for text in texts:
        # A branch the file comments out does not run, so TeX accepts the
        # spelling again; reading the raw text would keep counting it as a
        # refusal and report a pairing the parser no longer holds.
        text = strip_comments(text)
        for match in _KERNEL_TOMBSTONE.finditer(text):
            position = match.end()
            fields: list[str] = []
            for _ in range(4):
                field, position = _group(text, position)
                fields.append(field)
            family, key, value, migration = (_sentence(field) for field in fields)
            scope = family.removeprefix("tenkz-")
            tombstones[(scope, f"{key}={value}")] = migration
    return tombstones


def _kernel_tombstones() -> dict[tuple[str, str], str]:
    return _kernel_tombstones_from_texts(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "tex/tenkz").glob("*.code.tex")
    )


# A bare tombstone row bans its word from case source, and the word may
# outlive the key that died inside alphabets the registry types opaquely.
# The parsers state those alphabets -- the kernel's choice tables, the
# wire-end grammar whose open words follow the word `open', and the
# declaration door's compass faces spelled `<word>:<type>' -- so the live
# owners are read from the parser source, exactly as the refused spellings
# above are: adding or retiring a word is one parser edit and no edit here.
_KERNEL_CHOICE = re.compile(r"\\__tenkz_kernel_choice:nnnn\s*(?=\{)")
_KERNEL_OPEN_WORDS = re.compile(r"\\A\s+open\s+\\s\+\s+\(([a-z|]+)\)\s+\\Z")
_DECLAREATOM_FACES = re.compile(
    r"\\A\s+\\s\*\s+\(([a-z|]+)\)\s+:\s+\(([a-z|]+)\)\s+\\s\*\s+\\Z"
)


def _live_word_owners_from_texts(
    texts: Iterable[str],
) -> dict[str, set[tuple[str, str]]]:
    """Collect each parser-held word with the live spellings that carry it.

    The value is a set of frames, the text standing before and after the
    word in source: a choice word is carried as `<key>=<word>`, an open end
    word as `open <word>`, a declaration face word as `<word>:<type>`.  A
    pattern built for a dead bare key steps over these, so a live spelling
    of the surviving word is never reported as the dead key.  The face
    frames take every word-type pair the extraction admits, including the
    pairs validation then refuses; a refused pair never stands in a
    compiling document, so stepping over it passes nothing a compile would
    not already answer.
    """
    owners: dict[str, set[tuple[str, str]]] = {}
    for text in texts:
        text = strip_comments(text)
        for match in _KERNEL_CHOICE.finditer(text):
            position = match.end()
            fields: list[str] = []
            for _ in range(3):
                field, position = _group(text, position)
                fields.append(field)
            _family, key, words = (_sentence(field) for field in fields)
            for word in words.split(","):
                owners.setdefault(word.strip(), set()).add((f"{key}=", ""))
        for match in _KERNEL_OPEN_WORDS.finditer(text):
            for word in match.group(1).split("|"):
                owners.setdefault(word.strip(), set()).add(("open ", ""))
        for match in _DECLAREATOM_FACES.finditer(text):
            for word in match.group(1).split("|"):
                for port_type in match.group(2).split("|"):
                    owners.setdefault(word.strip(), set()).add(
                        ("", f":{port_type.strip()}")
                    )
    return owners


def live_word_owners() -> dict[str, set[tuple[str, str]]]:
    """Parser-held words and the live frames that carry them, read from the kernel source."""
    return _live_word_owners_from_texts(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "tex/tenkz").glob("*.code.tex")
    )


def tombstone_rows(entries: list[Entry]) -> list[tuple[str, str, str]]:
    """The ledger's rows as scope, spelling, and migration a reader is shown.

    The registry writes a multi-word key the parser's way, with `~` for the
    space, and wraps a long migration to keep its line short.  Neither is
    visible in a document, so both are read out here rather than at each of
    the three places that consume a row: the check, the lint, and a reader.
    """
    return [
        (entry.fields[0], _sentence(entry.fields[1]), _sentence(entry.fields[2]))
        for entry in entries
        if entry.kind == "tombstone"
    ]


def tombstone_errors(
    rows: list[tuple[str, str, str]],
    key_vocabulary: dict[tuple[str, str], tuple[str, str]],
    surface: dict[str, set[str]],
    kernel: dict[tuple[str, str], str],
) -> list[str]:
    """Hold the tombstone ledger, the live vocabulary, and the parser to one list.

    A row spelled `key=value` is a word struck from a live alphabet: the key
    must still exist, the word must not, and the parser must refuse the
    spelling with the migration the ledger states.  A bare row is a key that
    no longer exists, and a command or an environment row is one of those,
    checked against `surface`; none of the three leaves anything for the
    parser to branch on, so the check is that the spelling really is gone and
    only the lint reads the row.

    Rows arrive from `tombstone_rows`, which has already read `~` and any
    wrapping out of them, so every comparison here is against the spelling
    and the sentence a document and a reader actually carry.
    """
    errors: list[str] = []
    recorded: dict[tuple[str, str], str] = {}
    # Rows already reported for a word the alphabet still holds.
    stale: set[tuple[str, str]] = set()
    scopes = {scope for scope, _name in key_vocabulary}
    # The lint matches a spelling in flat source, where no scope is visible,
    # so one spelling buried twice would be reported with whichever migration
    # sorted first.  A ledger the lint can read is one spelling per row.
    seen: set[str] = set()
    for scope, spelling, migration in rows:
        if spelling in seen:
            errors.append(f"tombstone {scope}:{spelling} is recorded twice")
        seen.add(spelling)
        if not migration:
            errors.append(f"tombstone {scope}:{spelling} names no migration")
        shape = tombstone_shape(scope, spelling)
        if shape == "malformed":
            errors.append(
                f"tombstone {scope}:{spelling!r} states no spelling; a row is "
                "a command, an environment, a key, or key=value"
            )
            continue
        if shape in {"command", "environment"}:
            # A dead command or environment has no key scope to sit in, so it
            # says so; the spelling would otherwise be read as a key and the
            # lint would look for it as a bare word.
            if scope != shape:
                errors.append(
                    f"tombstone {scope}:{spelling} is a {shape} and takes "
                    f"the scope '{shape}'"
                )
            elif spelling.removeprefix("\\") in surface.get(shape, set()):
                errors.append(
                    f"tombstone {scope}:{spelling} names a {shape} the "
                    "registry still carries"
                )
            continue
        if scope not in scopes:
            errors.append(
                f"tombstone {scope}:{spelling} names no registered scope"
            )
            continue
        key, _separator, value = spelling.partition("=")
        key, value = key.strip(), value.strip()
        if shape == "key":
            if (scope, key) in key_vocabulary:
                errors.append(
                    f"tombstone {scope}:{spelling} names a key the registry "
                    "still carries"
                )
            continue
        record = key_vocabulary.get((scope, key))
        if record is None:
            errors.append(
                f"tombstone {scope}:{spelling} names no registered key"
            )
            continue
        enum = re.fullmatch(r"enum\(([^)]*)\)", record[1])
        if enum is not None and value in enum.group(1).split("|"):
            errors.append(
                f"tombstone {scope}:{spelling} is still a word of {record[1]}"
            )
            # A row landing ahead of its parser branch has one cause, and it
            # is this one.  The row stays recorded so the parser's own list is
            # still compared against it, but it is not reported a second time
            # as a spelling the parser does not refuse, which is true and
            # points at the wrong thing.
            stale.add((scope, f"{key}={value}"))
        recorded[(scope, f"{key}={value}")] = migration
    unrecorded = sorted(
        f"{scope}:{spelling}" for scope, spelling in kernel.keys() - recorded.keys()
    )
    if unrecorded:
        errors.append(
            "the parser refuses spellings the tombstone ledger does not record: "
            + ", ".join(unrecorded)
        )
    unrefused = sorted(
        f"{scope}:{spelling}"
        for scope, spelling in recorded.keys() - kernel.keys() - stale
    )
    if unrefused:
        errors.append(
            "the tombstone ledger records spellings the parser does not refuse: "
            + ", ".join(unrefused)
        )
    for scope, spelling in sorted(recorded.keys() & kernel.keys()):
        if recorded[(scope, spelling)] != kernel[(scope, spelling)]:
            errors.append(
                f"tombstone {scope}:{spelling} migrates to "
                f"{recorded[(scope, spelling)]!r} in the ledger and "
                f"{kernel[(scope, spelling)]!r} in the parser"
            )
    return errors


def contract_alphabets(text: str) -> dict[str, list[str]]:
    """Read the section 2.8 table: one row per alphabet, words in backticks.

    The reader is total over the table: the header and its delimiter are the
    only rows it skips, and every other row must be one alphabet name and a
    cell of backticked words.  A row it cannot account for is an error rather
    than a line it steps over, because a row the contract renders and this
    reader ignores is exactly the drift the gate exists to catch.
    """
    # A fenced block is a code sample: a heading inside one renders as text,
    # not as a section of the contract.
    unfenced = re.sub(r"^```.*?^```", lambda m: "\n" * m.group(0).count("\n"),
                      text, flags=re.M | re.S)
    sections = list(re.finditer(
        r"^### 2\.8 [^\n]*\n(.*?)(?=^#{2,3} |\Z)", unfenced, re.M | re.S
    ))
    if not sections:
        raise ValueError("LANGUAGE-1.0 has no section 2.8")
    # Two sections are two contracts, and a reader of the first would not see
    # the second even though the document publishes both.
    if len(sections) > 1:
        raise ValueError(f"LANGUAGE-1.0 has {len(sections)} section 2.8s")
    section = sections[0]
    alphabets: dict[str, list[str]] = {}
    seen_header = False
    seen_delimiter = False
    ended = False
    header_width = 0
    for line in section.group(1).splitlines():
        # Markdown allows up to three spaces of indentation before a row, and
        # renders it inside the table, so the reader must see it there too.
        row = line[:3].lstrip(" ") + line[3:]
        if ended and row.startswith("|"):
            raise ValueError(
                f"section 2.8 carries a second table below its first: {row!r}"
            )
        if not row.startswith("|"):
            # Markdown ends the table at the first line that is not a row, so
            # prose after the last row simply ends it -- with or without a
            # blank line between.  Before any row has been read, though, the
            # table is empty and whatever pipe-prefixed lines follow are not
            # its rows.
            if seen_delimiter:
                if not row.strip():
                    # A blank line ends the table, with or without rows above
                    # it; reading on would take later pipe-prefixed lines for
                    # rows of a table Markdown has already closed.
                    ended = True
                    continue
                if alphabets:
                    # The table has ended.  What follows is prose -- and must
                    # stay prose: a second table below it would be a second
                    # contract in the same section.
                    ended = True
                    continue
                if row.strip():
                    raise ValueError(
                        f"section 2.8's table is empty and interrupted by "
                        f"{row!r}"
                    )
            continue
        # One leading and one trailing border pipe, not every pipe: `||`
        # ends of a row are empty cells, and stripping them would read a
        # differently shaped table as the one expected here.
        trimmed = row.strip()
        body_cells = trimmed[1:] if trimmed.startswith("|") else trimmed
        body_cells = body_cells[:-1] if body_cells.endswith("|") else body_cells
        cells = [cell.strip() for cell in body_cells.split("|")]
        if not seen_header:
            seen_header = True
            header_width = len(cells)
            if header_width != 2:
                raise ValueError(
                    f"section 2.8 header has {header_width} cell(s), not two"
                )
            # The labels say what the rows below mean.  Renamed, the same rows
            # would be read as an alphabet table while the contract rendered
            # something else.
            if [cell.lower() for cell in cells] != ["alphabet", "words"]:
                raise ValueError(
                    f"section 2.8 header reads {cells!r}, not "
                    "['Alphabet', 'Words']"
                )
            continue
        if not seen_delimiter:
            # Markdown wants at least three hyphens in a delimiter cell;
            # `|-|-|` renders as text, not as the table read below.
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                raise ValueError(f"section 2.8 has no delimiter row; found {row!r}")
            # A delimiter of a different width does not form the two-column
            # table the rows are read as, so the shape is checked, not just
            # the characters.
            if len(cells) != header_width:
                raise ValueError(
                    f"section 2.8 delimiter has {len(cells)} cell(s) against a "
                    f"{header_width}-cell header"
                )
            seen_delimiter = True
            continue
        if len(cells) != 2 or not cells[0]:
            raise ValueError(f"section 2.8 has a row this reader cannot name: {row!r}")
        name, cell = cells
        # One row per alphabet: a second row for one name would let a
        # conflicting definition stand unread above the canonical one.
        if name in alphabets:
            raise ValueError(f"section 2.8 lists {name!r} twice")
        # The cell is backticked words and the space between them, nothing
        # else: bare text beside them would read as a word to a person and be
        # invisible to `findall`.
        if not re.fullmatch(r"(?:`[^`]+`\s*)+", cell):
            raise ValueError(
                f"section 2.8 row {name!r} has words this reader cannot name: {cell!r}"
            )
        alphabets[name] = re.findall(r"`([^`]+)`", cell)
    if not alphabets:
        raise ValueError("section 2.8 lists no alphabets")
    return alphabets


# expl3 and TeX spellings that install a body under a name.  A control
# sequence bound by any of them is a definition of it; `cs_generate_variant`
# is deliberately absent, since it derives a differently-signatured sibling
# and leaves the base alone.
def preceded_by_definition(text: str, position: int) -> bool:
    """Whether a definition token stands immediately before `position`.

    The whitespace between the token and the name is walked rather than
    bounded: a comment stripped to blanks can leave any amount of it, and a
    fixed window would miss the token behind a long one.  Only the token
    itself is then matched, so this stays linear.
    """
    cursor = position
    while cursor > 0 and text[cursor - 1].isspace():
        cursor -= 1
    return DEFINITION_TOKEN.search(text[max(0, cursor - 64):cursor]) is not None


DEFINITION_TOKEN = re.compile(
    r"\\(?:cs_(?:new|set|gset|undefine|gundefine)[a-z_]*:[A-Za-z]*"
    # `\\ProvideDocumentCommand` leaves an existing command alone, so it
    # binds nothing when one is already defined and is not counted.
    r"|(?:New|Renew|Declare)DocumentCommand"
    r"|let|[egx]?def)$"
)


# expl3's error-raising operations, `\\msg_expandable_error` included: any of
# them in a branch means the word is refused, not accepted.
REFUSAL = re.compile(r"\\msg_(?:[a-z_]*_)?(?:error|fatal|critical)(?::|\s)")
NAME_DEFINITION = re.compile(
    r"\\cs_(?:new|set|gset|undefine|gundefine)[a-z_]*:c[A-Za-z]*\s*\{\s*([^}]*?)\s*\}"
)


def macro_body(text: str, macro: str, start: int) -> str:
    """The balanced replacement text of the definition beginning at `start`.

    Reading to the next `\\cs_new_protected:Npn` instead would swallow any
    helper declared with another spelling, and attribute its tables to this
    parser.
    """
    cursor = text.index(macro, start) + len(macro)
    brace = text.find("{", cursor)
    if brace < 0:
        raise ValueError(f"definition of {macro} has no body")
    body, _ = _group(text, brace)
    return body


def macro_definitions(text: str, macro: str) -> list[int]:
    """Offsets at which `macro` is bound, in file order.

    Every occurrence is classified by the control sequence that precedes it,
    so a replacement spelt `\\cs_set:Nn` or `\\cs_set_eq:NN` counts as one
    definition just as `\\cs_new_protected:Npn` does, and so does a removal
    spelt `\\cs_undefine:N` -- after it the original body is not what runs
    either.  TeX runs the last binding, so a reader of the first would
    compare an alphabet the parser no longer has.
    """
    offsets: list[int] = []
    for match in re.finditer(r"\\" + re.escape(macro) + r"(?![A-Za-z_:])", text):
        if preceded_by_definition(text, match.start()):
            offsets.append(match.start())
    # A `:c` assignment names its target as text, so no backslashed occurrence
    # of the macro appears at the binding site at all.
    offsets.extend(
        match.start() for match in NAME_DEFINITION.finditer(text)
        if match.group(1) == macro
    )
    return sorted(offsets)


def kernel_case_words(text: str, macro: str) -> list[str]:
    """The ``\\str_case`` branch words of one kernel parser, in file order."""
    definitions = macro_definitions(text, macro)
    if not definitions:
        raise ValueError(f"kernel defines no parser {macro}")
    if len(definitions) > 1:
        raise ValueError(
            f"kernel defines {macro} {len(definitions)} times; "
            "the last would decide what the parser accepts"
        )
    body = macro_body(text, macro, definitions[0])
    cases = list(re.finditer(r"\\str_case:([A-Za-z]+)\s*(?:\\[A-Za-z_]+|\{[^}]*\})\s*", body))
    if not cases:
        raise ValueError(f"parser {macro} has no \\str_case")
    # A second table in the same body is a second acceptance path, and its
    # words would never be compared against the contract.
    if len(cases) > 1:
        raise ValueError(
            f"parser {macro} has {len(cases)} case tables; only the first "
            "would be read as its alphabet"
        )
    # A closed alphabet is closed by its fallback: without one, a value
    # outside the list completes silently and the branches describe nothing.
    signature = cases[0].group(1)
    if not signature.endswith("F") and not signature.endswith("TF"):
        raise ValueError(
            f"parser {macro} matches with \\str_case:{signature}, which has no "
            "fallback, so an unmatched value is accepted in silence"
        )
    branches, after = _group(body, cases[0].end())
    # `TF` takes the matched branch first and the unmatched branch second, so
    # the group that must refuse is the second one; reading the first would
    # accept a table that errors on every documented word and passes every
    # undocumented one.
    if signature.endswith("TF"):
        matched, after = _group(body, after)
        if REFUSAL.search(matched):
            raise ValueError(
                f"parser {macro} refuses in the branch it takes when a word "
                "matches"
            )
    fallback, _ = _group(body, after)
    if not REFUSAL.search(fallback):
        raise ValueError(
            f"parser {macro} has a fallback that does not refuse an unmatched "
            "value"
        )
    words: list[str] = []
    offset = 0
    while True:
        while offset < len(branches) and branches[offset].isspace():
            offset += 1
        if offset >= len(branches):
            return words
        word, offset = _group(branches, offset)
        # A branch key is one word of a closed alphabet.  Anything else --
        # a spelling this reader cannot name, an expansion, a nested group --
        # is reported rather than skipped, because a branch dropped here is a
        # word the gate would never compare (LionSR/tenkz#7).
        if not re.fullmatch(r"[a-z][a-z0-9-]*", word.strip()):
            raise ValueError(
                f"parser {macro} has a branch key this reader cannot name: "
                f"{word.strip()!r}"
            )
        action, offset = _group(branches, offset)
        # A label whose branch refuses is not an accepted word: the contract
        # would promise a spelling the parser answers with a diagnostic.
        if REFUSAL.search(action):
            raise ValueError(
                f"parser {macro} lists {word.strip()!r} as a case but its "
                "branch refuses the word"
            )
        words.append(word.strip())


def kernel_choice_words(text: str, scope: str, key: str) -> list[str]:
    """The words a `\\__tenkz_kernel_choice:nnnn` table accepts for one key."""
    bodies = named_macro_bodies(text)
    dormant = [
        (begin, end) for begin, end, name in bodies
        if not runs_at_load(text, name, bodies)
    ]
    matches = [
        call for call in re.finditer(
            r"\\__tenkz_kernel_choice:[a-zA-Z]{4}\s*\{\s*" + re.escape(scope)
            + r"\s*\}\s*\{\s*" + re.escape(key) + r"\s*\}",
            text,
        )
        # A call inside a macro body installs nothing until that macro runs.
        if not any(begin <= call.start() < end for begin, end in dormant)
    ]
    if not matches:
        raise ValueError(f"kernel installs no choice table for {scope}:{key}")
    # Every invocation installs its choices with `\keys_define:nn`, so a second
    # one silently decides what the parser accepts while a reader of the first
    # sees the stale list.  One definition per key, or the gate says so.
    if len(matches) > 1:
        raise ValueError(
            f"kernel installs {len(matches)} choice tables for {scope}:{key}; "
            "the last would decide what the parser accepts"
        )
    words, _ = _group(text, matches[0].end())
    return [word.strip() for word in words.split(",") if word.strip()]


def macro_body_spans(text: str) -> list[tuple[int, int]]:
    """The replacement-text spans of every macro definition in `text`."""
    return [(begin, end) for begin, end, _name in named_macro_bodies(text)]


def named_macro_bodies(text: str) -> list[tuple[int, int, str]]:
    """Each macro definition's body span, with the name it defines."""
    spans: list[tuple[int, int, str]] = []
    for match in re.finditer(
        r"(?:\\cs_(?:new|set|gset)[a-z_]*:Np[nx]\s*"
        r"|\\(?:New|Renew|Provide|Declare)DocumentCommand\s*)"
        r"\\([A-Za-z_@]+(?::[a-zA-Z]*)?)", text
    ):
        # An xparse declaration puts its argument specification between the
        # name and the body, so the body is the group after that one.
        brace = text.find("{", match.end())
        if "DocumentCommand" in match.group(0) and brace >= 0:
            try:
                _spec, after = _group(text, brace)
                brace = text.find("{", after)
            except ValueError:
                brace = -1
        if brace < 0:
            continue
        try:
            body, end = _group(text, brace)
        except ValueError:
            continue
        spans.append((brace, end, match.group(1)))
    return spans


def key_installing_helpers(text: str) -> list[str]:
    """Kernel helpers whose body binds their second argument in their first.

    `\\__tenkz_kernel_value:nnn { scope } { key } { stage }` installs a
    handler as surely as a literal `\\keys_define:nn` block does, so a call to
    one is a binding of that key.  The choice helper is excluded: its calls
    are the sanctioned ones this gate already reads.
    """
    helpers: list[str] = []
    for match in re.finditer(
        r"\\cs_(?:new|set|gset)[a-z_]*:Np[nx]\s*"
        r"\\(__tenkz_kernel_[A-Za-z_]*:[a-zA-Z]+)", text
    ):
        name = match.group(1)

        try:
            body = macro_body(text, name, match.start())
        except ValueError:
            continue
        if re.search(r"\\keys_define:[a-zA-Z]{2}\s*\{\s*#1\s*\}", body) and re.search(
            r"#2\s*\.[a-z_]+:", body
        ):
            helpers.append(name)
    return helpers


def top_level_entries(block: str) -> list[str]:
    """The comma-separated entries of one l3keys block, brace depth respected.

    A nested handler body may itself contain `, key .code:n = ...`, and a
    comma inside braces is not a separator of the outer block -- reading it as
    one reports a rebinding that is not there.
    """
    entries: list[str] = []
    depth = 0
    current: list[str] = []
    escaped = False
    for character in block:
        if escaped:
            escaped = False
            current.append(character)
            continue
        if character == "\\":
            # `\{` and `\}` are control symbols, not group delimiters, and
            # counting them would put the reader at the wrong depth for every
            # entry after them.
            escaped = True
            current.append(character)
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
        if character == "," and depth == 0:
            entries.append("".join(current))
            current = []
            continue
        current.append(character)
    entries.append("".join(current))
    return entries


def runs_at_load(text: str, macro: str, bodies: list[tuple[int, int, str]]) -> bool:
    """Whether `macro` is called from outside every macro body.

    A definition inside a body executes when that body does, so a body that
    something calls at load installs its keys at load.  This follows one link,
    not the whole call graph: a macro called only from another dormant macro
    reads as dormant, which is the safe direction -- it under-reports rather
    than failing a kernel TeX accepts.
    """
    for call in re.finditer(r"\\" + re.escape(macro) + r"(?![A-Za-z_:])", text):
        if preceded_by_definition(text, call.start()):
            continue
        if not any(begin <= call.start() < end for begin, end, _ in bodies):
            return True
    return False


def key_definitions(text: str, scope: str, key: str) -> int:
    """How many times `key` is bound in `scope`, by any spelling.

    The helper installs its choices with `\\keys_define:nn`, and so can any
    later code: a direct `key .code:n = { ... }` in the same scope replaces
    the handler and can accept words the helper's list does not carry.
    Counting only calls to the helper would read that override as absent.
    """
    bindings = 0
    bodies = named_macro_bodies(text)
    # A body that something calls at load installs its keys at load, so only
    # the bodies nothing reaches are dormant.
    dormant = [
        (begin, end) for begin, end, name in bodies
        if not runs_at_load(text, name, bodies)
    ]
    # A kernel helper that binds its second argument in its first installs a
    # handler as surely as a literal block does -- when it is called at load,
    # not from inside another macro's body.
    for helper in key_installing_helpers(text):
        if (scope, key) in SANCTIONED_INSTALLERS.get(helper, ()):
            continue
        bindings += sum(
            1 for call in re.finditer(
                r"\\" + re.escape(helper) + r"\s*\{\s*" + re.escape(scope)
                + r"\s*\}\s*\{\s*" + re.escape(key) + r"\s*\}",
                text,
            )
            if not any(begin <= call.start() < end for begin, end in dormant)
        )
    # `\\keys_define` has argument variants, and a generated one installs the
    # same handler, so the operation is matched by name rather than by one
    # signature.
    for match in re.finditer(r"\\keys_define:[a-zA-Z]{2}\s*", text):
        # A block inside a macro body runs when that macro is called, not at
        # load, so counting it would report a binding TeX never installs.
        if any(begin <= match.start() < end for begin, end in dormant):
            continue
        try:
            named, offset = _group(text, match.end())
            body, _ = _group(text, offset)
        except ValueError:
            # A scope this reader cannot read -- an unbraced variable from a
            # `:Vn` variant -- is reported, not skipped: a skip here is a
            # binding the gate never sees.
            raise ValueError(
                f"a \\keys_define call near offset {match.start()} takes a "
                "scope this reader cannot read"
            )
        if named.strip() != scope:
            continue
        # Read the other way round: a property binds the key unless it is one
        # of the few that only decorate it.  An allowlist of handler-setting
        # properties would miss the next spelling -- `.tl_set:N` accepts any
        # value where `.choices:nn` accepted a list -- and l3keys has more of
        # them than a gate should try to enumerate.
        for entry in top_level_entries(body):
            # `form / label .code:n` customises one branch of an existing
            # choice; the parent key's handler and its alphabet are untouched,
            # so counting it as an override would report one that is not there.
            # `form / unknown` is the exception: it replaces the refusal.
            property_match = re.match(
                r"\s*" + re.escape(key)
                + r"\s*(?:/\s*(?P<branch>[^.\s]+)\s*)?\.([a-z_]+):", entry
            )
            if property_match and property_match.group("branch") not in (None, "unknown"):
                continue
            if property_match and property_match.group(2) not in ORTHOGONAL_PROPERTIES:
                bindings += 1
    return bindings


def _sole_definition(text: str, macro: str) -> int:
    """The offset of `macro`'s one definition, or a reason there is not one."""
    definitions = macro_definitions(text, macro)
    if not definitions:
        raise ValueError(f"kernel defines no {macro}")
    if len(definitions) > 1:
        raise ValueError(f"kernel defines {macro} {len(definitions)} times")
    return definitions[0]


def key_binding_body(text: str, scope: str, key: str) -> str:
    """The replacement text bound to `key` in `scope`.

    More than one binding is refused rather than resolved: the last would be
    the effective handler, and reading the first would let an added block
    rewire the key while the original binding went on satisfying the check.
    """
    bodies: list[str] = []
    # A helper call binds the key as surely as a literal block does; the route
    # reader must count them for the same reason the override audit does.
    installed = key_definitions(text, scope, key)
    defined = named_macro_bodies(text)
    dormant = [
        (begin, end) for begin, end, name in defined
        if not runs_at_load(text, name, defined)
    ]
    for match in re.finditer(r"\\keys_define:[a-zA-Z]{2}\s*", text):
        # A block inside a macro body runs when that macro is called, not at
        # load; counting it would report a binding TeX never installs.
        if any(begin <= match.start() < end for begin, end in dormant):
            continue
        try:
            named, offset = _group(text, match.end())
            block, _ = _group(text, offset)
        except ValueError:
            # A call whose scope this reader cannot read -- an unbraced
            # variable from a `:Vn` variant -- is reported, not skipped: a
            # skip here is a binding the gate never sees.
            raise ValueError(
                f"a \\keys_define call near offset {match.start()} takes a scope "
                "this reader cannot read"
            )
        if named.strip() != scope:
            continue
        # A key may be assigned more than once inside one block, and l3keys
        # installs the last, so every assignment is collected.
        # A key may be assigned more than once inside one block, and l3keys
        # installs the last, so every assignment is collected.  A property
        # other than `.code:n` installs a handler this reader cannot read --
        # `.tl_set:N` accepts any value -- and saying so is the honest answer.
        for entry in top_level_entries(block):
            binding = re.match(
                r"\s*" + re.escape(key) + r"\s*\.([a-z_]+):[A-Za-z]*\s*=\s*", entry
            )
            if binding is None or binding.group(1) in ORTHOGONAL_PROPERTIES:
                continue
            if binding.group(1) != "code":
                raise ValueError(
                    f"{scope}:{key} is bound with .{binding.group(1)}, whose "
                    "handler this gate cannot read"
                )
            body, _ = _group(entry, binding.end())
            bodies.append(body)
    if not bodies:
        raise ValueError(f"no .code:n binding for {scope}:{key}")
    if installed > len(bodies):
        raise ValueError(
            f"{scope}:{key} is bound {installed} times, at least one through "
            "a key-installing helper; the last would be the effective handler"
        )
    if len(bodies) > 1:
        raise ValueError(
            f"{scope}:{key} is bound {len(bodies)} times; the last would be "
            "the effective handler"
        )
    return bodies[0]


def alphabet_errors(
    entries: list[Entry],
    contract_text: str | None = None,
    kernel_text: str | None = None,
) -> list[str]:
    """Every section 2.8 row equals the word set its acceptor holds."""
    contract_text = (
        CONTRACT.read_text(encoding="utf-8") if contract_text is None else contract_text
    )
    kernel_text = (
        strip_comments(KERNEL.read_text(encoding="utf-8"))
        if kernel_text is None
        else strip_comments(kernel_text)
    )
    errors: list[str] = []
    try:
        contract = contract_alphabets(contract_text)
    except ValueError as exc:
        return [f"alphabet table: {exc}"]
    enums = {
        (scope, name): value_type
        for kind, (scope, name, value_type, *_rest) in (
            (entry.kind, entry.fields) for entry in entries if entry.kind == "key"
        )
    }
    accepted: dict[str, list[str]] = {}
    for alphabet, macro in ALPHABET_PARSERS.items():
        kind, called, site = ALPHABET_REACHED_FROM[alphabet]
        try:
            body = (
                key_binding_body(kernel_text, *site)
                if kind == "key"
                else macro_body(
                    kernel_text, site, _sole_definition(kernel_text, site)
                )
            )
        except ValueError as exc:
            errors.append(f"alphabet {alphabet!r}: {exc}")
        else:
            if alphabet == "side policy":
                # The installer must bind the key it is handed, not some
                # other one while still calling the parser.
                if not re.search(r"#2\s*\.code:n\s*=\s*", body):
                    errors.append(
                        f"alphabet {alphabet!r}: {site} no longer binds the "
                        "key it is given"
                    )
                # A later block rebinding one generated key would leave the
                # installer untouched and that side accepting anything.
                for word in SIDE_KEYS:
                    # The installer must still be called for each side, or
                    # that key is simply not installed and its alphabet is
                    # not the picture's.
                    sleeping = macro_body_spans(kernel_text)
                    installs = sum(
                        1 for call in re.finditer(
                            r"\\__tenkz_kernel_side:nn\s*\{\s*tenkz-kernel-picture"
                            r"\s*\}\s*\{\s*" + word + r"\s*\}", kernel_text,
                        )
                        # A call inside a macro body installs nothing until
                        # that macro runs.
                        if not any(
                            begin <= call.start() < end for begin, end in sleeping
                        )
                    )
                    if installs != 1:
                        errors.append(
                            f"alphabet {alphabet!r}: tenkz-kernel-picture:{word} "
                            f"is installed {installs} time(s), not once"
                        )
                    direct = key_definitions(kernel_text, "tenkz-kernel-picture", word)
                    if direct:
                        errors.append(
                            f"alphabet {alphabet!r}: tenkz-kernel-picture:{word} "
                            f"is bound directly in {direct} block(s), past the "
                            "installer that reaches the parser"
                        )
            # The caller's own body, not a window around it: a window wide
            # enough to reach the call is wide enough to contain the parser's
            # own definition, which would satisfy the test by itself.
            if not re.search(
                r"\\" + re.escape(called) + r"(?![A-Za-z_:])", body
            ):
                errors.append(
                    f"alphabet {alphabet!r}: {called} is defined but "
                    f"{site if kind == 'macro' else ':'.join(site)} no longer "
                    "calls it; its branches are not what the surface accepts"
                )
        try:
            accepted[alphabet] = kernel_case_words(kernel_text, macro)
        except ValueError as exc:
            errors.append(f"alphabet {alphabet!r}: {exc}")
    if ALPHABET_CHOICES:
        try:
            helper = macro_body(
                kernel_text, CHOICE_HELPER, _sole_definition(kernel_text, CHOICE_HELPER)
            )
        except ValueError as exc:
            errors.append(f"the choice helper: {exc}")
        else:
            scoped = re.search(r"\\keys_define:[a-zA-Z]{2}\s*\{\s*#1\s*\}\s*", helper)
            if scoped is None:
                errors.append(
                    f"{CHOICE_HELPER} no longer installs into the scope it is "
                    "given, so the call sites this gate reads bind nothing"
                )
                block = ""
            else:
                try:
                    block, _ = _group(helper, scoped.end())
                except ValueError:
                    block = ""
            # The choice table must be in that block: installing `#2 .code:n`
            # into the given scope and the choices into another would satisfy
            # two independent checks and bound nothing.
            if ".choices:nn" not in block:
                errors.append(
                    f"{CHOICE_HELPER} does not install its choices into the "
                    "scope it is given"
                )
            if ".choices:nn" not in helper:
                errors.append(
                    f"{CHOICE_HELPER} no longer installs a choice table, so the "
                    "word lists it is given do not bound what the parser accepts"
                )
            unknown = re.search(
                r"#2\s*/\s*unknown\s*\.code:n\s*=\s*", helper
            )
            if unknown is None:
                errors.append(
                    f"{CHOICE_HELPER} installs no handler for an unknown word"
                )
            else:
                try:
                    handler, _ = _group(helper, unknown.end())
                except ValueError:
                    handler = ""
                if not REFUSAL.search(handler):
                    errors.append(
                        f"{CHOICE_HELPER}'s unknown-word handler does not "
                        "refuse, so a value outside the list completes in "
                        "silence"
                    )
    for alphabet, (scope, key) in ALPHABET_CHOICES.items():
        direct = key_definitions(kernel_text, scope, key)
        if direct:
            errors.append(
                f"alphabet {alphabet!r}: {scope}:{key} is also bound directly "
                f"in {direct} \\keys_define:nn block(s); the last handler "
                "installed decides what the parser accepts"
            )
        try:
            words = kernel_choice_words(kernel_text, scope, key)
        except ValueError as exc:
            errors.append(f"alphabet {alphabet!r}: {exc}")
            continue
        registry_key = ALPHABET_ENUMS.get(alphabet)
        if registry_key is not None:
            value_type = enums.get(registry_key, "")
            enum = re.fullmatch(r"enum\(([^)]*)\)", value_type)
            if enum is None:
                errors.append(
                    f"alphabet {alphabet!r}: {':'.join(registry_key)} is not an enum"
                )
            # The helper dispatches on the word, not on its position, so
            # the two lists must hold the same words -- not in the same order.
            elif sorted(enum.group(1).split("|")) != sorted(words):
                errors.append(
                    f"alphabet {alphabet!r}: the registry row "
                    f"{':'.join(registry_key)} reads {value_type} but the parser "
                    f"accepts {', '.join(words)}"
                )
        recording = ALPHABET_RECORDING_WORDS.get(alphabet, set())
        # Subtracting a word the acceptor no longer has would hide its
        # removal: the two lists would agree and the table would be silent,
        # while the contract still promises the spelling.
        missing = sorted(recording - set(words))
        if missing:
            errors.append(
                f"alphabet {alphabet!r}: the recording word(s) {', '.join(missing)} "
                "left the parser but the contract still carries them"
            )
        accepted[alphabet] = [word for word in words if word not in recording]
    for alphabet in sorted(set(accepted) | set(contract)):
        if alphabet not in contract:
            errors.append(f"alphabet {alphabet!r} is accepted but has no section 2.8 row")
            continue
        if alphabet not in accepted:
            errors.append(f"alphabet {alphabet!r} has a section 2.8 row but no acceptor")
            continue
        table, words = set(contract[alphabet]), set(accepted[alphabet])
        if table != words:
            missing = ", ".join(sorted(words - table)) or "-"
            extra = ", ".join(sorted(table - words)) or "-"
            errors.append(
                f"alphabet {alphabet!r}: accepted but not in section 2.8: {missing}; "
                f"in section 2.8 but not accepted: {extra}"
            )
        if sorted(set(contract[alphabet])) != sorted(contract[alphabet]):
            errors.append(f"alphabet {alphabet!r}: section 2.8 repeats a word")
    return errors


def _parser_leaf_keys() -> set[tuple[str, str]]:
    """Collect public leaf-key spellings installed by the TeX parsers.

    Choice values and family roots are deliberately excluded.  Shared
    forwards are expanded so the census fails if implementation and registry
    drift in either direction.
    """
    texts = [
        path.read_text(encoding="utf-8")
        for path in (ROOT / "tex/tenkz").glob("*.code.tex")
    ]
    return _parser_leaf_keys_from_texts(texts) | _kernel_leaf_keys_from_texts(texts)


def _parser_registry_keys() -> set[tuple[str, str]]:
    """Collapse parser families onto the public registry ownership scopes."""
    scoped: set[tuple[str, str]] = set()
    for family, name in _parser_leaf_keys():
        if family not in _PARSER_FAMILY_SCOPE:
            raise ValueError(f"parser family {family!r} has no registry scope")
        scope = (
            "kernel-setup"
            if name in _SETUP_FORWARDS.get(family, set())
            else _PARSER_FAMILY_SCOPE[family]
        )
        scoped.add((scope, name))
    return scoped


def check(
    entries: list[Entry],
    *,
    contract_text: str | None = None,
    kernel_text: str | None = None,
) -> list[str]:
    errors: list[str] = alphabet_errors(entries, contract_text, kernel_text)
    by_kind = {
        kind: [entry.fields for entry in entries if entry.kind == kind]
        for kind in ARITIES
    }
    for kind, rows in by_kind.items():
        names = [
            f"{row[0]}:{row[1]}"
            if kind in {"key", "prelude", "tombstone"}
            else row[0]
            for row in rows
        ]
        duplicates = sorted(name for name in set(names) if names.count(name) > 1)
        if duplicates:
            errors.append(f"duplicate {kind} records: {', '.join(duplicates)}")
    registered_commands = {row[0] for row in by_kind["command"]}
    registered_environments = {row[0] for row in by_kind["environment"]}
    declared_commands, declared_environments = _declared_api()
    missing_commands = sorted(declared_commands - registered_commands)
    missing_environments = sorted(declared_environments - registered_environments)
    absent_commands = sorted(registered_commands - declared_commands - {"tndeclareatom"})
    if missing_commands:
        errors.append(f"accidental public commands: {', '.join(missing_commands)}")
    if missing_environments:
        errors.append(f"accidental public environments: {', '.join(missing_environments)}")
    if absent_commands:
        errors.append(f"registered commands without declarations: {', '.join(absent_commands)}")
    for declaration_class, name, descriptor in by_kind["prelude"]:
        if declaration_class != "skin":
            errors.append(
                f"prelude declaration {name!r} has unsupported class "
                f"{declaration_class!r}; expected 'skin'"
            )
        if not name or not descriptor:
            errors.append(
                f"incomplete prelude declaration: {declaration_class}:{name}"
            )
    key_vocabulary: dict[tuple[str, str], tuple[str, str]] = {}
    for scope, name, value_type, default, status, meaning in by_kind["key"]:
        if not all((scope, name, value_type, default, status, meaning)):
            errors.append(f"incomplete key record: {scope}:{name}")
        try:
            ledger, _ = parse_status(status)
        except ValueError as exc:
            errors.append(f"{scope}:{name}: {exc}")
            continue
        key_vocabulary[(scope, name.replace("~", " "))] = (ledger, value_type)
    for scope, name, _vt, _default, status, _meaning in by_kind["key"]:
        try:
            ledger, payload = parse_status(status)
        except ValueError:
            continue
        if ledger == "sugar":
            # Expansion closure: a sugar row must spell its expansion in
            # kernel vocabulary.  Sugar that cannot expand is kernel in
            # disguise and fails here.
            try:
                expansion = parse_key_expression(payload)
            except ValueError as exc:
                errors.append(
                    f"sugar row {scope}:{name} has invalid expansion: {exc}"
                )
                continue
            unknown = [
                token
                for token, _value in expansion
                if key_vocabulary.get((scope, token), ("", ""))[0] != "kernel"
            ]
            if unknown:
                errors.append(
                    f"sugar row {scope}:{name} expansion names non-kernel "
                    f"token(s): {', '.join(unknown)}"
                )
                continue
            for target, value in expansion:
                value_error = _enum_value_error(
                    target,
                    value,
                    key_vocabulary[(scope, target)],
                )
                if value_error is not None:
                    errors.append(f"sugar row {scope}:{name} {value_error}")
        if ledger == "alias":
            try:
                replacement, _sunset = parse_alias_payload(payload)
                targets = parse_key_expression(replacement)
            except ValueError as exc:
                errors.append(f"alias row {scope}:{name}: {exc}")
                continue
            unknown = [
                token
                for token, _value in targets
                if key_vocabulary.get((scope, token), ("", ""))[0]
                not in {"kernel", "sugar"}
            ]
            if unknown:
                errors.append(
                    f"alias row {scope}:{name} replacement names unknown "
                    f"token(s): {', '.join(unknown)}"
                )
                continue
            for target, value in targets:
                value_error = _enum_value_error(
                    target,
                    value,
                    key_vocabulary[(scope, target)],
                )
                if value_error is not None:
                    errors.append(f"alias row {scope}:{name} {value_error}")
    for scope, spelling, replacement, meaning in by_kind["alias"]:
        try:
            parse_value_alias_sunset(meaning)
        except ValueError as exc:
            errors.append(f"value alias {scope}:{spelling}: {exc}")
        try:
            targets = parse_key_expression(replacement)
        except ValueError as exc:
            errors.append(f"value alias {scope}:{spelling}: {exc}")
            continue
        if len(targets) != 1 or targets[0][1] in (None, ""):
            errors.append(
                f"value alias {scope}:{spelling} replacement must be one key=value"
            )
            continue
        target, value = targets[0]
        target_record = key_vocabulary.get((scope, target))
        if target_record is None or target_record[0] not in {"kernel", "sugar"}:
            errors.append(
                f"value alias {scope}:{spelling} replacement key {target!r} "
                "is not registered vocabulary"
            )
            continue
        value_error = _enum_value_error(target, value, target_record)
        if value_error is not None:
            errors.append(
                f"value alias {scope}:{spelling} {value_error}"
            )
    errors.extend(
        tombstone_errors(
            tombstone_rows(entries),
            key_vocabulary,
            {
                "command": {row[0] for row in by_kind["command"]},
                "environment": {row[0] for row in by_kind["environment"]},
            },
            _kernel_tombstones(),
        )
    )
    if BASELINE.is_file():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        recorded = baseline["m1_census"]["value"]
        actual = public_census(entries)
        if actual != recorded:
            errors.append(
                f"ledger census {actual} != baseline {recorded}; a change is "
                "legal only as a shrink-session update or with an "
                "Extension-gate: #NNNN citation, and either way the baseline "
                "moves in the same commit"
            )
    registered_keys = {
        (row[0], row[1].replace("~", " ")) for row in by_kind["key"]
    }
    parser_keys = _parser_registry_keys()
    if registered_keys != parser_keys:
        missing = sorted(
            f"{scope}:{name}" for scope, name in parser_keys - registered_keys
        )
        extra = sorted(
            f"{scope}:{name}" for scope, name in registered_keys - parser_keys
        )
        errors.append(
            "parser/registry key census mismatch; missing=" + ",".join(missing)
            + "; extra=" + ",".join(extra)
        )
    expected_leaves = 145
    if BASELINE.is_file():
        expected_leaves = json.loads(BASELINE.read_text(encoding="utf-8"))[
            "m2_parser_paths"
        ]["value"]
    if len(_parser_leaf_keys()) != expected_leaves:
        errors.append(
            f"parser leaf-key census is {len(_parser_leaf_keys())}; expected "
            f"{expected_leaves} (raise only with an Extension-gate: #NNNN "
            "citation and the baseline bump in the same commit)"
        )
    examples = {row[0]: row for row in by_kind["example"]}
    registered_commands = {row[0] for row in by_kind["command"]}
    if set(examples) != registered_commands:
        missing = sorted(registered_commands - set(examples))
        extra = sorted(set(examples) - registered_commands)
        errors.append(
            "example census mismatch; missing=" + ",".join(missing)
            + "; extra=" + ",".join(extra)
        )
    for command, relative, failure in by_kind["example"]:
        example = ROOT / relative
        if not example.is_file():
            errors.append(f"missing example for {command}: {relative}")
            continue
        lines = example.read_text(encoding="utf-8").splitlines()
        if len(lines) > 15:
            errors.append(f"example for {command} has {len(lines)} lines; maximum is 15")
        if f"\\{command}" not in "\n".join(lines):
            errors.append(f"example for {command} does not use \\{command}")
        if not failure.strip():
            errors.append(f"example for {command} has no representative failure")
    contract_labels = ("% Input:", "% Output:", "% Owned state:", "% Invariants:", "% Next stage:")
    internal_files = [ROOT / "tex/tenkz/tenkz.sty", *sorted((ROOT / "tex/tenkz").glob("*.code.tex"))]
    for path in internal_files:
        first = path.read_text(encoding="utf-8").splitlines()[:5]
        if len(first) != 5 or any(
                not line.startswith(label) for line, label in zip(first, contract_labels)):
            errors.append(f"missing five-line stage contract: {path.relative_to(ROOT)}")
    return errors


def _tex(value: str) -> str:
    return (
        value.replace("_", r"\_")
        .replace("|", r"\textbar{}\allowbreak{}")
        .replace("(", r"(\allowbreak{}")
        .replace(",", r",\allowbreak{}")
        .replace("-", r"-\allowbreak{}")
        .replace(" ", r" \allowbreak{}")
    )


def reference_texts(entries: list[Entry]) -> tuple[str, str]:
    """Render the two generated chapters; the writer and the checker share this."""
    commands = [e.fields for e in entries if e.kind == "command"]
    examples = {e.fields[0]: e.fields[1:] for e in entries if e.kind == "example"}
    keys = [
        e.fields
        for e in entries
        if e.kind == "key" and parse_status(e.fields[4])[0] != "alias"
    ]
    aliases = [
        e.fields
        for e in entries
        if e.kind == "key" and parse_status(e.fields[4])[0] == "alias"
    ]
    value_aliases = [e.fields for e in entries if e.kind == "alias"]
    preludes = [e.fields for e in entries if e.kind == "prelude"]
    lines = [
        "% Generated by scripts/tenkz_language.py; do not edit.",
        r"{\footnotesize",
        r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{30mm}"
        r">{\raggedright\arraybackslash}p{24mm}"
        r">{\raggedright\arraybackslash}p{48mm}@{}}",
        r"\toprule Command & Class & Why this is a command \\ \midrule",
    ]
    for name, category, _scope, signature, why in commands:
        lines.append(
            rf"\texttt{{\textbackslash {_tex(name)}}} & {_tex(category)} & {_tex(why)} \\"
        )
        lines.append(
            rf"\multicolumn{{3}}{{@{{}}p{{106mm}}@{{}}}}{{\footnotesize\texttt{{\detokenize{{{signature}}}}}}} \\[2pt]"
        )
        example, failure = examples[name]
        lines.append(
            rf"\multicolumn{{3}}{{@{{}}p{{106mm}}@{{}}}}{{Example: \texttt{{\detokenize{{{example}}}}}. "
            rf"Representative failure: {_tex(failure)}}} \\[3pt]"
        )
    lines.extend(
        [
            r"\bottomrule\end{longtable}",
            r"\scriptsize",
            r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{20mm}"
            r">{\raggedright\arraybackslash}p{25mm}"
            r">{\raggedright\arraybackslash}p{20mm}"
            r">{\raggedright\arraybackslash}p{20mm}"
            r">{\raggedright\arraybackslash}p{18mm}@{}}",
            r"\toprule Scope & Key & Type & Default & Meaning \\ \midrule",
        ]
    )
    for scope, name, value_type, default, _status, meaning in keys:
        lines.append(
            rf"{_tex(scope)} & \texttt{{{_tex(name)}}} & {_tex(value_type)} & "
            rf"{_tex(default)} & {_tex(meaning)} \\"
        )
    lines.append(r"\bottomrule\end{longtable}")
    lines.extend(
        [
            r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{24mm}"
            r">{\raggedright\arraybackslash}p{24mm}"
            r">{\raggedright\arraybackslash}p{58mm}@{}}",
            r"\toprule Prelude class & Name & Declaration \\ \midrule",
        ]
    )
    for declaration_class, name, descriptor in preludes:
        lines.append(
            rf"{_tex(declaration_class)} & \texttt{{{_tex(name)}}} & "
            rf"\texttt{{{_tex(descriptor)}}} \\"
        )
    lines.append(r"\bottomrule\end{longtable}")
    lines.append("}")
    alias_lines = [
        "% Generated by scripts/tenkz_language.py; do not edit.",
        r"{\footnotesize",
        r"\begin{tabularx}{\linewidth}{@{}l l X@{}}\toprule Scope & Alias & Replacement \\ \midrule",
    ]
    for scope, name, _type, _default, status, meaning in aliases:
        alias_lines.append(
            rf"{_tex(scope)} & \texttt{{{_tex(name)}}} & {_tex(status)}; {_tex(meaning)} \\"
        )
    for scope, spelling, replacement, meaning in value_aliases:
        alias_lines.append(
            rf"{_tex(scope)} & \texttt{{{_tex(spelling)}}} & "
            rf"use \texttt{{{_tex(replacement)}}}; {_tex(meaning)} \\"
        )
    alias_lines.extend((r"\bottomrule\end{tabularx}", "}"))
    return "\n".join(lines) + "\n", "\n".join(alias_lines) + "\n"


def generate_reference(entries: list[Entry]) -> None:
    reference, aliases = reference_texts(entries)
    REFERENCE.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE.write_text(reference, encoding="utf-8")
    ALIASES.write_text(aliases, encoding="utf-8")


def stale_generated_chapters(entries: list[Entry]) -> list[str]:
    """Report a committed chapter that no longer matches the registry.

    The two chapters say they are generated, and until this check existed
    nothing held them to it: a registry row could change its prose and the
    reference could keep the old sentence, which is the drift the one-record
    rule exists to prevent.  Regenerate with `generate-reference'.
    """
    errors: list[str] = []
    for path, expected in zip((REFERENCE, ALIASES), reference_texts(entries)):
        name = path.relative_to(ROOT)
        if not path.exists():
            errors.append(f"generated chapter {name} is missing")
        elif path.read_text(encoding="utf-8") != expected:
            errors.append(
                f"generated chapter {name} does not match the registry; "
                "run scripts/tenkz_language.py generate-reference"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "generate-reference", "census"))
    args = parser.parse_args()
    entries = load_registry()
    if args.action == "generate-reference":
        generate_reference(entries)
    errors = check(entries)
    # The chapters call themselves generated; this is what holds them to it.
    # `check' is what CI runs, so a committed chapter that drifts from the
    # registry fails there rather than reaching a reader.  The generate action
    # has just written them from these same entries, so there is nothing there
    # for the comparison to find and it is skipped.
    if args.action != "generate-reference":
        errors.extend(stale_generated_chapters(entries))
    if args.action == "census":
        census = {kind: sum(e.kind == kind for e in entries) for kind in ARITIES}
        census["parser_leaf_keys"] = len(_parser_leaf_keys())
        census["ledgers"] = {
            ledger: len(rows) for ledger, rows in ledger_split(entries).items()
        }
        print(json.dumps(census, sort_keys=True))
    if errors:
        for error in errors:
            print(f"tenkz-language: {error}", file=sys.stderr)
        return 1
    if args.action != "census":
        print(f"PASS: tenkz language registry ({len(entries)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
