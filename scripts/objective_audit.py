#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0"
RUNTIME_ID = "browseforge-chromium"


def load_json(root: Path, path: str) -> dict[str, Any]:
    return json.loads((root / path).read_text(encoding="utf-8"))


def generated_at_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def patchset_by_id(patchset_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("patchset_id")): entry
        for entry in patchset_manifest.get("patchsets", [])
        if isinstance(entry, dict) and entry.get("patchset_id")
    }


def blocker_ids(release_status: dict[str, Any]) -> list[str]:
    return [str(blocker.get("blocker_id")) for blocker in release_status.get("blockers", []) if blocker.get("blocker_id")]


def deliverable(deliverable_id: str, title: str, *, satisfied: bool, evidence: list[str], blockers: list[str], requirements: list[str]) -> dict[str, Any]:
    return {
        "deliverable_id": deliverable_id,
        "title": title,
        "satisfied": bool(satisfied),
        "requirements": requirements,
        "evidence": evidence,
        "blockers": blockers,
    }


def objective_audit(root: Path = ROOT, generated_at: str | None = None) -> dict[str, Any]:
    source_acquisition = load_json(root, "knowledge/manifests/source-acquisition.json")
    patchset = load_json(root, "knowledge/manifests/patchset.json")
    release_status = load_json(root, "knowledge/manifests/release-status.json")
    native_preflight = load_json(root, "knowledge/manifests/native-artifact-preflight.json")
    surface_status = load_json(root, "knowledge/manifests/fingerprint-surface-status.json")
    integration_contract = load_json(root, "contracts/browseforge-integration.contract.json")

    chromium = source_acquisition.get("chromium_base", {})
    build_outputs = chromium.get("build_output_status", {}) if isinstance(chromium, dict) else {}
    required_build_outputs = [
        "dev_gn_args_exists",
        "dev_build_ninja_exists",
        "linux_docker_gn_args_exists",
        "linux_docker_build_ninja_exists",
        "linux_docker_chrome_exists",
    ]
    missing_build_outputs = [key for key in required_build_outputs if build_outputs.get(key) is not True]
    release_blockers = blocker_ids(release_status)
    patchsets = patchset_by_id(patchset)
    scaffold = patchsets.get("scaffold-browseforge-stealth-substrate", {})
    source_profile = chromium.get("dependency_profile_status", {}) if isinstance(chromium, dict) else {}
    workdir_contract = source_profile.get("profile_isolated_workdir_contract", {}) if isinstance(source_profile, dict) else {}
    source_build_status = chromium.get("source_build_status") or chromium.get("last_dev_baseline_probe", {}) if isinstance(chromium, dict) else {}
    source_build_blockers = [f"missing build output: {key}" for key in missing_build_outputs]
    if missing_build_outputs and isinstance(source_profile, dict) and source_profile.get("mac_gn_exists") is False:
        source_build_blockers.append("missing host dependency profile: mac_gn_exists")
    if missing_build_outputs and isinstance(source_build_status, dict) and str(source_build_status.get("status", "")).startswith("blocked_full_xcode"):
        source_build_blockers.append("blocked host toolchain: full Xcode required")
    surfaces = surface_status.get("surfaces", [])
    release_blocking_surfaces = [str(surface.get("surface")) for surface in surfaces if isinstance(surface, dict) and surface.get("release_blocker") is True]
    native_missing = [
        str(entry.get("platform"))
        for entry in native_preflight.get("platforms", [])
        if isinstance(entry, dict) and entry.get("ready") is not True
    ]

    deliverables = [
        deliverable(
            "source_build_baseline",
            "Reproducible Chromium source/build baseline",
            satisfied=not missing_build_outputs and chromium.get("source_checkout_status") == "checked_out_pinned_ref",
            requirements=[
                "Pinned Chromium source checkout matches source-acquisition manifest",
                "BrowseForgeDev GN args and build.ninja exist",
                "BrowseForgeLinuxDocker args.gn/build.ninja/chrome exist",
            ],
            evidence=[
                "knowledge/manifests/source-acquisition.json:chromium_base.source_checkout_status",
                "knowledge/manifests/source-acquisition.json:chromium_base.build_output_status",
                "python3 scripts/chromium_source.py check",
            ],
            blockers=source_build_blockers,
        ),
        deliverable(
            "native_stealth_substrate_patchset",
            "Native stealth substrate and source-level patchset scaffold",
            satisfied=bool(scaffold) and scaffold.get("upstream_status") not in {None, "unmodified_baseline"},
            requirements=[
                "Stealth substrate patchset is recorded",
                "Patchset names Chromium and runtime files touched",
                "Patchset status proves scaffold copied or linked into source checkout",
            ],
            evidence=[
                "knowledge/manifests/patchset.json:scaffold-browseforge-stealth-substrate",
                "browser/stealth/*",
                "scripts/apply_stealth_scaffold.py",
            ],
            blockers=[] if scaffold else ["scaffold-browseforge-stealth-substrate patchset missing"],
        ),
        deliverable(
            "source_acquisition_automation",
            "Source acquisition automation and dependency profile isolation",
            satisfied=bool(workdir_contract) and chromium.get("source_workdir_isolation_status") == "helpers_support_profile_specific_workdirs_with_shared_fallback",
            requirements=[
                "Source acquisition helper pins Chromium ref and syncs host deps",
                "Host/native and Linux Docker dependency profiles can use separate checkout paths",
                "Manifest records the workdir isolation contract",
            ],
            evidence=[
                "scripts/chromium_source.py",
                "scripts/chromium_docker.py",
                "scripts/chromium_native.py",
                "knowledge/manifests/source-acquisition.json:dependency_profile_status.profile_isolated_workdir_contract",
            ],
            blockers=[] if workdir_contract else ["profile_isolated_workdir_contract missing"],
        ),
        deliverable(
            "manifest_gates",
            "Manifest gates and release audit state",
            satisfied=isinstance(release_status.get("blocker_count"), int) and isinstance(release_status.get("release_grade_ready"), bool),
            requirements=[
                "Release status is generated from manifest inputs",
                "Unmet objective requirements are machine-readable blockers",
                "Validation suite fails closed on manifest drift",
            ],
            evidence=[
                "knowledge/manifests/release-status.json",
                "scripts/release_status.py",
                "scripts/validate.py",
            ],
            blockers=[],
        ),
        deliverable(
            "browseforge_integration_path",
            "BrowseForge integration path",
            satisfied=bool(integration_contract.get("required_browseforge_surfaces")) and bool(integration_contract.get("adapter_requirements")),
            requirements=[
                "BrowseForge integration contract declares runtime surfaces",
                "Adapter requirements cover config, profiles, sessions, MCP, workflow, dashboard, Docker seed",
                "Release blockers remain explicit until artifacts and detector evidence pass",
            ],
            evidence=["contracts/browseforge-integration.contract.json"],
            blockers=[],
        ),
        deliverable(
            "fingerprint_surface_implementation",
            "Fingerprint surface implementation and detector evidence",
            satisfied=not release_blocking_surfaces and surface_status.get("release_grade") is True,
            requirements=[
                "Every fingerprint surface is implemented or accepted",
                "Release-blocking detector surfaces have live evidence",
                "Cross-platform drift matrix is complete",
            ],
            evidence=[
                "knowledge/manifests/fingerprint-surface-status.json",
                "detector-summary.json",
                "knowledge/manifests/detector-score-comparison.json",
            ],
            blockers=[f"release-blocking surface: {surface}" for surface in release_blocking_surfaces],
        ),
        deliverable(
            "native_release_artifacts",
            "Native macOS and Windows BrowseForge Chromium release artifacts",
            satisfied=native_preflight.get("release_grade_ready") is True,
            requirements=[
                "macOS artifact is a BrowseForge Chromium .app built from the selected source ref",
                "Windows artifact is a portable chrome.exe/DLL layout built from the selected source ref",
                "Native artifacts have detector evidence before release_grade passes",
            ],
            evidence=["knowledge/manifests/native-artifact-preflight.json", "knowledge/manifests/runtime-artifacts.json"],
            blockers=[f"native platform not ready: {platform}" for platform in native_missing],
        ),
        deliverable(
            "release_grade_cutover",
            "Release-grade source-level anti-detect runtime cutover",
            satisfied=release_status.get("release_grade_ready") is True and not release_blockers,
            requirements=[
                "All release gates pass",
                "No release-status blockers remain",
                "Supported platform artifacts and detector gates pass",
            ],
            evidence=["knowledge/manifests/release-status.json"],
            blockers=release_blockers,
        ),
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_id": RUNTIME_ID,
        "generated_at": generated_at or generated_at_utc(),
        "objective": "source-level BrowseForge Chromium anti-detect runtime with reproducible source/build baseline, native stealth substrate, source acquisition automation, manifest gates, BrowseForge integration path, and fingerprint surface implementation",
        "overall_ready": all(item["satisfied"] for item in deliverables),
        "release_grade_ready": release_status.get("release_grade_ready") is True,
        "blocker_count": sum(len(item["blockers"]) for item in deliverables),
        "deliverables": deliverables,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a machine-readable audit of the BrowseForge Chromium anti-detect objective")
    parser.add_argument("--output", type=Path, default=ROOT / "knowledge" / "manifests" / "objective-audit.json")
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    payload = objective_audit(ROOT, args.generated_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
