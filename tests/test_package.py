import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


class PackageTests(unittest.TestCase):
    def test_build_is_reproducible_with_fixed_safe_metadata(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder) / name for name in ("one.zip", "two.zip")]
            for path in paths:
                subprocess.run(
                    [
                        sys.executable,
                        str(root / "scripts/package.py"),
                        "--output",
                        str(path),
                    ],
                    check=True,
                    capture_output=True,
                )
            self.assertEqual(paths[0].read_bytes(), paths[1].read_bytes())
            with ZipFile(paths[0]) as archive:
                self.assertEqual(len(archive.namelist()), 12)
                for entry in archive.infolist():
                    self.assertEqual(entry.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual(entry.external_attr >> 16, 0o100644)

    def test_native_clock_is_developer_only_and_never_changes_source(self):
        root = Path(__file__).resolve().parents[1]
        original = (root / "extension/config.js").read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            for enabled in (False, True):
                path = Path(folder) / ("timed.zip" if enabled else "normal.zip")
                command = [
                    sys.executable,
                    str(root / "scripts/package.py"),
                    "--output",
                    str(path),
                ]
                if enabled:
                    command.append("--benchmark-timing")
                subprocess.run(command, check=True, capture_output=True)
                with ZipFile(path) as archive:
                    config = archive.read("config.js")
                    self.assertIn(
                        b"BENCHMARK_TIMING = " + (b"true;" if enabled else b"false;"),
                        config,
                    )
                    self.assertEqual(
                        json.loads(archive.read("manifest.json"))[
                            "optional_host_permissions"
                        ],
                        ["https://verifai-ekan.onrender.com/*"],
                    )
                    self.assertIn(
                        b"const BENCHMARK_TIMING = "
                        + (b"true" if enabled else b"false")
                        + b";",
                        archive.read("content.js"),
                    )
                    self.assertNotIn(
                        b"benchmark", archive.read("settings.html").lower()
                    )
                    # The structure-aware punctuation rule contains Unicode.
                    # Packaging must decode UTF-8 even on Windows code pages.
                    self.assertIn("”", archive.read("content.js").decode("utf-8"))
        self.assertEqual((root / "extension/config.js").read_bytes(), original)
