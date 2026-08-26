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

from tenkz_audit import Audit, scan_picture_event_constructs
from tenkz_manual_doctest import _mask_inert_tex
from tenkzlib.texcase import strip_comments

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "tex" / "tenkz" / "tenkz.sty"
MANUAL_DIR = ROOT / "docs" / "tenkz"
MANUAL = MANUAL_DIR / "manual2.tex"
# Everything the manual reads besides the package itself.  A source the
# manual grows must be added here, and the isolated build fails loudly when
# it is not, because the copy is what makes the build reproducible.
MANUAL_SOURCES = ("manual2.tex", "tenkzmanual2.sty", "chapters2")
# Two passes were the documented recipe and are not enough: the manual asks
# for a rerun after its second, so the contents and cross-references it
# printed were a pass behind.  Compile until the engine stops asking, with a
# ceiling that fails rather than looping.
MINIMUM_PASSES = 2
MAXIMUM_PASSES = 6
DEFAULT_OUTPUT = ROOT / "output" / "pdf" / "tenkz-manual.pdf"
# `%B` is the caller's locale, and the manual's title page is English.
# A version is read as the whole token the page carries and then required to
# be one: matching a numeric prefix would accept `0.7-beta` as `0.7` and
# compare it equal to the package's `0.7` while the page says otherwise.
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+)*")
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
# Every spelling of "compile me again" the manual's own packages use.  The
# generic LaTeX warnings do not cover `longtable`, which the generated
# reference loads, and whose tables settle a pass later than the labels do.
RERUN = re.compile(
    r"Rerun to get|Label\(s\) may have changed|Please \(re\)run|"
    r"Table widths have changed|Rerun LaTeX"
)
UNRESOLVED = re.compile(
    r"There were undefined references|Citation `[^']*' on page|"
    r"Reference `[^']*' on page [0-9]+ undefined|"
    r"There were multiply-defined labels|multiply defined"
)


def package_release() -> tuple[str, str]:
    """The `\\ProvidesPackage` date (YYYY/MM/DD) and version of tenkz.sty.

    Inert source is blanked first, for the reason `executed_manual` records:
    a previous declaration left commented -- or wrapped in `\\iffalse` -- above
    the active one would otherwise be read from the dead line, and the build
    would date and name the PDF as a release it is not.
    """
    raw = PACKAGE.read_text(encoding="utf-8")
    text = _mask_inert_tex(strip_comments(raw), PACKAGE.parent)
    declaration = r"\\ProvidesPackage\s*\{tenkz\}\s*\["
    # Masking removes what TeX never reaches, but it recognises `\iffalse` and
    # not an inactive `\else` arm, and teaching it every conditional shape is
    # a losing race.  One declaration in the file is the property that makes
    # the question moot: a dead one beside the live one is refused outright.
    written = len(re.findall(declaration, strip_comments(raw)))
    if written > 1:
        raise ValueError(
            f"tenkz.sty writes {written} \\ProvidesPackage declarations; only "
            "one can be the release"
        )
    match = re.search(
        r"\\ProvidesPackage\s*\{tenkz\}\s*\[(\d{4}/\d{2}/\d{2})\s+v(\S+)", text
    )
    if match is None:
        raise ValueError("tenkz.sty has no active \\ProvidesPackage date and version")
    version = match.group(2)
    if not VERSION.fullmatch(version):
        raise ValueError(f"tenkz.sty names a version this reader cannot read: {version!r}")
    return match.group(1), version


# Every tree an installation legitimately answers from.  `hobby` and
# `spath3` are separate CTAN packages and may be installed in a site or
# personal tree rather than the distribution's own, so all of them count as
# installation homes -- what must not come from any of them is this
# repository's own material, which the name and inventory tests catch.
TEXMF_VARIABLES = ("TEXMFDIST", "TEXMFLOCAL", "TEXMFHOME", "TEXMFSYSCONFIG")


def tex_installation_roots(engine: str | None = None) -> tuple[Path, ...]:
    """The installation's own texmf trees, empty when they cannot be asked.

    Asked of the engine's own installation when one is named: a `--engine`
    from another tree would otherwise be audited against whatever `kpsewhich`
    happens to be on PATH, and its own trees would read as foreign.
    """
    beside = Path(engine).with_name("kpsewhich") if engine else None
    query = (
        str(beside) if beside is not None and beside.is_file()
        else shutil.which("kpsewhich")
    )
    if query is None:
        return ()
    roots: list[Path] = []
    for variable in TEXMF_VARIABLES:
        run = subprocess.run(
            [query, f"-var-value={variable}"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60,
        )
        value = run.stdout.strip()
        if run.returncode == 0 and value:
            root = Path(value)
            if root.exists():
                roots.append(root.resolve())
    return tuple(roots)


def requested_inputs() -> set[str]:
    """Every file name the manual's own sources `\\input`, with `.tex` added."""
    requested: set[str] = set()
    for name in MANUAL_SOURCES:
        root = MANUAL_DIR / name
        paths = root.rglob("*.tex") if root.is_dir() else [root]
        for path in paths:
            if not path.is_file():
                continue
            body = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
            for match in re.finditer(r"\\(?:input|include)\s*\{([^}]*)\}", body):
                asked = match.group(1).strip()
                # A name TeX builds at run time (`\jobname.exa`) is not a file
                # this reader can name, and the generated files it stands for
                # are written into the build directory anyway.
                if "\\" in asked or not asked:
                    continue
                stem = Path(asked).name
                requested.add(stem if stem.endswith(".tex") else f"{stem}.tex")
    return requested


def recorded_inputs(record: Path) -> list[str]:
    """Every file the engine opened, from its `-recorder` input record.

    The same reading `tenkz_ctan.py` does of an archive's smoke build, kept
    here rather than imported so the release build carries no dependency on
    the packaging tool.
    """
    return [
        line[len("INPUT "):].strip()
        for line in record.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.startswith("INPUT ")
    ]


def executed_manual(text: str | None = None) -> str:
    """The manual's source with everything that reaches no page blanked.

    Comments, false conditional branches, unselected file branches, and macro
    definitions all carry tokens the reader would otherwise take for the
    printed title page.  A release gate that accepted metadata from any of
    them would pass on a manual whose rendered title page states none.
    """
    text = MANUAL.read_text(encoding="utf-8") if text is None else text
    return _mask_inert_tex(strip_comments(text), MANUAL_DIR)


def manual_version(text: str | None = None) -> str:
    """The version the manual's title page names for the package."""
    text = executed_manual(text)
    matches = re.findall(r"manual for \\pkg\{\} version ([^\\}]*)", text)
    if not matches:
        raise ValueError("manual2.tex names no package version on its title page")
    # Two active lines are two claims, and the page shows both.
    if len(matches) > 1:
        raise ValueError(
            f"manual2.tex names {len(matches)} package versions on its title "
            f"page: {[value.strip() for value in matches]}"
        )
    version = matches[0].strip()
    if not VERSION.fullmatch(version):
        raise ValueError(
            f"manual2.tex names a version this reader cannot read: {version!r}"
        )
    return version


def manual_dateline(text: str | None = None) -> str:
    """The title page's month and year, as `tenkz_ctan.py sync` reads it.

    Inert source is blanked first, for the reason `executed_manual` records.
    """
    text = executed_manual(text)
    matches = re.findall(r"The TNLean project \\quad---\\quad ([^\\]*)\\par", text)
    if not matches:
        raise ValueError("manual2.tex has no title-page date line")
    if len(matches) > 1:
        raise ValueError(
            f"manual2.tex has {len(matches)} title-page date lines: "
            f"{[value.strip() for value in matches]}"
        )
    return matches[0].strip()


def source_date_epoch(date: str) -> int:
    year, month, day = (int(part) for part in date.split("/"))
    return int(dt.datetime(year, month, day, tzinfo=dt.timezone.utc).timestamp())


def metadata_errors(
    package_date: str, dateline: str, package_version: str = "", version: str = ""
) -> list[str]:
    """The manual's title page must name the package's release and date.

    Both halves are checked: a version bump inside one month would pass a
    date-only comparison, and the release policy (section 3) requires the
    manual version to agree with `\\ProvidesPackage` at a tag.
    """
    errors: list[str] = []
    year, month, _day = (int(part) for part in package_date.split("/"))
    expected = f"{MONTHS[month - 1]} {year}"
    if dateline != expected:
        errors.append(
            f"manual2.tex title page reads {dateline!r} but tenkz.sty is dated "
            f"{package_date} ({expected!r}); synchronize the release metadata"
        )
    if package_version and version != package_version:
        errors.append(
            f"manual2.tex names version {version!r} but tenkz.sty provides "
            f"v{package_version}; synchronize the release metadata"
        )
    return errors


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


EXAMPLE_ENVIRONMENTS = ("tnexample", "tnrefusal")


def direct_pictures(text: str | None = None) -> list[str]:
    """The manual's own picture sources, outside its example environments.

    `tenkz_manual_doctest.py` compiles and audits every displayed and
    reference example against its own driver, which is where source-linked
    auditing happens.  It does not reach the pictures the manual draws
    directly -- the two on the title page -- so they are collected here and
    given the same treatment.
    """
    text = executed_manual(text)
    spans = [
        (match.start(), text.find(f"\\end{{{name}}}", match.start()))
        for name in EXAMPLE_ENVIRONMENTS
        for match in re.finditer(rf"\\begin\{{{name}\}}", text)
    ]
    return [
        text[construct.start:construct.end]
        for construct in scan_picture_event_constructs(text)
        if not any(begin <= construct.start < end for begin, end in spans if end > 0)
    ]


def audit_direct_pictures(work: Path, epoch: int, engine: str) -> int:
    """Compile the manual's own pictures standalone and audit them linked.

    Their count and order match the driver's, so the audit links the source
    and its source-dependent checks run -- which they cannot do against the
    whole manual, whose pictures the example macros replay out of generated
    files.
    """
    pictures = direct_pictures()
    if not pictures:
        raise RuntimeError("the manual draws no pictures of its own to audit")
    work.mkdir(parents=True, exist_ok=True)
    driver = work / "direct.tex"
    driver.write_text(
        "\\documentclass{standalone}\n\\usepackage{tenkz}\n"
        "\\begin{document}\n" + "\n\\par\n".join(pictures) + "\n\\end{document}\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = str(epoch)
    env["TEXINPUTS"] = f"{ROOT / 'tex' / 'tenkz'}//:"
    run = subprocess.run(
        [engine, "-interaction=nonstopmode", "-halt-on-error", driver.name],
        cwd=work, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=300,
    )
    if run.returncode:
        tail = "\n".join(run.stdout.splitlines()[-40:])
        raise RuntimeError(f"the manual's own pictures did not compile:\n{tail}")
    audit = Audit(driver.with_suffix(".tnlog"), driver)
    if audit.run():
        raise RuntimeError("the manual's own pictures have hard audit findings")
    if not audit.tex_linked:
        raise RuntimeError(
            f"the {len(pictures)} direct picture(s) did not link to their source; "
            "the audit's source-dependent checks would not have run"
        )
    return len(pictures)


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
    # The trailing empty element restores kpathsea's own directories, which
    # the manual needs for tikz, hobby, and spath3 -- and which would also
    # answer a tenkz file this tree forgot, from whatever version the machine
    # has installed.  The engine's input record, not the exit status, says
    # where the runtime came from.
    env["TEXINPUTS"] = f"{ROOT / 'tex' / 'tenkz'}//:"
    engine_log = work / "manual2.log"
    for number in range(1, MAXIMUM_PASSES + 1):
        run = subprocess.run(
            [
                engine, "-interaction=nonstopmode", "-halt-on-error",
                "-recorder", "manual2.tex",
            ],
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
        transcript = engine_log.read_text(encoding="utf-8", errors="replace")
        if number >= MINIMUM_PASSES and not RERUN.search(transcript):
            break
    else:
        raise RuntimeError(
            f"the manual still asked for a rerun after {MAXIMUM_PASSES} passes; "
            "its cross-references do not settle"
        )
    package_tree = (ROOT / "tex" / "tenkz").resolve()
    record = work / "manual2.fls"
    if not record.is_file():
        raise RuntimeError("the engine wrote no input record; cannot prove the runtime")
    # Two homes are legitimate: the package tree under review, and the build
    # directory, which holds exactly the manual sources copied into it.  A
    # tenkz file from anywhere else is the installation answering for this
    # tree, which is what the record exists to catch.
    homes = (package_tree, work.resolve())
    # Every file this build copied in, by basename.  A chapter or a generated
    # reference does not begin with `tenkz`, and if one were missing from the
    # copy an older installed sibling would answer for it through the same
    # restored search path -- identically in both builds, so the byte
    # comparison would agree about the wrong document.
    own = {
        path.name
        for name in MANUAL_SOURCES
        for path in (
            (MANUAL_DIR / name).rglob("*")
            if (MANUAL_DIR / name).is_dir()
            else [MANUAL_DIR / name]
        )
        if path.is_file()
    }
    # The names the manual asks for, whether or not the copy has them: an
    # `\input` committed without its file is exactly the case where the
    # basename is absent from `own`, and an installation tree would answer it.
    own |= requested_inputs()
    # Anything read from the build directory is the copy, and anything from
    # the package tree is the tree under review.  The read-only distribution
    # is the third legitimate home: the manual needs tikz, hobby, and spath3.
    # A document source from anywhere else -- a personal or local texmf tree
    # -- is the installation answering for this build, whether or not this
    # build knows the name: an `\input` committed without its file would
    # otherwise be served by an older installed sibling, in both builds
    # alike, and the byte comparison would agree about the wrong document.
    installation = tex_installation_roots(engine)
    def at_home(opened: str) -> bool:
        resolved = (work / opened).resolve()
        return any(
            resolved.is_relative_to(home) for home in (*homes, *installation)
        )

    foreign = sorted({
        opened
        for opened in recorded_inputs(record)
        if (
            # This repository's own material must come from this repository,
            # from whichever tree an installed copy might sit in.
            Path(opened).name.startswith("tenkz")
            or Path(opened).name in own
        )
        and not any(
            (work / opened).resolve().is_relative_to(home) for home in homes
        )
        or Path(opened).suffix in {".tex", ".sty"} and not at_home(opened)
    })
    if foreign:
        raise RuntimeError(
            "the manual loaded tenkz runtime files from outside this tree:\n  "
            + "\n  ".join(foreign)
        )
    # A missing target leaves `??` on the page and leaves the engine's status
    # at zero, so a release artifact needs the transcript read, not the exit
    # code alone.
    if UNRESOLVED.search(transcript):
        lines = [
            line for line in transcript.splitlines()
            if UNRESOLVED.search(line) or "undefined" in line.lower()
        ]
        raise RuntimeError(
            "the manual has unresolved references or citations:\n  "
            + "\n  ".join(lines[:10])
        )
    log = work / "manual2.tnlog"
    if not log.is_file() or not log.read_text(encoding="utf-8").strip():
        raise RuntimeError("the manual build emitted no event stream")
    findings: list[str] = []
    # The manual's pictures are replayed by the example macros out of the
    # generated `.exa`/`.exm` files and spread over the chapter inputs, so no
    # single source describes this stream: a flattened source reads 61
    # picture constructs against the log's 55, and the four inside refusal
    # examples do not close the gap.  Rather than hand the audit a source it
    # would silently decline to link, this is the stream-internal audit and
    # is reported as such.  The source-linked half belongs to
    # `tenkz_manual_doctest.py`, which audits every displayed example against
    # its own standalone driver and runs immediately before this in CI.
    audit = Audit(log, None)
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


def rendered_title_page(pdf: Path) -> str:
    """The text of the built manual's first page.

    Every reader above works on source, and source can carry a version or a
    date that no page shows -- commented, in a branch TeX does not take, or
    qualified by markup a source pattern stops at.  The rendered page settles
    all of them at once, so it is what the release metadata is finally held
    to.
    """
    run = subprocess.run(
        ["pdftotext", "-f", "1", "-l", "1", str(pdf), "-"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
    )
    if run.returncode:
        raise RuntimeError(f"could not read the manual's title page:\n{run.stdout}")
    return run.stdout


def rendered_metadata_errors(
    pdf: Path, version: str, dateline: str, *, required: bool = False
) -> list[str]:
    """The title page must say the release the source claims, once."""
    if shutil.which("pdftotext") is None:
        # This is the only check that reads what a reader sees, so a release
        # build may not skip it.
        if required:
            return ["pdftotext is not installed, so the rendered title page "
                    "cannot be read"]
        return []
    page = rendered_title_page(pdf)
    errors: list[str] = []
    for what, expected in (("version", f"version {version}"), ("date", dateline)):
        found = page.count(expected)
        if found != 1:
            errors.append(
                f"the rendered title page shows the {what} {expected!r} "
                f"{found} time(s), not once"
            )
    # A qualifier the source readers stop at still reaches the page.
    # `version 0.7 beta` reads as a qualified version to a person, and the
    # source pattern that stopped at `\emph` never saw the word.  The rendered
    # line must end after the version.
    qualified = re.search(
        r"version\s+" + re.escape(version) + r"[^\S\n]*(\S.*)?$", page, re.M
    )
    if qualified and qualified.group(1):
        errors.append(
            f"the rendered title page qualifies the version: "
            f"{qualified.group(0).strip()!r}"
        )
    return errors


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
    errors = metadata_errors(date, manual_dateline(), version, manual_version())
    if errors:
        for error in errors:
            print(f"tenkz-manual: {error}", file=sys.stderr)
        return 1
    # Resolved before the builds start: each runs in its own directory, where
    # a relative engine path would no longer name the same file.
    engine = shutil.which(args.engine)
    if engine is None:
        if args.require_engine:
            print(f"tenkz-manual: {args.engine} not found", file=sys.stderr)
            return 1
        print(f"SKIP: {args.engine} not found")
        return 0
    # Absolute, but NOT resolved: TeX Live dispatches on the name it is
    # invoked as, and `xelatex` is a symlink to `xetex`, so following it loads
    # plain TeX and every `\documentclass` becomes an undefined control
    # sequence.  `abspath` answers the relative-path case without renaming the
    # engine.
    engine = os.path.abspath(engine)
    epoch = source_date_epoch(date)
    builds = 2 if args.action == "check" else 1
    pdfs: list[bytes] = []
    with tempfile.TemporaryDirectory(prefix="tenkz-manual-") as tmp:
        for number in range(1, builds + 1):
            work = Path(tmp) / f"build{number}"
            work.mkdir()
            try:
                pdf, findings = build(work, epoch, engine)
            except (RuntimeError, FileNotFoundError) as exc:
                print(f"tenkz-manual: {exc}", file=sys.stderr)
                return 1
            direct = audit_direct_pictures(work / "direct", epoch, engine)
            rendered = rendered_metadata_errors(
                work / "manual2.pdf", version, manual_dateline(),
                required=args.require_engine,
            )
            if rendered:
                for error in rendered:
                    print(f"tenkz-manual: {error}", file=sys.stderr)
                return 1
            pdfs.append(pdf)
            print(
                f"build {number}: {sha256(pdf)} ({len(pdf)} bytes, "
                f"{len(findings)} stream-internal audit advisories; "
                f"{direct} direct picture(s) audited source-linked, the rest "
                "per example by the doctest)"
            )
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
