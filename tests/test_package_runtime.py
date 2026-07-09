import hashlib
import json
import stat
import subprocess
import sys
import zipfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "build" / "package_runtime.py"

REQUIRED_LINUX_RUNTIME_ASSETS = (
    "icudtl.dat",
    "resources.pak",
    "chrome_100_percent.pak",
    "chrome_200_percent.pak",
    "chrome_crashpad_handler",
    "libEGL.so",
    "libGLESv2.so",
    "libvk_swiftshader.so",
    "libvulkan.so.1",
    "vk_swiftshader_icd.json",
    "v8_context_snapshot.bin",
    "snapshot_blob.bin",
    "headless_command_resources.pak",
    "locales/en-US.pak",
)

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

    def _write_runtime_assets(self, browser_dir: Path, *, omit: set[str] | None = None) -> None:
        omitted = omit or set()
        for relative_path in REQUIRED_LINUX_RUNTIME_ASSETS:
            if relative_path in omitted:
                continue
            asset = browser_dir / relative_path
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_bytes(f"runtime asset: {relative_path}\n".encode())

    def _run_package(
        self,
        td: Path,
        *,
        omit_runtime_assets: set[str] | None = None,
        expect_success: bool = True,
    ):
        browser_dir = td / "browser-output"
        browser_dir.mkdir()
        browser = self._write_executable(browser_dir / "chrome", "#!/bin/sh\necho chrome\n")
        self._write_runtime_assets(browser_dir, omit=omit_runtime_assets)
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
        if not expect_success:
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            return {
                "proc": proc,
                "browser_dir": browser_dir,
                "browser": browser,
                "wrapper": wrapper,
                "out": out,
                "artifact_id": artifact_id,
            }
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        stage = out / "stage" / artifact_id
        self.assertTrue(stage.is_dir())
        return {
            "artifact_id": artifact_id,
            "browser_dir": browser_dir,
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

    def test_package_writes_target_os_and_arch_to_metadata_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            package = self._run_package(Path(td))

            expected_target = {"os": "linux", "arch": "x64"}
            metadata_outputs = {
                "artifact-manifest.json": json.loads((package["stage"] / "artifact-manifest.json").read_text()),
                "provenance.json": json.loads((package["stage"] / "provenance.json").read_text()),
                "SBOM.json": json.loads((package["stage"] / "SBOM.json").read_text()),
            }

            for name, metadata in metadata_outputs.items():
                self.assertEqual(metadata["platform"], "linux-x64", name)
                self.assertEqual(metadata["os"], expected_target["os"], name)
                self.assertEqual(metadata["arch"], expected_target["arch"], name)

    def test_package_includes_linux_runtime_assets_in_stage_manifest_sbom_and_zip(self):
        with tempfile.TemporaryDirectory() as td:
            package = self._run_package(Path(td))
            manifest = json.loads((package["stage"] / "artifact-manifest.json").read_text())
            sbom = json.loads((package["stage"] / "SBOM.json").read_text())
            archive = Path(package["payload"]["archive"])

            manifest_files = {entry["path"]: entry for entry in manifest["files"]}
            sbom_files = {entry["path"]: entry for entry in sbom["files"]}
            with zipfile.ZipFile(archive) as zf:
                archive_names = set(zf.namelist())

            for relative_path in REQUIRED_LINUX_RUNTIME_ASSETS:
                source = package["browser_dir"] / relative_path
                staged = package["stage"] / relative_path
                self.assertTrue(staged.is_file(), relative_path)
                self.assertIn(relative_path, manifest_files)
                self.assertIn(relative_path, sbom_files)
                self.assertIn(f"{package['artifact_id']}/{relative_path}", archive_names)
                self.assertEqual(manifest_files[relative_path]["sha256"], self._sha256(source))
                self.assertEqual(manifest_files[relative_path]["size_bytes"], source.stat().st_size)
                self.assertEqual(sbom_files[relative_path]["sha256"], self._sha256(source))
                self.assertEqual(sbom_files[relative_path]["size"], source.stat().st_size)

    def test_package_fails_clearly_when_linux_runtime_asset_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            package = self._run_package(
                Path(td),
                omit_runtime_assets={"icudtl.dat"},
                expect_success=False,
            )

            output = package["proc"].stderr + package["proc"].stdout
            self.assertIn("missing file", output)
            self.assertIn("icudtl.dat", output)

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
