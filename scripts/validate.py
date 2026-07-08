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
    "knowledge/kb-manifest.json",
    "knowledge/manifests/detectors.json",
    "knowledge/manifests/patchset.json",
    "knowledge/manifests/runtime-artifacts.json",
    "knowledge/manifests/reference-sources.json",
    "knowledge/manifests/platform-matrix.json",
    "knowledge/manifests/release-gates.json",
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
    "scripts/apply_webdriver_patch.py",
    "scripts/apply_hardware_patch.py",
    "scripts/apply_screen_patch.py",
    "scripts/apply_platform_patch.py",
    "scripts/apply_timezone_patch.py",
    "scripts/apply_locale_patch.py",
    "scripts/apply_user_agent_patch.py",
    "scripts/apply_storage_quota_patch.py",
    "scripts/apply_plugins_patch.py",
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
        "TARGETS_ARTIFACT", "PRODUCES_EVIDENCE", "SUPPORTS_GATE", "REFERENCES_SOURCE",
    }
    missing_edge_labels = sorted(required_edge_labels - edge_labels)
    if missing_edge_labels:
        raise SystemExit(f"generated KG missing edge labels: {missing_edge_labels}")
    if not any(record.get("label") == "RuntimeArtifact" and record.get("properties", {}).get("status") == "missing" for record in graph_records):
        raise SystemExit("generated KG must represent the missing runtime artifact blocker explicitly")

    print("runtime framework validation ok")


if __name__ == "__main__":
    main()
