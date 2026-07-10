#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ID = "browseforge-chromium"
SCHEMA_VERSION = "1.0"
INPUT_PATHS = [
    "knowledge/manifests/release-gates.json",
    "knowledge/manifests/native-artifact-preflight.json",
    "knowledge/manifests/proxy-preflight.json",
    "detector-summary.json",
    "knowledge/manifests/detector-score-comparison.json",
    "knowledge/manifests/fingerprint-surface-status.json",
    "knowledge/manifests/signing-policy.json",
    "knowledge/manifests/source-acquisition.json",
    "contracts/browseforge-integration.contract.json",
]


def load_json(root: Path, path: str) -> dict[str, Any]:
    return json.loads((root / path).read_text(encoding="utf-8"))


def sha256_file(root: Path, path: str) -> str:
    return hashlib.sha256((root / path).read_bytes()).hexdigest()


def generated_at_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def add_blocker(blockers: list[dict[str, Any]], *, source: str, blocker_id: str, detail: str, severity: str = "high", **extra: Any) -> None:
    blocker = {
        "blocker_id": blocker_id,
        "detail": detail,
        "severity": severity,
        "source": source,
    }
    for key, value in extra.items():
        if value is not None:
            blocker[key] = value
    blockers.append(blocker)


def native_blocker_snapshot_fields(entry: dict[str, Any]) -> dict[str, Any]:
    snapshot = entry.get("status_snapshot")
    if not isinstance(snapshot, dict):
        return {}
    return {
        "host_supported": snapshot.get("host_supported"),
        "native_toolchain_ready": snapshot.get("native_toolchain_ready"),
        "build_ninja_exists": snapshot.get("build_ninja_exists"),
        "output_binary_exists": snapshot.get("output_binary_exists"),
        "package_zip_exists": snapshot.get("package_zip_exists"),
    }

def source_rebuild_blockers(source_acquisition: dict[str, Any]) -> list[dict[str, Any]]:
    chromium = source_acquisition.get("chromium_base", {})
    if not isinstance(chromium, dict) or chromium.get("artifact_rebuild_required") is not True:
        return []
    reasons = chromium.get("artifact_rebuild_reasons", [])
    if not isinstance(reasons, list) or not reasons:
        reasons = ["source patch changes require rebuilding packaged runtime artifacts"]
    blockers = []
    for index, reason in enumerate(reasons):
        blockers.append(
            {
                "blocker_id": f"source-acquisition:artifact-rebuild:{index}",
                "detail": str(reason),
                "severity": "high",
                "source": "knowledge/manifests/source-acquisition.json",
                "status": chromium.get("artifact_rebuild_status"),
            }
        )
    return blockers

def release_resource_requirements(
    native_preflight: dict[str, Any],
    proxy_preflight: dict[str, Any],
    detector_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    if proxy_preflight.get("ready") is not True:
        missing = [str(item) for item in proxy_preflight.get("missing", [])]
        errors = [str(item) for item in proxy_preflight.get("errors", [])]
        requirements.append(
            {
                "resource_id": "external-detector-proxy",
                "status": "missing" if missing else "invalid",
                "severity": "critical",
                "provide": missing or ["valid external proxy URL and redacted region label"],
                "requirements": proxy_preflight.get("requirements", []),
                "errors": errors,
                "unblocks": [
                    "external proxy exit-IP/geolocation detector evidence",
                    "proxy/IP coherence detector matrix",
                    "WebRTC public/private IP coherence evidence",
                ],
            }
        )

    for entry in native_preflight.get("platforms", []):
        if entry.get("ready") is True:
            continue
        platform = str(entry.get("platform"))
        missing = [str(item) for item in entry.get("missing_prerequisites", [])]
        requirements.append(
            {
                "resource_id": f"native-artifact-{platform}",
                "status": str(entry.get("status", "missing_native_release_artifact")),
                "severity": "critical",
                "provide": missing,
                "evidence": entry.get("evidence", []),
                "status_snapshot": entry.get("status_snapshot", {}),
                "unblocks": [
                    f"{platform} packaged native BrowseForge Chromium artifact",
                    f"{platform} native detector evidence",
                ],
            }
        )

    proxy_gaps = [
        gap
        for gap in detector_summary.get("coverage_gaps", [])
        if gap.get("network_mode") == "proxy"
    ]
    if proxy_gaps:
        requirements.append(
            {
                "resource_id": "live-proxy-detector-matrix",
                "status": "missing_detector_evidence",
                "severity": "high",
                "provide": sorted({str(gap.get("matrix_key")) for gap in proxy_gaps}),
                "requirements": ["headed detector runs through the configured external proxy"],
                "unblocks": ["release-grade live detector evidence gate"],
            }
        )
    return requirements






def release_status(root: Path = ROOT, generated_at: str | None = None) -> dict[str, Any]:
    release_gates = load_json(root, "knowledge/manifests/release-gates.json")
    native_preflight = load_json(root, "knowledge/manifests/native-artifact-preflight.json")
    proxy_preflight = load_json(root, "knowledge/manifests/proxy-preflight.json")
    detector_summary = load_json(root, "detector-summary.json")
    score_comparison = load_json(root, "knowledge/manifests/detector-score-comparison.json")
    surface_status = load_json(root, "knowledge/manifests/fingerprint-surface-status.json")
    signing_policy = load_json(root, "knowledge/manifests/signing-policy.json")
    integration_contract = load_json(root, "contracts/browseforge-integration.contract.json")
    source_acquisition = load_json(root, "knowledge/manifests/source-acquisition.json")

    blockers: list[dict[str, Any]] = []
    for gate in release_gates.get("release_candidate_required_gates", []):
        status = gate.get("status")
        if status != "passed":
            gate_id = str(gate.get("gate_id"))
            add_blocker(
                blockers,
                source="knowledge/manifests/release-gates.json",
                blocker_id=f"release-gate:{gate_id}",
                detail=f"release gate {gate_id} status is {status!r}, not 'passed'",
                severity="high" if status == "warning" else "critical",
                gate_id=gate_id,
                status=status,
                evidence=gate.get("evidence"),
            )

    blockers.extend(source_rebuild_blockers(source_acquisition))

    if native_preflight.get("release_grade_ready") is not True:
        for entry in native_preflight.get("platforms", []):
            if entry.get("ready") is True:
                continue
            platform = str(entry.get("platform"))
            missing = entry.get("missing_prerequisites") or [entry.get("status", "native platform not ready")]
            for index, detail in enumerate(missing):
                add_blocker(
                    blockers,
                    source="knowledge/manifests/native-artifact-preflight.json",
                    blocker_id=f"native-artifact:{platform}:{index}",
                    detail=str(detail),
                    severity="critical",
                    platform=platform,
                    status=entry.get("status"),
                    evidence=entry.get("evidence"),
                    **native_blocker_snapshot_fields(entry),
                )

    if proxy_preflight.get("ready") is not True:
        for key in proxy_preflight.get("missing", []):
            add_blocker(
                blockers,
                source="knowledge/manifests/proxy-preflight.json",
                blocker_id=f"proxy-preflight:missing:{key}",
                detail=f"required proxy setting {key} is missing",
                severity="critical",
            )
        for index, error in enumerate(proxy_preflight.get("errors", [])):
            add_blocker(
                blockers,
                source="knowledge/manifests/proxy-preflight.json",
                blocker_id=f"proxy-preflight:error:{index}",
                detail=str(error),
                severity="critical",
            )

    for index, finding in enumerate(detector_summary.get("blocking_findings", [])):
        add_blocker(
            blockers,
            source="detector-summary.json",
            blocker_id=f"detector:blocking-finding:{index}",
            detail=str(finding.get("finding", "blocking detector finding")),
            severity=str(finding.get("severity", "critical")),
            surface=finding.get("surface"),
            evidence=finding.get("path"),
        )
    for gap in detector_summary.get("coverage_gaps", []):
        matrix_key = str(gap.get("matrix_key"))
        add_blocker(
            blockers,
            source="detector-summary.json",
            blocker_id=f"detector:coverage-gap:{matrix_key}",
            detail=str(gap.get("required_evidence", "required detector matrix evidence missing")),
            severity="high" if gap.get("network_mode") == "proxy" else "medium",
            platform=gap.get("platform"),
            detector_id=gap.get("detector_id"),
            matrix_key=matrix_key,
            display_mode=gap.get("display_mode"),
            network_mode=gap.get("network_mode"),
            container=gap.get("container"),
        )

    for gap_key in ("baseline_gaps", "gaps"):
        for index, gap in enumerate(score_comparison.get(gap_key, [])):
            gap_id = str(gap.get("gap_id", index)) if isinstance(gap, dict) else str(index)
            add_blocker(
                blockers,
                source="knowledge/manifests/detector-score-comparison.json",
                blocker_id=f"score-comparison:{gap_key}:{gap_id}",
                detail=json.dumps(gap, sort_keys=True) if isinstance(gap, dict) else str(gap),
                severity="medium",
            )

    if surface_status.get("release_grade") is not True:
        for surface in surface_status.get("surfaces", []):
            if surface.get("release_blocker") is True:
                name = str(surface.get("surface"))
                add_blocker(
                    blockers,
                    source="knowledge/manifests/fingerprint-surface-status.json",
                    blocker_id=f"fingerprint-surface:{name}",
                    detail=str(surface.get("evidence", "fingerprint surface remains release-blocking")),
                    severity=str(surface.get("severity", "high")),
                    surface=name,
                    status=surface.get("status"),
                    result=surface.get("result"),
                )

    if signing_policy.get("release_grade_ready") is not True:
        for policy in signing_policy.get("policies", []):
            if policy.get("release_grade_allowed") is True:
                continue
            platform = str(policy.get("platform"))
            add_blocker(
                blockers,
                source="knowledge/manifests/signing-policy.json",
                blocker_id=f"signing-policy:{platform}",
                detail=str(policy.get("decision", "release-grade signing policy is not ready")),
                severity="high",
                platform=platform,
                status=policy.get("status"),
                evidence=policy.get("evidence"),
            )

    for index, detail in enumerate(integration_contract.get("release_blockers", [])):
        add_blocker(
            blockers,
            source="contracts/browseforge-integration.contract.json",
            blocker_id=f"browseforge-integration:{index}",
            detail=str(detail),
            severity="high",
        )

    blockers.sort(key=lambda item: (item["source"], item["blocker_id"]))
    return {
        "blocker_count": len(blockers),
        "blockers": blockers,
        "generated_at": generated_at or generated_at_utc(),
        "input_sha256": {path: sha256_file(root, path) for path in INPUT_PATHS},
        "inputs": INPUT_PATHS,
        "release_grade_ready": len(blockers) == 0,
        "resource_requirements": release_resource_requirements(native_preflight, proxy_preflight, detector_summary),
        "runtime_id": RUNTIME_ID,
        "schema_version": SCHEMA_VERSION,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate BrowseForge Chromium release-grade status from current gate manifests")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--generated-at")
    args = parser.parse_args()

    payload = release_status(args.root, args.generated_at)
    out = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out, encoding="utf-8")
        print(args.output)
    else:
        print(out, end="")


if __name__ == "__main__":
    main()
