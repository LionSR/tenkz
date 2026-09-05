#!/usr/bin/env python3
"""Seed failures in the product checks retained from the release campaign."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import check_tenkz_policy as policy


class CompatibilityChecks(unittest.TestCase):
    def setUp(self):
        self.room = tempfile.TemporaryDirectory()
        self.addCleanup(self.room.cleanup)
        self.root = Path(self.room.name)
        for name in (
            "tex/tenkz/tenkz.sty",
            policy.REGISTRY,
            policy.REFERENCE,
            "docs/tenkz/TNLOG.md",
        ):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(policy.ROOT / name, destination)

    def replace(self, name, old, new):
        path = self.root / name
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new))

    def test_current_tree(self):
        policy.check(self.root)

    def test_duplicate_package_version(self):
        path = self.root / "tex/tenkz/tenkz.sty"
        path.write_text(
            path.read_text() + "\n\\ProvidesPackage{tenkz}[2026/01/01 v1.0 Test]\n"
        )
        with self.assertRaisesRegex(SystemExit, "exactly one"):
            policy.check(self.root)

    def test_invalid_version_and_date(self):
        for payload in ("2026/01/01 v1..0 Test", "2026/99/01 v1.0 Test"):
            with self.subTest(payload=payload):
                (self.root / "tex/tenkz/tenkz.sty").write_text(
                    "\\ProvidesPackage{tenkz}[" + payload + "]\n"
                )
                with self.assertRaises(SystemExit):
                    policy.check(self.root)

    def test_commented_registry_is_empty(self):
        path = self.root / policy.REGISTRY
        path.write_text("\n".join("%" + line for line in path.read_text().splitlines()))
        with self.assertRaisesRegex(ValueError, "no command"):
            policy.check(self.root)

    def test_missing_reference_command(self):
        self.replace(
            policy.REFERENCE, "\\textbackslash tnwire}", "\\textbackslash missing}"
        )
        with self.assertRaisesRegex(ValueError, "omits commands"):
            policy.check(self.root)

    def test_missing_event_block(self):
        self.replace("docs/tenkz/TNLOG.md", "tenkz-event-kinds-v1", "removed")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            policy.check(self.root)

    def test_malformed_event_schema(self):
        self.replace("docs/tenkz/TNLOG.md", "schema = 1", "schema = true")
        with self.assertRaisesRegex(ValueError, "schema 1"):
            policy.check(self.root)

    def test_mismatched_event_kinds(self):
        self.replace("docs/tenkz/TNLOG.md", '"wire-geometry"', '"missing-kind"')
        with self.assertRaisesRegex(ValueError, "differ"):
            policy.check(self.root)

    def test_reader_rejecting_optional_fields(self):
        original = policy.tnlog.parse_log

        def reject(text, *, hard):
            hard("seed", "stream", "unknown field")
            return original(text, hard=hard)

        with patch.object(policy.tnlog, "parse_log", reject):
            with self.assertRaisesRegex(ValueError, "unknown optional"):
                policy.check(self.root)


if __name__ == "__main__":
    unittest.main()
