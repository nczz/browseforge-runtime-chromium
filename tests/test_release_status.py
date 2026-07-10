from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_status.py"

spec = importlib.util.spec_from_file_location("release_status", SCRIPT)
release_status = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(release_status)


class ReleaseStatusTests(unittest.TestCase):
    def write_json(self, root: Path, path: str, payload: dict) -> None:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def write_base_inputs(self, root: Path) -> None:
        self.write_json(
            root,
            "knowledge/manifests/release-gates.json",
            {
                "release_candidate_required_gates": [
                    {"gate_id": "chromium-base-selected", "status": "passed"},
                    {"gate_id": "live-detector-evidence", "status": "warning", "evidence": "proxy matrix incomplete"},
                ]
            },
        )
        self.write_json(
            root,
            "knowledge/manifests/native-artifact-preflight.json",
            {
                "release_grade_ready": False,
                "platforms": [
                    {
                        "platform": "linux-x64",
                        "ready": True,
                        "status": "packaged_detector_tested",
                        "missing_prerequisites": [],
                    },
                    {
                        "platform": "macos-arm64",
                        "ready": False,
                        "status": "missing_native_release_artifact",
                        "missing_prerequisites": ["full Xcode selected via xcode-select"],
                        "evidence": ["python3 scripts/chromium_native.py check --platform macos-arm64"],
                        "status_snapshot": {
                            "host_supported": True,
                            "native_toolchain_ready": False,
                            "build_ninja_exists": False,
                            "output_binary_exists": False,
                            "package_zip_exists": False,
                        },
                    },
                ],
            },
        )
        self.write_json(
            root,
            "knowledge/manifests/proxy-preflight.json",
            {
                "ready": False,
                "status": "failed",
                "missing": ["BROWSEFORGE_DETECTOR_PROXY_URL"],
                "errors": [],
            },
        )
        self.write_json(
            root,
            "detector-summary.json",
            {
                "blocking_findings": [],
                "coverage_gaps": [
                    {
                        "matrix_key": "macos-arm64:sannysoft:headed:proxy:host",
                        "platform": "macos-arm64",
                        "detector_id": "sannysoft",
                        "display_mode": "headed",
                        "network_mode": "proxy",
                        "container": False,
                        "required_evidence": "external proxy exit-IP/geolocation evidence",
                    }
                ],
            },
        )
        self.write_json(
            root,
            "knowledge/manifests/detector-score-comparison.json",
            {"baseline_gaps": [{"gap_id": "native_headed_font_corpus_parity_missing"}], "gaps": []},
        )
        self.write_json(
            root,
            "knowledge/manifests/fingerprint-surface-status.json",
            {
                "release_grade": False,
                "surfaces": [
                    {
                        "surface": "proxy/IP coherence",
                        "release_blocker": True,
                        "severity": "high",
                        "status": "detector_tested",
                        "result": "external_proxy_missing",
                        "evidence": "No external proxy detector run has been executed.",
                    }
                ],
            },
        )
        self.write_json(
            root,
            "knowledge/manifests/signing-policy.json",
            {
                "release_grade_ready": False,
                "policies": [
                    {
                        "platform": "linux-x64",
                        "release_grade_allowed": False,
                        "status": "unsigned_alpha_dev_artifact",
                        "decision": "Unsigned alpha artifact is not release-grade.",
                    }
                ],
            },
        )
        self.write_json(
            root,
            "contracts/browseforge-integration.contract.json",
            {"release_blockers": ["external proxy exit-IP/geolocation detector evidence is missing"]},
        )
        self.write_json(
            root,
            "knowledge/manifests/source-acquisition.json",
            {
                "chromium_base": {
                    "artifact_rebuild_required": True,
                    "artifact_rebuild_reasons": ["WebShare source patch has not been rebuilt into packaged artifacts."],
                    "artifact_rebuild_status": "pending_linux_rebuild",
                }
            },
        )

    def test_release_status_collects_blockers_and_input_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_base_inputs(root)
            payload = release_status.release_status(root, "2026-07-10T00:00:00Z")

        self.assertEqual(payload["runtime_id"], "browseforge-chromium")
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["generated_at"], "2026-07-10T00:00:00Z")
        self.assertIs(payload["release_grade_ready"], False)
        self.assertEqual(payload["blocker_count"], len(payload["blockers"]))
        blocker_ids = {blocker["blocker_id"] for blocker in payload["blockers"]}
        self.assertIn("release-gate:live-detector-evidence", blocker_ids)
        self.assertIn("native-artifact:macos-arm64:0", blocker_ids)
        self.assertIn("proxy-preflight:missing:BROWSEFORGE_DETECTOR_PROXY_URL", blocker_ids)
        self.assertIn("detector:coverage-gap:macos-arm64:sannysoft:headed:proxy:host", blocker_ids)
        self.assertIn("score-comparison:baseline_gaps:native_headed_font_corpus_parity_missing", blocker_ids)
        self.assertIn("fingerprint-surface:proxy/IP coherence", blocker_ids)
        self.assertIn("signing-policy:linux-x64", blocker_ids)
        self.assertIn("browseforge-integration:0", blocker_ids)
        self.assertIn("source-acquisition:artifact-rebuild:0", blocker_ids)
        detector_blocker = next(
            blocker for blocker in payload["blockers"]
            if blocker["blocker_id"] == "detector:coverage-gap:macos-arm64:sannysoft:headed:proxy:host"
        )
        self.assertEqual(detector_blocker["display_mode"], "headed")
        self.assertEqual(detector_blocker["network_mode"], "proxy")
        self.assertEqual(detector_blocker["container"], False)
        native_blocker = next(
            blocker for blocker in payload["blockers"]
            if blocker["blocker_id"] == "native-artifact:macos-arm64:0"
        )
        self.assertEqual(native_blocker["host_supported"], True)
        self.assertEqual(native_blocker["native_toolchain_ready"], False)
        self.assertEqual(native_blocker["package_zip_exists"], False)
        self.assertEqual(set(release_status.INPUT_PATHS), set(payload["input_sha256"]))

    def test_release_status_passes_only_without_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for path in release_status.INPUT_PATHS:
                if path == "knowledge/manifests/release-gates.json":
                    payload = {"release_candidate_required_gates": [{"gate_id": "live-detector-evidence", "status": "passed"}]}
                elif path == "knowledge/manifests/native-artifact-preflight.json":
                    payload = {"release_grade_ready": True, "platforms": [{"platform": "linux-x64", "ready": True}]}
                elif path == "knowledge/manifests/proxy-preflight.json":
                    payload = {"ready": True, "missing": [], "errors": []}
                elif path == "detector-summary.json":
                    payload = {"blocking_findings": [], "coverage_gaps": []}
                elif path == "knowledge/manifests/detector-score-comparison.json":
                    payload = {"baseline_gaps": [], "gaps": []}
                elif path == "knowledge/manifests/fingerprint-surface-status.json":
                    payload = {"release_grade": True, "surfaces": []}
                elif path == "knowledge/manifests/signing-policy.json":
                    payload = {"release_grade_ready": True, "policies": [{"platform": "linux-x64", "release_grade_allowed": True}]}
                elif path == "contracts/browseforge-integration.contract.json":
                    payload = {"release_blockers": []}
                elif path == "knowledge/manifests/source-acquisition.json":
                    payload = {"chromium_base": {"artifact_rebuild_required": False}}
                else:  # pragma: no cover - keeps the fixture exhaustive when inputs change.
                    raise AssertionError(path)
                self.write_json(root, path, payload)
            result = release_status.release_status(root, "2026-07-10T00:00:00Z")

        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["blocker_count"], 0)
        self.assertIs(result["release_grade_ready"], True)


if __name__ == "__main__":
    unittest.main()
