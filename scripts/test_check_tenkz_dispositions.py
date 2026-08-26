#!/usr/bin/env python3
"""Focused regression tests for the tenkz disposition checker."""

from __future__ import annotations

import re
from collections import Counter
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_tenkz_dispositions as guard


def test_document_gates_fire_on_seeded_tables() -> None:
    """LionSR/tenkz#6: the document-only checks refuse a seeded edit by name."""
    text = guard.DOCUMENT.read_text()
    seeded = text.replace("| preserve | 9 |", "| preserve | 9 |\n| bogus | 1 |", 1)
    assert seeded != text, "the standalone fixture table no longer has the preserve row"
    try:
        guard.parse_fixture_table(seeded)
    except SystemExit as error:
        assert "unknown dispositions: ['bogus']" in str(error), error
    else:
        raise AssertionError("an unknown disposition word in the fixture table passed")
    raw_body = guard.section(text, "| Raw construct | Occurrences |")
    total_row = next(row for row in raw_body.splitlines() if row.startswith("| **Total**"))
    seeded_total = text.replace(total_row, total_row.replace("**", "*9*", 1), 1)
    assert seeded_total != text
    _, before = guard.parse_counter_table(text, "| Raw construct | Occurrences |")
    try:
        guard.parse_counter_table(seeded_total, "| Raw construct | Occurrences |")
    except SystemExit:
        pass
    else:
        raise AssertionError("a mangled blueprint total row was parsed as valid")
    assert before == sum(guard.documented_blueprint(text)[0].values())


def _expect_document_failure(seeded: str, expected: str, name: str) -> None:
    """Run the whole checker against a seeded document and require it to fail."""
    original = guard.DOCUMENT
    with tempfile.TemporaryDirectory(prefix="tenkz-disposition-seed-") as tmp:
        path = Path(tmp) / "DISPOSITIONS.md"
        path.write_text(seeded, encoding="utf-8")
        guard.DOCUMENT = path
        try:
            guard.main()
        except SystemExit as error:
            if expected not in str(error):
                raise AssertionError(f"seed {name!r} failed for another reason: {error}")
        else:
            raise AssertionError(f"seed {name!r} passed the checker")
        finally:
            guard.DOCUMENT = original


def test_document_only_blueprint_gates_fire() -> None:
    """LionSR/tenkz#6: the checks that run without the chapter sources fire.

    Every seed below keeps the totals adding up, which is what the blueprint
    reconciliation looked like while it was skipped entirely, and each is run
    through the whole checker rather than through one function.
    """
    text = guard.DOCUMENT.read_text()
    if guard.BLUEPRINT_ROOT.is_dir():
        print("SKIP: blueprint sources present; the document-only path is not taken")
        return
    guard.main()

    # A construct moved between raw rows: both totals stay where they were.
    _expect_document_failure(
        text.replace("| `tenkz` | 188 |", "| `tenkz` | 187 |", 1)
            .replace("| `tntree` | 11 |", "| `tntree` | 12 |", 1),
        "raw-count table does not match the line inventory",
        "construct moved between raw rows",
    )
    # One occurrence inventoried twice, with the totals raised to match.
    _expect_document_failure(
        text.replace("| `ch03_single.tex` | L228 ", "| `ch03_single.tex` | L228, 228 ", 1)
            .replace("| `tenkz` | 188 |", "| `tenkz` | 189 |", 1)
            .replace("| **Total** | **199** |", "| **Total** | **200** |")
            .replace("| preserve | 188 |", "| preserve | 189 |", 1),
        "more than once",
        "occurrence listed twice",
    )
    # A target code the migration table does not define.
    _expect_document_failure(
        text.replace("L228 `tenkz` → `P-grid`", "L228 `tenkz` → `BOGUS`", 1),
        "unknown target code",
        "unknown target code",
    )
    # A preserve entry pointed at a redraw target.
    _expect_document_failure(
        text.replace("L228 `tenkz` → `P-grid`", "L228 `tenkz` → `R-free`", 1),
        "imply redraw",
        "preserve entry with a redraw target",
    )
    # A second occurrence written in a spelling the grammar does not read,
    # which leaves every counter where it was.
    _expect_document_failure(
        text.replace(
            "| `ch03_single.tex` | L228 `tenkz` → `P-grid` |",
            "| `ch03_single.tex` | L228 `tenkz` → `P-grid`; L229 tenkz -> P-grid |",
            1,
        ),
        "the occurrence grammar does not read",
        "cell text outside the grammar",
    )
    # A migration code outside P/C/R would be filed as preserve by default.
    _expect_document_failure(
        text.replace(
            "| `P-none` |", "| `X-grid` | A typo. |\n| `P-none` |", 1
        ),
        "outside P/C/R",
        "migration code outside the three families",
    )
    # A deleted zero row is not a zero: the totals do not move.
    _expect_document_failure(
        text.replace("| `tenkzcd` | 0 |\n", "", 1),
        "every tracked construct row",
        "deleted zero ratchet row",
    )
    # A repeated row overwrites the earlier one and the total still adds up.
    _expect_document_failure(
        text.replace("| preserve | 9 |", "| preserve | 999 |\n| preserve | 9 |", 1),
        "more than once",
        "duplicate fixture disposition row",
    )
    _expect_document_failure(
        text.replace("| `tntree` | 11 |", "| `tntree` | 999 |\n| `tntree` | 11 |", 1),
        "more than once",
        "duplicate blueprint raw row",
    )
    # The fixture ratchet must be consulted, not merely declared.
    _expect_document_failure(
        text.replace("| `tnpic` | 0 |\n| `tntree` | 0 |\n", "| `tntree` | 0 |\n", 1),
        "fixture raw-count table must carry",
        "deleted fixture zero ratchet row",
    )
    # A malformed row naming the header word is still a data row.
    _expect_document_failure(
        text.replace("| preserve | 9 |", "| bogusDisposition | 1 |\n| preserve | 9 |", 1),
        "unknown dispositions",
        "row containing the header word",
    )
    # A repeated migration code makes the canonical table ambiguous.
    _expect_document_failure(
        text.replace("| `P-none` |", "| `P-grid` | A contradictory second row. |\n| `P-none` |", 1),
        "more than once",
        "duplicate migration code",
    )
    # A counter row the grammar cannot read leaves every number in place.
    _expect_document_failure(
        text.replace("| `tntree` | 11 |", "| `bogus` | eleven |\n| `tntree` | 11 |", 1),
        "a row it cannot read",
        "unreadable counter row",
    )
    # Source lines are one-based, so `L0` names nothing.
    _expect_document_failure(
        text.replace("| `ch03_single.tex` | L228 ", "| `ch03_single.tex` | L0 ", 1),
        "the occurrence grammar does not read",
        "zero line number",
    )
    # A malformed definition in the canonical table, unreferenced today.
    _expect_document_failure(
        text.replace("| `C-picture` |", "| `C-pictur3` |", 1),
        "a row it cannot read",
        "malformed migration definition",
    )
    # A target set mixing preserve with a codemod code: the source classifier
    # drops every P- code as soon as another family is present, so no source
    # produces this, yet reading the strongest family alone accepts it.
    _expect_document_failure(
        text.replace("`tntree` → `C-tree`", "`tntree` → `P-grid+C-tree`", 1),
        "mixes preserve and non-preserve",
        "mixed preserve and codemod targets",
    )
    # An unreadable row standing before the first valid entry is still a row.
    _expect_document_failure(
        text.replace("| `tenkz` | 188 |", "| `bogus` | eleven |\n| `tenkz` | 188 |", 1),
        "a row it cannot read",
        "unreadable counter row before the first entry",
    )
    # A mistyped source name would drop its occurrences from the inventory,
    # and the totals could then be lowered to agree.
    _expect_document_failure(
        text.replace("| `ch03_single.tex` |", "| `ch03_single.tx` |", 1)
            .replace("| `tenkz` | 188 |", "| `tenkz` | 187 |", 1)
            .replace("| **Total** | **199** |", "| **Total** | **198** |")
            .replace("| preserve | 188 |", "| preserve | 187 |", 1),
        "a row it cannot read",
        "mistyped inventory source name",
    )


def test_fixture_table_reads_every_row() -> None:
    """A row the grammar cannot read is refused rather than skipped."""
    text = guard.DOCUMENT.read_text()
    for seed in ("| BOGUS | 1 |", "| bogus-value | 1 |"):
        seeded = text.replace("| preserve | 9 |", f"| preserve | 9 |\n{seed}", 1)
        assert seeded != text
        try:
            guard.parse_fixture_table(seeded)
        except SystemExit as error:
            assert "unknown dispositions" in str(error), (seed, str(error))
        else:
            raise AssertionError(f"the fixture table accepted {seed!r}")


def main() -> int:
    test_document_gates_fire_on_seeded_tables()
    test_document_only_blueprint_gates_fire()
    test_fixture_table_reads_every_row()
    tombstones = (
        r"\begin{tenkzfree}\end{tenkzfree}",
        r"\tnghost{}",
        r"\tnset{tensor style=box}",
        r"\tnset{compact}",
        r"\tnwire[route=hv]{}{}",
        r"\begin{tenkz}[rows={op:none}]\end{tenkz}",
        r"\tnfuse[rows=2]{}",
        r"\tnmark[form=brace-below]{}{}",
        r"\tnmark[form={brace-below}]{}{}",
        r"\tnspan[brace below]{2}{}",
        r"\tnspan[brace above]{2}{}",
        r"\tn[cluster]{}",
        r"\tn[enclosure]{}",
        r"\tn[poly=5]{}",
        r"\begin{tenkz}[boundary legs]\end{tenkz}",
        r"\begin{tenkz}[frame={rotate=90}]\end{tenkz}",
        r"\begin{tenkz}[frame={matrix={1,0,0,1}}]\end{tenkz}",
        r"\begin{tenkzcd}[maps]\end{tenkzcd}",
        r"\begin{tenkz}[bond dir=right]\end{tenkz}",
        r"\begin{tenkz}[up={i}]\end{tenkz}",
        r"\begin{tenkz}[down={j}]\end{tenkz}",
        r"\tnbond[none]{a}{b}",
        r"\begin{tenkz}[layer sep=2]\tn{}\end{tenkz}",
        r"\tntree[tree style=wire]{(a,b)}",
        r"\begin{tenkz}[invented key=value]\tn{}\end{tenkz}",
        r"\begin{tenkz}[invented-key=value]\tn{}\end{tenkz}",
        r"\tn[invented key=value]{}",
        r"\tndeclare{species}{x}{invented-key=}",
        r"\tndeclareatom{\tnprojector}{invented-key=}",
        r"\tngroup[form=label]{}",
        r"\tnpic[maps]{}",
        r"\tnpic[boundary legs]{}",
        "\\tntree\n[invented-key=]{(a,b)}",
    )
    for source in tombstones:
        assert guard.uses_tombstone(source), source

    accepted = (
        r"\begin{tenkz}[rows={op}, cols=2]\tn{}\end{tenkz}",
        r"\tn[box]{}",
        r"\tn[pill]{}",
        r"\tnfuse[span=2]{}",
        r"\tnmark[form=bracket]{}{}",
        r"\tnmark[form=enclosure]{{(1,1)}}{}",
        r"\tnmark[form=enclosure]{(1,1) .. (3,3) - (2,2)}{}",
        r"\tnwire[route=orth]{}{}",
        r"\tnset{species={left,right}}",
        r"\begin{tenkz}[frame={plane, basis={ket at (0,0), bra at (2,2)}}]"
        r"\end{tenkz}",
        r"\begin{tenkz}[frame={flat, basis={wire at (0,0), wire at (2,0)}}]"
        r"\end{tenkz}",
        r"\begin{tenkz}[rows={wire}, cols=2]\tn[skin=box, wide=2]{}"
        r"\tnwire[route=orth, dir=forward]{}{}\end{tenkz}",
        r"\tndeclare{species}{x}{hue=blue, base=box, pairings={up:down}}",
        r"\tngroup[frame=flat]{}",
        r"\begin{tenkz}\tn{$in=x$}\tn{weight=2}\tn{role=x}\end{tenkz}",
    )
    for source in accepted:
        assert not guard.uses_tombstone(source), source
    # Since the S4 surface swap the kernel reaches every construct, so a
    # signed key (physical=) owes no work; the 0.7 atom flag still does.
    assert guard.source_target_codes(
        r"\begin{tenkz}[physical=up]\tn[box]{}\end{tenkz}"
    ) == frozenset({"C-record"})
    assert guard.source_target_codes(
        r"\tnset{species={alpha,beta}}"
    ) == frozenset({"C-declare"})
    assert guard.source_target_codes(r"\tndeclareatom{pill}") == frozenset(
        {"C-declare"}
    )
    assert guard.source_target_codes(
        r"\tndeclareatom{\tnprojector}{skin=box, ports={west:virtual}}"
    ) == frozenset({"C-declare"})
    assert guard.source_target_codes(r"\tenkzkernel") == frozenset({"C-switch"})
    for source in (
        r"\tnset{}",
        r"\tndeclare{}{}{}",
        r"\tndeclareatom{}",
        r"\tenkzkernel",
    ):
        assert guard.SETUP_COMMAND.search(source), source
    assert guard.source_target_codes(r"\tn[pill]{}") == frozenset({"C-record"})
    # cluster={RxC} is the signed kernel basis sugar, so it owes no work
    # under the load-time surface.
    assert guard.source_target_codes(r"\tn[cluster={2x3}]{}") == frozenset(
        {"P-grid"}
    )
    for source in (
        r"\begin{tenkz}\tn{$in=x$}\end{tenkz}",
        r"\begin{tenkz}\tn{weight=2}\end{tenkz}",
        r"\begin{tenkz}\tn{role=x}\end{tenkz}",
        r"\tngroup[frame=flat]{}",
        r"\tndeclare{species}{x}{hue=blue, base=box, pairings={up:down}}",
    ):
        assert guard.source_target_codes(source) == frozenset({"P-grid"}), source
    assert guard.source_target_codes("\\tntree\n[skin=box]{(a,b)}") == frozenset(
        {"C-tree"}
    )
    assert guard.source_target_codes(
        r"\begin{tenkzfree}\tnghost{}\end{tenkzfree}"
        r"\begin{tenkz}[physical=up]\tn{}\end{tenkz}"
    ) == frozenset({"R-free", "R-record"})
    assert guard.fragment_target_codes(
        r"\begin{tenkz}[physical=up]\tnspan[brace below]{2}{}\end{tenkz}"
    ) == frozenset({"C-policy", "C-record", "R-record"})

    # A signed kernel row owes no migration work under the kernel switch,
    # whether its registry status is kernel or sugar; the same key on a 0.7
    # picture still does, because the two tiers read it differently.
    signed_sugar = (
        r"\begin{tenkz}[physical=up]\tn{}\end{tenkz}",
        r"\begin{tenkz}[boundary=periodic]\tn{}\end{tenkz}",
        r"\begin{tenkz}[sandwich]\tn{}\end{tenkz}",
        r"\begin{tenkz}[lattice={2x2}]\tn{}\end{tenkz}",
        r"\begin{tenkz}[ring=4]\tn{}\end{tenkz}",
        r"\begin{tenkz}[surface=torus]\tn{}\end{tenkz}",
        r"\begin{tenkz}[west={cup=$m$}]\tn{}\end{tenkz}",
        r"\begin{tenkz}\tn[cluster={2x3}]{}\end{tenkz}",
        r"\begin{tenkz}\tn[role=operator]{}\end{tenkz}",
    )
    for source in signed_sugar:
        assert guard.fragment_target_codes(source, True) == frozenset(
            {"P-grid"}
        ), source
        assert guard.fragment_target_codes(source) != frozenset({"P-grid"}), source

    # A sugar command the kernel binds (tnfuse, tnbond) owes no migration
    # work under the switch; one it does not yet bind still does.
    kernel_bound_sugar = (
        r"\begin{tenkz}[rows={op,op}, cols=3]"
        r"\tnfuse[at=(1,1), name=e, skin=pill]{e}\end{tenkz}",
        r"\begin{tenkz}[rows={wire,wire}, cols=2]"
        r"\tnbond{(1,1)}{(2,2)}\end{tenkz}",
    )
    for source in kernel_bound_sugar:
        assert guard.fragment_target_codes(source, True) == frozenset(
            {"P-grid"}
        ), source
        assert "C-record" in guard.fragment_target_codes(source), source
    assert "C-record" in guard.fragment_target_codes(
        r"\begin{tenkz}[rows={wire}, cols=2]\tndots\end{tenkz}", True
    )

    # Keys with no kernel row keep their codemod under the switch.
    unsigned_policy = (
        r"\begin{tenkz}[periodic]\tn{}\end{tenkz}",
        r"\begin{tenkz}[west label=$m$]\tn{}\end{tenkz}",
        r"\begin{tenkz}[bond label=$m$]\tn{}\end{tenkz}",
        r"\begin{tenkz}[west={tail=$m$}]\tn{}\end{tenkz}",
    )
    for source in unsigned_policy:
        assert "C-policy" in guard.fragment_target_codes(source, True), source

    # A tombstoned key stays a redraw under the switch even where the
    # registry still carries a kernel row of that name.
    assert guard.fragment_target_codes(
        r"\begin{tenkz}\tn[nudge={1,0}]{}\end{tenkz}", True
    ) == frozenset({"R-record"})

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        dependency = root / "dependency.inc"
        dependency.write_text(r"\begin{tenkz}\tncut{}\end{tenkz}")
        fixture = root / "fixture.tex"
        fixture.write_text(r"\input{dependency.inc}")
        expanded = guard.expanded_source(fixture)
        assert r"\tncut" in expanded
        assert guard.uses_tombstone(expanded)

        spaced_input = root / "spaced-input.tex"
        spaced_input.write_text(r"\input {dependency.inc}")
        assert r"\tncut" in guard.expanded_source(spaced_input)

        unbraced_input = root / "unbraced-input.tex"
        unbraced_input.write_text(r"\input dependency.inc")
        assert r"\tncut" in guard.expanded_source(unbraced_input)

        blueprint = root / "blueprint.tex"
        blueprint.write_text(
            r"\begin{tenkz}\tn{}\tnspan[brace below]{2}{}\end{tenkz}"
        )
        sources = guard.construct_sources(blueprint)
        construct = sources[("blueprint.tex", 1, "tenkz")]
        assert any(guard.uses_tombstone(source) for source, _ in construct)
        # The load-time surface reaches every construct.
        assert all(kernel for _, kernel in construct)

        switched = root / "switched.tex"
        switched.write_text(
            "\\begin{center}\n"
            r"\tenkzkernel" "\n"
            r"\begin{tenkz}[physical=up]\tn{}\end{tenkz}" "\n"
            "\\end{center}\n"
            r"\begin{tenkz}[physical=up]\tn{}\end{tenkz}"
        )
        switched_sources = guard.construct_sources(switched)
        # The switch's position no longer matters: the package binds the
        # kernel surface at load, so both pictures read as kernel.
        assert switched_sources[("switched.tex", 3, "tenkz")] == [
            (r"\begin{tenkz}[physical=up]\tn{}\end{tenkz}", True)
        ]
        assert switched_sources[("switched.tex", 5, "tenkz")] == [
            (r"\begin{tenkz}[physical=up]\tn{}\end{tenkz}", True)
        ]
        assert guard.source_target_codes(switched.read_text()) == frozenset(
            {"C-switch"}
        )

        cycle = root / "cycle.tex"
        cycle.write_text(r"\input{cycle.tex}")
        try:
            guard.expanded_source(cycle)
        except SystemExit as error:
            assert "recursive fixture input" in str(error)
        else:
            raise AssertionError("recursive input was not rejected")

        alias_cycle = root / "alias-cycle.tex"
        alias_cycle.write_text(r"\input{sub/../alias-cycle.tex}")
        try:
            guard.expanded_source(alias_cycle)
        except SystemExit as error:
            assert "recursive fixture input" in str(error)
        else:
            raise AssertionError("alias-path recursive input was not rejected")

        spaced = root / "spaced.tex"
        spaced.write_text(r"\begin {tenkz}\tn{}\end {tenkz}")
        assert guard.occurrences(spaced) == [(1, "tenkz")]
        assert ("spaced.tex", 1, "tenkz") in guard.construct_sources(spaced)

        multiline = root / "multiline.tex"
        multiline.write_text(
            r"\begin" "\n {tenkz}\n" r"\tn{}" "\n" r"\end" "\n {tenkz}"
        )
        normalized = guard.normalized_environment_spacing(multiline.read_text())
        assert len(normalized) == len(multiline.read_text())
        assert normalized.count("\n") == multiline.read_text().count("\n")
        assert guard.occurrences(multiline) == [(1, "tenkz")]
        assert ("multiline.tex", 1, "tenkz") in guard.construct_sources(multiline)

        equation = root / "equation.tex"
        equation.write_text(
            r"\begin{tenkzeq}\begin{tenkz}\tn{}\end{tenkz}\end{tenkzeq}"
        )
        assert guard.occurrences(equation) == [(1, "tenkzeq"), (1, "tenkz")]
        assert ("equation.tex", 1, "tenkzeq") in guard.construct_sources(equation)
        equation_source = equation.read_text()
        assert [
            construct.name for construct in guard.scan_constructs(equation_source)
        ] == ["tenkz"]
        assert [
            construct.name
            for construct in guard.scan_inventory_constructs(equation_source)
        ] == ["tenkzeq", "tenkz"]

        tree = root / "tree.tex"
        tree.write_text("\\tntree\n[skin=box]{(a,b)}")
        tree_source = tree.read_text()
        tree_sources = guard.construct_sources(tree)
        tree_key = ("tree.tex", 1, "tntree")
        assert list(tree_sources) == [tree_key]
        assert tree_sources[tree_key] == [(tree_source, True)]
        assert guard.source_target_codes(tree_source) == frozenset({"C-tree"})
        assert guard.fragment_target_codes(*tree_sources[tree_key][0]) == frozenset(
            {"C-tree"}
        )

    fixture_inventory = guard.documented_fixtures(guard.DOCUMENT.read_text())
    assert len(fixture_inventory) == 9
    assert fixture_inventory["iso_h.tex"] == (
        "preserve",
        frozenset({"P-grid"}),
    )
    assert fixture_inventory["plane_experiment.tex"] == (
        "preserve",
        frozenset({"P-none"}),
    )
    _, _, blueprint_inventory, _ = guard.documented_blueprint(
        guard.DOCUMENT.read_text()
    )
    # Structural checks only: naming a live row's disposition here would
    # break this test whenever a migration legitimately discharges it.
    assert blueprint_inventory
    assert all(
        disposition in guard.DISPOSITIONS
        for disposition in blueprint_inventory.values()
    )

    # Corrupt the first reconciliation total, whatever its current value:
    # hard-coding the live number would make this probe a silent no-op the
    # next time a migration legitimately moves the total.
    broken_total, replacements = re.subn(
        r"\| \*\*Total\*\* \| \*\*\d+\*\* \|",
        "| **Total** | **999** |",
        guard.DOCUMENT.read_text(),
        count=1,
    )
    assert replacements == 1, "no reconciliation total row found to corrupt"
    try:
        guard.parse_counter_table(
            broken_total, "| Raw construct | Occurrences |"
        )
    except SystemExit as error:
        assert "invalid total" in str(error)
    else:
        raise AssertionError("stale reconciliation total was not rejected")

    print("PASS: disposition checker detects contract and dependency regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
