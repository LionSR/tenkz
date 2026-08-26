#!/usr/bin/env python3
"""Seeded-failure evidence for the reproducible manual build (LionSR/tenkz#8).

Each gate the build script carries is shown to fire on the input it exists
to refuse: a manual dated against another release, two builds that differ,
and an event stream with a hard audit finding.  The TeX builds themselves
run only where xelatex is installed.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
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
    bumped = build.metadata_errors(date, build.manual_dateline(), "0.8", manual)
    if not any("names version" in error for error in bumped):
        raise SystemExit(f"a stale manual version was not refused: {bumped}")
    try:
        build.manual_version("\\title{no version here}")
    except ValueError:
        pass
    else:
        raise SystemExit("a manual naming no version was not refused")
    # Metadata that reaches no page is metadata the manual does not carry.
    commented = build.MANUAL.read_text(encoding="utf-8")
    commented = commented.replace(
        "  {\\small manual for \\pkg{} version 0.7\\par}",
        "  % {\\small manual for \\pkg{} version 0.7\\par}",
    )
    try:
        build.manual_version(commented)
    except ValueError:
        pass
    else:
        raise SystemExit("a commented-out version line was read as the manual's")
    commented_date = build.MANUAL.read_text(encoding="utf-8").replace(
        "  {The TNLean project \\quad---\\quad July 2026\\par}",
        "  % {The TNLean project \\quad---\\quad July 2026\\par}",
    )
    try:
        build.manual_dateline(commented_date)
    except ValueError:
        pass
    else:
        raise SystemExit("a commented-out date line was read as the manual's")
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
    if shutil.which("xelatex") is None:
        print("PASS: manual build gates fire on seeded input; SKIP: xelatex not found")
        return 0
    # A hard audit finding must fail the build: a picture with no ink is the
    # audit's first hard rule, seeded into a copy of the manual's chapter set.
    import tempfile

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
