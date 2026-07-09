#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "go.mod",
    "cmd/browseforge-runtime-chromium/main.go",
    "internal/launcher/config.go",
    "internal/launcher/launch.go",
    "internal/stealth/persona.go",
    "contracts/runtime.manifest.json",
    "contracts/runtime-manifest.schema.json",
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
    "knowledge/manifests/source-acquisition.json",
    "browser/chromium-base.json",
    "browser/stealth/BUILD.gn",
    "browser/stealth/stealth_switches.h",
    "browser/stealth/stealth_switches.cc",
    "browser/stealth/persona_snapshot.h",
    "browser/stealth/persona_snapshot.cc",
    "browser/stealth/persona_resolver.h",
    "browser/stealth/persona_resolver.cc",
    "browser/stealth/public/mojom/stealth.mojom",
    "build/package_runtime.py",
    "scripts/chromium_source.py",
    "scripts/apply_stealth_scaffold.py",
    "scripts/chromium_docker.py",
    "scripts/package_linux_runtime.py",
    "scripts/apply_webdriver_patch.py",
    "scripts/apply_hardware_patch.py",
    "scripts/apply_screen_patch.py",
    "scripts/apply_platform_patch.py",
    "scripts/apply_timezone_patch.py",
    "scripts/apply_locale_patch.py",
    "scripts/apply_user_agent_patch.py",
    "scripts/apply_storage_quota_patch.py",
    "scripts/apply_plugins_patch.py",
    "scripts/apply_webrtc_patch.py",
    "scripts/apply_audio_patch.py",
    "scripts/apply_canvas_patch.py",
    "scripts/apply_webgl_patch.py",
    "scripts/apply_feature_parity_patch.py",
    "scripts/apply_fonts_patch.py",
    "scripts/apply_process_priority_patch.py",
    "scripts/apply_switch_propagation_patch.py",
    "scripts/detector_harness.py",
    "docker/chromium-build.Dockerfile",
    "graph/schema/runtime-kg.schema.md",
    "graph/queries/development-readiness.cypher",
    "graph/queries/fingerprint-risk.cypher",
    "graph/queries/cross-repo-impact.cypher",
    "graph/queries/source-coverage.cypher",
    "generated/kg/runtime.graph.jsonl",
    "generated/kg/runtime.ttl",
    "docs/architecture.md",
    "docs/browseforge-integration.md",
    "docs/research-map.md",
    "docs/fingerprint-surfaces.md",
    "docs/release-readiness.md",
    "docs/kb-kg-completeness-assessment.md",
    "tests/test_detector_harness.py",
    "tests/test_package_runtime.py",
    "tests/test_chromium_source.py",
    "tests/test_apply_stealth_scaffold.py",
    "tests/test_apply_webdriver_patch.py",
    "tests/test_apply_hardware_patch.py",
    "tests/test_apply_screen_patch.py",
    "tests/test_apply_platform_patch.py",
    "tests/test_apply_timezone_patch.py",
    "tests/test_apply_locale_patch.py",
    "tests/test_apply_user_agent_patch.py",
    "tests/test_apply_storage_quota_patch.py",
    "tests/test_apply_plugins_patch.py",
    "tests/test_apply_webrtc_patch.py",
    "tests/test_apply_audio_patch.py",
    "tests/test_apply_canvas_patch.py",
    "tests/test_apply_webgl_patch.py",
    "tests/test_apply_feature_parity_patch.py",
    "tests/test_apply_fonts_patch.py",
    "tests/test_apply_process_priority_patch.py",
    "tests/test_apply_switch_propagation_patch.py",
    "tests/test_chromium_docker.py",
    "internal/stealth/persona_test.go",
    "tests/test_stealth_scaffold.py",
]

REQUIRED_DIRS = [
    "browser",
    "wrapper",
    "build",
    "docker",
    "detectors",
    "knowledge",
    "graph",
    "tests",
    "examples",
]


def load_json(path: str) -> object:
    with (ROOT / path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(path: str) -> list[dict]:
    records = []
    with (ROOT / path).open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSONL: {exc}") from exc
    return records

def validate_evidence_schema_contract(evidence_schema: dict) -> None:
    properties = evidence_schema.get("properties", {})
    harness_props = properties.get("harness", {}).get("properties", {})
    matrix_props = properties.get("matrix", {}).get("properties", {})
    storage_props = properties.get("storage", {}).get("properties", {})
    required_enums = {
        "harness.name": (harness_props.get("name", {}).get("enum") or [], {"browseforge-detector-harness", "browseforge-detector-harness + local-connect-proxy"}),
        "harness.mode": (harness_props.get("mode", {}).get("enum") or [], {"manual_ingest", "synthetic_fixture", "live_collect", "live_collect_local_proxy"}),
        "matrix.display_mode": (matrix_props.get("display_mode", {}).get("enum") or [], {"headed", "headed_xvfb", "headless", "unknown"}),
        "matrix.network_mode": (matrix_props.get("network_mode", {}).get("enum") or [], {"direct", "proxy", "local_proxy", "unknown"}),
        "matrix.proxy": (matrix_props.get("proxy", {}).get("enum") or [], {"none", "redacted", "public_test_infra", "local-connect-observer"}),
    }
    for field, (actual_values, required_values) in required_enums.items():
        missing_values = sorted(required_values - set(actual_values))
        if missing_values:
            raise SystemExit(f"evidence schema {field} missing admitted values: {missing_values}")

    required_storage_keys = {"evidence_path", "sha256", "raw_capture_path", "raw_capture_sha256", "proxy_summary_sha256", "text_sha256", "summary_path"}
    missing_storage_keys = sorted(required_storage_keys - set(storage_props))
    if missing_storage_keys:
        raise SystemExit(f"evidence schema storage missing properties: {missing_storage_keys}")

    admitted = {
        "harness.name": set(harness_props["name"]["enum"]),
        "harness.mode": set(harness_props["mode"]["enum"]),
        "matrix.display_mode": set(matrix_props["display_mode"]["enum"]),
        "matrix.network_mode": set(matrix_props["network_mode"]["enum"]),
        "matrix.proxy": set(matrix_props["proxy"]["enum"]),
    }
    storage_keys = set(storage_props)
    for path in sorted((ROOT / "detectors" / "evidence").glob("**/*.json")):
        with path.open("r", encoding="utf-8") as fh:
            evidence = json.load(fh)
        values = {
            "harness.name": evidence.get("harness", {}).get("name"),
            "harness.mode": evidence.get("harness", {}).get("mode"),
            "matrix.display_mode": evidence.get("matrix", {}).get("display_mode"),
            "matrix.network_mode": evidence.get("matrix", {}).get("network_mode"),
            "matrix.proxy": evidence.get("matrix", {}).get("proxy"),
        }
        for field, value in values.items():
            if value not in admitted[field]:
                rel = path.relative_to(ROOT)
                raise SystemExit(f"detector evidence {rel} {field} value {value!r} is not admitted by evidence schema")
        for storage_key in evidence.get("storage", {}):
            if storage_key not in storage_keys:
                rel = path.relative_to(ROOT)
                raise SystemExit(f"detector evidence {rel} storage key {storage_key!r} is not admitted by evidence schema")

def validate_surface_status_manifest(surface_status: dict, gate_status: dict[str, str | None]) -> None:
    if surface_status.get("runtime_id") != "browseforge-chromium":
        raise SystemExit("fingerprint surface status runtime_id must be browseforge-chromium")
    allowed_statuses = set(surface_status.get("allowed_status_values", []))
    if not allowed_statuses:
        raise SystemExit("fingerprint surface status must declare allowed_status_values")
    surfaces = surface_status.get("surfaces", [])
    if not surfaces:
        raise SystemExit("fingerprint surface status must contain surfaces")
    required_fields = {"surface", "status", "release_blocker", "result", "evidence", "severity"}
    release_blockers = []
    for surface in surfaces:
        missing_fields = sorted(required_fields - surface.keys())
        if missing_fields:
            raise SystemExit(f"fingerprint surface status entry missing fields: {missing_fields}")
        if surface["status"] not in allowed_statuses:
            raise SystemExit(f"fingerprint surface {surface['surface']} uses unknown status {surface['status']}")
        if not isinstance(surface["release_blocker"], bool):
            raise SystemExit(f"fingerprint surface {surface['surface']} release_blocker must be boolean")
        if surface["release_blocker"]:
            release_blockers.append(surface["surface"])
    if surface_status.get("release_grade") is True and release_blockers:
        raise SystemExit(f"fingerprint surface status cannot be release_grade with blockers: {sorted(release_blockers)}")
    if gate_status.get("live-detector-evidence") == "passed" and release_blockers:
        raise SystemExit(f"live-detector-evidence gate cannot pass while fingerprint surfaces block release: {sorted(release_blockers)}")
    for source_path in surface_status.get("updated_from", []):
        if not (ROOT / source_path).is_file():
            raise SystemExit(f"fingerprint surface status references missing evidence source: {source_path}")

def validate_score_comparison_manifest(score_comparison: dict, gate_status: dict[str, str | None]) -> None:
    if score_comparison.get("runtime_id") != "browseforge-chromium":
        raise SystemExit("detector score comparison runtime_id must be browseforge-chromium")
    if score_comparison.get("release_grade") is not False:
        raise SystemExit("offline detector score comparison must not claim release grade")

    comparisons = score_comparison.get("comparisons", [])
    comparison_ids = {comparison.get("comparison_id") for comparison in comparisons}
    for comparison_id in ["creepjs_audio_headless_vs_headed", "browserleaks_creepjs_font_metrics"]:
        if comparison_id not in comparison_ids:
            raise SystemExit(f"detector score comparison missing {comparison_id}")

    baseline_gap_ids = {gap.get("gap_id") for gap in score_comparison.get("baseline_gaps", [])}
    for gap_id in [
        "native_headed_font_corpus_parity_missing",
    ]:
        if gap_id not in baseline_gap_ids:
            raise SystemExit(f"detector score comparison missing baseline gap {gap_id}")

    gap_ids = {gap.get("gap_id") for gap in score_comparison.get("gaps", [])}
    webgl_comparison = next((comparison for comparison in comparisons if comparison.get("comparison_id") == "webgl_metadata_cross_detector"), None)
    if webgl_comparison is None:
        for gap_id in ["webgl_metadata_hashes_missing", "webgl_cross_detector_metadata_comparison_missing"]:
            if gap_id not in gap_ids:
                raise SystemExit(f"detector score comparison missing WebGL comparison blocker {gap_id}")
    else:
        for field in ["vendor_renderer_match", "extension_count_match", "extension_profile_match", "hash_matches"]:
            if field not in webgl_comparison:
                raise SystemExit(f"detector score comparison WebGL comparison missing field {field}")
        hash_matches = webgl_comparison.get("hash_matches")
        if not isinstance(hash_matches, dict):
            raise SystemExit("detector score comparison WebGL hash_matches must be an object")
        for field in ["extensionSha256", "parameterSha256", "precisionSha256", "pixelSha256"]:
            if field not in hash_matches:
                raise SystemExit(f"detector score comparison WebGL hash_matches missing {field}")

    if gate_status.get("live-detector-evidence") == "passed":
        warning_comparisons = [comparison.get("comparison_id") for comparison in comparisons if comparison.get("status") == "warning"]
        if score_comparison.get("baseline_gaps") or score_comparison.get("gaps") or warning_comparisons:
            raise SystemExit("live-detector-evidence gate cannot pass while detector score comparison has baseline gaps, evidence gaps, or warning comparisons")



def main() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    missing_dirs = [path for path in REQUIRED_DIRS if not (ROOT / path).is_dir()]
    if missing_dirs:
        raise SystemExit(f"missing required directories: {missing_dirs}")

    manifest = load_json("contracts/runtime.manifest.json")
    if manifest["id"] != "browseforge-chromium":
        raise SystemExit("runtime id must be browseforge-chromium")
    if manifest["family"] != "chromium":
        raise SystemExit("runtime family must be chromium")
    if manifest["browseforge"]["profile_field"] != "runtime_id":
        raise SystemExit("BrowseForge profile field must stay runtime_id")

    kb_manifest = load_json("knowledge/kb-manifest.json")
    source_ids = {src["source_id"] for src in kb_manifest["sources"]}
    required_sources = {"runtime-repo-contracts", "runtime-repo-docs", "runtime-repo-detectors", "runtime-repo-graph", "browseforge-consumer-contract", "cloakbrowser-reference", "camoufox-reference", "chromium-upstream"}
    missing_sources = sorted(required_sources - source_ids)
    if missing_sources:
        raise SystemExit(f"missing KB source ids: {missing_sources}")

    detectors = load_json("knowledge/manifests/detectors.json")
    detector_ids = {det["detector_id"] for det in detectors["detectors"]}
    required_detectors = {"sannysoft", "browserleaks", "creepjs", "pixelscan", "iphey", "browserscan"}
    missing_detectors = sorted(required_detectors - detector_ids)
    if missing_detectors:
        raise SystemExit(f"missing detector ids: {missing_detectors}")
    runtime_surfaces = set(manifest["fingerprint"]["surfaces"])
    for det in detectors["detectors"]:
        if det.get("required") is not True:
            raise SystemExit(f"detector {det['detector_id']} must declare required=true")
        matrix = det.get("matrix", {})
        for key in ["display_modes", "network_modes", "container_modes"]:
            if key not in matrix:
                raise SystemExit(f"detector {det['detector_id']} missing matrix.{key}")
        for surface in det.get("canonical_surfaces", []):
            if surface not in runtime_surfaces:
                raise SystemExit(f"detector {det['detector_id']} references unknown canonical surface {surface}")

    evidence_schema = load_json("detectors/evidence-schema.json")
    if evidence_schema["properties"]["schema_version"].get("const") != "1.1":
        raise SystemExit("evidence schema must be 1.1")
    for field in ["run_id", "evidence_id", "artifact_id", "matrix", "status", "failure_mode", "storage", "kg"]:
        if field not in evidence_schema["required"]:
            raise SystemExit(f"evidence schema missing required field {field}")
    validate_evidence_schema_contract(evidence_schema)


    reference_sources = load_json("knowledge/manifests/reference-sources.json")
    source_class_ids = {src["id"] for src in reference_sources["source_classes"]}
    required_source_classes = {"browseforge-consumer", "cloakbrowser-reference", "camoufox-reference", "chromium-upstream", "detector-evidence"}
    missing_source_classes = sorted(required_source_classes - source_class_ids)
    if missing_source_classes:
        raise SystemExit(f"missing reference source classes: {missing_source_classes}")

    patchset = load_json("knowledge/manifests/patchset.json")
    if patchset.get("base_version") == "unselected" or patchset.get("base_ref") == "unselected":
        raise SystemExit("Chromium base version/ref must be selected")
    if not patchset.get("patchsets"):
        raise SystemExit("patchset manifest must contain at least an explicit baseline patchset")

    platform_matrix = load_json("knowledge/manifests/platform-matrix.json")
    platform_ids = {platform["id"] for platform in platform_matrix["platforms"]}
    required_platforms = {"linux-x64", "macos-arm64", "macos-x64", "windows-x64", "linux-arm64"}
    missing_platforms = sorted(required_platforms - platform_ids)
    if missing_platforms:
        raise SystemExit(f"missing platform matrix ids: {missing_platforms}")

    release_gates = load_json("knowledge/manifests/release-gates.json")
    gate_ids = {gate["gate_id"] for gate in release_gates["release_candidate_required_gates"]}
    for gate_id in ["chromium-base-selected", "wrapper-contract-tests", "detector-harness-contract-tests", "packaging-contract-tests", "chromium-source-indexed", "runtime-artifact-produced", "browseforge-adapter-merged", "live-detector-evidence", "sbom-provenance-release-assets"]:
        if gate_id not in gate_ids:
            raise SystemExit(f"release gates missing {gate_id}")
    gate_status = {gate["gate_id"]: gate.get("status") for gate in release_gates["release_candidate_required_gates"]}

    surface_status = load_json("knowledge/manifests/fingerprint-surface-status.json")
    validate_surface_status_manifest(surface_status, gate_status)

    detector_summary = load_json("detector-summary.json")
    coverage_gaps = detector_summary.get("coverage_gaps", [])
    coverage_gap_count = detector_summary.get("coverage_gap_count")
    if coverage_gap_count != len(coverage_gaps):
        raise SystemExit("detector summary coverage_gap_count must match coverage_gaps length")
    required_gap_fields = {"matrix_key", "platform", "detector_id", "display_mode", "network_mode", "container", "required_evidence"}
    for gap in coverage_gaps:
        missing_gap_fields = sorted(required_gap_fields - gap.keys())
        if missing_gap_fields:
            raise SystemExit(f"detector summary coverage gap missing fields: {missing_gap_fields}")
    if gate_status.get("live-detector-evidence") == "passed" and (
        coverage_gap_count or detector_summary.get("blocking_findings")
    ):
        raise SystemExit("live-detector-evidence gate cannot pass while detector summary has coverage gaps or blocking findings")


    score_comparison = load_json("knowledge/manifests/detector-score-comparison.json")
    validate_score_comparison_manifest(score_comparison, gate_status)

    query_text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in [
        "graph/queries/development-readiness.cypher",
        "graph/queries/fingerprint-risk.cypher",
        "graph/queries/cross-repo-impact.cypher",
        "graph/queries/source-coverage.cypher",
    ])
    for token in ["RuntimeArtifact", "DetectorRun", "BrowseForgeConsumer", "FingerprintSurface", "KnowledgeSource", "Platform", "RUNS_DETECTOR", "TARGETS_PLATFORM"]:
        if token not in query_text:
            raise SystemExit(f"graph queries missing {token}")
    for stale_token in ["RAN_DETECTOR", "platform_id"]:
        if stale_token in query_text:
            raise SystemExit(f"graph queries contain stale schema token {stale_token}")

    graph_records = load_jsonl("generated/kg/runtime.graph.jsonl")
    node_labels = {record.get("label") for record in graph_records if record.get("record_type") == "node"}
    edge_labels = {record.get("label") for record in graph_records if record.get("record_type") == "edge"}
    required_node_labels = {
        "RuntimeProvider", "RuntimeArtifact", "BrowseForgeConsumer", "FingerprintSurface", "Patch",
        "SourceFile", "Symbol", "Detector", "DetectorRun", "EvidenceArtifact", "Platform",
        "Capability", "ReleaseGate", "KnowledgeSource",
    }
    missing_node_labels = sorted(required_node_labels - node_labels)
    if missing_node_labels:
        raise SystemExit(f"generated KG missing node labels: {missing_node_labels}")
    required_edge_labels = {
        "REQUIRES_CAPABILITY", "DECLARES_CAPABILITY", "BUILT_FOR", "GENERATED_FROM",
        "MODIFIES_SOURCE", "CONTROLS_SURFACE", "CHECKS_SURFACE", "RUNS_DETECTOR",
        "TARGETS_ARTIFACT", "TESTS_ARTIFACT", "PRODUCES_EVIDENCE", "SUPPORTS_GATE",
        "REFERENCES_SOURCE",
    }
    missing_edge_labels = sorted(required_edge_labels - edge_labels)
    if missing_edge_labels:
        raise SystemExit(f"generated KG missing edge labels: {missing_edge_labels}")

    graph_nodes = {
        record["id"]: record
        for record in graph_records
        if record.get("record_type") == "node" and "id" in record
    }
    graph_edges = {
        (record.get("from"), record.get("label"), record.get("to"))
        for record in graph_records
        if record.get("record_type") == "edge"
    }
    runtime_artifacts = load_json("knowledge/manifests/runtime-artifacts.json")
    required_artifact_fields = set(runtime_artifacts.get("required_artifact_fields", []))
    supported_package_platforms = set(runtime_artifacts.get("supported_package_platforms", []))
    artifact_platforms = {artifact.get("platform") for artifact in runtime_artifacts.get("artifacts", [])}
    missing_artifact_contracts = sorted(artifact_platforms - supported_package_platforms)
    if missing_artifact_contracts:
        raise SystemExit(f"runtime-artifacts packaged platforms missing runtime asset contracts: {missing_artifact_contracts}")
    unsupported_package_platforms = runtime_artifacts.get("unsupported_package_platforms", {})
    for platform in artifact_platforms:
        if platform in unsupported_package_platforms:
            raise SystemExit(f"runtime-artifacts packages unsupported platform without runtime asset contract: {platform}")
    for artifact in runtime_artifacts.get("artifacts", []):
        artifact_id = artifact["artifact_id"]
        node_id = f"RuntimeArtifact:{artifact_id}"
        node = graph_nodes.get(node_id)
        if node is None:
            raise SystemExit(f"generated KG missing RuntimeArtifact node for {artifact_id}")
        props = node.get("properties", {})
        missing_fields = sorted(required_artifact_fields - props.keys())
        if missing_fields:
            raise SystemExit(f"generated KG RuntimeArtifact {artifact_id} missing fields: {missing_fields}")
        for key in ["runtime_id", "runtime_version", "platform", "os", "arch", "browser_version", "source_ref", "patchset_id", "wrapper_version", "sha256", "size_bytes", "sbom_path", "provenance_path", "release_channel"]:
            if props.get(key) != artifact.get(key):
                raise SystemExit(f"generated KG RuntimeArtifact {artifact_id} {key} drifted: {props.get(key)!r} != {artifact.get(key)!r}")
        if props.get("release_grade") is not True or props.get("status") != "packaged":
            raise SystemExit(f"generated KG RuntimeArtifact {artifact_id} must be release_grade packaged")
        for edge in [
            (node_id, "GENERATED_FROM", "RuntimeProvider:browseforge-chromium"),
            (node_id, "BUILT_FOR", f"Platform:{artifact['platform']}"),
            (node_id, "TARGETS_PLATFORM", f"Platform:{artifact['platform']}"),
        ]:
            if edge not in graph_edges:
                raise SystemExit(f"generated KG missing artifact edge: {edge}")
        stale_linux_missing = [
            record for record in graph_records
            if record.get("record_type") == "edge"
            and record.get("to") == f"Platform:{artifact['platform']}"
            and record.get("properties", {}).get("status") == "missing_artifact"
        ]
        if stale_linux_missing:
            raise SystemExit(f"generated KG still links {artifact['platform']} to missing artifact blockers")

    for row in detector_summary.get("rows", []):
        path = ROOT / row["path"]
        evidence = load_json(path)
        if evidence["artifact_id"] not in {artifact["artifact_id"] for artifact in runtime_artifacts.get("artifacts", [])}:
            continue
        run_node = f"DetectorRun:{evidence['run_id']}"
        evidence_node = f"EvidenceArtifact:{evidence['evidence_id']}"
        artifact_node = f"RuntimeArtifact:{evidence['artifact_id']}"
        if run_node not in graph_nodes:
            raise SystemExit(f"generated KG missing DetectorRun node for {evidence['run_id']}")
        if evidence_node not in graph_nodes:
            raise SystemExit(f"generated KG missing EvidenceArtifact node for {evidence['evidence_id']}")
        for edge in [
            (run_node, "RUNS_DETECTOR", f"Detector:{evidence['detector']['detector_id']}"),
            (run_node, "TESTS_ARTIFACT", artifact_node),
            (run_node, "TARGETS_ARTIFACT", artifact_node),
            (run_node, "PRODUCES_EVIDENCE", evidence_node),
            (evidence_node, "SUPPORTS_GATE", "ReleaseGate:live-detector-evidence"),
        ]:
            if edge not in graph_edges:
                raise SystemExit(f"generated KG missing detector evidence edge: {edge}")

    print("runtime framework validation ok")


if __name__ == "__main__":
    main()
