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
                        "next_commands": ["python3 scripts/chromium_native.py gn-gen --platform macos-arm64 --execute"],
                        "status_snapshot": {
                            "host_supported": True,
                            "native_toolchain_ready": False,
                            "build_ninja_exists": False,
                            "output_binary_exists": False,
                            "package_zip_exists": False,
                        },
                    },
                    {
                        "platform": "macos-x64",
                        "ready": False,
                        "status": "missing_native_release_artifact",
                        "missing_prerequisites": [
                            "macos-x64 packaged artifact with checksum/SBOM/provenance metadata"
                        ],
                        "evidence": ["python3 scripts/chromium_native.py check --platform macos-x64"],
                        "next_commands": [
                            "GOOS=darwin GOARCH=amd64 go build -o bin/browseforge-runtime-chromium-darwin-amd64 ./cmd/browseforge-runtime-chromium"
                        ],
                        "status_snapshot": {
                            "host_supported": True,
                            "native_toolchain_ready": True,
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
                "next_commands": [
                    "python3 scripts/detector_harness.py run --detector sannysoft --proxy-url \"$BROWSEFORGE_DETECTOR_PROXY_URL\" --network-mode proxy --display headed"
                ],
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
                    },
                    {
                        "matrix_key": "windows-x64:browserleaks:headed:direct:host",
                        "platform": "windows-x64",
                        "detector_id": "browserleaks",
                        "display_mode": "headed",
                        "network_mode": "direct",
                        "container": False,
                        "required_evidence": "Windows native detector evidence",
                    },
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
                    },
                    {
                        "platform": "windows-x64",
                        "release_grade_allowed": False,
                        "status": "missing_authenticode_policy",
                        "decision": "Windows artifacts need an Authenticode signing path before release.",
                    },
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
                    "build_output_status": {
                        "dev_build_ninja_exists": False,
                        "dev_gn_args_exists": False,
                    },
                    "dependency_profile_status": {"current_checkout_profile": "linux_docker_deps", "mac_gn_exists": False},
                    "source_build_status": {
                        "status": "blocked_full_xcode_required_after_platform_gn_installed",
                        "platform_gn_binary": "/tmp/chromium/src/buildtools/mac/gn",
                        "error_summary": "xcodebuild requires full Xcode while xcode-select points at CommandLineTools",
                        "next_action": "Select full Xcode, then rerun generate-dev-build",
                    },
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
        self.assertIn("native-artifact:macos-x64:0", blocker_ids)
        self.assertIn("proxy-preflight:missing:BROWSEFORGE_DETECTOR_PROXY_URL", blocker_ids)
        self.assertIn("detector:coverage-gap:macos-arm64:sannysoft:headed:proxy:host", blocker_ids)
        self.assertIn("detector:coverage-gap:windows-x64:browserleaks:headed:direct:host", blocker_ids)
        self.assertIn("score-comparison:baseline_gaps:native_headed_font_corpus_parity_missing", blocker_ids)
        self.assertIn("fingerprint-surface:proxy/IP coherence", blocker_ids)
        self.assertIn("signing-policy:linux-x64", blocker_ids)
        self.assertIn("signing-policy:windows-x64", blocker_ids)
        self.assertIn("browseforge-integration:0", blocker_ids)
        self.assertIn("source-acquisition:artifact-rebuild:0", blocker_ids)
        self.assertIn("source-acquisition:dev-baseline:gn-args", blocker_ids)
        self.assertIn("source-acquisition:dev-baseline:build-ninja", blocker_ids)
        self.assertIn("source-acquisition:dev-baseline:platform-gn", blocker_ids)
        self.assertIn("source-acquisition:dev-baseline:full-xcode", blocker_ids)
        detector_blocker = next(
            blocker for blocker in payload["blockers"]
            if blocker["blocker_id"] == "detector:coverage-gap:macos-arm64:sannysoft:headed:proxy:host"
        )
        self.assertEqual(detector_blocker["display_mode"], "headed")
        self.assertEqual(detector_blocker["network_mode"], "proxy")
        self.assertEqual(detector_blocker["container"], False)
        self.assertEqual(
            detector_blocker["remediation_command"],
            "python3 scripts/detector_harness.py run --detector sannysoft --proxy-url \"$BROWSEFORGE_DETECTOR_PROXY_URL\" --network-mode proxy --display headed",
        )
        native_blocker = next(
            blocker for blocker in payload["blockers"]
            if blocker["blocker_id"] == "native-artifact:macos-arm64:0"
        )
        self.assertEqual(native_blocker["host_supported"], True)
        self.assertEqual(native_blocker["native_toolchain_ready"], False)
        self.assertEqual(native_blocker["package_zip_exists"], False)
        self.assertEqual(
            native_blocker["remediation_commands"],
            ["python3 scripts/chromium_native.py gn-gen --platform macos-arm64 --execute"],
        )
        macos_x64_blocker = next(
            blocker for blocker in payload["blockers"]
            if blocker["blocker_id"] == "native-artifact:macos-x64:0"
        )
        self.assertEqual(macos_x64_blocker["status"], "missing_native_release_artifact")
        macos_x64_detail = macos_x64_blocker["detail"].lower()
        for token in ["artifact", "checksum", "sbom", "provenance"]:
            with self.subTest(token=token):
                self.assertIn(token, macos_x64_detail)
        self.assertNotIn("detector evidence", macos_x64_detail)
        self.assertEqual(set(release_status.INPUT_PATHS), set(payload["input_sha256"]))
        resource_ids = {requirement["resource_id"] for requirement in payload["resource_requirements"]}
        self.assertIn("external-detector-proxy", resource_ids)
        self.assertIn("native-artifact-macos-arm64", resource_ids)
        self.assertIn("native-artifact-macos-x64", resource_ids)
        self.assertIn("live-proxy-detector-matrix", resource_ids)
        self.assertIn("windows-manual-detector-validation", resource_ids)
        self.assertIn("release-grade-code-signing", resource_ids)
        proxy_requirement = next(
            requirement for requirement in payload["resource_requirements"]
            if requirement["resource_id"] == "external-detector-proxy"
        )
        self.assertEqual(proxy_requirement["provide"], ["BROWSEFORGE_DETECTOR_PROXY_URL"])
        native_requirement = next(
            requirement for requirement in payload["resource_requirements"]
            if requirement["resource_id"] == "native-artifact-macos-arm64"
        )
        self.assertEqual(native_requirement["provide"], ["full Xcode selected via xcode-select"])
        self.assertEqual(
            native_requirement["unblocks"],
            [
                "macos-arm64 packaged native BrowseForge Chromium artifact",
                "macos-arm64 native detector evidence",
            ],
        )
        macos_x64_requirement = next(
            requirement for requirement in payload["resource_requirements"]
            if requirement["resource_id"] == "native-artifact-macos-x64"
        )
        self.assertEqual(
            macos_x64_requirement["unblocks"],
            [
                "macos-x64 packaged native BrowseForge Chromium artifact",
                "macos-x64 checksum/SBOM/provenance metadata",
            ],
        )
        self.assertFalse(
            any("detector evidence" in item for item in macos_x64_requirement["unblocks"]),
            macos_x64_requirement["unblocks"],
        )
        windows_requirement = next(
            requirement for requirement in payload["resource_requirements"]
            if requirement["resource_id"] == "windows-manual-detector-validation"
        )
        self.assertEqual(windows_requirement["status"], "missing_detector_evidence")
        self.assertEqual(
            windows_requirement["provide"],
            ["windows-x64:browserleaks:headed:direct:host"],
        )
        self.assertEqual(
            windows_requirement["requirements"],
            [
                "manual Windows OS validation host that can launch the packaged chrome.exe",
                "sanitized headed detector evidence for each required Windows matrix row",
                "local wine/qemu execution is not required for the Windows compile/runtime verification step",
            ],
        )
        self.assertEqual(
            windows_requirement["unblocks"],
            [
                "Windows native detector evidence",
                "cross-platform drift detector matrix",
            ],
        )
        signing_requirement = next(
            requirement for requirement in payload["resource_requirements"]
            if requirement["resource_id"] == "release-grade-code-signing"
        )
        self.assertEqual(signing_requirement["status"], "missing_signing_policy")
        self.assertEqual(signing_requirement["provide"], ["linux-x64", "windows-x64"])
        self.assertIn(
            "Authenticode/code-signing path for Windows artifacts",
            signing_requirement["requirements"],
        )
        self.assertIn(
            "release-grade signed artifact publication",
            signing_requirement["unblocks"],
        )

    def test_release_status_allows_empty_integration_blockers_while_signing_policy_blocks_release(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_base_inputs(root)
            self.write_json(root, "contracts/browseforge-integration.contract.json", {"release_blockers": []})

            payload = release_status.release_status(root, "2026-07-10T00:00:00Z")

        blocker_ids = {blocker["blocker_id"] for blocker in payload["blockers"]}
        self.assertFalse(
            any(blocker_id.startswith("browseforge-integration:") for blocker_id in blocker_ids),
            blocker_ids,
        )
        self.assertIn("signing-policy:linux-x64", blocker_ids)
        self.assertIn("signing-policy:windows-x64", blocker_ids)
        self.assertFalse(payload["release_grade_ready"])

    def test_windows_detector_summary_gap_requirement_provides_matrix_keys(self) -> None:
        requirements = release_status.release_resource_requirements(
            native_preflight={"release_grade_ready": True, "platforms": []},
            proxy_preflight={"ready": True, "missing": [], "errors": []},
            detector_summary={
                "blocking_findings": [],
                "coverage_gaps": [
                    {
                        "matrix_key": "windows-x64:browserleaks:headed:direct:host",
                        "platform": "windows-x64",
                        "detector_id": "browserleaks",
                        "display_mode": "headed",
                        "network_mode": "direct",
                    },
                    {
                        "matrix_key": "windows-x64:sannysoft:headed:direct:host",
                        "platform": "windows-x64",
                        "detector_id": "sannysoft",
                        "display_mode": "headed",
                        "network_mode": "direct",
                    },
                ],
            },
            signing_policy={"release_grade_ready": True, "policies": []},
            integration_contract={"release_blockers": []},
        )

        self.assertEqual(
            [
                {
                    "resource_id": "windows-manual-detector-validation",
                    "status": "missing_detector_evidence",
                    "severity": "high",
                    "provide": [
                        "windows-x64:browserleaks:headed:direct:host",
                        "windows-x64:sannysoft:headed:direct:host",
                    ],
                    "requirements": [
                        "manual Windows OS validation host that can launch the packaged chrome.exe",
                        "sanitized headed detector evidence for each required Windows matrix row",
                        "local wine/qemu execution is not required for the Windows compile/runtime verification step",
                    ],
                    "unblocks": [
                        "Windows native detector evidence",
                        "cross-platform drift detector matrix",
                    ],
                }
            ],
            requirements,
        )

    def test_windows_integration_contract_blocker_uses_manual_validation_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_base_inputs(root)
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
                "contracts/browseforge-integration.contract.json",
                {
                    "release_blockers": [
                        "Windows native headed detector evidence is missing from the release contract"
                    ]
                },
            )
            payload = release_status.release_status(root, "2026-07-10T00:00:00Z")

        blocker_ids = {blocker["blocker_id"] for blocker in payload["blockers"]}
        self.assertNotIn("detector:coverage-gap:windows-x64:browserleaks:headed:direct:host", blocker_ids)
        self.assertIn("browseforge-integration:0", blocker_ids)
        windows_requirement = next(
            requirement for requirement in payload["resource_requirements"]
            if requirement["resource_id"] == "windows-manual-detector-validation"
        )
        self.assertEqual(windows_requirement["status"], "missing_detector_evidence")
        self.assertEqual(
            windows_requirement["provide"],
            ["windows-x64 native headed detector evidence"],
        )

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
                    payload = {
                        "chromium_base": {
                            "artifact_rebuild_required": False,
                            "build_output_status": {
                                "dev_build_ninja_exists": True,
                                "dev_gn_args_exists": True,
                            },
                        }
                    }
                else:  # pragma: no cover - keeps the fixture exhaustive when inputs change.
                    raise AssertionError(path)
                self.write_json(root, path, payload)
            result = release_status.release_status(root, "2026-07-10T00:00:00Z")

        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["blocker_count"], 0)
        self.assertIs(result["release_grade_ready"], True)
        self.assertEqual(result["resource_requirements"], [])


if __name__ == "__main__":
    unittest.main()
