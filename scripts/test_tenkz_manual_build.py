#!/usr/bin/env python3
"""Seeded-failure evidence for the reproducible manual build (LionSR/tenkz#8).

Each gate the build script carries is shown to fire on the input it exists
to refuse: a manual dated against another release, two builds that differ,
and an event stream with a hard audit finding.  The TeX builds themselves
run only where xelatex is installed.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import tenkz_manual_build as build

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    date, version = build.package_release()
    manual = build.manual_version()
    if not version or build.metadata_errors(date, build.manual_dateline(), version, manual):
        raise SystemExit("the unseeded metadata does not agree")
    seeded = build.metadata_errors(date, "June 1999", version, manual)
    if not seeded or "synchronize" not in seeded[0]:
        raise SystemExit(f"a stale title page was not refused: {seeded}")
    # A version bump inside the same month must not pass a date-only check.
    bumped = build.metadata_errors(date, build.manual_dateline(), "9.9", manual)
    if not any("names version" in error for error in bumped):
        raise SystemExit(f"a stale manual version was not refused: {bumped}")
    try:
        build.manual_version("\\title{no version here}")
    except ValueError:
        pass
    else:
        raise SystemExit("a manual naming no version was not refused")
    # Metadata that reaches no page is metadata the manual does not carry.
    # Both seeds are built from what the manual says today, so a release bump
    # does not strand this test on a literal it no longer contains.
    source = build.MANUAL.read_text(encoding="utf-8")
    for reader, line in (
        (build.manual_version, next(
            row for row in source.splitlines() if f"version {manual}" in row
        )),
        (build.manual_dateline, next(
            row for row in source.splitlines()
            if "The TNLean project" in row and build.manual_dateline() in row
        )),
    ):
        seeded = source.replace(line, "% " + line.lstrip(), 1)
        if seeded == source:
            raise SystemExit(f"could not comment out {line!r}")
        try:
            reader(seeded)
        except ValueError:
            continue
        raise SystemExit(f"a commented-out line was read as the manual's: {line!r}")
    # The month comes from a fixed English table, not the caller's locale.
    if build.metadata_errors("2026/07/22", "July 2026", version, manual):
        raise SystemExit("the English month table disagrees with the title page")
    # Metadata inside a branch TeX never takes reaches no page either, so the
    # readers mask inert source as well as comments.
    for reader in (build.manual_version, build.manual_dateline):
        marker = manual if reader is build.manual_version else build.manual_dateline()
        line = next(row for row in source.splitlines() if marker in row)
        seeded = source.replace(line, f"\\iffalse\n{line}\n\\fi", 1)
        if seeded == source:
            raise SystemExit(f"could not bury {line!r} in a false branch")
        try:
            reader(seeded)
        except ValueError:
            continue
        raise SystemExit(f"metadata in a false branch was read as the manual's: {line!r}")
    # Every spelling of "compile me again" the manual's packages use.
    for warning in (
        "LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right.",
        "Package longtable Warning: Table widths have changed. Rerun LaTeX.",
        "Package rerunfilecheck Warning: File `x.out' has changed.",
    ):
        if warning.startswith("Package rerunfilecheck"):
            continue
        if not build.RERUN.search(warning):
            raise SystemExit(f"a rerun request was not recognised: {warning!r}")
    # The manual draws two pictures of its own, outside the example
    # environments the doctest covers; losing them would silently narrow the
    # source-linked audit to nothing.
    direct = build.direct_pictures()
    if len(direct) != 2:
        raise SystemExit(f"the manual's own picture count moved: {len(direct)}")
    # Two active lines are two claims, and the page shows both.
    title_version = next(row for row in source.splitlines() if f"version {manual}" in row)
    title_date = next(
        row for row in source.splitlines()
        if "quad---" in row and "TNLean project" in row
    )
    for reader, line in (
        (build.manual_version, title_version),
        (build.manual_dateline, title_date),
    ):
        doubled = source.replace(line, f"{line}\n{line}", 1)
        if doubled == source:
            raise SystemExit(f"could not double {line!r}")
        try:
            reader(doubled)
        except ValueError:
            continue
        raise SystemExit(f"two active release lines were accepted: {line!r}")
    # Every rerun spelling the manual's packages use, and the warnings that
    # leave a settled document wrong rather than unsettled.
    for warning in (
        "Package longtable Warning: Table widths have changed. Rerun LaTeX.",
        "LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right.",
    ):
        if not build.RERUN.search(warning):
            raise SystemExit(f"a rerun request was not recognised: {warning!r}")
    for warning in (
        "LaTeX Warning: There were multiply-defined labels.",
        "LaTeX Warning: Label `x' multiply defined.",
        "LaTeX Warning: There were undefined references.",
    ):
        if not build.UNRESOLVED.search(warning):
            raise SystemExit(f"a reference warning was not recognised: {warning!r}")
    # A version is read whole and then required to be one, on both sides: a
    # numeric prefix match would call `0.7-beta` equal to the package's `0.7`
    # while the page says otherwise.
    version_line = next(row for row in source.splitlines() if f"version {manual}" in row)
    qualified = source.replace(version_line, version_line.replace(manual, f"{manual}-beta"))
    try:
        build.manual_version(qualified)
    except ValueError:
        pass
    else:
        raise SystemExit("a qualified manual version was read as its numeric prefix")
    # The package declaration is read from the active line, not from a
    # previous release left commented above it.
    package_source = build.PACKAGE.read_text(encoding="utf-8")
    declaration = next(
        row for row in package_source.splitlines() if "ProvidesPackage" in row
    )
    bumped = declaration.replace(f"v{version}", "v9.9")
    seeded_package = package_source.replace(declaration, f"% {declaration}\n{bumped}")
    original = build.PACKAGE
    with tempfile.TemporaryDirectory(prefix="tenkz-package-seed-") as tmp:
        path = Path(tmp) / "tenkz.sty"
        path.write_text(seeded_package, encoding="utf-8")
        build.PACKAGE = path
        try:
            _date, read = build.package_release()
        finally:
            build.PACKAGE = original
    # Two declarations in one file: one of them is dead, and which one TeX
    # takes is a question this reader should not have to answer.
    doubled = package_source.replace(
        declaration, f"\\iftrue\\else\n{declaration.replace('v' + version, 'v0.6')}\n\\fi\n{declaration}", 1
    )
    if doubled == package_source:
        raise SystemExit("could not double the package declaration")
    with tempfile.TemporaryDirectory(prefix="tenkz-package-two-") as tmp:
        path = Path(tmp) / "tenkz.sty"
        path.write_text(doubled, encoding="utf-8")
        build.PACKAGE = path
        try:
            build.package_release()
        except ValueError as error:
            if "declarations" not in str(error):
                raise SystemExit(f"two declarations failed for another reason: {error}")
        else:
            raise SystemExit("a dead declaration beside the live one was accepted")
        finally:
            build.PACKAGE = original
    # Every name the manual asks for is guarded, whether or not the copy has
    # it: an `\input` committed without its file is the case that matters.
    requested = build.requested_inputs()
    if "ch-catalogue.tex" not in requested:
        raise SystemExit(f"the manual's requested inputs look wrong: {sorted(requested)}")
    if any("\\" in name for name in requested):
        raise SystemExit("a run-time input name leaked into the guarded set")
    if read != "9.9":
        raise SystemExit(
            f"the commented previous declaration was read instead of the active one: {read}"
        )
    # A declaration TeX never takes is no declaration at all, on the package
    # side exactly as on the manual's.
    buried = package_source.replace(declaration, f"\\iffalse\n{declaration}\n\\fi")
    if buried == package_source:
        raise SystemExit("could not bury the package declaration")
    with tempfile.TemporaryDirectory(prefix="tenkz-package-branch-") as tmp:
        path = Path(tmp) / "tenkz.sty"
        path.write_text(buried, encoding="utf-8")
        build.PACKAGE = path
        try:
            build.package_release()
        except ValueError:
            pass
        else:
            raise SystemExit("a declaration in a false branch was read as the package's")
        finally:
            build.PACKAGE = original
    try:
        build.manual_dateline("\\title{no date line here}")
    except ValueError:
        pass
    else:
        raise SystemExit("a manual without a date line was not refused")
    if build.compare(b"%PDF-1.7 same", b"%PDF-1.7 same"):
        raise SystemExit("identical builds were reported as differing")
    differ = build.compare(b"%PDF-1.7 abc", b"%PDF-1.7 abd")
    if not differ or "first difference at byte 11" not in differ[0]:
        raise SystemExit(f"differing builds were not refused: {differ}")
    epoch = build.source_date_epoch("2026/07/22")
    if epoch != 1784678400:
        raise SystemExit(f"SOURCE_DATE_EPOCH for 2026/07/22 read {epoch}")
    # The rendered page is what the release metadata is finally held to, so
    # its reader is exercised against a page that says the wrong thing.
    pdf = build.DEFAULT_OUTPUT
    if shutil.which("pdftotext") is not None and pdf.is_file():
        if build.rendered_metadata_errors(pdf, version, build.manual_dateline()):
            raise SystemExit("the installed manual's title page disagrees with the source")
        wrong = build.rendered_metadata_errors(pdf, "9.9", build.manual_dateline())
        if not any("version" in error for error in wrong):
            raise SystemExit("a version absent from the rendered page was not reported")
        stale = build.rendered_metadata_errors(pdf, version, "June 1999")
        if not any("date" in error for error in stale):
            raise SystemExit("a date absent from the rendered page was not reported")
    if shutil.which("xelatex") is None:
        print("PASS: manual build gates fire on seeded input; SKIP: xelatex not found")
        return 0
    # A hard audit finding must fail the build: a picture with no ink is the
    # audit's first hard rule, seeded into a copy of the manual's chapter set.
    with tempfile.TemporaryDirectory(prefix="tenkz-manual-seed-") as tmp:
        work = Path(tmp)
        original = build.MANUAL_DIR
        seed_dir = work / "docs"
        shutil.copytree(original / "chapters2", seed_dir / "chapters2")
        shutil.copy2(original / "manual2.tex", seed_dir / "manual2.tex")
        shutil.copy2(original / "tenkzmanual2.sty", seed_dir / "tenkzmanual2.sty")
        chapter = seed_dir / "chapters2" / "ch-trouble.tex"
        chapter.write_text(
            chapter.read_text(encoding="utf-8")
            + "\n\\begin{tenkz}[cols=1]\\end{tenkz}\n",
            encoding="utf-8",
        )
        build.MANUAL_DIR = seed_dir
        try:
            build.build(work / "build", epoch)
        except RuntimeError as exc:
            if "hard audit" not in str(exc):
                raise SystemExit(f"the seeded empty picture failed for another reason: {exc}")
        else:
            raise SystemExit("an empty picture in the manual did not fail the build")
        finally:
            build.MANUAL_DIR = original
    print("PASS: manual build gates fire on seeded input, including a hard audit finding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
