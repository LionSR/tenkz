#!/usr/bin/env python3
"""Focused contract tests for the executable tenkz language registry."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import tenkz_language


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=cwd, check=check, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=120,
    )


def compile_source(source: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="tenkz-language-") as tmp:
        path = Path(tmp)
        (path / "case.tex").write_text(source, encoding="utf-8")
        env = os.environ.copy()
        env["TEXINPUTS"] = f"{ROOT / 'tex/tenkz'}//:"
        return subprocess.run(
            ("xelatex", "-interaction=nonstopmode", "-halt-on-error", "case.tex"),
            cwd=path, env=env, check=False, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=120,
        )


def compile_event_source(source: str) -> tuple[subprocess.CompletedProcess[str], str]:
    with tempfile.TemporaryDirectory(prefix="tenkz-language-events-") as tmp:
        path = Path(tmp)
        (path / "case.tex").write_text(source, encoding="utf-8")
        env = os.environ.copy()
        env["TEXINPUTS"] = f"{ROOT / 'tex/tenkz'}//:"
        result = subprocess.run(
            ("xelatex", "-interaction=nonstopmode", "-halt-on-error", "case.tex"),
            cwd=path, env=env, check=False, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=120,
        )
        log = (path / "case.tnlog").read_text(encoding="utf-8") if result.returncode == 0 else ""
        return result, log


def alphabet_gate_fails_when_seeded(registry: list[tenkz_language.Entry]) -> None:
    """LionSR/tenkz#7: the section 2.8 table and its acceptors pin each other.

    Each seed below is one drift the census meters cannot see: a word added
    to or struck from the contract's table, a branch added to a kernel
    parser, and a registry enum that grows.  The unseeded texts pass; every
    seed must be named by the check, in both directions of the diff.
    """
    contract = tenkz_language.CONTRACT.read_text(encoding="utf-8")
    kernel = tenkz_language.KERNEL.read_text(encoding="utf-8")
    if tenkz_language.alphabet_errors(registry, contract, kernel):
        raise SystemExit("the alphabet check fails on the unseeded tree")
    seeds = {
        "contract gains a route word": (
            contract.replace("| routes | `straight` `orth` `arc` |",
                             "| routes | `straight` `orth` `arc` `bezier` |"),
            kernel, registry, "in section 2.8 but not accepted: bezier",
        ),
        "contract drops a skin word": (
            contract.replace("`triwest` ", ""),
            kernel, registry, "accepted but not in section 2.8: triwest",
        ),
        "kernel gains a side word": (
            contract,
            kernel.replace(
                "        {cup}   { \\__tenkz_kernel_stage_put:nn {#1} {cup}   }\n",
                "        {cup}   { \\__tenkz_kernel_stage_put:nn {#1} {cup}   }\n"
                "        {seal}  { \\__tenkz_kernel_stage_put:nn {#1} {none}  }\n",
            ),
            registry, "accepted but not in section 2.8: seal",
        ),
        "kernel choice table gains a form word": (
            contract,
            kernel.replace(
                "  { bracket, enclosure, label, prose }\n",
                "  { bracket, enclosure, label, prose, band }\n",
            ),
            registry, "accepted but not in section 2.8: band",
        ),
        "registry enum drifts from the parser": (
            contract, kernel,
            [
                tenkz_language.Entry(
                    entry.kind,
                    (*entry.fields[:2], "enum(bracket|enclosure|label)",
                     *entry.fields[3:]),
                )
                if entry.kind == "key" and entry.fields[:2] == ("kernel-mark", "form")
                else entry
                for entry in registry
            ],
            "the registry row kernel-mark:form reads enum(bracket|enclosure|label) "
            "but the parser accepts bracket, enclosure, label, prose",
        ),
        "contract lists an alphabet twice": (
            contract.replace(
                "| routes | `straight` `orth` `arc` |",
                "| routes | `straight` `orth` |\n| routes | `straight` `orth` `arc` |",
            ),
            kernel, registry, "lists 'routes' twice",
        ),
    }
    for name, (seed_contract, seed_kernel, seed_registry, expected) in seeds.items():
        if seed_contract == contract and seed_kernel == kernel and seed_registry is registry:
            raise SystemExit(f"seed {name!r} changed nothing")
        errors = tenkz_language.alphabet_errors(seed_registry, seed_contract, seed_kernel)
        if not any(expected in error for error in errors):
            raise SystemExit(f"seed {name!r} was not caught; errors: {errors}")
    # A branch key the reader cannot name is reported rather than skipped, so
    # a word this gate would never compare cannot slip in silently.
    unreadable = kernel.replace(
        "        {cup}   { \\__tenkz_kernel_stage_put:nn {#1} {cup}   }\n",
        "        {cup}   { \\__tenkz_kernel_stage_put:nn {#1} {cup}   }\n"
        "        {\\l_tenkz_word_tl} { }\n",
    )
    assert unreadable != kernel
    errors = tenkz_language.alphabet_errors(registry, contract, unreadable)
    if not any("cannot name" in error for error in errors):
        raise SystemExit(f"an unreadable branch key was skipped; errors: {errors}")
    # A word written beside the backticked ones reads as part of the alphabet
    # on the page and would otherwise be dropped in silence.
    loose = contract.replace(
        "| routes | `straight` `orth` `arc` |",
        "| routes | `straight` `orth` `arc` bezier |",
    )
    assert loose != contract
    errors = tenkz_language.alphabet_errors(registry, loose, kernel)
    if not any("cannot name" in error for error in errors):
        raise SystemExit(f"loose text in an alphabet cell was ignored; errors: {errors}")
    # A row whose cell opens with bare text is read like any other row: a
    # reader that only matched well-formed cells would not see it at all.
    bare = contract.replace(
        "| routes | `straight` `orth` `arc` |",
        "| routes | `straight` `orth` `arc` |\n| weights | thin thick |",
    )
    assert bare != contract
    errors = tenkz_language.alphabet_errors(registry, bare, kernel)
    if not any("cannot name" in error for error in errors):
        raise SystemExit(f"a bare-text alphabet row was skipped; errors: {errors}")
    # A second choice table for one key decides what the parser accepts, so
    # reading the first would report a stale alphabet as current.
    twice = kernel.replace(
        "\\__tenkz_kernel_choice:nnnn { tenkz-kernel-mark } { form }\n"
        "  { bracket, enclosure, label, prose }\n",
        "\\__tenkz_kernel_choice:nnnn { tenkz-kernel-mark } { form }\n"
        "  { bracket, enclosure, label, prose }\n"
        "\\__tenkz_kernel_choice:nnnn { tenkz-kernel-mark } { form }\n"
        "  { bracket, enclosure, label, prose, glow }\n",
    )
    assert twice != kernel
    errors = tenkz_language.alphabet_errors(registry, contract, twice)
    if not any("choice tables" in error for error in errors):
        raise SystemExit(f"a second choice table was not reported; errors: {errors}")
    # The recording word is subtracted from the comparison, so its removal
    # would otherwise leave both lists agreeing and the table silent.
    dropped = kernel.replace(
        "  { bracket, enclosure, label, prose }\n",
        "  { bracket, enclosure, label }\n",
    )
    dropped_registry = [
        tenkz_language.Entry(
            entry.kind,
            (*entry.fields[:2], "enum(bracket|enclosure|label)", *entry.fields[3:]),
        )
        if entry.kind == "key" and entry.fields[:2] == ("kernel-mark", "form")
        else entry
        for entry in registry
    ]
    assert dropped != kernel
    errors = tenkz_language.alphabet_errors(dropped_registry, contract, dropped)
    if not any("recording word" in error for error in errors):
        raise SystemExit(f"a retired recording word was not reported; errors: {errors}")
    # Markdown renders a row indented by up to three spaces as part of the
    # table, so a reader that required column zero would not see it.
    indented = contract.replace(
        "| routes | `straight` `orth` `arc` |",
        "| routes | `straight` `orth` `arc` |\n   | routes | `straight` |",
    )
    assert indented != contract
    errors = tenkz_language.alphabet_errors(registry, indented, kernel)
    if not any("twice" in error for error in errors):
        raise SystemExit(f"an indented duplicate row was skipped; errors: {errors}")
    # A parser redefined later is the body TeX runs; reading the first would
    # compare an alphabet the kernel no longer accepts.
    redefined = kernel + (
        "\n\\cs_set_protected:Npn \\__tenkz_kernel_route:n #1 { }\n"
    )
    errors = tenkz_language.alphabet_errors(registry, contract, redefined)
    if not any("times" in error for error in errors):
        raise SystemExit(f"a redefined parser was not reported; errors: {errors}")
    # The reader is total over the table and over the parser's bindings: a row
    # it cannot account for, and any spelling that installs a second body,
    # are reported rather than stepped over.
    anchor = "| routes | `straight` `orth` `arc` |"
    for label, seed in (
        ("a row with no alphabet name", f"{anchor}\n|  | `bezier` |"),
        ("a row with an extra cell", f"{anchor}\n| weights | `thin` | `thick` |"),
    ):
        errors = tenkz_language.alphabet_errors(
            registry, contract.replace(anchor, seed), kernel
        )
        if not any("cannot name" in error for error in errors):
            raise SystemExit(f"{label} was skipped; errors: {errors}")
    for form in (
        r"\cs_set:Nn", r"\cs_set_eq:NN", r"\cs_gset_protected:Npn", r"\let", r"\def",
    ):
        seeded = f"{kernel}\n{form} \\__tenkz_kernel_route:n {{ }}\n"
        errors = tenkz_language.alphabet_errors(registry, contract, seeded)
        if not any("times" in error for error in errors):
            raise SystemExit(f"a parser replaced with {form} was missed; errors: {errors}")
    # A generated variant derives a sibling and leaves the base alone, so it
    # is not a second definition and must not be reported as one.
    variant = f"{kernel}\n\\cs_generate_variant:Nn \\__tenkz_kernel_route:n {{ V }}\n"
    if any("times" in error for error in tenkz_language.alphabet_errors(
        registry, contract, variant
    )):
        raise SystemExit("a generated variant was counted as a redefinition")
    # Removing a parser changes what runs as surely as replacing it.
    undefined = f"{kernel}\n\\cs_undefine:N \\__tenkz_kernel_route:n\n"
    if not any("times" in error for error in tenkz_language.alphabet_errors(
        registry, contract, undefined
    )):
        raise SystemExit("an undefined parser was not reported")
    # A key bound directly in its scope replaces the handler the helper
    # installed, and can then accept words the helper's list does not carry.
    override = (
        f"{kernel}\n\\keys_define:nn {{ tenkz-kernel-mark }} "
        "{ form .code:n = { } }\n"
    )
    if not any("bound directly" in error for error in tenkz_language.alphabet_errors(
        registry, contract, override
    )):
        raise SystemExit("a direct key override was not reported")
    # Another key in the same scope is ordinary and must not report.
    sibling = (
        f"{kernel}\n\\keys_define:nn {{ tenkz-kernel-mark }} "
        "{ species .code:n = { } }\n"
    )
    if any("bound directly" in error for error in tenkz_language.alphabet_errors(
        registry, contract, sibling
    )):
        raise SystemExit("binding a sibling key was reported as an override")
    # The remaining ways a branch list could stop being the accepted alphabet:
    # the parser bound by name, the key overridden through a variant spelling,
    # the key rewired past the parser, a branch that refuses its own word, a
    # second case table, and a delimiter that does not form the table.
    for label, seeded_kernel, expected in (
        (
            "a parser bound by name",
            f"{kernel}\n\\cs_set:cpn {{ __tenkz_kernel_route:n }} #1 {{ }}\n",
            "times",
        ),
        (
            "a key overridden through a keys_define variant",
            f"{kernel}\n\\keys_define:nx {{ tenkz-kernel-mark }} "
            "{ form .code:n = { } }\n",
            "bound directly",
        ),
        (
            "the route key rewired past its parser",
            kernel.replace(
                r"route .code:n    = { \__tenkz_kernel_route:n {#1} }",
                r"route .code:n    = { \__tenkz_kernel_stage_put:nn {route} {#1} }",
            ),
            "no longer calls it",
        ),
        (
            "a branch that refuses its own word",
            kernel.replace(
                r"{arc}      { \__tenkz_kernel_route_keep: }",
                r"{arc}      { \msg_error:nn {tenkz}{gone} }",
            ),
            "branch refuses the word",
        ),
        (
            "a second case table inside one parser",
            kernel.replace(
                r"\regex_match:nVTF { \A (?: all | n | e | s | w ) \s+ of \s+ \S }",
                "\\str_case:nnF {x} { {bezier} {} } { }\n    "
                r"\regex_match:nVTF { \A (?: all | n | e | s | w ) \s+ of \s+ \S }",
                1,
            ),
            "case tables",
        ),
    ):
        if seeded_kernel == kernel:
            raise SystemExit(f"seed {label!r} changed nothing")
        errors = tenkz_language.alphabet_errors(registry, contract, seeded_kernel)
        if not any(expected in error for error in errors):
            raise SystemExit(f"{label} was not reported; errors: {errors}")
    misshaped = contract.replace(
        "| Alphabet | Words |\n|---|---|", "| Alphabet | Words |\n|---|"
    )
    if misshaped == contract:
        raise SystemExit("the section 2.8 header no longer has its delimiter")
    errors = tenkz_language.alphabet_errors(registry, misshaped, kernel)
    if not any("delimiter" in error for error in errors):
        raise SystemExit(f"a misshaped delimiter was accepted; errors: {errors}")
    colons = contract.replace(
        "| Alphabet | Words |\n|---|---|", "| Alphabet | Words |\n|:|:|"
    )
    if not any("delimiter" in error for error in tenkz_language.alphabet_errors(
        registry, colons, kernel
    )):
        raise SystemExit("a delimiter with no hyphen was accepted")
    # A parser's branches are its alphabet only while the surface reaches it,
    # the fallback refuses what the branches do not name, and the helper that
    # installs a choice list still installs a choice list.
    for label, seeded_kernel, expected in (
        (
            "the side helper stops calling its parser",
            kernel.replace(
                r"{ #2 .code:n = { \__tenkz_kernel_side_policy:nn {#2} {##1} } }",
                r"{ #2 .code:n = { } }", 1,
            ),
            "no longer calls it",
        ),
        (
            "the skin helper stops calling its parser",
            kernel.replace(
                r"\__tenkz_kernel_skin_base_aux:nN {#1} #2",
                r"\tl_set:Nn #2 {box}", 1,
            ),
            "no longer calls it",
        ),
        (
            "a branch refusing expandably",
            kernel.replace(
                r"{arc}      { \__tenkz_kernel_route_keep: }",
                r"{arc}      { \msg_expandable_error:nnn {a}{b}{c} }",
            ),
            "branch refuses the word",
        ),
        (
            "a case operation with no fallback",
            kernel.replace(
                r"\str_case:VnF \l__tenkz_kernel_list_item_tl",
                r"\str_case:Vn \l__tenkz_kernel_list_item_tl", 1,
            ),
            "no fallback",
        ),
        (
            "the choice helper made unrestricted",
            kernel.replace("#2 .choices:nn = {#3}", "#2 .code:n = {#3}", 1),
            "no longer installs a choice table",
        ),
    ):
        if seeded_kernel == kernel:
            raise SystemExit(f"seed {label!r} changed nothing")
        errors = tenkz_language.alphabet_errors(registry, contract, seeded_kernel)
        if not any(expected in error for error in errors):
            raise SystemExit(f"{label} was not reported; errors: {errors}")
    # An unrelated helper declared after a parser, with a table of its own,
    # belongs to itself: the body is a balanced group, not everything up to a
    # sentinel.
    neighbour = kernel.replace(
        r"\cs_new_protected:Npn \__tenkz_kernel_route_keep:",
        "\\cs_new:Npn \\__tenkz_language_probe: { \\str_case:nn {x} { {q} {} } }\n"
        r"\cs_new_protected:Npn \__tenkz_kernel_route_keep:",
        1,
    )
    if neighbour == kernel:
        raise SystemExit("could not place a neighbouring helper")
    if tenkz_language.alphabet_errors(registry, contract, neighbour):
        raise SystemExit(
            "a neighbouring helper's case table was attributed to the parser"
        )
    # A second binding is the effective handler; reading the first would let
    # the original go on satisfying the check while the key was rewired.
    rebound = (
        f"{kernel}\n\\keys_define:nn {{ tenkz-kernel-wire }} "
        r"{ route .code:n = { \__tenkz_kernel_stage_put:nn {route} {#1} } }"
        "\n"
    )
    if not any("bound 2 times" in error for error in tenkz_language.alphabet_errors(
        registry, contract, rebound
    )):
        raise SystemExit("a second route binding was not reported")
    # Markdown ends the table at the first line that is not a row, so reading
    # past one would take later pipe-prefixed lines for rows of a table the
    # contract no longer renders.
    interrupted = contract.replace(
        "| Alphabet | Words |\n|---|---|\n",
        "| Alphabet | Words |\n|---|---|\nA sentence interrupts the table.\n",
        1,
    )
    if interrupted == contract:
        raise SystemExit("could not interrupt the section 2.8 table")
    if not any("interrupted" in error for error in tenkz_language.alphabet_errors(
        registry, interrupted, kernel
    )):
        raise SystemExit("an interrupted alphabet table was accepted")
    for label, seeded_kernel, expected in (
        (
            "a TF table whose refusal is in the matched branch",
            kernel.replace(
                r"\str_case:VnF \l__tenkz_kernel_list_item_tl",
                r"\str_case:VnTF \l__tenkz_kernel_list_item_tl", 1,
            ),
            "refuses in the branch it takes",
        ),
        (
            "a variant call to the choice helper",
            f"{kernel}\n\\__tenkz_kernel_choice:nnnx {{ tenkz-kernel-mark }} "
            "{ form } { bracket, enclosure, label, prose, glow } { form }\n",
            "choice tables",
        ),
        (
            "a keys_define:nf override",
            f"{kernel}\n\\keys_define:nf {{ tenkz-kernel-mark }} "
            "{ form .code:n = { } }\n",
            "bound directly",
        ),
    ):
        if seeded_kernel == kernel:
            raise SystemExit(f"seed {label!r} changed nothing")
        errors = tenkz_language.alphabet_errors(registry, contract, seeded_kernel)
        if not any(expected in error for error in errors):
            raise SystemExit(f"{label} was not reported; errors: {errors}")
    # `.default:n` changes the value a key takes without an explicit one; it
    # installs no handler, so reporting it as an override would be wrong.
    orthogonal = (
        f"{kernel}\n\\keys_define:nn {{ tenkz-kernel-mark }} "
        "{ form .default:n = label }\n"
    )
    if tenkz_language.alphabet_errors(registry, contract, orthogonal):
        raise SystemExit("an orthogonal key property was reported as an override")
    import re as _re

    for label, seeded_kernel, expected in (
        (
            "a call to a longer control sequence",
            kernel.replace(
                r"route .code:n    = { \__tenkz_kernel_route:n {#1} }",
                r"route .code:n    = { \__tenkz_kernel_route:n_unchecked {#1} }",
                1,
            ),
            "no longer calls it",
        ),
        (
            "an unknown-word handler that does not refuse",
            _re.sub(
                r"(#2 / unknown \.code:n =\s*)\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}",
                r"\1{ }", kernel, count=1,
            ),
            "does not refuse",
        ),
        (
            "a handler-setting property outside any allowlist",
            f"{kernel}\n\\keys_define:nn {{ tenkz-kernel-mark }} "
            r"{ form .tl_set:N = \l_tmpa_tl }" "\n",
            "bound directly",
        ),
    ):
        if seeded_kernel == kernel:
            raise SystemExit(f"seed {label!r} changed nothing")
        errors = tenkz_language.alphabet_errors(registry, contract, seeded_kernel)
        if not any(expected in error for error in errors):
            raise SystemExit(f"{label} was not reported; errors: {errors}")
    for label, seeded_kernel, expected in (
        (
            "two assignments of one key in one block",
            kernel.replace(
                r"route .code:n    = { \__tenkz_kernel_route:n {#1} } ,",
                r"route .code:n    = { \__tenkz_kernel_route:n {#1} } , "
                r"route .code:n = { } ,", 1,
            ),
            "bound 2 times",
        ),
        (
            "a generated side key rebound past its installer",
            f"{kernel}\n\\keys_define:nn {{ tenkz-kernel-picture }} "
            "{ west .code:n = { } }\n",
            "past the installer",
        ),
    ):
        if seeded_kernel == kernel:
            raise SystemExit(f"seed {label!r} changed nothing")
        errors = tenkz_language.alphabet_errors(registry, contract, seeded_kernel)
        if not any(expected in error for error in errors):
            raise SystemExit(f"{label} was not reported; errors: {errors}")
    for label, seeded_kernel, expected in (
        (
            "a key installed through a kernel helper",
            f"{kernel}\n\\__tenkz_kernel_value:nnn {{ tenkz-kernel-mark }} "
            "{ form } { form }\n",
            "bound directly",
        ),
        (
            "the route key bound with a handler this gate cannot read",
            f"{kernel}\n\\keys_define:nn {{ tenkz-kernel-wire }} "
            r"{ route .tl_set:N = \l_tmpa_tl }" "\n",
            "cannot read",
        ),
    ):
        if seeded_kernel == kernel:
            raise SystemExit(f"seed {label!r} changed nothing")
        errors = tenkz_language.alphabet_errors(registry, contract, seeded_kernel)
        if not any(expected in error for error in errors):
            raise SystemExit(f"{label} was not reported; errors: {errors}")
    # The sanctioned installers must not report: the four side keys are
    # installed by the helper this gate checks separately.
    if any(
        "past the installer" in error
        for error in tenkz_language.alphabet_errors(registry, contract, kernel)
    ):
        raise SystemExit("the sanctioned side installer was read as an override")
    at_eof = (
        contract
        + "\n### 2.8 Closed alphabets\n\n| Alphabet | Words |\n|---|---|\n"
        "| routes | `bezier` |\n"
    )
    if not any("section 2.8s" in error for error in tenkz_language.alphabet_errors(
        registry, at_eof, kernel
    )):
        raise SystemExit("a second section 2.8 at end of file was accepted")
    short = contract.replace(
        "| Alphabet | Words |\n|---|---|", "| Alphabet | Words |\n|-|-|", 1
    )
    if not any("delimiter" in error for error in tenkz_language.alphabet_errors(
        registry, short, kernel
    )):
        raise SystemExit("a delimiter with fewer than three hyphens was accepted")
    moved = kernel.replace(
        "\\keys_define:nn {#1}\n      {\n        #2 .choices:nn = {#3}",
        "\\keys_define:nn {#1}\n      {\n        #2 .code:n = {#3}", 1,
    )
    if moved != kernel and not any(
        "choices into the" in error
        for error in tenkz_language.alphabet_errors(registry, contract, moved)
    ):
        raise SystemExit("choices installed outside the given scope were accepted")
    # A definition inside a macro body runs when that macro is called, not at
    # load, so counting it would report a binding TeX never installs.
    dormant = (
        f"{kernel}\n\\cs_new_protected:Npn \\__tenkz_language_dormant: "
        "{ \\keys_define:nn { tenkz-kernel-wire } { route .code:n = { } } }\n"
    )
    if tenkz_language.alphabet_errors(registry, contract, dormant):
        raise SystemExit("a dormant key definition was counted as a binding")
    # A comma inside a nested handler body is not a separator of the outer
    # block, and reading it as one reports a rebinding that is not there.
    nested = (
        f"{kernel}\n\\keys_define:nn {{ tenkz-kernel-mark }} "
        "{ probe .code:n = { \\keys_define:nn {inner} "
        "{ x .code:n = {a}, form .code:n = {b} } } }\n"
    )
    if tenkz_language.alphabet_errors(registry, contract, nested):
        raise SystemExit("a nested comma was read as a top-level key assignment")
    duplicated = (
        contract
        + "\n### 2.8 Closed alphabets\n\n| Alphabet | Words |\n|---|---|\n"
        "| routes | `bezier` |\n\n## 99. A closing heading\n"
    )
    if not any("section 2.8s" in error for error in tenkz_language.alphabet_errors(
        registry, duplicated, kernel
    )):
        raise SystemExit("a second section 2.8 was accepted")
    # Prose immediately after the last row ends the table, blank line or not,
    # and must not be reported as an interruption.
    unspaced = contract.replace(
        "| mark forms | `bracket` `enclosure` `label` |\n\n",
        "| mark forms | `bracket` `enclosure` `label` |\n", 1,
    )
    if unspaced == contract:
        raise SystemExit("the section 2.8 table no longer ends with a blank line")
    if tenkz_language.alphabet_errors(registry, unspaced, kernel):
        raise SystemExit("prose closing the table was reported as an interruption")
    renamed = contract.replace("| Alphabet | Words |", "| Deprecated | Replacements |", 1)
    if not any("header reads" in error for error in tenkz_language.alphabet_errors(
        registry, renamed, kernel
    )):
        raise SystemExit("a renamed section 2.8 header was accepted")
    for label, seeded_kernel, expected in (
        (
            "the side installer binding another key",
            kernel.replace(
                r"{ #2 .code:n = { \__tenkz_kernel_side_policy:nn {#2} {##1} } }",
                r"{ ignored .code:n = { \__tenkz_kernel_side_policy:nn {#2} {##1} } }",
                1,
            ),
            "no longer binds the key it is given",
        ),
        (
            "the choice helper installing into another scope",
            kernel.replace(
                "\\keys_define:nn {#1}\n      {\n        #2 .choices:nn",
                "\\keys_define:nn {other-scope}\n      {\n        #2 .choices:nn",
                1,
            ),
            "installs into the scope it is given",
        ),
    ):
        if seeded_kernel == kernel:
            raise SystemExit(f"seed {label!r} changed nothing")
        errors = tenkz_language.alphabet_errors(registry, contract, seeded_kernel)
        if not any(expected in error for error in errors):
            raise SystemExit(f"{label} was not reported; errors: {errors}")


def main() -> int:
    run("python3", "scripts/tenkz_language.py", "check")
    registry = tenkz_language.load_registry()
    alphabet_gate_fails_when_seeded(registry)
    mpo_preludes = [
        entry.fields
        for entry in registry
        if entry.kind == "prelude" and entry.fields[:2] == ("skin", "mpo")
    ]
    if mpo_preludes != [("skin", "mpo", "base=box")]:
        raise SystemExit("the executable registry lost the stock MPO box declaration")
    reference = tenkz_language.REFERENCE.read_text(encoding="utf-8")
    if "Prelude class & Name & Declaration" not in reference or "base=box" not in reference:
        raise SystemExit("the generated language reference omitted the stock MPO declaration")
    # Both chapters say they are generated, so both must equal what the
    # generator emits from the registry as committed.  Without this a registry
    # row could change its prose and the published reference keep the old
    # sentence, which is exactly the drift the one-record rule forbids.
    drifted = tenkz_language.stale_generated_chapters(registry)
    if drifted:
        raise SystemExit(
            "generated chapters drifted from the registry:\n" + "\n".join(drifted)
        )
    distinct_skin = tenkz_language.Entry(
        kind="prelude", fields=("skin", "probe", "base=ring")
    )
    distinct_errors = tenkz_language.check([*registry, distinct_skin])
    if distinct_errors:
        raise SystemExit(
            "a distinct stock skin was rejected:\n" + "\n".join(distinct_errors)
        )
    duplicate_skin = tenkz_language.Entry(
        kind="prelude", fields=("skin", "mpo", "base=box")
    )
    duplicate_errors = tenkz_language.check([*registry, duplicate_skin])
    if duplicate_errors != ["duplicate prelude records: skin:mpo"]:
        raise SystemExit(
            "an exact stock-skin duplicate was not rejected by class:name"
        )
    for declaration_class, descriptor in (
        ("atom", "skin=box"),
        ("species", "hue=source:red"),
    ):
        name = f"invalid-{declaration_class}"
        invalid = tenkz_language.Entry(
            kind="prelude", fields=(declaration_class, name, descriptor)
        )
        expected = (
            f"prelude declaration {name!r} has unsupported class "
            f"{declaration_class!r}; expected 'skin'"
        )
        if tenkz_language.check([*registry, invalid]) != [expected]:
            raise SystemExit(
                f"the registry validator accepted a {declaration_class} prelude"
            )
    # Everything above is Python over the registry and the contract, and runs
    # anywhere; from here on every check compiles.  The skip belongs here so a
    # machine without TeX still reports the drift the alphabet gate exists for
    # rather than passing on the first missing engine (LionSR/tenkz#7).
    if shutil.which("xelatex") is None:
        print(
            "PASS: registry, alphabet drift, prelude inventory, and generated "
            "reference; SKIP: xelatex not found, so the compile probes did not run"
        )
        return 0
    for declaration_class, name, descriptor in (
        ("atom", "mpo-command-leak", "skin=box"),
        ("species", "mpo-species-leak", "hue=source:red"),
    ):
        rejected = compile_source(
            rf"""\documentclass{{standalone}}
\usepackage{{tenkz}}
\ExplSyntaxOn
\__tenkz_kernel_install_prelude:nnn
  {{{declaration_class}}}{{{name}}}{{{descriptor}}}
\ExplSyntaxOff
\begin{{document}}x\end{{document}}
"""
        )
        if (
            rejected.returncode == 0
            or "TKZ-LANG-PRELUDE-CLASS" not in rejected.stdout
        ):
            raise SystemExit(
                f"the runtime installer accepted a {declaration_class} prelude"
            )
    good = compile_source(r"""\documentclass{standalone}
\usepackage{tenkz}
\tndeclareatom{\tnphase}{skin=box, ports={west:virtual,east:virtual}}
\begin{document}
\begin{tenkz}[rows={wire}]\tn{A}&\tnphase{B}\end{tenkz}
\end{document}
""")
    if good.returncode:
        raise SystemExit(f"typed declaration did not compile:\n{good.stdout}")
    bad = compile_source(r"""\documentclass{standalone}
\usepackage{tenkz}
\tndeclareatom{\tnbad}{skin=box, ports={west:physical}}
\begin{document}x\end{document}
""")
    if bad.returncode == 0 or "TKZ-ATOM-INVALID-PORT" not in bad.stdout:
        raise SystemExit("invalid typed port did not produce TKZ-ATOM-INVALID-PORT")
    # No alias remains since the S4 surface swap, so the event-equivalence
    # probe compares a sugar row with its kernel expansion instead.
    canonical, canonical_events = compile_event_source(r"""\documentclass{standalone}
\usepackage{tenkz}
\begin{document}
\begin{tenkz}[rows={ket,op,bra}, cols=2]\end{tenkz}
\end{document}
""")
    sugared, sugared_events = compile_event_source(r"""\documentclass{standalone}
\usepackage{tenkz}
\begin{document}
\begin{tenkz}[sandwich, cols=2]\end{tenkz}
\end{document}
""")
    if canonical.returncode or sugared.returncode:
        raise SystemExit("kernel/sugar event-equivalence probe did not compile")
    if canonical_events != sugared_events:
        raise SystemExit("sandwich and rows={ket,op,bra} emitted different semantic events")
    # Each retired word stays installed as a parser branch that refuses the
    # spelling and states the migration.  What is pinned here is that the
    # branch fires and prints its own words: the four are read out of the
    # kernel source rather than written again, so a migration reworded in one
    # place and not the other cannot pass.  Holding those branches to the
    # registry's tombstone rows is the ledger's own check, which
    # `tenkz_language.py check` runs.
    form_row = next(
        entry.fields
        for entry in registry
        if entry.kind == "key" and entry.fields[:2] == ("kernel-mark", "form")
    )
    if form_row[2] != "enum(bracket|enclosure|label|prose)":
        raise SystemExit(f"the mark form alphabet is no longer the contract's: {form_row[2]}")
    kernel = (ROOT / "tex/tenkz/tenkz-kernel.code.tex").read_text(encoding="utf-8")
    branches = re.findall(
        r"\\__tenkz_kernel_tombstone:nnnn\s*\{\s*tenkz-kernel-mark\s*\}"
        r"\s*\{\s*form\s*\}\s*\{\s*([a-z-]+)\s*\}\s*\{(.*?)\}\n",
        kernel,
        re.DOTALL,
    )
    if len(branches) != 4:
        raise SystemExit(
            f"expected four retired mark forms in the parser, found {len(branches)}"
        )
    for word, migration in branches:
        refused = compile_source(
            rf"""\documentclass{{standalone}}
\usepackage{{tenkz}}
\begin{{document}}
\begin{{tenkz}}[rows={{ket}}, cols=2, bonds=none]
  \tn[name=a]{{A}} & \tn[name=b]{{B}}
  \tnmark[form={word}]{{(1,1) .. (1,2)}}{{$L$}}
\end{{tenkz}}
\end{{document}}
"""
        )
        # l3msg wraps a long diagnostic and prefixes each continuation line
        # with the package name, which lands between the words it broke.  The
        # comparison therefore drops that prefix and then every space, so it
        # asks only which characters were printed and never where the engine
        # of the day chose to break the line.
        transcript = re.sub(
            r"\s+|\(tenkz\)", "", refused.stdout.replace("(tenkz)", " ")
        )

        def printed(text: str) -> bool:
            return re.sub(r"\s+|~", "", text) in transcript

        if refused.returncode == 0 or not printed("TKZ-LANG-TOMBSTONE"):
            raise SystemExit(f"form={word} was not refused as a tombstone")
        if not printed(migration):
            raise SystemExit(
                f"form={word} was refused without the parser's own migration"
            )

    live = compile_source(r"""\documentclass{standalone}
\usepackage{tenkz}
\begin{document}
\begin{tenkz}[rows={ket}, cols=2]
  \tn{A} & \tn{A}
  \tnmark[form=bracket]{(1,1) .. (1,2)}{$L$}
\end{tenkz}
\end{document}
""")
    if live.returncode:
        raise SystemExit(f"the surviving bracket form did not compile:\n{live.stdout}")
    print(
        "PASS: registry, typed atom diagnostic, sugar event equivalence, "
        "and the four retired mark forms refused by a compile"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
