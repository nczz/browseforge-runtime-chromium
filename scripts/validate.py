#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "SECURITY.md",
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
    "graph/schema/runtime-kg.schema.md",
    "graph/queries/development-readiness.cypher",
    "graph/queries/fingerprint-risk.cypher",
    "graph/queries/cross-repo-impact.cypher",
    "graph/queries/source-coverage.cypher",
    "docs/architecture.md",
    "docs/browseforge-integration.md",
    "docs/research-map.md",
    "docs/fingerprint-surfaces.md",
    "docs/release-readiness.md",
    "docs/kb-kg-completeness-assessment.md",
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
    required_sources = {"runtime-repo-contracts", "runtime-repo-docs", "runtime-repo-detectors", "runtime-repo-graph", "browseforge-consumer-contract"}
    missing_sources = sorted(required_sources - source_ids)
    if missing_sources:
        raise SystemExit(f"missing KB source ids: {missing_sources}")

    detectors = load_json("knowledge/manifests/detectors.json")
    detector_ids = {det["detector_id"] for det in detectors["detectors"]}
    required_detectors = {"sannysoft", "browserleaks", "creepjs", "pixelscan", "iphey", "browserscan"}
    missing_detectors = sorted(required_detectors - detector_ids)
    if missing_detectors:
        raise SystemExit(f"missing detector ids: {missing_detectors}")

    reference_sources = load_json("knowledge/manifests/reference-sources.json")
    source_class_ids = {src["id"] for src in reference_sources["source_classes"]}
    required_source_classes = {"browseforge-consumer", "cloakbrowser-reference", "camoufox-reference", "chromium-upstream", "detector-evidence"}
    missing_source_classes = sorted(required_source_classes - source_class_ids)
    if missing_source_classes:
        raise SystemExit(f"missing reference source classes: {missing_source_classes}")

    platform_matrix = load_json("knowledge/manifests/platform-matrix.json")
    platform_ids = {platform["id"] for platform in platform_matrix["platforms"]}
    required_platforms = {"linux-x64", "macos-arm64", "macos-x64", "windows-x64", "linux-arm64"}
    missing_platforms = sorted(required_platforms - platform_ids)
    if missing_platforms:
        raise SystemExit(f"missing platform matrix ids: {missing_platforms}")

    query_text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in [
        "graph/queries/development-readiness.cypher",
        "graph/queries/fingerprint-risk.cypher",
        "graph/queries/cross-repo-impact.cypher",
        "graph/queries/source-coverage.cypher",
    ])
    for token in ["RuntimeArtifact", "DetectorRun", "BrowseForgeConsumer", "FingerprintSurface", "KnowledgeSource", "Platform"]:
        if token not in query_text:
            raise SystemExit(f"graph queries missing {token}")

    print("runtime framework validation ok")


if __name__ == "__main__":
    main()
