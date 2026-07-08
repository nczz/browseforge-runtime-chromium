import hashlib
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "build" / "package_runtime.py"

class PackageRuntimeTests(unittest.TestCase):
    def _write_executable(self, path: Path, content: str = "#!/bin/sh\nexit 0\n") -> Path:
        path.write_text(content)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def _sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _run_package(self, td: Path):
        browser = self._write_executable(td / "chrome", "#!/bin/sh\necho chrome\n")
        wrapper = self._write_executable(td / "wrapper", "#!/bin/sh\necho wrapper\n")
        out = td / "dist"
        runtime_version = "v0.1.0-alpha.0"
        platform_id = "linux-x64"
        artifact_id = f"browseforge-runtime-chromium-{runtime_version}-{platform_id}"
        source_acquisition_manifest = ROOT / "knowledge" / "manifests" / "source-acquisition.json"
        patchset_manifest = ROOT / "knowledge" / "manifests" / "patchset.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(PACKAGER),
                "package",
                "--platform",
                platform_id,
                "--browser-binary",
                str(browser),
                "--wrapper-binary",
                str(wrapper),
                "--output-dir",
                str(out),
                "--runtime-version",
                runtime_version,
                "--browser-version",
                "150.0.7871.100",
                "--source-ref",
                "b5a9b587b83512ef1fab99cb7510c58a06d22089",
                "--patchset-id",
                "browseforge-anti-detect-v0",
                "--wrapper-version",
                "v0.1.0-alpha.0",
                "--release-channel",
                "dev",
                "--source-acquisition-manifest",
                str(source_acquisition_manifest),
                "--patchset-manifest",
                str(patchset_manifest),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        stage = out / "stage" / artifact_id
        self.assertTrue(stage.is_dir())
        return {
            "artifact_id": artifact_id,
            "browser": browser,
            "wrapper": wrapper,
            "out": out,
            "stage": stage,
            "payload": payload,
            "runtime_version": runtime_version,
            "platform_id": platform_id,
            "browser_version": "150.0.7871.100",
            "source_ref": "b5a9b587b83512ef1fab99cb7510c58a06d22089",
            "patchset_id": "browseforge-anti-detect-v0",
            "source_acquisition_manifest": source_acquisition_manifest,
            "patchset_manifest": patchset_manifest,
        }

    def test_plan_lists_platforms(self):
        proc = subprocess.run([sys.executable, str(PACKAGER), "plan"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(any(p["id"] == "linux-x64" for p in data["platforms"]))

    def test_package_requires_browser_binary(self):
        with tempfile.TemporaryDirectory() as td:
            wrapper = self._write_executable(Path(td) / "wrapper")
            proc = subprocess.run([sys.executable, str(PACKAGER), "package", "--platform", "linux-x64", "--browser-binary", str(Path(td) / "missing"), "--wrapper-binary", str(wrapper), "--runtime-version", "v0.1.0-alpha.0", "--browser-version", "150.0.7871.100", "--source-ref", "b5a9"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("missing file", proc.stderr + proc.stdout)

    def test_package_creates_checksum_for_real_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            package = self._run_package(Path(td))
            payload = package["payload"]
            self.assertTrue(Path(payload["archive"]).is_file())
            self.assertRegex((package["out"] / "checksums.txt").read_text(), r"^[0-9a-f]{64}  browseforge-runtime-chromium-")

    def test_package_writes_non_placeholder_sbom_with_hashed_files(self):
        with tempfile.TemporaryDirectory() as td:
            package = self._run_package(Path(td))
            sbom = json.loads((package["stage"] / "SBOM.json").read_text())

            self.assertNotEqual(sbom.get("schema"), "placeholder-spdx-compatible")
            for key in (
                "artifact_id",
                "runtime_id",
                "runtime_version",
                "platform",
                "browser_version",
                "source_ref",
                "patchset_id",
                "generated_by",
                "files",
            ):
                self.assertIn(key, sbom)
            self.assertEqual(sbom["artifact_id"], package["artifact_id"])
            self.assertEqual(sbom["runtime_id"], "browseforge-chromium")
            self.assertEqual(sbom["runtime_version"], package["runtime_version"])
            self.assertEqual(sbom["platform"], package["platform_id"])
            self.assertEqual(sbom["browser_version"], package["browser_version"])
            self.assertEqual(sbom["source_ref"], package["source_ref"])
            self.assertEqual(sbom["patchset_id"], package["patchset_id"])
            self.assertTrue(sbom["generated_by"])

            files = {entry["path"]: entry for entry in sbom["files"]}
            self.assertIn("chrome", files)
            self.assertIn("browseforge-runtime-chromium", files)
            for entry in files.values():
                self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
                self.assertIsInstance(entry["size"], int)
                self.assertGreater(entry["size"], 0)
            self.assertEqual(files["chrome"]["sha256"], self._sha256(package["browser"]))
            self.assertEqual(files["chrome"]["size"], package["browser"].stat().st_size)
            self.assertEqual(files["browseforge-runtime-chromium"]["sha256"], self._sha256(package["wrapper"]))
            self.assertEqual(files["browseforge-runtime-chromium"]["size"], package["wrapper"].stat().st_size)

    def test_package_writes_provenance_for_inputs_and_manifest_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            package = self._run_package(Path(td))
            provenance = json.loads((package["stage"] / "provenance.json").read_text())

            expected_fields = (
                "builder",
                "source_ref",
                "patchset_id",
                "source_acquisition_sha256",
                "patchset_manifest_sha256",
                "browser_binary_sha256",
                "wrapper_binary_sha256",
                "git_commit",
            )
            for key in expected_fields:
                self.assertIn(key, provenance)
            self.assertTrue(provenance["builder"])
            self.assertEqual(provenance["source_ref"], package["source_ref"])
            self.assertEqual(provenance["patchset_id"], package["patchset_id"])
            self.assertEqual(provenance["source_acquisition_sha256"], self._sha256(package["source_acquisition_manifest"]))
            self.assertEqual(provenance["patchset_manifest_sha256"], self._sha256(package["patchset_manifest"]))
            self.assertEqual(provenance["browser_binary_sha256"], self._sha256(package["browser"]))
            self.assertEqual(provenance["wrapper_binary_sha256"], self._sha256(package["wrapper"]))
            self.assertTrue(provenance["git_commit"] is None or isinstance(provenance["git_commit"], str))

if __name__ == "__main__":
    unittest.main()
