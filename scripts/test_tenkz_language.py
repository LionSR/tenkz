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

    Each seed is a drift the census meters cannot see -- a word added to or
    struck from the contract, from a kernel parser, from the choice table, or
    from the registry row -- together with the malformed spellings the readers
    must refuse rather than skip, and the benign spellings they must not
    report.  The unseeded texts pass.
    """
    contract = tenkz_language.CONTRACT.read_text(encoding="utf-8")
    kernel = tenkz_language.kernel_source()
    if tenkz_language.alphabet_errors(registry, contract, kernel):
        raise SystemExit("the alphabet check fails on the unseeded tree")

    def seeded(contract_text: str, kernel_text: str, entries=None) -> list[str]:
        return tenkz_language.alphabet_errors(
            registry if entries is None else entries, contract_text, kernel_text
        )

    def must_report(label: str, errors: list[str], expected: str) -> None:
        if not any(expected in error for error in errors):
            raise SystemExit(f"{label} was not reported; errors: {errors}")

    # Words added or struck, on each side of the comparison.
    must_report(
        "a route word added to the contract",
        seeded(contract.replace("| routes | `straight` `orth` `arc` |",
                                "| routes | `straight` `orth` `arc` `bezier` |"), kernel),
        "in section 2.8 but not accepted: bezier",
    )
    must_report(
        "a skin word struck from the contract",
        seeded(contract.replace("`triwest` ", ""), kernel),
        "accepted but not in section 2.8: triwest",
    )
    must_report(
        "a side word added to the kernel",
        seeded(contract, kernel.replace(
            "        {cup}   { \\__tenkz_kernel_stage_put:nn {#1} {cup}   }\n",
            "        {cup}   { \\__tenkz_kernel_stage_put:nn {#1} {cup}   }\n"
            "        {seal}  { \\__tenkz_kernel_stage_put:nn {#1} {none}  }\n")),
        "accepted but not in section 2.8: seal",
    )
    must_report(
        "a form word added to the choice table",
        seeded(contract, kernel.replace("  { bracket, enclosure, label, prose }\n",
                                        "  { bracket, enclosure, label, prose, band }\n")),
        "accepted but not in section 2.8: band",
    )
    drifted = [
        tenkz_language.Entry(
            entry.kind,
            (*entry.fields[:2], "enum(bracket|enclosure|label)", *entry.fields[3:]),
        )
        if entry.kind == "key" and entry.fields[:2] == ("kernel-mark", "form")
        else entry
        for entry in registry
    ]
    must_report(
        "the registry row drifting from the parser",
        seeded(contract, kernel, drifted),
        "but the parser accepts bracket, enclosure, label, prose",
    )
    must_report(
        "the recording word retired from both acceptors",
        seeded(contract, kernel.replace("  { bracket, enclosure, label, prose }\n",
                                        "  { bracket, enclosure, label }\n"), drifted),
        "recording word",
    )

    # Malformed contract spellings the reader must refuse, not step over.
    anchor = "| routes | `straight` `orth` `arc` |"
    header = "| Alphabet | Words |\n|---|---|"
    for label, text, expected in (
        ("a duplicate alphabet row", contract.replace(anchor, f"{anchor}\n| routes | `straight` |"), "twice"),
        ("bare text beside the words", contract.replace(anchor, "| routes | `straight` `orth` `arc` bezier |"), "cannot name"),
        ("a row opening with bare text", contract.replace(anchor, f"{anchor}\n| weights | thin thick |"), "cannot name"),
        ("a row with no alphabet name", contract.replace(anchor, f"{anchor}\n|  | `bezier` |"), "cannot name"),
        ("a row with an extra cell", contract.replace(anchor, f"{anchor}\n| weights | `thin` | `thick` |"), "cannot name"),
        ("a renamed header", contract.replace("| Alphabet | Words |", "| Deprecated | Replacements |", 1), "header reads"),
        ("a one-cell delimiter", contract.replace(header, "| Alphabet | Words |\n|---|", 1), "delimiter"),
        ("a delimiter with too few hyphens", contract.replace(header, "| Alphabet | Words |\n|-|-|", 1), "delimiter"),
        ("a second section 2.8", contract + "\n### 2.8 Closed alphabets\n\n| Alphabet | Words |\n|---|---|\n| routes | `bezier` |\n", "section 2.8s"),
    ):
        if text == contract:
            raise SystemExit(f"seed {label!r} changed nothing")
        must_report(label, seeded(text, kernel), expected)

    # Kernel spellings that change what is accepted.
    for label, text, expected in (
        ("a parser replaced by another definition",
         f"{kernel}\n\\cs_set:Nn \\__tenkz_kernel_route:n {{ }}\n", "times"),
        ("a parser matching with no fallback",
         kernel.replace(r"\str_case:VnF \l__tenkz_kernel_list_item_tl",
                        r"\str_case:Vn \l__tenkz_kernel_list_item_tl", 1), "no fallback"),
        ("a branch that refuses its own word",
         kernel.replace(r"{arc}      { \__tenkz_kernel_route_keep: }",
                        r"{arc}      { \msg_expandable_error:nnn {a}{b}{c} }"),
         "branch refuses the word"),
        ("a branch key the reader cannot name",
         kernel.replace(
             "        {cup}   { \\__tenkz_kernel_stage_put:nn {#1} {cup}   }\n",
             "        {cup}   { \\__tenkz_kernel_stage_put:nn {#1} {cup}   }\n"
             "        {\\l_tenkz_word_tl} { }\n"),
         "cannot name"),
        ("a second choice table for one key",
         f"{kernel}\n\\__tenkz_kernel_choice:nnnx {{ tenkz-kernel-mark }} "
         "{ form } { bracket, enclosure, label, prose, glow } { form }\n",
         "choice tables"),
    ):
        if text == kernel:
            raise SystemExit(f"seed {label!r} changed nothing")
        must_report(label, seeded(contract, text), expected)

    # Benign spellings that must not report.
    reordered = [
        tenkz_language.Entry(
            entry.kind,
            (*entry.fields[:2], "enum(prose|label|enclosure|bracket)", *entry.fields[3:]),
        )
        if entry.kind == "key" and entry.fields[:2] == ("kernel-mark", "form")
        else entry
        for entry in registry
    ]
    if seeded(contract, kernel, reordered):
        raise SystemExit("a reordered enum row was reported as drift")
    unspaced = contract.replace(
        "| mark forms | `bracket` `enclosure` `label` |\n\n",
        "| mark forms | `bracket` `enclosure` `label` |\n", 1,
    )
    if unspaced != contract and seeded(unspaced, kernel):
        raise SystemExit("prose closing the table was reported as an interruption")


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
    # anywhere; from here on every check compiles.
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
    kernel = tenkz_language.kernel_source()
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
