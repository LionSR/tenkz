#!/usr/bin/env python3
"""Build the compact tenkz manual reproducibly (LionSR/tenkz#8).

`build` compiles `docs/tenkz/manual2.tex` in an isolated directory holding
only the manual's own sources, under a `SOURCE_DATE_EPOCH` derived from the
package's `\\ProvidesPackage` date, runs the two passes the contents need,
audits the event stream, and prints the PDF's SHA-256.  `check` performs
two such builds in two directories and requires their PDFs to be identical
byte for byte, so the archive can carry a manual whose bytes any machine
with the same TeX installation reproduces.  The package's version and date
must agree with the manual's title page in both commands: a manual dated
against a different release is not the release's documentation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tenkz_audit import Audit

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "tex" / "tenkz" / "tenkz.sty"
MANUAL_DIR = ROOT / "docs" / "tenkz"
MANUAL = MANUAL_DIR / "manual2.tex"
# Everything the manual reads besides the package itself.  A source the
# manual grows must be added here, and the isolated build fails loudly when
# it is not, because the copy is what makes the build reproducible.
MANUAL_SOURCES = ("manual2.tex", "tenkzmanual2.sty", "chapters2")
PASSES = 2
DEFAULT_OUTPUT = ROOT / "output" / "pdf" / "tenkz-manual.pdf"


def package_release() -> tuple[str, str]:
    """The `\\ProvidesPackage` date (YYYY/MM/DD) and version of tenkz.sty."""
    text = PACKAGE.read_text(encoding="utf-8")
    match = re.search(
        r"\\ProvidesPackage\{tenkz\}\[(\d{4}/\d{2}/\d{2}) v([0-9.]+)", text
    )
    if match is None:
        raise ValueError("tenkz.sty has no \\ProvidesPackage date and version")
    return match.group(1), match.group(2)


def manual_dateline(text: str | None = None) -> str:
    """The title page's month and year, as `tenkz_ctan.py sync` reads it."""
    text = MANUAL.read_text(encoding="utf-8") if text is None else text
    match = re.search(r"The TNLean project \\quad---\\quad ([^\\]*)\\par", text)
    if match is None:
        raise ValueError("manual2.tex has no title-page date line")
    return match.group(1).strip()


def source_date_epoch(date: str) -> int:
    year, month, day = (int(part) for part in date.split("/"))
    return int(dt.datetime(year, month, day, tzinfo=dt.timezone.utc).timestamp())


def metadata_errors(package_date: str, dateline: str) -> list[str]:
    """The manual's date line must name the package's month and year."""
    year, month, _day = (int(part) for part in package_date.split("/"))
    expected = f"{dt.date(year, month, 1):%B %Y}"
    if dateline != expected:
        return [
            f"manual2.tex title page reads {dateline!r} but tenkz.sty is dated "
            f"{package_date} ({expected!r}); synchronize the release metadata"
        ]
    return []


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(work: Path, epoch: int, engine: str = "xelatex") -> tuple[bytes, list[str]]:
    """Compile the manual in `work`; return the PDF bytes and audit lines."""
    work.mkdir(parents=True, exist_ok=True)
    for name in MANUAL_SOURCES:
        source = MANUAL_DIR / name
        if not source.exists():
            raise FileNotFoundError(f"manual source {source} is missing")
        if source.is_dir():
            shutil.copytree(source, work / name)
        else:
            shutil.copy2(source, work / name)
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = str(epoch)
    env["FORCE_SOURCE_DATE"] = "1"
    # Only the package tree is reachable: the manual's own directory is
    # deliberately not on the path, so a stale generated file there cannot
    # leak into the build.
    env["TEXINPUTS"] = f"{ROOT / 'tex' / 'tenkz'}//:"
    for number in range(1, PASSES + 1):
        run = subprocess.run(
            [engine, "-interaction=nonstopmode", "-halt-on-error", "manual2.tex"],
            cwd=work,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=600,
        )
        if run.returncode:
            tail = "\n".join(run.stdout.splitlines()[-40:])
            raise RuntimeError(f"manual pass {number} failed in {work}:\n{tail}")
    log = work / "manual2.tnlog"
    if not log.is_file() or not log.read_text(encoding="utf-8").strip():
        raise RuntimeError("the manual build emitted no event stream")
    findings: list[str] = []
    audit = Audit(log, work / "manual2.tex")
    if audit.run():
        raise RuntimeError("the manual's event stream has hard audit findings")
    findings.extend(f"{f.severity} [{f.rule}] {f.msg}" for f in audit.findings)
    return (work / "manual2.pdf").read_bytes(), findings


def compare(first: bytes, second: bytes) -> list[str]:
    """Two builds of one source must agree byte for byte."""
    if first == second:
        return []
    prefix = 0
    for a, b in zip(first, second):
        if a != b:
            break
        prefix += 1
    return [
        f"the two manual builds differ: {sha256(first)} vs {sha256(second)} "
        f"({len(first)} and {len(second)} bytes; first difference at byte {prefix})"
    ]


def install(data: bytes, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("build", "check"))
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help=f"where to install the PDF (default {DEFAULT_OUTPUT.relative_to(ROOT)})",
    )
    parser.add_argument("--engine", default="xelatex")
    parser.add_argument(
        "--require-engine", action="store_true",
        help="fail rather than skip when the engine is not installed",
    )
    args = parser.parse_args()
    date, version = package_release()
    errors = metadata_errors(date, manual_dateline())
    if errors:
        for error in errors:
            print(f"tenkz-manual: {error}", file=sys.stderr)
        return 1
    if shutil.which(args.engine) is None:
        if args.require_engine:
            print(f"tenkz-manual: {args.engine} not found", file=sys.stderr)
            return 1
        print(f"SKIP: {args.engine} not found")
        return 0
    epoch = source_date_epoch(date)
    builds = 2 if args.action == "check" else 1
    pdfs: list[bytes] = []
    with tempfile.TemporaryDirectory(prefix="tenkz-manual-") as tmp:
        for number in range(1, builds + 1):
            work = Path(tmp) / f"build{number}"
            work.mkdir()
            try:
                pdf, findings = build(work, epoch, args.engine)
            except (RuntimeError, FileNotFoundError) as exc:
                print(f"tenkz-manual: {exc}", file=sys.stderr)
                return 1
            pdfs.append(pdf)
            print(f"build {number}: {sha256(pdf)} ({len(pdf)} bytes, {len(findings)} audit advisories)")
    if builds == 2:
        errors = compare(pdfs[0], pdfs[1])
        if errors:
            for error in errors:
                print(f"tenkz-manual: {error}", file=sys.stderr)
            return 1
    install(pdfs[0], args.output)
    print(
        f"PASS: tenkz manual v{version} ({date}) built "
        f"{'reproducibly ' if builds == 2 else ''}under SOURCE_DATE_EPOCH={epoch}; "
        f"installed to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
