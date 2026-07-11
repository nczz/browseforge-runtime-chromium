from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "objective_audit.py"

spec = importlib.util.spec_from_file_location("objective_audit", SCRIPT)
objective_audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(objective_audit)


class ObjectiveAuditTests(unittest.TestCase):
    def write_json(self, root: Path, path: str, payload: dict) -> None:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def write_inputs(self, root: Path, *, ready: bool) -> None:
        self.write_json(
            root,
            "knowledge/manifests/source-acquisition.json",
            {
                "chromium_base": {
                    "source_checkout_status": "checked_out_pinned_ref",
                    "source_workdir_isolation_status": "helpers_support_profile_specific_workdirs_with_shared_fallback",
                    "build_output_status": {
                        "dev_gn_args_exists": ready,
                        "dev_build_ninja_exists": ready,
                        "linux_docker_gn_args_exists": True,
                        "linux_docker_build_ninja_exists": True,
                        "linux_docker_chrome_exists": True,
                    },
                    "dependency_profile_status": {
                        "profile_isolated_workdir_contract": {
                            "host_source_env": "BROWSEFORGE_CHROMIUM_HOST_WORKDIR",
                            "linux_docker_source_env": "BROWSEFORGE_CHROMIUM_LINUX_WORKDIR",
                            "shared_fallback_env": "BROWSEFORGE_CHROMIUM_WORKDIR",
                        }
                    },
                }
            },
        )
        self.write_json(
            root,
            "knowledge/manifests/patchset.json",
            {
                "patchsets": [
                    {
                        "patchset_id": "scaffold-browseforge-stealth-substrate",
                        "upstream_status": "copied_to_external_checkout_and_linked_to_gn_all",
                    }
                ]
            },
        )
        self.write_json(
            root,
            "knowledge/manifests/release-status.json",
            {
                "release_grade_ready": ready,
                "blocker_count": 0 if ready else 2,
                "blockers": []
                if ready
                else [
                    {"blocker_id": "source-acquisition:dev-baseline:gn-args"},
                    {"blocker_id": "browseforge-integration:1"},
                ],
            },
        )
        self.write_json(
            root,
            "knowledge/manifests/native-artifact-preflight.json",
            {
                "release_grade_ready": ready,
                "platforms": [
                    {"platform": "linux-x64", "ready": True},
                    {"platform": "macos-arm64", "ready": ready},
                    {"platform": "windows-x64", "ready": ready},
                ],
            },
        )
        self.write_json(
            root,
            "knowledge/manifests/fingerprint-surface-status.json",
            {
                "release_grade": ready,
                "surfaces": []
                if ready
                else [
                    {"surface": "proxy/IP coherence", "release_blocker": True},
                    {"surface": "cross-platform drift", "release_blocker": True},
                ],
            },
        )
        self.write_json(
            root,
            "contracts/browseforge-integration.contract.json",
            {
                "required_browseforge_surfaces": ["config.runtimes.<id>", "MCP open_browser"],
                "adapter_requirements": ["runtime descriptor registered with chromium family"],
                "release_blockers": [] if ready else ["macOS native BrowseForge Chromium release artifact is missing"],
            },
        )

    def test_objective_audit_reports_current_blockers_without_claiming_completion(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_inputs(root, ready=False)
            payload = objective_audit.objective_audit(root, "2026-07-11T02:20:00Z")

        self.assertFalse(payload["overall_ready"])
        self.assertFalse(payload["release_grade_ready"])
        deliverables = {entry["deliverable_id"]: entry for entry in payload["deliverables"]}
        self.assertFalse(deliverables["source_build_baseline"]["satisfied"])
        self.assertIn("missing build output: dev_gn_args_exists", deliverables["source_build_baseline"]["blockers"])
        self.assertFalse(deliverables["native_release_artifacts"]["satisfied"])
        self.assertIn("native platform not ready: macos-arm64", deliverables["native_release_artifacts"]["blockers"])
        self.assertFalse(deliverables["release_grade_cutover"]["satisfied"])
        self.assertIn("browseforge-integration:1", deliverables["release_grade_cutover"]["blockers"])

    def test_objective_audit_can_report_all_deliverables_ready(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.write_inputs(root, ready=True)
            payload = objective_audit.objective_audit(root, "2026-07-11T02:20:00Z")

        self.assertTrue(payload["overall_ready"])
        self.assertTrue(payload["release_grade_ready"])
        self.assertEqual(0, payload["blocker_count"])
        self.assertTrue(all(entry["satisfied"] for entry in payload["deliverables"]))


if __name__ == "__main__":
    unittest.main()
