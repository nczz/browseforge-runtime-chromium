#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS_VERSION = "0.1.0"
SENSITIVE_RE = re.compile(r"(gh[pousr]_[A-Za-z0-9_]+|xox[baprs]-[A-Za-z0-9-]+|\b(?:\d{1,3}\.){3}\d{1,3}\b)")

EXIT_SCHEMA = 1
EXIT_COLLECT_UNAVAILABLE = 2
EXIT_SANITIZATION = 3
EXIT_MANIFEST = 4
EXIT_UNSUPPORTED = 5

CANONICAL_SURFACES = set(json.loads((ROOT / "contracts/runtime.manifest.json").read_text())["fingerprint"]["surfaces"])
SURFACE_ALIASES = {
    "automation": "automation_signals",
    "webdriver": "automation_signals",
    "plugins": "automation_signals",
    "languages": "locale",
    "features": "permissions",
    "incognito": "storage_quota",
    "platform": "client_hints",
}

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def detectors_manifest():
    data = load_json(ROOT / "knowledge/manifests/detectors.json")
    ids = [d["detector_id"] for d in data["detectors"]]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate detector_id in manifest")
    return data

def platforms_manifest():
    return load_json(ROOT / "knowledge/manifests/platform-matrix.json")

def detector_by_id(detector_id: str):
    for det in detectors_manifest()["detectors"]:
        if det["detector_id"] == detector_id:
            return det
    return None

def canonical_surface(surface: str) -> str:
    return SURFACE_ALIASES.get(surface, surface)

def list_targets(args):
    detectors = detectors_manifest()["detectors"]
    platforms = platforms_manifest()["platforms"]
    payload = {
        "runtime_id": "browseforge-chromium",
        "canonical_surfaces": sorted(CANONICAL_SURFACES),
        "detectors": detectors,
        "platforms": platforms,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0

def plan(args):
    platforms = {p["id"]: p for p in platforms_manifest()["platforms"]}
    if args.platform not in platforms:
        print(f"unsupported platform: {args.platform}", file=sys.stderr)
        return EXIT_UNSUPPORTED
    rows = []
    for det in sorted(detectors_manifest()["detectors"], key=lambda d: d["detector_id"]):
        matrix = det.get("matrix", {})
        display_modes = matrix.get("display_modes") or ["headed"]
        network_modes = matrix.get("network_modes") or ["direct"]
        container_modes = matrix.get("container_modes") or []
        containers = [False, True] if "docker" in container_modes else [False]
        if args.platform == "linux-x64" and "docker" in container_modes:
            containers = [False, True]
        for display in display_modes:
            for network in network_modes:
                for container in containers:
                    key = f"{args.platform}:{det['detector_id']}:{display}:{network}:{'container' if container else 'host'}"
                    rows.append({
                        "matrix_key": key,
                        "runtime_version": args.runtime_version,
                        "platform": args.platform,
                        "detector_id": det["detector_id"],
                        "display_mode": display,
                        "network_mode": network,
                        "container": container,
                        "required": bool(det.get("required", True)),
                        "surfaces": det.get("canonical_surfaces", [canonical_surface(s) for s in det.get("surfaces", [])]),
                    })
    print(json.dumps({"rows": rows}, indent=2, sort_keys=True))
    return 0

def validate_evidence_file(path: Path):
    evidence = load_json(path)
    errors = []
    detector = evidence.get("detector", {})
    det = detector_by_id(detector.get("detector_id", ""))
    if det is None:
        errors.append(f"unknown detector_id: {detector.get('detector_id')}")
    if evidence.get("runtime_id") != "browseforge-chromium":
        errors.append("runtime_id must be browseforge-chromium")
    status = evidence.get("status")
    failure = evidence.get("failure_mode")
    if status == "passed" and failure != "none":
        errors.append("passed evidence requires failure_mode none")
    if status == "error" and failure == "none":
        errors.append("error evidence requires operational failure_mode")
    if failure in {"timeout", "detector_unreachable", "browser_launch_failed", "browser_crash"}:
        for result in evidence.get("results", []):
            if result.get("status") not in {"not_tested", "accepted_risk"}:
                errors.append("operational detector failures cannot be encoded as fingerprint pass/fail")
    for result in evidence.get("results", []):
        surf = canonical_surface(result.get("surface", ""))
        if surf not in CANONICAL_SURFACES:
            errors.append(f"unknown surface: {result.get('surface')}")
    sanitization = evidence.get("sanitization", {})
    for key in ["ip_redacted", "credentials_redacted", "profiles_redacted", "tokens_redacted", "cookies_storage_redacted", "screenshot_metadata_redacted"]:
        if sanitization.get(key) is not True:
            return EXIT_SANITIZATION, [f"sanitization failure: {key} must be true"]
    if sanitization.get("raw_capture_committed") is not False:
        return EXIT_SANITIZATION, ["raw_capture_committed must be false"]
    text = json.dumps(evidence, sort_keys=True)
    if SENSITIVE_RE.search(text):
        return EXIT_SANITIZATION, ["sensitive-looking token or IP literal present in committed evidence"]
    if errors:
        return EXIT_SCHEMA, errors
    return 0, []

def validate_evidence(args):
    code, errors = validate_evidence_file(Path(args.path))
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
    return code

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def kg_edges(evidence):
    det_id = evidence["detector"]["detector_id"]
    run_id = evidence["run_id"]
    evidence_id = evidence["evidence_id"]
    artifact_id = evidence["artifact_id"]
    nodes = [
        {"label": "DetectorRun", "id": run_id, "properties": {"status": evidence["status"], "failure_mode": evidence["failure_mode"], "matrix_key": evidence["matrix"]["matrix_key"]}},
        {"label": "EvidenceArtifact", "id": evidence_id, "properties": {"path": evidence["storage"]["evidence_path"], "sha256": evidence["storage"]["sha256"], "sanitized": True}},
    ]
    edges = [
        {"from": run_id, "edge": "RUNS_DETECTOR", "to": det_id},
        {"from": run_id, "edge": "TESTS_ARTIFACT", "to": artifact_id},
        {"from": evidence_id, "edge": "EVIDENCES", "to": run_id},
    ]
    for surface in sorted({canonical_surface(r["surface"]) for r in evidence.get("results", [])}):
        edges.append({"from": det_id, "edge": "CHECKS_SURFACE", "to": surface})
    return {"nodes": nodes, "edges": edges}

def ingest(args):
    src = Path(args.input)
    code, errors = validate_evidence_file(src)
    if code:
        for err in errors:
            print(err, file=sys.stderr)
        return code
    evidence = load_json(src)
    out = Path(args.output_root) / evidence["runtime_version"] / evidence["target"]["platform"] / evidence["detector"]["detector_id"] / f"{evidence['run_id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    evidence["storage"]["evidence_path"] = str(out)
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = sha256(out)
    evidence["storage"]["sha256"] = digest
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    kg = kg_edges(evidence)
    kg_path = Path(args.kg_out)
    kg_path.parent.mkdir(parents=True, exist_ok=True)
    with kg_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(kg, sort_keys=True) + "\n")
    print(str(out))
    return 0

def summary(args):
    root = Path(args.evidence_root)
    files = sorted(root.glob("**/*.json"))
    blocking = []
    rows = []
    for path in files:
        code, errors = validate_evidence_file(path)
        if code:
            return code
        evidence = load_json(path)
        for result in evidence.get("results", []):
            if result.get("severity") in {"high", "critical"} and result.get("status") in {"fail", "warn"} and not result.get("accepted_risk_id"):
                blocking.append({"path": str(path), "surface": result.get("surface"), "severity": result.get("severity"), "finding": result.get("finding")})
        rows.append({"path": str(path), "detector_id": evidence["detector"]["detector_id"], "platform": evidence["target"]["platform"], "status": evidence["status"]})
    payload = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "evidence_count": len(rows), "blocking_findings": blocking, "rows": rows}
    Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0

def collect(args):
    print("live detector collection requires an explicit browser binary and a future live collector implementation", file=sys.stderr)
    return EXIT_COLLECT_UNAVAILABLE

def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)
    p = sub.add_parser("list-targets"); p.set_defaults(func=list_targets)
    p = sub.add_parser("plan"); p.add_argument("--runtime-version", required=True); p.add_argument("--platform", required=True); p.add_argument("--format", default="json"); p.set_defaults(func=plan)
    p = sub.add_parser("validate-evidence"); p.add_argument("path"); p.add_argument("--schema", default="detectors/evidence-schema.json"); p.set_defaults(func=validate_evidence)
    p = sub.add_parser("ingest"); p.add_argument("--input", required=True); p.add_argument("--output-root", default="detectors/evidence"); p.add_argument("--kg-out", default="generated/kg/detector-evidence.jsonl"); p.set_defaults(func=ingest)
    p = sub.add_parser("summary"); p.add_argument("--evidence-root", default="detectors/evidence"); p.add_argument("--output", default="detector-summary.json"); p.set_defaults(func=summary)
    p = sub.add_parser("collect"); p.set_defaults(func=collect)
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
