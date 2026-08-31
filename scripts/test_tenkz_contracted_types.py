#!/usr/bin/env python3
"""Regression checks for the contracted-index audit."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import tenkz_contracted_types as contracted  # noqa: E402


def test_canonical_parser_preserves_legacy_picture_ownership() -> None:
    languages, contractions = contracted.read_stream(
        "picture|id=1|lang=grid\n"
        "bond|picture=1\n"
        "pairleg|picture=1\n",
        source_name="legacy.tnlog",
    )

    assert languages == ["grid"], languages
    assert [item.picture for item in contractions] == ["1", "1"], contractions
    assert [item.type for item in contractions] == ["virtual", "physical"], (
        contractions
    )


def test_failed_compile_cannot_certify_a_partial_stream() -> None:
    target = SimpleNamespace(id="partial")

    def fail_after_stream(command, *, cwd, **_kwargs):
        Path(cwd, "partial-standalone.tnlog").write_text(
            "picture|id=p1|lang=kernel\n"
            "wire|from=A.0|to=B.180|origin=tnwire\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            command,
            7,
            stdout="earlier output\n",
            stderr="fatal engine failure\n",
        )

    with tempfile.TemporaryDirectory() as directory:
        stream = Path(directory, target.id, "partial-standalone.tnlog")
        with mock.patch.object(contracted, "standalone_wrapper", return_value="fixture"):
            with mock.patch.object(contracted.subprocess, "run", fail_after_stream):
                report = contracted.compile_target(target, Path(directory), {})
        assert not stream.exists(), stream

    assert report.error is not None, report
    assert "xelatex exited 7" in report.error, report.error
    assert "fatal engine failure" in report.error, report.error
    assert not report.contractions, report.contractions


def test_preexisting_stream_is_replaced_by_a_fresh_compile() -> None:
    target = SimpleNamespace(id="cached")

    def compile_fresh(command, *, cwd, **_kwargs):
        Path(cwd, "cached-standalone.tnlog").write_text(
            "picture|id=k1|lang=kernel\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory, target.id)
        work.mkdir()
        stream = work / "cached-standalone.tnlog"
        stream.write_text("picture|id=1|lang=grid\n", encoding="utf-8")
        with mock.patch.object(contracted, "standalone_wrapper", return_value="fixture"):
            with mock.patch.object(contracted.subprocess, "run", compile_fresh):
                report = contracted.compile_target(target, Path(directory), {})

    assert report.error is None, report.error
    assert report.languages == ["kernel"], report.languages


def test_malformed_stream_cannot_certify_contraction_types() -> None:
    target = SimpleNamespace(id="malformed")

    def compile_malformed(command, *, cwd, **_kwargs):
        Path(cwd, "malformed-standalone.tnlog").write_text(
            "picture|id=k1|lang=kernel\n"
            "wire|id=wire-1|kind=index|from=addr-1|to=addr-2|"
            "port-type=physical|port-type=virtual\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with tempfile.TemporaryDirectory() as directory:
        with mock.patch.object(contracted, "standalone_wrapper", return_value="fixture"):
            with mock.patch.object(contracted.subprocess, "run", compile_malformed):
                report = contracted.compile_target(target, Path(directory), {})

    assert report.error is not None, report
    assert "duplicate field 'port-type'" in report.error, report.error
    assert not report.contractions, report.contractions


if __name__ == "__main__":
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            test()
            print(f"PASS {name}")
