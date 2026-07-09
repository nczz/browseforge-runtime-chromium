from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = ROOT / "scripts" / "validate.py"
GRAPH_PATH = ROOT / "generated" / "kg" / "runtime.graph.jsonl"
RUNTIME_ARTIFACTS_MANIFEST = ROOT / "knowledge" / "manifests" / "runtime-artifacts.json"
LINUX_ARTIFACT_ID = "browseforge-runtime-chromium-v0.1.0-alpha.0-linux-x64"
LINUX_ARTIFACT_NODE_ID = f"RuntimeArtifact:{LINUX_ARTIFACT_ID}"
LINUX_PLATFORM_NODE_ID = "Platform:linux-x64"


class ValidateRuntimeGraphTests(unittest.TestCase):
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


    def test_runtime_artifact_manifest_blocks_non_linux_without_contract(self) -> None:
        with RUNTIME_ARTIFACTS_MANIFEST.open(encoding="utf-8") as fh:
            manifest = json.load(fh)

        self.assertEqual(["linux-x64"], manifest.get("supported_package_platforms"))
        unsupported = manifest.get("unsupported_package_platforms")
        self.assertIsInstance(unsupported, dict)
        assert isinstance(unsupported, dict)
        self.assertIn("macos-arm64", unsupported)
        self.assertIn("windows-x64", unsupported)

        artifact_platforms = {artifact.get("platform") for artifact in manifest.get("artifacts", [])}
        self.assertEqual({"linux-x64"}, artifact_platforms)
        self.assertTrue(set(manifest["supported_package_platforms"]).issubset(artifact_platforms))

    def test_validate_rejects_graph_whose_only_runtime_artifact_is_missing(self) -> None:
        """scripts.validate.main must fail closed when no release-grade linux-x64 RuntimeArtifact exists."""
        module = self._load_validate_module()
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            self._write_minimal_validate_tree(temp_root, module)
            original_root = module.ROOT
            try:
                module.ROOT = temp_root
                with self.assertRaises(SystemExit) as raised:
                    module.main()
            finally:
                module.ROOT = original_root

        message = str(raised.exception).lower()
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


    def _run_validate_expect_exit(self, module: Any, temp_root: Path) -> str:
        original_root = module.ROOT
        try:
            module.ROOT = temp_root
            with self.assertRaises(SystemExit) as raised:
                module.main()
        finally:
            module.ROOT = original_root
        return str(raised.exception)

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
                "fingerprint": {"surfaces": ["automation_signals", "canvas", "locale", "webgl"]},
            },
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
            {"platforms": [{"id": platform_id} for platform_id in ["linux-x64", "macos-arm64", "macos-x64", "windows-x64", "linux-arm64"]]},
        )
        self._write_release_gates(root, live_detector_status="warning")
        self._write_surface_status(root)
        self._write_score_comparison(root)
        self._write_json(
            root / "knowledge" / "manifests" / "runtime-artifacts.json",
            {
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
                        "sha256": "1a991ac31efee72a2f93c688619644e97b52b5e4d8732eb30014fa0265ffd93a",
                        "size_bytes": 567798165,
                        "sbom_path": "dist/stage/browseforge-runtime-chromium-v0.1.0-alpha.0-linux-x64/SBOM.json",
                        "provenance_path": "dist/stage/browseforge-runtime-chromium-v0.1.0-alpha.0-linux-x64/provenance.json",
                        "release_channel": "dev",
                    }
                ],
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
                    "sha256",
                    "size_bytes",
                    "sbom_path",
                    "provenance_path",
                    "release_channel",
                ],
                "supported_package_platforms": ["linux-x64"],
                "unsupported_package_platforms": {
                    "macos-arm64": "missing macOS runtime asset contract",
                    "windows-x64": "missing Windows runtime asset contract",
                },
            },
        )
        self._write_json(root / "knowledge" / "manifests" / "source-acquisition.json", {})
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
                "RUNS_DETECTOR",
                "TARGETS_PLATFORM",
            ]
        )
        for query_path in [
            root / "graph" / "queries" / "development-readiness.cypher",
            root / "graph" / "queries" / "fingerprint-risk.cypher",
            root / "graph" / "queries" / "cross-repo-impact.cypher",
            root / "graph" / "queries" / "source-coverage.cypher",
        ]:
            query_path.write_text(query_text, encoding="utf-8")

        graph_records = self._minimal_graph_with_only_missing_runtime_artifact()
        with (root / "generated" / "kg" / "runtime.graph.jsonl").open("w", encoding="utf-8") as fh:
            for record in graph_records:
                fh.write(json.dumps(record, sort_keys=True) + "\n")

    def _minimal_graph_with_only_missing_runtime_artifact(self) -> list[dict[str, Any]]:
        return [
            {"record_type": "node", "label": "RuntimeProvider", "id": "RuntimeProvider:browseforge-chromium", "properties": {}},
            {
                "record_type": "node",
                "label": "RuntimeArtifact",
                "id": "RuntimeArtifact:missing-runtime-artifact",
                "properties": {"artifact_id": "missing-runtime-artifact", "runtime_id": "browseforge-chromium", "status": "missing", "release_grade": False},
            },
            {"record_type": "node", "label": "BrowseForgeConsumer", "id": "BrowseForgeConsumer:browseforge-main", "properties": {}},
            {"record_type": "node", "label": "FingerprintSurface", "id": "FingerprintSurface:automation_signals", "properties": {}},
            {"record_type": "node", "label": "Patch", "id": "Patch:baseline", "properties": {}},
            {"record_type": "node", "label": "SourceFile", "id": "SourceFile:main", "properties": {}},
            {"record_type": "node", "label": "Symbol", "id": "Symbol:main", "properties": {}},
            {"record_type": "node", "label": "Detector", "id": "Detector:sannysoft", "properties": {}},
            {"record_type": "node", "label": "DetectorRun", "id": "DetectorRun:planned-sannysoft", "properties": {"status": "planned_missing_artifact"}},
            {"record_type": "node", "label": "EvidenceArtifact", "id": "EvidenceArtifact:missing-sannysoft", "properties": {}},
            {"record_type": "node", "label": "Platform", "id": LINUX_PLATFORM_NODE_ID, "properties": {"key": "linux-x64"}},
            {"record_type": "node", "label": "Capability", "id": "Capability:persistent_context", "properties": {}},
            {"record_type": "node", "label": "ReleaseGate", "id": "ReleaseGate:runtime-artifact-produced", "properties": {"gate_id": "runtime-artifact-produced", "status": "passed"}},
            {"record_type": "node", "label": "KnowledgeSource", "id": "KnowledgeSource:chromium-upstream", "properties": {}},
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
                {"gap_id": "browserleaks_audio_score_baseline_missing"},
                {"gap_id": "pixelscan_audio_font_score_baseline_missing"},
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
        self._write_json(
            root / "knowledge" / "manifests" / "release-gates.json",
            {
                "release_candidate_required_gates": [
                    {
                        "gate_id": gate_id,
                        "status": live_detector_status if gate_id == "live-detector-evidence" else "passed",
                    }
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
                    ]
                ]
            },
        )

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
        self._write_json(
            root / "knowledge" / "manifests" / "fingerprint-surface-status.json",
            {
                "allowed_status_values": ["not_started", "designed", "implemented", "detector_tested", "accepted", "blocked"],
                "release_grade": release_grade,
                "runtime_id": "browseforge-chromium",
                "surfaces": [
                    {
                        "evidence": "fixture",
                        "release_blocker": release_blocker,
                        "result": "fixture_surface_status",
                        "severity": "medium" if release_blocker else "info",
                        "status": "detector_tested",
                        "surface": "automation/headless/CDP",
                    }
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

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
