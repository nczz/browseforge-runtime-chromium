from __future__ import annotations

import contextlib
import io
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = ROOT / "scripts" / "validate.py"
RELEASE_STATUS_SCRIPT = ROOT / "scripts" / "release_status.py"
OBJECTIVE_AUDIT_SCRIPT = ROOT / "scripts" / "objective_audit.py"
GRAPH_PATH = ROOT / "generated" / "kg" / "runtime.graph.jsonl"
RUNTIME_ARTIFACTS_MANIFEST = ROOT / "knowledge" / "manifests" / "runtime-artifacts.json"
LINUX_ARTIFACT_ID = "browseforge-runtime-chromium-v0.1.0-alpha.0-linux-x64"
LINUX_ARTIFACT_NODE_ID = f"RuntimeArtifact:{LINUX_ARTIFACT_ID}"
LINUX_PLATFORM_NODE_ID = "Platform:linux-x64"


class ValidateRuntimeGraphTests(unittest.TestCase):
    REQUIRED_RUNTIME_GRAPH_MANIFEST_SOURCES = (
        "contracts/runtime.manifest.json",
        "contracts/browseforge-integration.contract.json",
        "detectors/evidence-schema.json",
        "detector-summary.json",
        "knowledge/kb-manifest.json",
        "knowledge/manifests/detectors.json",
        "knowledge/manifests/patchset.json",
        "knowledge/manifests/runtime-artifacts.json",
        "knowledge/manifests/reference-sources.json",
        "knowledge/manifests/platform-matrix.json",
        "knowledge/manifests/release-gates.json",
        "knowledge/manifests/detector-score-comparison.json",
        "knowledge/manifests/fingerprint-surface-status.json",
        "knowledge/manifests/proxy-preflight.json",
        "knowledge/manifests/native-artifact-preflight.json",
        "knowledge/manifests/signing-policy.json",
        "knowledge/manifests/release-status.json",
        "knowledge/manifests/objective-audit.json",
        "knowledge/manifests/source-acquisition.json",
    )
    REQUIRED_GRAPH_FINGERPRINT_SURFACE_IDS = (
        "audio",
        "automation_signals",
        "canvas",
        "client_hints",
        "fonts",
        "hardware",
        "locale",
        "permissions",
        "proxy_ip_coherence",
        "screen",
        "seed_identity",
        "storage_quota",
        "timezone",
        "user_agent",
        "webgl",
        "webrtc",
    )

    def _load_graph(self, path: Path = GRAPH_PATH) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:  # pragma: no cover - keeps malformed JSONL failures actionable.
                    self.fail(f"{path}:{line_no}: invalid JSONL: {exc}")
                self.assertIsInstance(record, dict)
                records.append(record)
        self.assertTrue(records, "runtime graph must not be empty")
        return records

    def _load_linux_artifact_manifest(self) -> dict[str, Any]:
        with RUNTIME_ARTIFACTS_MANIFEST.open(encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.assertIsInstance(manifest, dict)
        artifacts = manifest.get("artifacts")
        self.assertIsInstance(artifacts, list)
        matches = [artifact for artifact in artifacts if artifact.get("artifact_id") == LINUX_ARTIFACT_ID]
        self.assertEqual(1, len(matches), f"expected exactly one manifest artifact {LINUX_ARTIFACT_ID}")
        artifact = matches[0]
        self.assertIsInstance(artifact, dict)
        return artifact

    def _node_by_id(self, graph: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
        matches = [record for record in graph if record.get("record_type") == "node" and record.get("id") == node_id]
        self.assertLessEqual(len(matches), 1, f"duplicate node id {node_id}")
        return matches[0] if matches else None

    def _edges(self, graph: list[dict[str, Any]], *, label: str, from_id: str | None = None, to_id: str | None = None) -> list[dict[str, Any]]:
        edges = [record for record in graph if record.get("record_type") == "edge" and record.get("label") == label]
        if from_id is not None:
            edges = [edge for edge in edges if edge.get("from") == from_id]
        if to_id is not None:
            edges = [edge for edge in edges if edge.get("to") == to_id]
        return edges

    def _load_validate_module(self) -> Any:
        spec = importlib.util.spec_from_file_location("validate_under_test", VALIDATE_SCRIPT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None
        assert spec.loader is not None
        sys.modules["validate_under_test"] = module
        spec.loader.exec_module(module)
        return module

    def _manifest_node_id(self, manifest_path: str) -> str:
        return f"Manifest:{manifest_path.replace('/', '-')}"

    def _runtime_graph_manifest_source_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for manifest_path in self.REQUIRED_RUNTIME_GRAPH_MANIFEST_SOURCES:
            node_id = self._manifest_node_id(manifest_path)
            records.extend(
                [
                    {
                        "record_type": "node",
                        "label": "Manifest",
                        "id": node_id,
                        "properties": {"manifest_id": manifest_path, "repo_path": manifest_path},
                    },
                    {
                        "record_type": "edge",
                        "label": "DECLARES_SOURCE",
                        "from": node_id,
                        "to": "RuntimeProvider:browseforge-chromium",
                        "properties": {},
                    },
                ]
            )
        return records

    def test_runtime_graph_promotes_packaged_linux_artifact_from_manifest(self) -> None:
        """The generated KG binds linux-x64 to the packaged release artifact, not the stale missing blocker."""
        graph = self._load_graph()
        manifest_artifact = self._load_linux_artifact_manifest()

        artifact_node = self._node_by_id(graph, LINUX_ARTIFACT_NODE_ID)
        self.assertIsNotNone(artifact_node, f"missing RuntimeArtifact node {LINUX_ARTIFACT_NODE_ID}")
        assert artifact_node is not None
        self.assertEqual("RuntimeArtifact", artifact_node.get("label"))
        properties = artifact_node.get("properties")
        self.assertIsInstance(properties, dict)
        assert isinstance(properties, dict)

        for field in [
            "artifact_id",
            "platform",
            "os",
            "arch",
            "sha256",
            "size_bytes",
            "sbom_path",
            "provenance_path",
            "browser_version",
            "source_ref",
            "patchset_id",
            "wrapper_version",
            "release_channel",
        ]:
            self.assertEqual(manifest_artifact[field], properties.get(field), f"RuntimeArtifact.{field}")
        self.assertEqual("linux-x64", properties["platform"])
        self.assertEqual("linux", properties["os"])
        self.assertEqual("x64", properties["arch"])
        self.assertTrue(properties.get("release_grade"), "linux-x64 artifact must be marked release-grade")
        self.assertEqual("packaged", properties.get("status"))

        self.assertTrue(
            self._edges(graph, label="BUILT_FOR", from_id=LINUX_ARTIFACT_NODE_ID, to_id=LINUX_PLATFORM_NODE_ID),
            "linux-x64 BUILT_FOR edge must originate at the real packaged artifact",
        )
        self.assertTrue(
            self._edges(graph, label="TARGETS_PLATFORM", from_id=LINUX_ARTIFACT_NODE_ID, to_id=LINUX_PLATFORM_NODE_ID),
            "linux-x64 TARGETS_PLATFORM edge must originate at the real packaged artifact",
        )
        self.assertFalse(
            self._edges(graph, label="BUILT_FOR", from_id="RuntimeArtifact:missing-runtime-artifact", to_id=LINUX_PLATFORM_NODE_ID),
            "linux-x64 must not still be BUILT_FOR the missing-artifact blocker",
        )
        self.assertFalse(
            self._edges(graph, label="TARGETS_PLATFORM", from_id="RuntimeArtifact:missing-runtime-artifact", to_id=LINUX_PLATFORM_NODE_ID),
            "linux-x64 must not still TARGETS_PLATFORM from the missing-artifact blocker",
        )

    def test_runtime_graph_release_gates_do_not_block_packaged_artifact_prerequisites(self) -> None:
        """Release gates for indexed Chromium source and produced artifacts cannot remain blocked after packaging."""
        graph = self._load_graph()

        for gate_id in ["chromium-source-indexed", "runtime-artifact-produced"]:
            with self.subTest(gate_id=gate_id):
                gate_node = self._node_by_id(graph, f"ReleaseGate:{gate_id}")
                self.assertIsNotNone(gate_node, f"missing ReleaseGate:{gate_id}")
                assert gate_node is not None
                properties = gate_node.get("properties")
                self.assertIsInstance(properties, dict)
                assert isinstance(properties, dict)
                self.assertNotEqual("blocked", properties.get("status"), f"ReleaseGate:{gate_id} must not remain blocked")
                self.assertNotIn("blocker", properties, f"ReleaseGate:{gate_id} must not retain a blocker claim")
                for edge in self._edges(graph, label="SUPPORTS_GATE", to_id=f"ReleaseGate:{gate_id}"):
                    edge_properties = edge.get("properties") or {}
                    self.assertNotEqual("blocked", edge_properties.get("status"), f"SUPPORTS_GATE edge to {gate_id} must not be blocked")

    def test_browseforge_adapter_gate_tracks_native_stealth_config_commit(self) -> None:
        graph = self._load_graph()
        gate_node = self._node_by_id(graph, "ReleaseGate:browseforge-adapter-merged")
        self.assertIsNotNone(gate_node)
        assert gate_node is not None
        properties = gate_node.get("properties")
        self.assertIsInstance(properties, dict)
        assert isinstance(properties, dict)
        evidence = properties.get("evidence")
        self.assertIsInstance(evidence, str)
        assert isinstance(evidence, str)
        for token in [
            "5dc2749",
            "--browseforge-stealth-config",
            "--browseforge-stealth-mode=enabled",
            "profile-scoped native stealth persona config",
            "persona_id_hash",
            "origin_salt_key",
        ]:
            self.assertIn(token, evidence)

    def test_committed_detector_runs_do_not_keep_missing_artifact_placeholders(self) -> None:
        """Detectors with committed linux-x64 evidence must not keep no-artifact placeholders as evidence."""
        graph = self._load_graph()
        detector_runs = {
            record["id"]: record.get("properties", {}).get("detector_id")
            for record in graph
            if record.get("record_type") == "node" and record.get("label") == "DetectorRun" and "id" in record
        }
        committed_detector_ids = {
            detector_runs[edge["from"]]
            for edge in self._edges(graph, label="TARGETS_ARTIFACT", to_id=LINUX_ARTIFACT_NODE_ID)
            if edge.get("from") in detector_runs and detector_runs[edge["from"]]
        }
        self.assertTrue(committed_detector_ids, "expected committed detector runs for the packaged linux-x64 artifact")

        stale_placeholder_edges = [
            edge
            for edge in self._edges(graph, label="TARGETS_ARTIFACT", to_id="RuntimeArtifact:missing-runtime-artifact")
            if detector_runs.get(edge.get("from")) in committed_detector_ids
        ]
        self.assertFalse(
            stale_placeholder_edges,
            "detectors with committed linux-x64 evidence must not also target the missing-artifact blocker",
        )


    def test_runtime_artifact_manifest_distinguishes_supported_contracts_from_artifacts(self) -> None:
        """macos-arm64 and windows-x64 have packager contracts, but artifacts still list only produced packages."""
        with RUNTIME_ARTIFACTS_MANIFEST.open(encoding="utf-8") as fh:
            manifest = json.load(fh)

        self.assertEqual(["linux-x64", "macos-arm64", "windows-x64"], manifest.get("supported_package_platforms"))
        unsupported = manifest.get("unsupported_package_platforms")
        self.assertIsInstance(unsupported, dict)
        assert isinstance(unsupported, dict)
        self.assertEqual({"macos-x64", "linux-arm64"}, set(unsupported))
        self.assertNotIn("windows-x64", unsupported)

        artifact_platforms = {artifact.get("platform") for artifact in manifest.get("artifacts", [])}
        self.assertEqual({"linux-x64"}, artifact_platforms)
        self.assertGreater(set(manifest["supported_package_platforms"]), artifact_platforms)

    def test_validate_allows_supported_package_contract_without_artifact(self) -> None:
        """A supported packager contract must not require a RuntimeArtifact until an artifact is listed."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self.assertEqual(["linux-x64", "macos-arm64", "windows-x64"], manifest["supported_package_platforms"])
            self.assertEqual({"linux-x64"}, {artifact["platform"] for artifact in manifest["artifacts"]})
            self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])

            output = self._run_validate_expect_success(module, temp_root)

        self.assertIn("runtime framework validation ok", output)

    def test_validate_accepts_native_artifact_preflight_for_linux_ready_and_native_blockers(self) -> None:
        """native-artifact-preflight records the Linux artifact as ready while native OS artifacts remain blockers."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            runtime_manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, runtime_manifest["artifacts"])
            preflight = self._write_native_artifact_preflight(temp_root, runtime_manifest=runtime_manifest)

            platforms = {entry["platform"]: entry for entry in preflight["platforms"]}
            self.assertEqual(["linux-x64", "macos-arm64", "windows-x64"], preflight["supported_package_platforms"])
            self.assertTrue(platforms["linux-x64"]["ready"])
            self.assertEqual("ready", platforms["linux-x64"]["status"])
            self.assertEqual(LINUX_ARTIFACT_ID, platforms["linux-x64"]["artifact_id"])
            self.assertEqual(
                [f"knowledge/manifests/runtime-artifacts.json:{LINUX_ARTIFACT_ID}"],
                platforms["linux-x64"]["evidence"],
            )
            self.assertEqual([], platforms["linux-x64"]["missing_prerequisites"])
            for platform in ["macos-arm64", "windows-x64"]:
                with self.subTest(platform=platform):
                    self.assertFalse(platforms[platform]["ready"])
                    self.assertEqual("blocked", platforms[platform]["status"])
                    self.assertNotIn("artifact_id", platforms[platform])
                    self.assertEqual([], platforms[platform]["evidence"])
                    self.assertIn(
                        "runtime-artifacts artifact missing",
                        platforms[platform]["missing_prerequisites"],
                    )
                    snapshot = platforms[platform]["status_snapshot"]
                    self.assertIs(snapshot["package_zip_exists"], False)
                    self.assertIs(snapshot["native_toolchain_ready"], False)
                    self.assertIn("host_supported", snapshot)

            output = self._run_validate_expect_success(module, temp_root)

        self.assertIn("runtime framework validation ok", output)

    def test_validate_accepts_signing_policy_with_linux_signature_and_native_decisions(self) -> None:
        """Signing policy records the Linux artifact signature and native signing blockers without claiming release readiness."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            runtime_manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, runtime_manifest["artifacts"])
            signing_policy = self._write_signing_policy(temp_root, runtime_manifest=runtime_manifest)

            policies = {entry["platform"]: entry for entry in signing_policy["policies"]}
            linux_artifact = runtime_manifest["artifacts"][0]
            self.assertEqual(linux_artifact["signature"], policies["linux-x64"]["signature"])
            for platform in ["macos-arm64", "windows-x64"]:
                with self.subTest(platform=platform):
                    self.assertIn("signing_requirement", policies[platform])
                    self.assertFalse(policies[platform]["release_grade_allowed"])

            output = self._run_validate_expect_success(module, temp_root)

        self.assertIn("runtime framework validation ok", output)

    def test_validate_rejects_signing_policy_missing_native_platform_decision(self) -> None:
        """macOS and Windows platform-matrix signing requirements must each have a signing-policy row."""
        module = self._load_validate_module()
        for platform in ["macos-arm64", "windows-x64"]:
            with self.subTest(platform=platform):
                with tempfile.TemporaryDirectory() as td:
                    temp_root = Path(td)
                    self._write_minimal_validate_tree(temp_root, module)
                    runtime_manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
                    self._write_runtime_graph_for_artifacts(temp_root, runtime_manifest["artifacts"])
                    self._write_signing_policy(temp_root, runtime_manifest=runtime_manifest, omit_platforms={platform})

                    message = self._run_validate_expect_exit(module, temp_root).lower()

                self.assertIn("signing policy", message)
                self.assertIn(platform, message)

    def test_validate_rejects_signing_policy_linux_signature_drift(self) -> None:
        """linux-x64 signing policy cannot retain stale signature metadata after runtime-artifacts changes."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            runtime_manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, runtime_manifest["artifacts"])
            self.assertNotEqual("stale-linux-signature", runtime_manifest["artifacts"][0]["signature"])
            self._write_signing_policy(
                temp_root,
                runtime_manifest=runtime_manifest,
                platform_overrides={"linux-x64": {"signature": "stale-linux-signature"}},
            )

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("signing policy", message)
        self.assertIn("linux-x64", message)
        self.assertIn("signature", message)

    def test_validate_rejects_signing_policy_release_grade_ready_with_blocked_platform(self) -> None:
        """release_grade_ready cannot be true while any supported platform signing decision is not release-grade allowed."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            runtime_manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, runtime_manifest["artifacts"])
            signing_policy = self._write_signing_policy(temp_root, runtime_manifest=runtime_manifest, release_grade_ready=True)
            self.assertTrue(any(not policy["release_grade_allowed"] for policy in signing_policy["policies"]))

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("signing policy", message)
        self.assertIn("release_grade_ready", message)
        self.assertIn("release-grade signing", message)

    def test_validate_rejects_native_artifact_preflight_missing_supported_platform(self) -> None:
        """Every runtime-artifacts supported package platform must have a native preflight row."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            runtime_manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, runtime_manifest["artifacts"])
            self._write_native_artifact_preflight(
                temp_root,
                runtime_manifest=runtime_manifest,
                omit_platforms={"windows-x64"},
            )

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("native artifact preflight", message)
        self.assertIn("windows-x64", message)

    def test_validate_rejects_native_artifact_preflight_native_ready_without_artifact(self) -> None:
        """macOS and Windows cannot claim preflight readiness until their artifacts exist in runtime-artifacts."""
        module = self._load_validate_module()
        for platform in ["macos-arm64", "windows-x64"]:
            with self.subTest(platform=platform):
                with tempfile.TemporaryDirectory() as td:
                    temp_root = Path(td)
                    self._write_minimal_validate_tree(temp_root, module)
                    runtime_manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
                    self._write_runtime_graph_for_artifacts(temp_root, runtime_manifest["artifacts"])
                    fake_artifact_id = f"browseforge-runtime-chromium-v0.1.0-alpha.0-{platform}"
                    self._write_native_artifact_preflight(
                        temp_root,
                        runtime_manifest=runtime_manifest,
                        platform_overrides={
                            platform: {
                                "artifact_id": fake_artifact_id,
                                "evidence": [f"knowledge/manifests/runtime-artifacts.json:{fake_artifact_id}"],
                                "missing_prerequisites": [],
                                "ready": True,
                                "status": "ready",
                            }
                        },
                    )

                    message = self._run_validate_expect_exit(module, temp_root).lower()

                self.assertIn("native artifact preflight", message)
                self.assertIn(platform, message)
                self.assertIn("runtime-artifacts", message)

    def test_validate_rejects_native_artifact_preflight_missing_status_snapshot(self) -> None:
        """Native preflight rows must preserve the host/toolchain booleans behind each blocker."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            runtime_manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, runtime_manifest["artifacts"])
            preflight = self._write_native_artifact_preflight(temp_root, runtime_manifest=runtime_manifest)
            for entry in preflight["platforms"]:
                if entry["platform"] == "macos-arm64":
                    del entry["status_snapshot"]
            self._write_json(temp_root / "knowledge" / "manifests" / "native-artifact-preflight.json", preflight)

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("native artifact preflight", message)
        self.assertIn("macos-arm64", message)
        self.assertIn("status_snapshot", message)

    def test_validate_rejects_native_artifact_preflight_release_grade_ready_with_blocked_platform(self) -> None:
        """release_grade_ready cannot be true while any supported package platform remains not ready."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            runtime_manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, runtime_manifest["artifacts"])
            self._write_native_artifact_preflight(
                temp_root,
                runtime_manifest=runtime_manifest,
                release_grade_ready=True,
            )

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("native artifact preflight", message)
        self.assertIn("release_grade_ready", message)
        self.assertIn("blocked", message)

    def test_validate_rejects_platform_node_drift_from_platform_matrix(self) -> None:
        """A generated Platform node cannot silently diverge from the release planning matrix."""
        module = self._load_validate_module()
        cases: list[tuple[str, Any]] = [
            ("status", "planned"),
            ("required_evidence", ["build succeeds", "artifact checksum exists"]),
        ]
        for field, stale_value in cases:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as td:
                    temp_root = Path(td)
                    self._write_minimal_validate_tree(temp_root, module)
                    manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
                    self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
                    self._rewrite_platform_node_property(temp_root, "linux-x64", field, stale_value)

                    message = self._run_validate_expect_exit(module, temp_root).lower()

                self.assertIn("platform", message)
                self.assertIn("drift", message)
                self.assertIn("linux-x64", message)
                self.assertIn(field, message)

    def test_validate_rejects_artifact_for_unsupported_package_platform(self) -> None:
        """An actual artifact for an unsupported platform is invalid even if the KG node exists."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            unsupported_artifact = dict(manifest["artifacts"][0])
            unsupported_artifact.update(
                {
                    "artifact_id": "browseforge-runtime-chromium-v0.1.0-alpha.0-linux-arm64",
                    "platform": "linux-arm64",
                    "os": "linux",
                    "arch": "arm64",
                    "sha256": "2a991ac31efee72a2f93c688619644e97b52b5e4d8732eb30014fa0265ffd93a",
                    "size_bytes": 567798166,
                    "sbom_path": "dist/stage/browseforge-runtime-chromium-v0.1.0-alpha.0-linux-arm64/SBOM.json",
                    "provenance_path": "dist/stage/browseforge-runtime-chromium-v0.1.0-alpha.0-linux-arm64/provenance.json",
                }
            )
            manifest["artifacts"].append(unsupported_artifact)
            self._write_json(temp_root / "knowledge" / "manifests" / "runtime-artifacts.json", manifest)
            self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])

            message = self._run_validate_expect_exit(module, temp_root)

        self.assertIn("runtime asset contract", message)
        self.assertIn("linux-arm64", message)


    def test_validate_rejects_runtime_artifact_manifest_with_stale_archive_metadata(self) -> None:
        """runtime-artifacts.json cannot retain stale archive sha/size after the packaged zip changes."""
        cases: list[tuple[str, str | int]] = [
            ("sha256", "0" * 64),
            ("size_bytes", 1),
        ]
        for field, stale_value in cases:
            with self.subTest(field=field):
                module = self._load_validate_module()
                with tempfile.TemporaryDirectory() as td:
                    temp_root = Path(td)
                    self._write_minimal_validate_tree(temp_root, module)
                    manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
                    manifest["artifacts"][0][field] = stale_value
                    if field == "sha256":
                        manifest["artifact_sha256"] = stale_value
                    else:
                        manifest["artifact_size_bytes"] = stale_value
                    self._write_json(temp_root / "knowledge" / "manifests" / "runtime-artifacts.json", manifest)
                    self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])

                    message = self._run_validate_expect_exit(module, temp_root).lower()

                self.assertRegex(message, r"runtime[- ]artifacts?", message)
                self.assertIn(field, message)
                self.assertIn("drift", message)

    def test_validate_accepts_release_gate_artifact_evidence_with_current_sha_and_size(self) -> None:
        """Passed artifact release gates must cite the current packaged archive sha and byte size."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            artifact = manifest["artifacts"][0]
            self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
            self._write_release_gates(temp_root, live_detector_status="warning")

            release_gates = json.loads((temp_root / "knowledge" / "manifests" / "release-gates.json").read_text(encoding="utf-8"))
            gates_by_id = {gate["gate_id"]: gate for gate in release_gates["release_candidate_required_gates"]}
            for gate_id in ["runtime-artifact-produced", "sbom-provenance-release-assets"]:
                with self.subTest(gate_id=gate_id):
                    evidence = gates_by_id[gate_id]["evidence"]
                    self.assertIn(artifact["sha256"], evidence)
                    self.assertIn(str(artifact["size_bytes"]), evidence)

            output = self._run_validate_expect_success(module, temp_root)

        self.assertIn("runtime framework validation ok", output)

    def test_validate_accepts_runtime_graph_release_gate_nodes_matching_manifest(self) -> None:
        """Generated KG ReleaseGate nodes are valid when they mirror release-gates.json exactly."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])

            output = self._run_validate_expect_success(module, temp_root)

        self.assertIn("runtime framework validation ok", output)

    def test_validate_accepts_runtime_graph_manifest_source_nodes_and_edges(self) -> None:
        """Machine-readable manifest sources must remain declared in the generated KG."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
            graph = self._load_graph(temp_root / "generated" / "kg" / "runtime.graph.jsonl")

            for source_path in self.REQUIRED_RUNTIME_GRAPH_MANIFEST_SOURCES:
                with self.subTest(source_path=source_path):
                    manifest_node_id = self._manifest_node_id(source_path)
                    self.assertIsNotNone(self._node_by_id(graph, manifest_node_id), f"missing Manifest node {source_path}")
                    self.assertTrue(
                        self._edges(
                            graph,
                            label="DECLARES_SOURCE",
                            from_id=manifest_node_id,
                            to_id="RuntimeProvider:browseforge-chromium",
                        ),
                        f"missing DECLARES_SOURCE edge for {source_path}",
                    )

            output = self._run_validate_expect_success(module, temp_root)

        self.assertIn("runtime framework validation ok", output)

    def test_validate_rejects_runtime_manifest_missing_required_fingerprint_surface(self) -> None:
        """runtime.manifest.json cannot drop a fingerprint surface required by the KG contract."""
        removed_surface = "seed_identity"
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest_path = temp_root / "contracts" / "runtime.manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["fingerprint"]["surfaces"].remove(removed_surface)
            self._write_json(manifest_path, manifest)

            message = self._run_validate_expect_exit(module, temp_root)

        self.assertIn("runtime manifest missing required fingerprint surfaces", message)
        self.assertIn(removed_surface, message)

    def test_validate_rejects_runtime_manifest_unknown_fingerprint_surface(self) -> None:
        """runtime.manifest.json cannot advertise fingerprint surfaces outside the KG contract."""
        unknown_surface = "legacy_plugin_entropy"
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest_path = temp_root / "contracts" / "runtime.manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["fingerprint"]["surfaces"].append(unknown_surface)
            self._write_json(manifest_path, manifest)

            message = self._run_validate_expect_exit(module, temp_root)

        self.assertIn("runtime manifest declares unknown fingerprint surfaces", message)
        self.assertIn(unknown_surface, message)

    def test_validate_rejects_graph_queries_missing_manifest_source_tokens(self) -> None:
        """Graph queries must cover Manifest provenance nodes and DECLARES_SOURCE edges."""
        required_tokens = [
            "RuntimeArtifact",
            "DetectorRun",
            "BrowseForgeConsumer",
            "FingerprintSurface",
            "KnowledgeSource",
            "Platform",
            "Manifest",
            "RUNS_DETECTOR",
            "TARGETS_PLATFORM",
            "DECLARES_SOURCE",
        ]

        for missing_token in ["Manifest", "DECLARES_SOURCE"]:
            with self.subTest(missing_token=missing_token):
                module = self._load_validate_module()
                with tempfile.TemporaryDirectory() as td:
                    temp_root = Path(td)
                    self._write_minimal_validate_tree(temp_root, module)
                    manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
                    self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
                    query_text = " ".join(token for token in required_tokens if token != missing_token)
                    for query_path in [
                        temp_root / "graph" / "queries" / "development-readiness.cypher",
                        temp_root / "graph" / "queries" / "fingerprint-risk.cypher",
                        temp_root / "graph" / "queries" / "cross-repo-impact.cypher",
                        temp_root / "graph" / "queries" / "source-coverage.cypher",
                    ]:
                        query_path.write_text(query_text, encoding="utf-8")

                    message = self._run_validate_expect_exit(module, temp_root)

                self.assertEqual(f"graph queries missing {missing_token}", message)


    def test_validate_rejects_runtime_graph_missing_required_manifest_source_node(self) -> None:
        """A gate/source manifest cannot disappear from the KG as an orphan DECLARES_SOURCE edge."""
        missing_source_path = "knowledge/manifests/proxy-preflight.json"
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            missing_node_id = self._manifest_node_id(missing_source_path)
            graph_records = [
                record
                for record in self._minimal_graph_with_packaged_runtime_artifacts(temp_root, manifest["artifacts"])
                if not (record.get("record_type") == "node" and record.get("id") == missing_node_id)
            ]
            self._write_runtime_graph_records(temp_root, graph_records)

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("generated kg", message)
        self.assertIn("manifest", message)
        self.assertIn(missing_source_path, message)
        self.assertIn("node", message)

    def test_validate_rejects_runtime_graph_missing_required_manifest_source_edge(self) -> None:
        """A Manifest node must explicitly DECLARES_SOURCE back to the runtime provider."""
        missing_source_path = "knowledge/manifests/signing-policy.json"
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            missing_node_id = self._manifest_node_id(missing_source_path)
            graph_records = [
                record
                for record in self._minimal_graph_with_packaged_runtime_artifacts(temp_root, manifest["artifacts"])
                if not (
                    record.get("record_type") == "edge"
                    and record.get("label") == "DECLARES_SOURCE"
                    and record.get("from") == missing_node_id
                    and record.get("to") == "RuntimeProvider:browseforge-chromium"
                )
            ]
            self._write_runtime_graph_records(temp_root, graph_records)

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("generated kg", message)
        self.assertIn("manifest", message)
        self.assertIn(missing_source_path, message)
        self.assertIn("declare", message)

    def test_validate_rejects_runtime_graph_release_gate_node_drift_from_manifest(self) -> None:
        """Generated KG ReleaseGate status/evidence cannot drift from authoritative release-gates.json."""
        cases: list[tuple[str, str]] = [
            ("status", "blocked"),
            ("evidence", "stale fixture cites sha256 0000 and size 1 bytes"),
        ]
        for field, stale_value in cases:
            with self.subTest(field=field):
                module = self._load_validate_module()
                with tempfile.TemporaryDirectory() as td:
                    temp_root = Path(td)
                    self._write_minimal_validate_tree(temp_root, module)
                    manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
                    self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
                    self._rewrite_runtime_graph_release_gate_property(
                        temp_root,
                        gate_id="runtime-artifact-produced",
                        field=field,
                        value=stale_value,
                    )

                    message = self._run_validate_expect_exit(module, temp_root).lower()

                self.assertIn("generated kg releasegate", message)
                self.assertIn("runtime-artifact-produced", message)
                self.assertIn(field, message)
                self.assertIn("drifted", message)

    def test_validate_rejects_passed_release_gate_artifact_evidence_with_stale_sha_and_size(self) -> None:
        """A passed artifact release gate cannot keep old archive sha/size text after runtime-artifacts changes."""
        stale_sha = "1a991ac31efee72a2f93c688619644e97b52b5e4d8732eb30014fa0265ffd93a"
        stale_size_bytes = 567798165
        for gate_id in ["runtime-artifact-produced", "sbom-provenance-release-assets"]:
            with self.subTest(gate_id=gate_id):
                module = self._load_validate_module()
                with tempfile.TemporaryDirectory() as td:
                    temp_root = Path(td)
                    self._write_minimal_validate_tree(temp_root, module)
                    manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
                    artifact = manifest["artifacts"][0]
                    self.assertNotEqual(stale_sha, artifact["sha256"])
                    self.assertNotEqual(stale_size_bytes, artifact["size_bytes"])
                    self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
                    self._write_release_gates(temp_root, live_detector_status="warning")
                    self._rewrite_release_gate_artifact_evidence(
                        temp_root,
                        gate_id=gate_id,
                        sha256=stale_sha,
                        size_bytes=stale_size_bytes,
                    )

                    message = self._run_validate_expect_exit(module, temp_root).lower()

                self.assertIn("release gate", message)
                self.assertIn(gate_id, message)
                self.assertIn("stale", message)
                self.assertIn("metadata", message)

    def test_validate_rejects_source_acquisition_with_stale_packaged_artifact_metadata(self) -> None:
        """source-acquisition.json cannot retain stale archive or packaged binary hashes."""
        cases: list[tuple[str, str | int]] = [
            ("archive_sha256", "0" * 64),
            ("archive_size_bytes", 1),
            ("browser_binary_sha256", "1" * 64),
            ("wrapper_binary_sha256", "2" * 64),
        ]
        for field, stale_value in cases:
            with self.subTest(field=field):
                module = self._load_validate_module()
                with tempfile.TemporaryDirectory() as td:
                    temp_root = Path(td)
                    self._write_minimal_validate_tree(temp_root, module)
                    manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
                    self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
                    source_acquisition_path = temp_root / "knowledge" / "manifests" / "source-acquisition.json"
                    source_acquisition = json.loads(source_acquisition_path.read_text(encoding="utf-8"))
                    linux_artifact = source_acquisition["chromium_base"]["linux_x64_artifact"]
                    linux_artifact[field] = stale_value
                    self._write_json(source_acquisition_path, source_acquisition)

                    message = self._run_validate_expect_exit(module, temp_root).lower()

                self.assertRegex(message, r"source[- ]acquisition", message)
                self.assertIn(field, message)
                self.assertIn("drift", message)

    def test_validate_rejects_source_acquisition_with_native_build_automation_drift(self) -> None:
        """macOS/Windows native build automation must stay pinned to the packager contract."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
            source_acquisition_path = temp_root / "knowledge" / "manifests" / "source-acquisition.json"
            source_acquisition = json.loads(source_acquisition_path.read_text(encoding="utf-8"))
            source_acquisition["chromium_base"]["native_build_automation"]["platforms"]["macos-arm64"][
                "gn_args"
            ] = 'target_os="mac" target_cpu="x64" is_debug=false'
            self._write_json(source_acquisition_path, source_acquisition)

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertRegex(message, r"source[- ]acquisition", message)
        self.assertIn("native_build_automation", message)
        self.assertIn("macos-arm64", message)
        self.assertIn("gn_args", message)
        self.assertIn("drifted", message)

    def test_validate_rejects_source_acquisition_with_linux_build_output_drift(self) -> None:
        """A packaged linux-x64 artifact requires source-acquisition build output gates to stay true."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
            source_acquisition_path = temp_root / "knowledge" / "manifests" / "source-acquisition.json"
            source_acquisition = json.loads(source_acquisition_path.read_text(encoding="utf-8"))
            source_acquisition["chromium_base"]["build_output_status"]["linux_docker_chrome_exists"] = False
            self._write_json(source_acquisition_path, source_acquisition)

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertRegex(message, r"source[- ]acquisition", message)
        self.assertIn("build_output_status", message)
        self.assertIn("linux_docker_chrome_exists", message)

    def test_validate_rejects_source_acquisition_with_linux_runtime_sidecar_status_drift(self) -> None:
        """A packaged linux-x64 artifact requires the recorded runtime sidecar gate to stay present and true."""
        sidecar_key = "linux_docker_runtime_sidecars_exist"
        cases: tuple[tuple[str, object], ...] = (
            ("false", False),
            ("non_boolean", "true"),
            ("missing", None),
        )
        for case_name, value in cases:
            with self.subTest(case=case_name):
                module = self._load_validate_module()
                with tempfile.TemporaryDirectory() as td:
                    temp_root = Path(td)
                    self._write_minimal_validate_tree(temp_root, module)
                    manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
                    self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
                    source_acquisition_path = temp_root / "knowledge" / "manifests" / "source-acquisition.json"
                    source_acquisition = json.loads(source_acquisition_path.read_text(encoding="utf-8"))
                    status = source_acquisition["chromium_base"]["build_output_status"]
                    if case_name == "missing":
                        status.pop(sidecar_key)
                    else:
                        status[sidecar_key] = value
                    self._write_json(source_acquisition_path, source_acquisition)

                    message = self._run_validate_expect_exit(module, temp_root).lower()

                self.assertRegex(message, r"source[- ]acquisition", message)
                self.assertIn("build_output_status", message)
                self.assertIn(sidecar_key, message)


    def test_validate_rejects_source_acquisition_without_dependency_profile_contract(self) -> None:
        """source-acquisition.json must document the active Chromium dependency profile and Darwin sync contract."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
            source_acquisition_path = temp_root / "knowledge" / "manifests" / "source-acquisition.json"
            source_acquisition = json.loads(source_acquisition_path.read_text(encoding="utf-8"))
            source_acquisition["chromium_base"]["dependency_profile_status"][
                "source_sync_command_uses_host_deps"
            ] = "gclient sync --with_branch_heads --with_tags"
            self._write_json(source_acquisition_path, source_acquisition)

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertRegex(message, r"source[- ]acquisition", message)
        self.assertIn("dependency_profile_status", message)
        self.assertIn("--deps=mac", message)

    def test_validate_rejects_source_acquisition_without_profile_isolated_workdirs(self) -> None:
        """source-acquisition.json must gate host and Linux Docker profile-specific checkout paths."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
            source_acquisition_path = temp_root / "knowledge" / "manifests" / "source-acquisition.json"
            source_acquisition = json.loads(source_acquisition_path.read_text(encoding="utf-8"))
            source_acquisition["chromium_base"]["dependency_profile_status"].pop("profile_isolated_workdir_contract")
            self._write_json(source_acquisition_path, source_acquisition)

            message = self._run_validate_expect_exit(module, temp_root)

        self.assertRegex(message, r"source[- ]acquisition", message)
        self.assertIn("profile_isolated_workdir_contract", message)
        self.assertIn("dependency_profile_status", message)

    def test_validate_rejects_graph_whose_only_runtime_artifact_is_missing(self) -> None:
        """scripts.validate.main must fail closed when no release-grade linux-x64 RuntimeArtifact exists."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            message = self._run_validate_expect_exit(module, temp_root)

        message = message.lower()
        self.assertRegex(message, r"artifact|linux-x64|release", message)


    def test_validate_rejects_passed_live_detector_gate_with_coverage_gaps(self) -> None:
        """A passed live-detector-evidence gate cannot coexist with uncovered detector matrix cells."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._write_release_gates(temp_root, live_detector_status="passed")
            self._write_detector_summary(temp_root, coverage_gaps=self._coverage_gaps(1))

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertRegex(message, r"detector[- ]summary", message)
        self.assertIn("live-detector", message)

    def test_validate_rejects_detector_summary_coverage_gap_count_mismatch(self) -> None:
        """coverage_gap_count must describe the actual coverage_gaps list, not stale bookkeeping."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._write_detector_summary(temp_root, coverage_gap_count=2, coverage_gaps=self._coverage_gaps(1))

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("coverage_gap_count", message)
        self.assertIn("coverage_gaps", message)

    def test_validate_rejects_detector_summary_coverage_gaps_missing_stable_fields(self) -> None:
        """Every coverage gap must carry the stable matrix dimensions and evidence label release review depends on."""
        module = self._load_validate_module()
        stable_gap_fields = [
            "matrix_key",
            "platform",
            "detector_id",
            "display_mode",
            "network_mode",
            "container",
            "required_evidence",
        ]
        for missing_field in stable_gap_fields:
            with self.subTest(missing_field=missing_field):
                with tempfile.TemporaryDirectory() as td:
                    temp_root = Path(td)
                    self._write_minimal_validate_tree(temp_root, module)
                    coverage_gaps = self._coverage_gaps(1)
                    coverage_gaps[0].pop(missing_field)
                    self._write_detector_summary(temp_root, coverage_gaps=coverage_gaps)

                    message = self._run_validate_expect_exit(module, temp_root).lower()

                self.assertRegex(message, r"detector[- ]summary|coverage_gaps", message)
                self.assertIn(missing_field, message)

    def test_validate_rejects_detector_summary_coverage_gap_matrix_key_mismatch(self) -> None:
        """Coverage gap matrix_key must be derived from stable matrix dimensions."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            coverage_gaps = self._coverage_gaps(1)
            coverage_gaps[0]["matrix_key"] = "linux-x64:sannysoft:headed:proxy:host"
            self._write_detector_summary(temp_root, coverage_gaps=coverage_gaps)

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("detector summary", message)
        self.assertIn("matrix_key mismatch", message)

    def test_validate_rejects_detector_summary_row_missing_evidence_file(self) -> None:
        """Detector summary evidence rows must point at committed detector evidence files."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._write_json(
                temp_root / "detector-summary.json",
                {
                    "blocking_findings": [],
                    "coverage_gap_count": 0,
                    "coverage_gaps": [],
                    "evidence_count": 1,
                    "rows": [
                        {
                            "detector_id": "sannysoft",
                            "path": "detectors/evidence/missing-detector-evidence.json",
                            "platform": "linux-x64",
                            "status": "passed",
                        }
                    ],
                },
            )

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("detector summary", message)
        self.assertIn("missing evidence", message)

    def test_validate_rejects_passed_live_detector_gate_with_blocking_findings(self) -> None:
        """A passed live-detector-evidence gate cannot coexist with detector blocking findings."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._write_release_gates(temp_root, live_detector_status="passed")
            self._write_detector_summary(
                temp_root,
                coverage_gaps=[],
                blocking_findings=[{"finding_id": "canvas_mismatch", "severity": "blocking"}],
            )

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("live-detector", message)
        self.assertRegex(message, r"blocking[_ -]findings?", message)

    def test_validate_allows_warning_live_detector_gate_with_current_coverage_gaps(self) -> None:
        """The current warning gate posture with 13 gaps is coherent and reaches later artifact validation."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._write_release_gates(temp_root, live_detector_status="warning")
            self._write_detector_summary(temp_root, coverage_gaps=self._coverage_gaps(13))

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertRegex(message, r"artifact|linux-x64|release", message)
        self.assertNotRegex(message, r"detector[- ]summary|coverage_gap|live-detector", message)

    def test_validate_rejects_release_status_duplicate_blocker_ids(self) -> None:
        """Release-status blocker IDs must be unique so automation can address blockers deterministically."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._refresh_release_status(temp_root)
            payload = json.loads((temp_root / "knowledge" / "manifests" / "release-status.json").read_text(encoding="utf-8"))
            payload["blockers"].append(dict(payload["blockers"][0]))
            payload["blocker_count"] = len(payload["blockers"])

            original_root = module.ROOT
            try:
                module.ROOT = temp_root
                with self.assertRaises(SystemExit) as raised:
                    module.validate_release_status(payload)
            finally:
                module.ROOT = original_root

        self.assertIn("duplicate blocker_id", str(raised.exception))

    def test_validate_rejects_release_status_non_utc_generated_at(self) -> None:
        """Release-status timestamps must be stable whole-second UTC Z values."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._refresh_release_status(temp_root)
            payload = json.loads((temp_root / "knowledge" / "manifests" / "release-status.json").read_text(encoding="utf-8"))
            payload["generated_at"] = "2026-07-10T00:00:00+00:00"

            original_root = module.ROOT
            try:
                module.ROOT = temp_root
                with self.assertRaises(SystemExit) as raised:
                    module.validate_release_status(payload)
            finally:
                module.ROOT = original_root

        self.assertIn("generated_at", str(raised.exception))

    def test_validate_rejects_release_status_unsorted_blockers(self) -> None:
        """Release-status blockers must remain sorted for stable diffs and deterministic automation."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._refresh_release_status(temp_root)
            payload = json.loads((temp_root / "knowledge" / "manifests" / "release-status.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(payload["blockers"]), 2)
            payload["blockers"] = [payload["blockers"][1], payload["blockers"][0], *payload["blockers"][2:]]

            original_root = module.ROOT
            try:
                module.ROOT = temp_root
                with self.assertRaises(SystemExit) as raised:
                    module.validate_release_status(payload)
            finally:
                module.ROOT = original_root

        self.assertIn("sorted", str(raised.exception))


    def test_validate_accepts_safe_failed_proxy_preflight_manifest(self) -> None:
        """A failed proxy preflight is valid release metadata when it redacts proxy inputs and names missing env prerequisites."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])

            output = self._run_validate_expect_success(module, temp_root)

        self.assertIn("runtime framework validation ok", output)

    def test_validate_rejects_proxy_preflight_manifest_with_raw_proxy_url_or_credentials(self) -> None:
        """Proxy preflight metadata is safe to commit only when raw proxy endpoints and credentials are absent."""
        module = self._load_validate_module()
        cases: list[tuple[str, dict[str, Any]]] = [
            ("raw_proxy_url", {"proxy": "http://proxy.example.test:8080"}),
            ("embedded_credentials", {"proxy": "http://user:secret@proxy.example.test:8080"}),
        ]
        for case_name, overrides in cases:
            with self.subTest(case=case_name):
                with tempfile.TemporaryDirectory() as td:
                    temp_root = Path(td)
                    self._write_minimal_validate_tree(temp_root, module)
                    manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
                    self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
                    self._write_proxy_preflight(temp_root, **overrides)

                    message = self._run_validate_expect_exit(module, temp_root).lower()

                self.assertIn("proxy", message)
                self.assertIn("preflight", message)

    def test_validate_rejects_ready_proxy_preflight_while_live_gate_or_proxy_gaps_block_release(self) -> None:
        """Proxy preflight cannot claim readiness before the live detector gate and proxy coverage have cleared."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
            self._write_release_gates(temp_root, live_detector_status="warning")
            proxy_gaps = [gap for gap in self._coverage_gaps(2) if gap["network_mode"] == "proxy"]
            self.assertTrue(proxy_gaps)
            self._write_detector_summary(temp_root, coverage_gaps=proxy_gaps)
            self._write_proxy_preflight(
                temp_root,
                ready=True,
                status="passed",
                missing=[],
                proxy="redacted",
                proxy_region_redacted="region-redacted",
            )

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("proxy", message)
        self.assertIn("preflight", message)
        self.assertIn("ready", message)
        self.assertRegex(message, r"live[- ]detector|coverage")

    def test_validate_rejects_evidence_schema_missing_committed_contract_values(self) -> None:
        """The release validation gate keeps the evidence schema aligned with committed harness/matrix shapes."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            schema_path = temp_root / "detectors" / "evidence-schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["properties"]["matrix"]["properties"]["display_mode"]["enum"].remove("headed_xvfb")
            self._write_json(schema_path, schema)

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("evidence schema", message)
        self.assertIn("matrix.display_mode", message)
        self.assertIn("headed_xvfb", message)

    def test_validate_rejects_committed_detector_evidence_value_not_admitted_by_schema(self) -> None:
        """Committed detector evidence cannot drift beyond the schema enum/property contract."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._write_detector_evidence(
                temp_root / "detectors" / "evidence" / "v0.1.0-alpha.0" / "linux-x64" / "sannysoft" / "bad-proxy.json",
                matrix={"display_mode": "headed", "network_mode": "direct", "proxy": "unlisted-proxy"},
                storage={"evidence_path": "detectors/evidence/bad-proxy.json", "sha256": "fixture"},
            )

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("detector evidence", message)
        self.assertIn("matrix.proxy", message)
        self.assertIn("not admitted", message)

    def test_validate_rejects_release_grade_surface_status_with_blockers(self) -> None:
        """Surface status cannot claim release-grade while any fingerprint surface remains a blocker."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._write_surface_status(temp_root, release_grade=True, release_blocker=True)

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("fingerprint surface", message)
        self.assertIn("release_grade", message)
        self.assertIn("blockers", message)

    def test_validate_rejects_passed_live_detector_gate_with_surface_blockers(self) -> None:
        """A passed live-detector-evidence gate cannot coexist with release-blocking fingerprint surfaces."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._write_release_gates(temp_root, live_detector_status="passed")
            self._write_surface_status(temp_root, release_grade=False, release_blocker=True)

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("live-detector", message)
        self.assertIn("fingerprint surfaces", message)
        self.assertIn("block release", message)

    def test_validate_rejects_passed_live_detector_gate_with_score_gaps(self) -> None:
        """A passed live-detector-evidence gate cannot coexist with detector score comparison blockers."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._write_release_gates(temp_root, live_detector_status="passed")
            self._write_surface_status(temp_root, release_grade=False, release_blocker=False)

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("live-detector", message)
        self.assertIn("score comparison", message)

    def test_validate_rejects_webgl_comparison_missing_extension_profile_field(self) -> None:
        """WebGL score comparison must expose the extension-profile parity decision explicitly."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            comparison = {
                "comparison_id": "webgl_metadata_cross_detector",
                "vendor_renderer_match": True,
                "extension_count_match": True,
                "hash_matches": {
                    "extensionSha256": True,
                    "parameterSha256": True,
                    "precisionSha256": True,
                    "pixelSha256": True,
                },
                "status": "pass",
            }
            self._write_score_comparison(temp_root, webgl_comparison=comparison, gaps=[])

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("webgl", message)
        self.assertIn("extension_profile_match", message)


    def test_validate_rejects_surface_status_missing_updated_source(self) -> None:
        """Surface status provenance must point at committed evidence sources."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            self._write_surface_status(temp_root, updated_from=["detectors/evidence/missing.json"])

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("fingerprint surface", message)
        self.assertIn("missing evidence source", message)

    def test_validate_rejects_surface_status_missing_evidence_ref(self) -> None:
        """Surface status summary evidence_refs must point at committed evidence files."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            surface_status_path = temp_root / "knowledge" / "manifests" / "fingerprint-surface-status.json"
            payload = json.loads(surface_status_path.read_text(encoding="utf-8"))
            payload["evidence_refs"] = ["detectors/evidence/missing-ref.json"]
            self._write_json(surface_status_path, payload)

            message = self._run_validate_expect_exit(module, temp_root).lower()

        self.assertIn("fingerprint surface", message)
        self.assertIn("missing evidence_ref", message)

    def test_validate_accepts_committed_browseforge_integration_contract(self) -> None:
        """The committed integration contract must be current enough for release validation."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            committed_contract = json.loads((ROOT / "contracts" / "browseforge-integration.contract.json").read_text(encoding="utf-8"))
            self._write_json(temp_root / "contracts" / "browseforge-integration.contract.json", committed_contract)
            manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
            self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])

            output = self._run_validate_expect_success(module, temp_root)

        self.assertIn("runtime framework validation ok", output)

    def test_validate_rejects_stale_browseforge_integration_release_blockers_after_evidence_gates_pass(self) -> None:
        """Passed release evidence gates make old missing-evidence BrowseForge blockers invalid."""
        module = self._load_validate_module()
        stale_blockers = [
            "no runtime graph index",
            "no detector baseline",
            "no Docker smoke evidence",
            "no Playwright bind evidence",
        ]
        for stale_blocker in stale_blockers:
            with self.subTest(stale_blocker=stale_blocker):
                with tempfile.TemporaryDirectory() as td:
                    temp_root = Path(td)
                    self._write_minimal_validate_tree(temp_root, module)
                    self._write_browseforge_integration_contract(temp_root, release_blockers=[stale_blocker])
                    manifest = self._load_temp_runtime_artifacts_manifest(temp_root)
                    self._write_runtime_graph_for_artifacts(temp_root, manifest["artifacts"])
                    self._write_release_gates(temp_root, live_detector_status="passed")
                    self._write_detector_summary(temp_root, coverage_gaps=[])
                    self._write_score_comparison(temp_root, baseline_gaps=[])

                    message = self._run_validate_expect_exit(module, temp_root).lower()

                self.assertIn("stale browseforge integration release blockers", message)
                self.assertIn(stale_blocker.lower(), message)



    def _refresh_release_status(self, temp_root: Path) -> None:
        spec = importlib.util.spec_from_file_location("release_status_for_validate_tests", RELEASE_STATUS_SCRIPT)
        self.assertIsNotNone(spec)
        release_status_module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(release_status_module)
        payload = release_status_module.release_status(temp_root, "2026-07-10T00:00:00Z")
        self._write_json(temp_root / "knowledge" / "manifests" / "release-status.json", payload)

    def _refresh_objective_audit(self, temp_root: Path) -> None:
        spec = importlib.util.spec_from_file_location("objective_audit_for_validate_tests", OBJECTIVE_AUDIT_SCRIPT)
        self.assertIsNotNone(spec)
        objective_audit_module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(objective_audit_module)
        payload = objective_audit_module.objective_audit(temp_root, "2026-07-10T00:00:00Z")
        self._write_json(temp_root / "knowledge" / "manifests" / "objective-audit.json", payload)



    def _run_validate_expect_success(self, module: Any, temp_root: Path) -> str:
        original_root = module.ROOT
        output = io.StringIO()
        self._refresh_release_status(temp_root)
        self._refresh_objective_audit(temp_root)
        try:
            module.ROOT = temp_root
            with contextlib.redirect_stdout(output):
                result = module.main()
        finally:
            module.ROOT = original_root
        self.assertIsNone(result)
        return output.getvalue()

    def _run_validate_expect_exit(self, module: Any, temp_root: Path) -> str:
        original_root = module.ROOT
        self._refresh_release_status(temp_root)
        self._refresh_objective_audit(temp_root)
        try:
            module.ROOT = temp_root
            with self.assertRaises(SystemExit) as raised:
                module.main()
        finally:
            module.ROOT = original_root
        return str(raised.exception)

    def _platform_matrix_platforms(self) -> list[dict[str, Any]]:
        return [
            {
                "evidence": {
                    "artifact": "dist/browseforge-runtime-chromium-v0.1.0-alpha.0-linux-x64.zip",
                    "artifact_manifest": "dist/browseforge-runtime-chromium-v0.1.0-alpha.0-linux-x64.zip:browseforge-runtime-chromium-v0.1.0-alpha.0-linux-x64/artifact-manifest.json",
                    "detector_summary": "detector-summary.json",
                    "runtime_artifacts_manifest": "knowledge/manifests/runtime-artifacts.json",
                },
                "id": "linux-x64",
                "priority": 1,
                "required_evidence": [
                    "build succeeds",
                    "artifact checksum exists",
                    "Docker seed installs runtime",
                    "BrowseForge launches profile",
                    "REST smoke passes",
                    "MCP smoke passes",
                    "Playwright bind smoke passes",
                    "detector run exists",
                ],
                "status": "packaged_detector_tested",
            },
            {
                "id": "macos-arm64",
                "priority": 2,
                "required_evidence": [
                    "build succeeds",
                    "artifact checksum exists",
                    "app bundle layout packaged",
                    "codesign/notarization decision exists",
                    "BrowseForge launches profile",
                    "detector run exists",
                ],
                "status": "packager_contract_defined",
            },
            {
                "id": "macos-x64",
                "priority": 3,
                "required_evidence": [
                    "build succeeds",
                    "artifact checksum exists",
                    "BrowseForge launches profile",
                    "detector run exists",
                ],
                "status": "planned",
            },
            {
                "id": "windows-x64",
                "priority": 4,
                "required_evidence": [
                    "build succeeds",
                    "artifact checksum exists",
                    "portable executable/DLL layout packaged",
                    "code signing decision exists",
                    "BrowseForge launches profile",
                    "detector run exists",
                ],
                "status": "packager_contract_defined",
            },
            {
                "id": "linux-arm64",
                "priority": 5,
                "required_evidence": [
                    "Docker/KasmVNC runtime validation",
                    "browser engine support confirmed",
                    "detector run exists",
                ],
                "status": "deferred",
            },
        ]

    def _platform_node_properties(self, platform: dict[str, Any]) -> dict[str, Any]:
        properties: dict[str, Any] = {
            "id": platform["id"],
            "key": platform["id"],
            "priority": platform["priority"],
            "required_evidence": list(platform["required_evidence"]),
            "status": platform["status"],
        }
        if "evidence" in platform:
            properties["evidence"] = dict(platform["evidence"])
        return properties

    def _write_minimal_validate_tree(self, root: Path, module: Any) -> None:
        for directory in module.REQUIRED_DIRS:
            (root / directory).mkdir(parents=True, exist_ok=True)
        for required_file in module.REQUIRED_FILES:
            path = root / required_file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("placeholder\n", encoding="utf-8")

        self._write_json(
            root / "contracts" / "runtime.manifest.json",
            {
                "id": "browseforge-chromium",
                "family": "chromium",
                "browseforge": {"profile_field": "runtime_id"},
                "fingerprint": {"surfaces": list(self.REQUIRED_GRAPH_FINGERPRINT_SURFACE_IDS)},
            },
        )
        self._write_browseforge_integration_contract(
            root,
            release_blockers=[
                "external proxy exit-IP/geolocation detector evidence is missing",
                "macOS native BrowseForge Chromium release artifact is missing",
                "Windows native BrowseForge Chromium release artifact is missing",
                "native headed WebGL/audio/font/cross-platform detector matrix remains incomplete",
                "runtime release_grade must remain false until supported platform artifacts and live detector gates pass",
            ],
        )

        self._write_json(
            root / "knowledge" / "kb-manifest.json",
            {
                "sources": [
                    {"source_id": source_id}
                    for source_id in [
                        "runtime-repo-contracts",
                        "runtime-repo-docs",
                        "runtime-repo-detectors",
                        "runtime-repo-graph",
                        "browseforge-consumer-contract",
                        "cloakbrowser-reference",
                        "camoufox-reference",
                        "chromium-upstream",
                    ]
                ]
            },
        )
        self._write_json(
            root / "knowledge" / "manifests" / "detectors.json",
            {
                "detectors": [
                    {
                        "detector_id": detector_id,
                        "required": True,
                        "matrix": {"display_modes": [], "network_modes": [], "container_modes": []},
                        "canonical_surfaces": ["automation_signals"],
                    }
                    for detector_id in ["sannysoft", "browserleaks", "creepjs", "pixelscan", "iphey", "browserscan"]
                ]
            },
        )
        self._write_json(
            root / "detectors" / "evidence-schema.json",
            {
                "properties": {
                    "schema_version": {"const": "1.1"},
                    "harness": {
                        "properties": {
                            "name": {"enum": ["browseforge-detector-harness", "browseforge-detector-harness + local-connect-proxy"]},
                            "mode": {"enum": ["manual_ingest", "synthetic_fixture", "live_collect", "live_collect_local_proxy"]},
                        }
                    },
                    "matrix": {
                        "properties": {
                            "display_mode": {"enum": ["headed", "headed_xvfb", "headless", "unknown"]},
                            "network_mode": {"enum": ["direct", "proxy", "local_proxy", "unknown"]},
                            "proxy": {"enum": ["none", "redacted", "public_test_infra", "local-connect-observer"]},
                        }
                    },
                    "storage": {
                        "properties": {
                            "evidence_path": {},
                            "sha256": {},
                            "raw_capture_path": {},
                            "raw_capture_sha256": {},
                            "proxy_summary_sha256": {},
                            "text_sha256": {},
                            "summary_path": {},
                        }
                    },
                },
                "required": ["run_id", "evidence_id", "artifact_id", "matrix", "status", "failure_mode", "storage", "kg"],
            },
        )
        self._write_json(
            root / "knowledge" / "manifests" / "reference-sources.json",
            {
                "source_classes": [
                    {"id": source_id}
                    for source_id in [
                        "browseforge-consumer",
                        "cloakbrowser-reference",
                        "camoufox-reference",
                        "chromium-upstream",
                        "detector-evidence",
                    ]
                ]
            },
        )
        self._write_json(
            root / "knowledge" / "manifests" / "patchset.json",
            {"base_version": "150.0.7871.101", "base_ref": "refs/tags/150.0.7871.101", "patchsets": [{"patchset_id": "baseline"}]},
        )
        self._write_json(
            root / "knowledge" / "manifests" / "platform-matrix.json",
            {"platforms": self._platform_matrix_platforms()},
        )
        self._write_surface_status(root)
        self._write_score_comparison(root)
        self._write_proxy_preflight(root)
        self._write_json(
            root / "knowledge" / "manifests" / "runtime-artifacts.json",
            {
                "artifact_sha256": "",
                "artifact_size_bytes": 0,
                "artifacts": [
                    {
                        "artifact_id": LINUX_ARTIFACT_ID,
                        "runtime_id": "browseforge-chromium",
                        "runtime_version": "v0.1.0-alpha.0",
                        "platform": "linux-x64",
                        "os": "linux",
                        "arch": "x64",
                        "browser_version": "150.0.7871.101",
                        "source_ref": "51b83660c3609f271ccbbd65785bf7e50a21312d",
                        "patchset_id": "baseline",
                        "wrapper_version": "v0.1.0-alpha.0",
                        "download_url": "test://browseforge-runtime-chromium-v0.1.0-alpha.0-linux-x64",
                        "sha256": "",
                        "size_bytes": 0,
                        "signature": "unsigned-test-artifact",
                        "sbom_path": "dist/stage/browseforge-runtime-chromium-v0.1.0-alpha.0-linux-x64/SBOM.json",
                        "provenance_path": "dist/stage/browseforge-runtime-chromium-v0.1.0-alpha.0-linux-x64/provenance.json",
                        "release_channel": "alpha",
                        "browseforge_compatibility": {"min_version": "v2.0.0", "profile_field": "runtime_id"},
                        "created_at": "2026-07-09T00:00:00+00:00",
                    }
                ],
                "browser_binary_sha256": "",
                "required_artifact_fields": [
                    "artifact_id",
                    "runtime_id",
                    "runtime_version",
                    "platform",
                    "os",
                    "arch",
                    "browser_version",
                    "source_ref",
                    "patchset_id",
                    "wrapper_version",
                    "download_url",
                    "sha256",
                    "size_bytes",
                    "signature",
                    "sbom_path",
                    "provenance_path",
                    "release_channel",
                    "browseforge_compatibility",
                    "created_at",
                    "browser_binary_sha256",
                    "wrapper_binary_sha256",
                ],
                "runtime_id": "browseforge-chromium",
                "schema_version": "1.0",
                "supported_package_platforms": ["linux-x64", "macos-arm64", "windows-x64"],
                "unsupported_package_platforms": {
                    "linux-arm64": "missing Linux arm64 runtime asset contract",
                    "macos-x64": "missing macOS x64 runtime asset contract",
                },
                "wrapper_binary_sha256": "",
            },
        )
        self._write_current_runtime_artifact_fixture(root)
        self._write_signing_policy(root)
        self._write_native_artifact_preflight(root)

        self._write_release_gates(root, live_detector_status="warning")
        self._write_json(root / "browser" / "chromium-base.json", {})
        self._write_detector_summary(root, coverage_gaps=[])

        query_text = " ".join(
            [
                "RuntimeArtifact",
                "DetectorRun",
                "BrowseForgeConsumer",
                "FingerprintSurface",
                "KnowledgeSource",
                "Platform",
                "Manifest",
                "RUNS_DETECTOR",
                "TARGETS_PLATFORM",
                "DECLARES_SOURCE",
            ]
        )
        for query_path in [
            root / "graph" / "queries" / "development-readiness.cypher",
            root / "graph" / "queries" / "fingerprint-risk.cypher",
            root / "graph" / "queries" / "cross-repo-impact.cypher",
            root / "graph" / "queries" / "source-coverage.cypher",
        ]:
            query_path.write_text(query_text, encoding="utf-8")

        graph_records = self._minimal_graph_with_only_missing_runtime_artifact(root)
        with (root / "generated" / "kg" / "runtime.graph.jsonl").open("w", encoding="utf-8") as fh:
            for record in graph_records:
                fh.write(json.dumps(record, sort_keys=True) + "\n")

    def _minimal_graph_with_only_missing_runtime_artifact(self, root: Path) -> list[dict[str, Any]]:
        return [
            {"record_type": "node", "label": "RuntimeProvider", "id": "RuntimeProvider:browseforge-chromium", "properties": {}},
            {
                "record_type": "node",
                "label": "RuntimeArtifact",
                "id": "RuntimeArtifact:missing-runtime-artifact",
                "properties": {"artifact_id": "missing-runtime-artifact", "runtime_id": "browseforge-chromium", "status": "missing", "release_grade": False},
            },
            {"record_type": "node", "label": "BrowseForgeConsumer", "id": "BrowseForgeConsumer:browseforge-main", "properties": {}},
            *[
                {
                    "record_type": "node",
                    "label": "FingerprintSurface",
                    "id": f"FingerprintSurface:{surface_id}",
                    "properties": {"surface_id": surface_id},
                }
                for surface_id in self.REQUIRED_GRAPH_FINGERPRINT_SURFACE_IDS
            ],
            {"record_type": "node", "label": "Patch", "id": "Patch:baseline", "properties": {}},
            {"record_type": "node", "label": "SourceFile", "id": "SourceFile:main", "properties": {}},
            {"record_type": "node", "label": "Symbol", "id": "Symbol:main", "properties": {}},
            {"record_type": "node", "label": "Detector", "id": "Detector:sannysoft", "properties": {}},
            {"record_type": "node", "label": "DetectorRun", "id": "DetectorRun:planned-sannysoft", "properties": {"status": "planned_missing_artifact"}},
            {"record_type": "node", "label": "EvidenceArtifact", "id": "EvidenceArtifact:missing-sannysoft", "properties": {}},
            *[
                {"record_type": "node", "label": "Platform", "id": f"Platform:{platform['id']}", "properties": self._platform_node_properties(platform)}
                for platform in self._platform_matrix_platforms()
            ],
            {"record_type": "node", "label": "Capability", "id": "Capability:persistent_context", "properties": {}},
            *self._release_gate_graph_nodes(root),
            {"record_type": "node", "label": "KnowledgeSource", "id": "KnowledgeSource:chromium-upstream", "properties": {}},
            *self._runtime_graph_manifest_source_records(),
            {"record_type": "edge", "label": "REQUIRES_CAPABILITY", "from": "BrowseForgeConsumer:browseforge-main", "to": "Capability:persistent_context", "properties": {}},
            {"record_type": "edge", "label": "DECLARES_CAPABILITY", "from": "RuntimeProvider:browseforge-chromium", "to": "Capability:persistent_context", "properties": {}},
            {"record_type": "edge", "label": "BUILT_FOR", "from": "RuntimeArtifact:missing-runtime-artifact", "to": LINUX_PLATFORM_NODE_ID, "properties": {"status": "missing_artifact"}},
            {"record_type": "edge", "label": "TARGETS_PLATFORM", "from": "RuntimeArtifact:missing-runtime-artifact", "to": LINUX_PLATFORM_NODE_ID, "properties": {"status": "missing_artifact"}},
            {"record_type": "edge", "label": "GENERATED_FROM", "from": "RuntimeArtifact:missing-runtime-artifact", "to": "RuntimeProvider:browseforge-chromium", "properties": {}},
            {"record_type": "edge", "label": "MODIFIES_SOURCE", "from": "Patch:baseline", "to": "SourceFile:main", "properties": {}},
            {"record_type": "edge", "label": "MODIFIES_SOURCE", "from": "Patch:baseline", "to": "Symbol:main", "properties": {}},
            {"record_type": "edge", "label": "CONTROLS_SURFACE", "from": "Patch:baseline", "to": "FingerprintSurface:automation_signals", "properties": {}},
            {"record_type": "edge", "label": "CHECKS_SURFACE", "from": "Detector:sannysoft", "to": "FingerprintSurface:automation_signals", "properties": {}},
            {"record_type": "edge", "label": "RUNS_DETECTOR", "from": "DetectorRun:planned-sannysoft", "to": "Detector:sannysoft", "properties": {}},
            {"record_type": "edge", "label": "TARGETS_ARTIFACT", "from": "DetectorRun:planned-sannysoft", "to": "RuntimeArtifact:missing-runtime-artifact", "properties": {"status": "blocked_no_artifact"}},
            {"record_type": "edge", "label": "TESTS_ARTIFACT", "from": "DetectorRun:planned-sannysoft", "to": "RuntimeArtifact:missing-runtime-artifact", "properties": {"status": "blocked_no_artifact"}},
            {"record_type": "edge", "label": "PRODUCES_EVIDENCE", "from": "DetectorRun:planned-sannysoft", "to": "EvidenceArtifact:missing-sannysoft", "properties": {}},
            {"record_type": "edge", "label": "SUPPORTS_GATE", "from": "RuntimeProvider:browseforge-chromium", "to": "ReleaseGate:runtime-artifact-produced", "properties": {"status": "passed"}},
            {"record_type": "edge", "label": "REFERENCES_SOURCE", "from": "RuntimeProvider:browseforge-chromium", "to": "KnowledgeSource:chromium-upstream", "properties": {}},
        ]

    def _load_temp_runtime_artifacts_manifest(self, root: Path) -> dict[str, Any]:
        manifest_path = root / "knowledge" / "manifests" / "runtime-artifacts.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertIsInstance(manifest, dict)
        assert isinstance(manifest, dict)
        return manifest

    def _write_current_runtime_artifact_fixture(self, root: Path) -> None:
        manifest_path = root / "knowledge" / "manifests" / "runtime-artifacts.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact = manifest["artifacts"][0]
        artifact_id = artifact["artifact_id"]
        stage_rel = Path("dist") / "stage" / artifact_id
        stage = root / stage_rel
        stage.mkdir(parents=True, exist_ok=True)

        browser_path = stage / "chrome"
        wrapper_path = stage / "browseforge-runtime"
        runtime_manifest_path = stage / "runtime.manifest.json"
        browser_path.write_bytes(b"browseforge chromium browser binary fixture\n")
        wrapper_path.write_bytes(b"browseforge chromium wrapper binary fixture\n")
        self._write_json(
            runtime_manifest_path,
            {
                "browseforge": {"profile_field": "runtime_id"},
                "family": "chromium",
                "id": artifact["runtime_id"],
                "version": artifact["runtime_version"],
            },
        )

        browser_sha256 = self._sha256_file(browser_path)
        wrapper_sha256 = self._sha256_file(wrapper_path)
        runtime_manifest_sha256 = self._sha256_file(runtime_manifest_path)
        patchset_manifest_sha256 = self._sha256_file(root / "knowledge" / "manifests" / "patchset.json")
        artifact_manifest_rel = stage_rel / "artifact-manifest.json"
        sbom_rel = stage_rel / "SBOM.json"
        provenance_rel = stage_rel / "provenance.json"
        artifact_manifest = {
            **artifact,
            "browser_binary_sha256": browser_sha256,
            "files": [
                {"path": "browseforge-runtime", "sha256": wrapper_sha256, "size_bytes": wrapper_path.stat().st_size},
                {"path": "chrome", "sha256": browser_sha256, "size_bytes": browser_path.stat().st_size},
                {
                    "path": "runtime.manifest.json",
                    "sha256": runtime_manifest_sha256,
                    "size_bytes": runtime_manifest_path.stat().st_size,
                },
            ],
            "git_commit": "validation-test-fixture",
            "patchset_manifest_sha256": patchset_manifest_sha256,
            "runtime_manifest_sha256": runtime_manifest_sha256,
            "source_acquisition_sha256": None,
            "wrapper_binary_sha256": wrapper_sha256,
        }
        provenance = {
            "arch": artifact["arch"],
            "browser_binary_sha256": browser_sha256,
            "browser_version": artifact["browser_version"],
            "builder": "tests/test_validate.py",
            "created_at": artifact["created_at"],
            "git_commit": "validation-test-fixture",
            "os": artifact["os"],
            "patchset_id": artifact["patchset_id"],
            "patchset_manifest": "knowledge/manifests/patchset.json",
            "patchset_manifest_sha256": patchset_manifest_sha256,
            "platform": artifact["platform"],
            "release_channel": artifact["release_channel"],
            "runtime_id": artifact["runtime_id"],
            "runtime_manifest_sha256": runtime_manifest_sha256,
            "runtime_version": artifact["runtime_version"],
            "source_acquisition_manifest": "knowledge/manifests/source-acquisition.json",
            "source_acquisition_sha256": None,
            "source_ref": artifact["source_ref"],
            "wrapper_version": artifact["wrapper_version"],
            "wrapper_binary_sha256": wrapper_sha256,
        }
        self._write_json(root / artifact_manifest_rel, artifact_manifest)
        self._write_json(root / sbom_rel, {"SPDXID": "SPDXRef-DOCUMENT", "files": artifact_manifest["files"]})
        self._write_json(root / provenance_rel, provenance)

        archive_rel = Path("dist") / f"{artifact_id}.zip"
        archive_path = root / archive_rel
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(stage.rglob("*")):
                if file_path.is_file():
                    archive.write(file_path, arcname=f"{stage.name}/{file_path.relative_to(stage).as_posix()}")
        archive_sha256 = self._sha256_file(archive_path)
        archive_size_bytes = archive_path.stat().st_size
        (root / "dist" / "checksums.txt").write_text(f"{archive_sha256}  {archive_path.name}\n", encoding="utf-8")

        artifact.update(
            {
                "browser_binary_sha256": browser_sha256,
                "sha256": archive_sha256,
                "size_bytes": archive_size_bytes,
                "wrapper_binary_sha256": wrapper_sha256,
            }
        )
        manifest.update(
            {
                "artifact_sha256": archive_sha256,
                "artifact_size_bytes": archive_size_bytes,
                "browser_binary_sha256": browser_sha256,
                "wrapper_binary_sha256": wrapper_sha256,
            }
        )
        self._write_json(manifest_path, manifest)
        self._write_json(
            root / "knowledge" / "manifests" / "source-acquisition.json",
            {
                "chromium_base": {
                    "base_commit": artifact["source_ref"],
                    "base_ref": f"refs/tags/{artifact['browser_version']}",
                    "base_version": artifact["browser_version"],
                    "linux_x64_artifact": {
                        "archive": archive_rel.as_posix(),
                        "archive_sha256": archive_sha256,
                        "archive_size_bytes": archive_size_bytes,
                        "artifact_id": artifact_id,
                        "artifact_manifest": artifact_manifest_rel.as_posix(),
                        "artifact_manifest_sha256": self._sha256_file(root / artifact_manifest_rel),
                        "browser_binary_sha256": browser_sha256,
                        "patchset_manifest_sha256": patchset_manifest_sha256,
                        "provenance": provenance_rel.as_posix(),
                        "provenance_sha256": self._sha256_file(root / provenance_rel),
                        "runtime_manifest_sha256": runtime_manifest_sha256,
                        "sbom": sbom_rel.as_posix(),
                        "sbom_sha256": self._sha256_file(root / sbom_rel),
                        "stage_dir": stage_rel.as_posix(),
                        "status": "packaged",
                        "wrapper_binary_sha256": wrapper_sha256,
                    },
                    "build_output_status": {
                        "dev_build_ninja_exists": False,
                        "dev_gn_args_exists": False,
                        "linux_docker_build_ninja_exists": True,
                        "linux_docker_chrome_exists": True,
                        "linux_docker_gn_args_exists": True,
                        "linux_docker_runtime_sidecars_exist": True,
                    },
                    "dependency_profile_status": {
                        "current_checkout_profile": "linux_docker_deps",
                        "linux_gn_exists": True,
                        "mac_gn_exists": False,
                        "windows_gn_exists": False,
                        "source_sync_command_uses_host_deps": "python3 scripts/chromium_source.py acquire --execute --step sync-deps expands to gclient sync --with_branch_heads --with_tags --deps=mac on Darwin",
                        "profile_switching_note": "The shared external checkout is dependency-profile specific; Docker linux sync and Darwin mac sync must not be treated as simultaneously ready.",
                        "profile_isolated_workdir_contract": {
                            "host_source_env": "BROWSEFORGE_CHROMIUM_HOST_WORKDIR",
                            "linux_docker_source_env": "BROWSEFORGE_CHROMIUM_LINUX_WORKDIR",
                            "shared_fallback_env": "BROWSEFORGE_CHROMIUM_WORKDIR",
                            "source_helper_default": "scripts/chromium_source.py uses BROWSEFORGE_CHROMIUM_HOST_WORKDIR before BROWSEFORGE_CHROMIUM_WORKDIR.",
                            "native_helper_default": "scripts/chromium_native.py uses BROWSEFORGE_CHROMIUM_HOST_WORKDIR before BROWSEFORGE_CHROMIUM_WORKDIR.",
                            "docker_helper_default": "scripts/chromium_docker.py uses BROWSEFORGE_CHROMIUM_LINUX_WORKDIR before BROWSEFORGE_CHROMIUM_WORKDIR.",
                        },
                    },
                    "native_build_automation": self._native_build_automation_fixture(),
                    "source_checkout_status": "checked_out_pinned_ref",
                },
                "runtime_id": "browseforge-chromium",
                "schema_version": "1.0",
            },
        )

    def _native_build_automation_fixture(self) -> dict[str, Any]:
        return {
            "script": "scripts/chromium_native.py",
            "platforms": {
                "macos-arm64": {
                    "artifact_id": "browseforge-runtime-chromium-v0.1.0-alpha.0-macos-arm64",
                    "gn_args": 'target_os="mac" target_cpu="arm64" is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false',
                    "out_dir": "out/BrowseForgeMacArm64",
                    "output_binary": "out/BrowseForgeMacArm64/Chromium.app/Contents/MacOS/Chromium",
                    "required_host_os": "darwin",
                    "status": "preflight_ready_artifact_missing",
                },
                "windows-x64": {
                    "artifact_id": "browseforge-runtime-chromium-v0.1.0-alpha.0-windows-x64",
                    "gn_args": 'target_os="win" target_cpu="x64" is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false',
                    "out_dir": "out/BrowseForgeWindowsX64",
                    "output_binary": "out/BrowseForgeWindowsX64/chrome.exe",
                    "required_host_os": "windows",
                    "status": "preflight_ready_artifact_missing",
                },
            },
        }

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _release_gate_graph_nodes(self, root: Path) -> list[dict[str, Any]]:
        release_gates = json.loads((root / "knowledge" / "manifests" / "release-gates.json").read_text(encoding="utf-8"))
        return [
            {
                "record_type": "node",
                "label": "ReleaseGate",
                "id": f"ReleaseGate:{gate['gate_id']}",
                "properties": dict(gate),
            }
            for gate in release_gates["release_candidate_required_gates"]
        ]

    def _write_runtime_graph_records(self, root: Path, graph_records: list[dict[str, Any]]) -> None:
        graph_path = root / "generated" / "kg" / "runtime.graph.jsonl"
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        with graph_path.open("w", encoding="utf-8") as fh:
            for record in graph_records:
                fh.write(json.dumps(record, sort_keys=True) + "\n")

    def _sync_runtime_graph_release_gate_nodes(self, root: Path) -> None:
        graph_path = root / "generated" / "kg" / "runtime.graph.jsonl"
        if not graph_path.is_file():
            return
        if graph_path.read_text(encoding="utf-8") == "placeholder\n":
            return
        graph_records = [
            record
            for record in self._load_graph(graph_path)
            if not (record.get("record_type") == "node" and record.get("label") == "ReleaseGate")
        ]
        graph_records.extend(self._release_gate_graph_nodes(root))
        self._write_runtime_graph_records(root, graph_records)

    def _write_runtime_graph_for_artifacts(self, root: Path, artifacts: list[dict[str, Any]]) -> None:
        self._write_runtime_graph_records(root, self._minimal_graph_with_packaged_runtime_artifacts(root, artifacts))

    def _rewrite_runtime_graph_release_gate_property(self, root: Path, *, gate_id: str, field: str, value: Any) -> None:
        graph_path = root / "generated" / "kg" / "runtime.graph.jsonl"
        graph_records = self._load_graph(graph_path)
        node_id = f"ReleaseGate:{gate_id}"
        for record in graph_records:
            if record.get("record_type") == "node" and record.get("label") == "ReleaseGate" and record.get("id") == node_id:
                properties = record.get("properties")
                self.assertIsInstance(properties, dict)
                assert isinstance(properties, dict)
                properties[field] = value
                break
        else:
            self.fail(f"missing ReleaseGate node {node_id}")
        self._write_runtime_graph_records(root, graph_records)


    def _rewrite_platform_node_property(self, root: Path, platform_id: str, field: str, value: Any) -> None:
        graph_path = root / "generated" / "kg" / "runtime.graph.jsonl"
        graph_records = self._load_graph(graph_path)
        node_id = f"Platform:{platform_id}"
        for record in graph_records:
            if record.get("record_type") == "node" and record.get("label") == "Platform" and record.get("id") == node_id:
                properties = record.get("properties")
                self.assertIsInstance(properties, dict)
                assert isinstance(properties, dict)
                properties[field] = value
                break
        else:
            self.fail(f"missing Platform node {node_id}")
        with graph_path.open("w", encoding="utf-8") as fh:
            for record in graph_records:
                fh.write(json.dumps(record, sort_keys=True) + "\n")

    def _minimal_graph_with_packaged_runtime_artifacts(self, root: Path, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        first_artifact_id = artifacts[0]["artifact_id"]
        records: list[dict[str, Any]] = [
            {"record_type": "node", "label": "RuntimeProvider", "id": "RuntimeProvider:browseforge-chromium", "properties": {}},
            {"record_type": "node", "label": "BrowseForgeConsumer", "id": "BrowseForgeConsumer:browseforge-main", "properties": {}},
            *[
                {
                    "record_type": "node",
                    "label": "FingerprintSurface",
                    "id": f"FingerprintSurface:{surface_id}",
                    "properties": {"surface_id": surface_id},
                }
                for surface_id in self.REQUIRED_GRAPH_FINGERPRINT_SURFACE_IDS
            ],
            {"record_type": "node", "label": "Patch", "id": "Patch:baseline", "properties": {}},
            {"record_type": "node", "label": "SourceFile", "id": "SourceFile:main", "properties": {}},
            {"record_type": "node", "label": "Symbol", "id": "Symbol:main", "properties": {}},
            {"record_type": "node", "label": "Detector", "id": "Detector:sannysoft", "properties": {}},
            {"record_type": "node", "label": "DetectorRun", "id": "DetectorRun:planned-sannysoft", "properties": {"status": "planned"}},
            {"record_type": "node", "label": "EvidenceArtifact", "id": "EvidenceArtifact:planned-sannysoft", "properties": {}},
            {"record_type": "node", "label": "Capability", "id": "Capability:persistent_context", "properties": {}},
            *self._release_gate_graph_nodes(root),
            {"record_type": "node", "label": "KnowledgeSource", "id": "KnowledgeSource:chromium-upstream", "properties": {}},
            *self._runtime_graph_manifest_source_records(),
            *[
                {"record_type": "node", "label": "Platform", "id": f"Platform:{platform['id']}", "properties": self._platform_node_properties(platform)}
                for platform in self._platform_matrix_platforms()
            ],
        ]
        for artifact in artifacts:
            platform = artifact["platform"]
            node_id = f"RuntimeArtifact:{artifact['artifact_id']}"
            records.extend(
                [
                    {
                        "record_type": "node",
                        "label": "RuntimeArtifact",
                        "id": node_id,
                        "properties": {**artifact, "status": "packaged", "release_grade": True},
                    },
                    {"record_type": "edge", "label": "BUILT_FOR", "from": node_id, "to": f"Platform:{platform}", "properties": {}},
                    {"record_type": "edge", "label": "TARGETS_PLATFORM", "from": node_id, "to": f"Platform:{platform}", "properties": {}},
                    {"record_type": "edge", "label": "GENERATED_FROM", "from": node_id, "to": "RuntimeProvider:browseforge-chromium", "properties": {}},
                ]
            )
        records.extend(
            [
                {"record_type": "edge", "label": "REQUIRES_CAPABILITY", "from": "BrowseForgeConsumer:browseforge-main", "to": "Capability:persistent_context", "properties": {}},
                {"record_type": "edge", "label": "DECLARES_CAPABILITY", "from": "RuntimeProvider:browseforge-chromium", "to": "Capability:persistent_context", "properties": {}},
                {"record_type": "edge", "label": "MODIFIES_SOURCE", "from": "Patch:baseline", "to": "SourceFile:main", "properties": {}},
                {"record_type": "edge", "label": "MODIFIES_SOURCE", "from": "Patch:baseline", "to": "Symbol:main", "properties": {}},
                {"record_type": "edge", "label": "CONTROLS_SURFACE", "from": "Patch:baseline", "to": "FingerprintSurface:automation_signals", "properties": {}},
                {"record_type": "edge", "label": "CHECKS_SURFACE", "from": "Detector:sannysoft", "to": "FingerprintSurface:automation_signals", "properties": {}},
                {"record_type": "edge", "label": "RUNS_DETECTOR", "from": "DetectorRun:planned-sannysoft", "to": "Detector:sannysoft", "properties": {}},
                {"record_type": "edge", "label": "TARGETS_ARTIFACT", "from": "DetectorRun:planned-sannysoft", "to": f"RuntimeArtifact:{first_artifact_id}", "properties": {}},
                {"record_type": "edge", "label": "TESTS_ARTIFACT", "from": "DetectorRun:planned-sannysoft", "to": f"RuntimeArtifact:{first_artifact_id}", "properties": {}},
                {"record_type": "edge", "label": "PRODUCES_EVIDENCE", "from": "DetectorRun:planned-sannysoft", "to": "EvidenceArtifact:planned-sannysoft", "properties": {}},
                {"record_type": "edge", "label": "SUPPORTS_GATE", "from": "RuntimeProvider:browseforge-chromium", "to": "ReleaseGate:runtime-artifact-produced", "properties": {"status": "passed"}},
                {"record_type": "edge", "label": "REFERENCES_SOURCE", "from": "RuntimeProvider:browseforge-chromium", "to": "KnowledgeSource:chromium-upstream", "properties": {}},
            ]
        )
        return records

    def _write_score_comparison(
        self,
        root: Path,
        *,
        webgl_comparison: dict[str, Any] | None = None,
        gaps: list[dict[str, Any]] | None = None,
        baseline_gaps: list[dict[str, Any]] | None = None,
    ) -> None:
        if webgl_comparison is None:
            webgl_comparison = {
                "comparison_id": "webgl_metadata_cross_detector",
                "extension_count_match": True,
                "extension_profile_match": True,
                "hash_matches": {
                    "extensionSha256": True,
                    "parameterSha256": True,
                    "precisionSha256": True,
                    "pixelSha256": True,
                },
                "status": "pass",
                "vendor_renderer_match": True,
            }
        if baseline_gaps is None:
            baseline_gaps = [
                {"gap_id": "native_headed_font_corpus_parity_missing"},
            ]
        self._write_json(
            root / "knowledge" / "manifests" / "detector-score-comparison.json",
            {
                "runtime_id": "browseforge-chromium",
                "release_grade": False,
                "comparisons": [
                    {"comparison_id": "creepjs_audio_headless_vs_headed"},
                    {"comparison_id": "browserleaks_creepjs_font_metrics"},
                    webgl_comparison,
                ],
                "baseline_gaps": baseline_gaps,
                "gaps": [] if gaps is None else gaps,
            },
        )

    def _write_release_gates(self, root: Path, *, live_detector_status: str) -> None:
        artifact_evidence = self._current_artifact_release_gate_evidence(root)
        gates: list[dict[str, Any]] = []
        for gate_id in [
            "chromium-base-selected",
            "wrapper-contract-tests",
            "detector-harness-contract-tests",
            "packaging-contract-tests",
            "chromium-source-indexed",
            "runtime-artifact-produced",
            "browseforge-adapter-merged",
            "live-detector-evidence",
            "sbom-provenance-release-assets",
        ]:
            gate = {
                "gate_id": gate_id,
                "status": live_detector_status if gate_id == "live-detector-evidence" else "passed",
            }
            if artifact_evidence is not None and gate_id in {"runtime-artifact-produced", "sbom-provenance-release-assets"}:
                gate["evidence"] = artifact_evidence
            gates.append(gate)
        self._write_json(
            root / "knowledge" / "manifests" / "release-gates.json",
            {"release_candidate_required_gates": gates},
        )
        self._sync_runtime_graph_release_gate_nodes(root)

    def _current_artifact_release_gate_evidence(self, root: Path) -> str | None:
        manifest_path = root / "knowledge" / "manifests" / "runtime-artifacts.json"
        if not manifest_path.is_file():
            return None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = manifest.get("artifacts") or []
        if not artifacts:
            return None
        artifact = artifacts[0]
        artifact_sha256 = artifact.get("sha256")
        artifact_size_bytes = artifact.get("size_bytes")
        if not artifact_sha256 or not artifact_size_bytes:
            return None
        return (
            f"{artifact['artifact_id']} packaged archive {Path('dist') / (artifact['artifact_id'] + '.zip')} "
            f"has sha256 {artifact_sha256} and size {artifact_size_bytes} bytes; "
            f"runtime-artifacts.json records sha256 {artifact_sha256} and size_bytes {artifact_size_bytes}."
        )

    def _rewrite_release_gate_artifact_evidence(self, root: Path, *, gate_id: str, sha256: str, size_bytes: int) -> None:
        release_gates_path = root / "knowledge" / "manifests" / "release-gates.json"
        release_gates = json.loads(release_gates_path.read_text(encoding="utf-8"))
        stale_evidence = (
            f"stale fixture says dist/browseforge-runtime-chromium-v0.1.0-alpha.0-linux-x64.zip "
            f"has sha256 {sha256} and size {size_bytes} bytes."
        )
        for gate in release_gates["release_candidate_required_gates"]:
            if gate["gate_id"] == gate_id:
                gate["evidence"] = stale_evidence
                break
        else:
            self.fail(f"missing release gate {gate_id}")
        self._write_json(release_gates_path, release_gates)
        self._sync_runtime_graph_release_gate_nodes(root)

    def _write_proxy_preflight(
        self,
        root: Path,
        *,
        ready: bool = False,
        status: str = "failed",
        missing: list[str] | None = None,
        errors: list[str] | None = None,
        proxy: object | None = None,
        proxy_region_redacted: str | None = None,
        requirements: list[dict[str, str]] | None = None,
    ) -> None:
        if missing is None:
            missing = ["BROWSEFORGE_DETECTOR_PROXY_URL", "BROWSEFORGE_DETECTOR_PROXY_REGION"]
        if errors is None:
            errors = []
        if requirements is None:
            requirements = [
                {
                    "name": name,
                    "source": "env",
                    "status": "missing" if name in missing else "configured",
                }
                for name in ["BROWSEFORGE_DETECTOR_PROXY_URL", "BROWSEFORGE_DETECTOR_PROXY_REGION"]
            ]
        self._write_json(
            root / "knowledge" / "manifests" / "proxy-preflight.json",
            {
                "errors": errors,
                "generated_at": "2026-07-09T00:00:00+00:00",
                "missing": missing,
                "proxy": proxy,
                "proxy_region_redacted": proxy_region_redacted,
                "ready": ready,
                "requirements": requirements,
                "runtime_id": "browseforge-chromium",
                "schema_version": "1.0",
                "status": status,
            },
        )

    def _native_status_snapshot_fixture(self, platform: str) -> dict[str, Any] | None:
        if platform == "linux-x64":
            return None
        snapshot: dict[str, Any] = {
            "host_os": "darwin",
            "required_host_os": "darwin" if platform == "macos-arm64" else "windows",
            "host_supported": platform == "macos-arm64",
            "chromium_src_exists": False,
            "chromium_deps_exists": False,
            "depot_tools_exists": False,
            "gn_binary_exists": False,
            "out_args_exists": False,
            "build_ninja_exists": False,
            "output_binary_exists": False,
            "package_zip_exists": False,
            "native_toolchain_ready": False,
        }
        if platform == "macos-arm64":
            snapshot.update(
                {
                    "xcodebuild_ok": False,
                    "xcodebuild_status": "failed",
                    "app_bundle_exists": False,
                }
            )
        if platform == "windows-x64":
            snapshot["portable_layout_exists"] = False
        return snapshot


    def _write_native_artifact_preflight(
        self,
        root: Path,
        *,
        runtime_manifest: dict[str, Any] | None = None,
        platform_overrides: dict[str, dict[str, Any]] | None = None,
        omit_platforms: set[str] | None = None,
        release_grade_ready: bool = False,
    ) -> dict[str, Any]:
        if runtime_manifest is None:
            runtime_manifest = self._load_temp_runtime_artifacts_manifest(root)
        if platform_overrides is None:
            platform_overrides = {}
        if omit_platforms is None:
            omit_platforms = set()
        artifacts_by_platform = {artifact["platform"]: artifact for artifact in runtime_manifest["artifacts"]}
        supported_platforms = list(runtime_manifest["supported_package_platforms"])
        platforms: list[dict[str, Any]] = []
        for platform in supported_platforms:
            if platform in omit_platforms:
                continue
            artifact = artifacts_by_platform.get(platform)
            entry: dict[str, Any] = {
                "evidence": [],
                "missing_prerequisites": ["runtime-artifacts artifact missing"],
                "platform": platform,
                "ready": False,
                "status": "blocked",
            }
            status_snapshot = self._native_status_snapshot_fixture(platform)
            if status_snapshot is not None:
                entry["status_snapshot"] = status_snapshot
            if artifact is not None:
                entry.update(
                    {
                        "artifact_id": artifact["artifact_id"],
                        "evidence": [
                            f"knowledge/manifests/runtime-artifacts.json:{artifact['artifact_id']}"
                        ],
                        "missing_prerequisites": [],
                        "ready": True,
                        "status": "ready",
                    }
                )
            entry.update(platform_overrides.get(platform, {}))
            platforms.append(entry)
        preflight = {
            "generated_at": "2026-07-09T00:00:00+00:00",
            "requirements": [
                {
                    "id": "runtime-artifacts-artifact",
                    "description": "supported package platform has a packaged artifact listed in runtime-artifacts.json",
                },
                {
                    "id": "native-release-evidence",
                    "description": "native package has release evidence for BrowseForge launch and detector coverage",
                },
            ],
            "platforms": platforms,
            "release_grade_ready": release_grade_ready,
            "runtime_artifacts_manifest": "knowledge/manifests/runtime-artifacts.json",
            "runtime_id": runtime_manifest["runtime_id"],
            "schema_version": "1.0",
            "supported_package_platforms": supported_platforms,
        }
        self._write_json(root / "knowledge" / "manifests" / "native-artifact-preflight.json", preflight)
        return preflight

    def _write_signing_policy(
        self,
        root: Path,
        *,
        runtime_manifest: dict[str, Any] | None = None,
        platform_overrides: dict[str, dict[str, Any]] | None = None,
        omit_platforms: set[str] | None = None,
        release_grade_ready: bool = False,
    ) -> dict[str, Any]:
        if runtime_manifest is None:
            runtime_manifest = self._load_temp_runtime_artifacts_manifest(root)
        if platform_overrides is None:
            platform_overrides = {}
        if omit_platforms is None:
            omit_platforms = set()

        artifacts_by_platform = {artifact["platform"]: artifact for artifact in runtime_manifest["artifacts"]}
        signing_requirements = {
            platform["id"]: [
                requirement
                for requirement in platform["required_evidence"]
                if "sign" in requirement or "codesign" in requirement or "notarization" in requirement
            ]
            for platform in self._platform_matrix_platforms()
        }
        supported_platforms = list(runtime_manifest["supported_package_platforms"])
        policies: list[dict[str, Any]] = []
        for platform in supported_platforms:
            if platform in omit_platforms:
                continue
            artifact = artifacts_by_platform.get(platform)
            if artifact is not None:
                entry: dict[str, Any] = {
                    "artifact_id": artifact["artifact_id"],
                    "decision": artifact["signature"],
                    "signature": artifact["signature"],
                    "release_channel": artifact["release_channel"],
                    "evidence": [
                        f"knowledge/manifests/runtime-artifacts.json:{artifact['artifact_id']}:signature={artifact['signature']}"
                    ],
                    "missing_prerequisites": [],
                    "platform": platform,
                    "release_grade_allowed": True,
                    "signing_requirement": "runtime-artifacts signature metadata matches artifact",
                    "status": "allowed",
                }
            elif platform == "macos-arm64":
                entry = {
                    "decision": "codesign/notarization deferred until a native macOS artifact exists",
                    "evidence": ["knowledge/manifests/platform-matrix.json:macos-arm64:codesign/notarization decision exists"],
                    "missing_prerequisites": ["macOS native release artifact is missing"],
                    "platform": platform,
                    "release_grade_allowed": False,
                    "signing_requirement": signing_requirements[platform][0],
                    "status": "blocked",
                }
            elif platform == "windows-x64":
                entry = {
                    "decision": "code signing deferred until a native Windows artifact exists",
                    "evidence": ["knowledge/manifests/platform-matrix.json:windows-x64:code signing decision exists"],
                    "missing_prerequisites": ["Windows native release artifact is missing"],
                    "platform": platform,
                    "release_grade_allowed": False,
                    "signing_requirement": signing_requirements[platform][0],
                    "status": "blocked",
                }
            else:
                self.fail(f"missing signing-policy fixture for supported platform {platform}")
            entry.update(platform_overrides.get(platform, {}))
            policies.append(entry)

        signing_policy = {
            "generated_at": "2026-07-09T00:00:00+00:00",
            "platform_matrix_manifest": "knowledge/manifests/platform-matrix.json",
            "policies": policies,
            "release_grade_ready": release_grade_ready,
            "runtime_artifacts_manifest": "knowledge/manifests/runtime-artifacts.json",
            "runtime_id": runtime_manifest["runtime_id"],
            "schema_version": "1.0",
            "supported_package_platforms": supported_platforms,
        }
        self._write_json(root / "knowledge" / "manifests" / "signing-policy.json", signing_policy)
        return signing_policy

    def _write_detector_summary(
        self,
        root: Path,
        *,
        coverage_gaps: list[dict[str, Any]],
        coverage_gap_count: int | None = None,
        blocking_findings: list[dict[str, Any]] | None = None,
    ) -> None:
        self._write_json(
            root / "detector-summary.json",
            {
                "blocking_findings": [] if blocking_findings is None else blocking_findings,
                "coverage_gap_count": len(coverage_gaps) if coverage_gap_count is None else coverage_gap_count,
                "coverage_gaps": coverage_gaps,
                "evidence_count": 0,
                "rows": [],
            },
        )

    def _coverage_gaps(self, count: int) -> list[dict[str, Any]]:
        gaps: list[dict[str, Any]] = []
        for detector_id in ["browserleaks", "browserscan", "creepjs", "iphey", "pixelscan", "sannysoft"]:
            for network_mode, container_values in [("direct", [False]), ("proxy", [False, True])]:
                for container in container_values:
                    network_evidence = (
                        "external proxy exit-IP/geolocation" if network_mode == "proxy" else "direct network"
                    )
                    container_evidence = "Docker/container" if container else "native/host"
                    gaps.append(
                        {
                            "container": container,
                            "detector_id": detector_id,
                            "display_mode": "headed",
                            "matrix_key": f"linux-x64:{detector_id}:headed:{network_mode}:{'container' if container else 'host'}",
                            "network_mode": network_mode,
                            "platform": "linux-x64",
                            "required_evidence": f"headed / {container_evidence} / {network_evidence} sanitized detector evidence",
                        }
                    )
                    if len(gaps) == count:
                        return gaps
        self.fail(f"test fixture requested {count} detector coverage gaps but only {len(gaps)} are defined")
        return gaps

    def _write_surface_status(
        self,
        root: Path,
        *,
        release_grade: bool = False,
        release_blocker: bool = False,
        updated_from: list[str] | None = None,
    ) -> None:
        surface_names = [
            "seed identity",
            "UA",
            "Client Hints",
            "platform",
            "timezone",
            "locale",
            "screen/window/DPR",
            "hardwareConcurrency/deviceMemory",
            "Canvas",
            "WebGL vendor/renderer",
            "AudioContext",
            "fonts",
            "WebRTC",
            "permissions",
            "storage quota",
            "automation/headless/CDP",
            "proxy/IP coherence",
            "profile persistence",
            "cross-platform drift",
        ]
        self._write_json(
            root / "knowledge" / "manifests" / "fingerprint-surface-status.json",
            {
                "allowed_status_values": ["not_started", "designed", "implemented", "detector_tested", "accepted", "blocked"],
                "release_grade": release_grade,
                "runtime_id": "browseforge-chromium",
                "surfaces": [
                    {
                        "evidence": "fixture",
                        "release_blocker": release_blocker and surface == "proxy/IP coherence",
                        "result": "fixture_surface_status",
                        "severity": "medium" if release_blocker and surface == "proxy/IP coherence" else "info",
                        "status": "detector_tested",
                        "surface": surface,
                    }
                    for surface in surface_names
                ],
                "updated_from": [] if updated_from is None else updated_from,
            },
        )

    def _write_detector_evidence(
        self,
        path: Path,
        *,
        matrix: dict[str, Any],
        storage: dict[str, Any],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "harness": {"name": "browseforge-detector-harness", "mode": "live_collect"},
            "matrix": {
                "display_mode": matrix["display_mode"],
                "network_mode": matrix["network_mode"],
                "proxy": matrix["proxy"],
            },
            "storage": storage,
        }
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def _write_browseforge_integration_contract(self, root: Path, *, release_blockers: list[str]) -> None:
        self._write_json(
            root / "contracts" / "browseforge-integration.contract.json",
            {
                "adapter_requirements": [
                    "runtime descriptor registered with chromium family",
                    "binary path resolved from config.runtimes.<id>.binary_path",
                    "profile create/update/import/restore stores runtime_id, not engine",
                    "launch path assembles deterministic profile-specific args without mutating unrelated runtimes",
                    "Playwright bind endpoint is reachable for launched sessions",
                    "browser cache version marker prevents stale seeded runtime reuse",
                    "smoke rest and smoke mcp pass under Docker",
                ],
                "browseforge_min_version": "v2.0.0",
                "contract_version": "v0.1.0",
                "release_blockers": release_blockers,
                "required_browseforge_surfaces": [
                    "config.runtimes.<id>",
                    "GET /api/runtimes",
                    "POST /api/profiles",
                    "PUT /api/profiles/{id}",
                    "POST /api/profiles/import",
                    "POST /api/backup/restore",
                    "POST /api/sessions",
                    "MCP list_runtimes",
                    "MCP create_profile",
                    "MCP open_browser",
                    "workflow create_profile",
                    "dashboard runtime selector",
                    "browsers status",
                    "browsers install",
                    "Docker seed /app/browsers/<runtime>",
                ],
                "runtime_id": "browseforge-chromium",
            },
        )

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
