import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "build" / "package_runtime.py"

class PackageRuntimeTests(unittest.TestCase):
    def test_plan_lists_platforms(self):
        proc = subprocess.run([sys.executable, str(PACKAGER), "plan"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(any(p["id"] == "linux-x64" for p in data["platforms"]))

    def test_package_requires_browser_binary(self):
        with tempfile.TemporaryDirectory() as td:
            wrapper = Path(td) / "wrapper"
            wrapper.write_text("#!/bin/sh\nexit 0\n")
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
            proc = subprocess.run([sys.executable, str(PACKAGER), "package", "--platform", "linux-x64", "--browser-binary", str(Path(td) / "missing"), "--wrapper-binary", str(wrapper), "--runtime-version", "v0.1.0-alpha.0", "--browser-version", "150.0.7871.100", "--source-ref", "b5a9"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("missing file", proc.stderr + proc.stdout)

    def test_package_creates_checksum_for_real_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            browser = td / "chrome"
            wrapper = td / "wrapper"
            for path in (browser, wrapper):
                path.write_text("#!/bin/sh\nexit 0\n")
                path.chmod(path.stat().st_mode | stat.S_IXUSR)
            out = td / "dist"
            proc = subprocess.run([sys.executable, str(PACKAGER), "package", "--platform", "linux-x64", "--browser-binary", str(browser), "--wrapper-binary", str(wrapper), "--output-dir", str(out), "--runtime-version", "v0.1.0-alpha.0", "--browser-version", "150.0.7871.100", "--source-ref", "b5a9b587b83512ef1fab99cb7510c58a06d22089"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(Path(payload["archive"]).is_file())
            self.assertRegex((out / "checksums.txt").read_text(), r"^[0-9a-f]{64}  browseforge-runtime-chromium-")

if __name__ == "__main__":
    unittest.main()
