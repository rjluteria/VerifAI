import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


class PackageTests(unittest.TestCase):
    def test_developer_override_is_packaged_with_exact_permission(self):
        root = Path(__file__).resolve().parents[1]
        original = (root / "extension/config.js").read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.zip"
            subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts/package.py"),
                    "--backend-origin",
                    "https://verifai-test.onrender.com",
                    "--output",
                    str(path),
                ],
                check=True,
                capture_output=True,
            )
            with ZipFile(path) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(
                    manifest["optional_host_permissions"],
                    ["https://verifai-test.onrender.com/*"],
                )
                self.assertIn(
                    b'backend("https://verifai-test.onrender.com")',
                    archive.read("config.js"),
                )
                self.assertNotIn(b"Hosted service URL", archive.read("settings.html"))
        self.assertEqual((root / "extension/config.js").read_bytes(), original)

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
        self.assertEqual((root / "extension/config.js").read_bytes(), original)

    def test_unsafe_developer_origins_rejected_before_archive(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            for origin in [
                "http://x.onrender.com",
                "https://x.onrender.com.evil.test",
                "https://user:password@x.onrender.com",
                "https://x.onrender.com/path",
                "https://x.onrender.com:444",
                "https://x.onrender.com?url=x",
            ]:
                path = Path(folder) / "bad.zip"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(root / "scripts/package.py"),
                        "--backend-origin",
                        origin,
                        "--output",
                        str(path),
                    ],
                    capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(path.exists())
