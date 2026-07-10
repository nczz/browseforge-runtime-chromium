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


def release_status(root: Path = ROOT, generated_at: str | None = None) -> dict[str, Any]:
    release_gates = load_json(root, "knowledge/manifests/release-gates.json")
    native_preflight = load_json(root, "knowledge/manifests/native-artifact-preflight.json")
    proxy_preflight = load_json(root, "knowledge/manifests/proxy-preflight.json")
    detector_summary = load_json(root, "detector-summary.json")
    score_comparison = load_json(root, "knowledge/manifests/detector-score-comparison.json")
    surface_status = load_json(root, "knowledge/manifests/fingerprint-surface-status.json")
    signing_policy = load_json(root, "knowledge/manifests/signing-policy.json")
    integration_contract = load_json(root, "contracts/browseforge-integration.contract.json")

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
