#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import base64
import datetime as dt
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import struct
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS_VERSION = "0.1.0"
SENSITIVE_RE = re.compile(r"(gh[pousr]_[A-Za-z0-9_]+|xox[baprs]-[A-Za-z0-9-]+|\b(?:\d{1,3}\.){3}\d{1,3}\b)")
TEXT_EXCERPT_SENSITIVE_RE = re.compile(r"(gh[pousr]_[A-Za-z0-9_]+|xox[baprs]-[A-Za-z0-9-]+|\b[0-9a-fA-F]{32,}\b|\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\.local\b|\b(?:\d{1,3}\.){3}\d{1,3}\b)")

def redact_sensitive_text(text: str) -> str:
    return TEXT_EXCERPT_SENSITIVE_RE.sub("[REDACTED]", text)

def _bounded_redacted_value(value: str, *, limit: int = 80) -> str:
    normalized = " ".join(value.split())
    return redact_sensitive_text(normalized[:limit])

def _extract_percent(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return float(match.group(1)) if match else None

def _extract_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return float(match.group(1)) if match else None

def extract_creepjs_metrics(text: str) -> dict:
    metrics: dict[str, object] = {}
    headless = {
        "like_headless_percent": _extract_percent(r"\b(\d+(?:\.\d+)?)%\s+like\s+headless\b", text),
        "headless_percent": _extract_percent(r"\b(\d+(?:\.\d+)?)%\s+headless\b", text),
        "stealth_percent": _extract_percent(r"\b(\d+(?:\.\d+)?)%\s+stealth\b", text),
    }
    headless = {key: value for key, value in headless.items() if value is not None}
    if headless:
        metrics["headless"] = headless

    audio: dict[str, float] = {}
    for field in ("sum", "gain", "freq", "time", "trap", "unique"):
        value = _extract_float(rf"^\s*{field}\s*:\s*(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)\b", text)
        if value is not None:
            audio[field] = value
    if audio:
        metrics["audio"] = audio

    fonts_match = re.search(r"\b(?:fonts\s+)?load(?:\s+count)?\s*(?:\((\d+)\)|:\s*(\d+))", text, re.IGNORECASE)
    if fonts_match:
        metrics["fonts"] = {"load_count": int(next(group for group in fonts_match.groups() if group))}

    return metrics

EXIT_SCHEMA = 1
EXIT_COLLECT_UNAVAILABLE = 2
EXIT_SANITIZATION = 3
EXIT_MANIFEST = 4
EXIT_UNSUPPORTED = 5
EXIT_PREFLIGHT = 6

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
CANVAS_RAW_RESULT_FIELDS = {
    "data_url",
    "dataUrl",
    "dataUrlSha256Input",
    "image_data",
    "imageData",
    "pixels",
    "pixel_data",
    "raw_pixels",
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

def _is_external_proxy_host(host: str) -> bool:
    lowered = host.strip().lower().strip("[]")
    if lowered in {"localhost", "ip6-localhost"} or lowered.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return True
    return not (address.is_loopback or address.is_private or address.is_link_local or address.is_reserved or address.is_unspecified)

def sanitized_proxy_descriptor(proxy_url: str) -> tuple[dict[str, object] | None, list[str]]:
    errors: list[str] = []
    parsed = urllib.parse.urlsplit(proxy_url)
    if parsed.scheme not in {"http", "https", "socks4", "socks5"}:
        errors.append("external proxy URL must use http, https, socks4, or socks5 scheme")
    if not parsed.hostname:
        errors.append("external proxy URL must include a host")
    if parsed.port is None:
        errors.append("external proxy URL must include a port")
    if parsed.hostname and not _is_external_proxy_host(parsed.hostname):
        errors.append("external proxy host must be an external routable proxy, not loopback/private/local infrastructure")
    if errors:
        return None, errors
    descriptor = {
        "scheme": parsed.scheme,
        "host_redacted": "[REDACTED_PROXY_HOST]",
        "port_redacted": "[REDACTED_PROXY_PORT]",
        "has_credentials": bool(parsed.username or parsed.password),
    }
    return descriptor, []

def proxy_preflight(args):
    proxy_url = args.proxy_url or os.environ.get("BROWSEFORGE_DETECTOR_PROXY_URL", "")
    proxy_region = args.proxy_region or os.environ.get("BROWSEFORGE_DETECTOR_PROXY_REGION", "")
    missing = []
    if not proxy_url:
        missing.append("BROWSEFORGE_DETECTOR_PROXY_URL")
    if not proxy_region:
        missing.append("BROWSEFORGE_DETECTOR_PROXY_REGION")
    errors: list[str] = []
    proxy = None
    if proxy_url:
        proxy, errors = sanitized_proxy_descriptor(proxy_url)
    payload = {
        "errors": errors,
        "generated_at": args.generated_at or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "missing": missing,
        "proxy": proxy,
        "proxy_region_redacted": _bounded_redacted_value(proxy_region) if proxy_region else None,
        "ready": not missing and not errors,
        "requirements": [
            "external proxy URL with scheme, host, and port",
            "redacted external proxy region/geolocation label",
            "no loopback, private, link-local, or .local proxy authority",
            "no raw credentials or IP literals in committed evidence",
        ],
        "runtime_id": "browseforge-chromium",
        "schema_version": "1.0",
        "status": "passed" if not missing and not errors else "failed",
    }
    out = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out, encoding="utf-8")
        print(args.output)
    else:
        print(out, end="")
    return 0 if payload["ready"] else EXIT_PREFLIGHT

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
    errors.extend(validate_external_proxy_coherence(evidence))
    for result in evidence.get("results", []):
        surf = canonical_surface(result.get("surface", ""))
        if surf not in CANONICAL_SURFACES:
            errors.append(f"unknown surface: {result.get('surface')}")
        if surf == "canvas":
            raw_fields = sorted(CANVAS_RAW_RESULT_FIELDS.intersection(result))
            if raw_fields:
                return EXIT_SANITIZATION, [f"canvas sanitization failure: raw payload fields are not allowed: {', '.join(raw_fields)}"]
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
    detector_node = f"Detector:{det_id}"
    run_node = f"DetectorRun:{run_id}"
    evidence_node = f"EvidenceArtifact:{evidence_id}"
    artifact_node = f"RuntimeArtifact:{artifact_id}"
    nodes = [
        {
            "record_type": "node",
            "label": "DetectorRun",
            "id": run_node,
            "properties": {
                "run_id": run_id,
                "detector_id": det_id,
                "status": evidence["status"],
                "failure_mode": evidence["failure_mode"],
                "matrix_key": evidence["matrix"]["matrix_key"],
            },
        },
        {
            "record_type": "node",
            "label": "EvidenceArtifact",
            "id": evidence_node,
            "properties": {
                "evidence_id": evidence_id,
                "path": evidence["storage"]["evidence_path"],
                "sha256": evidence["storage"]["sha256"],
                "sanitized": True,
                "status": evidence["status"],
            },
        },
    ]
    edges = [
        {"record_type": "edge", "from": run_node, "label": "RUNS_DETECTOR", "to": detector_node, "properties": {}},
        {"record_type": "edge", "from": run_node, "label": "TESTS_ARTIFACT", "to": artifact_node, "properties": {"status": evidence["status"]}},
        {"record_type": "edge", "from": run_node, "label": "TARGETS_ARTIFACT", "to": artifact_node, "properties": {"status": evidence["status"]}},
        {"record_type": "edge", "from": run_node, "label": "PRODUCES_EVIDENCE", "to": evidence_node, "properties": {"status": evidence["status"]}},
        {"record_type": "edge", "from": evidence_node, "label": "SUPPORTS_GATE", "to": "ReleaseGate:live-detector-evidence", "properties": {"status": evidence["status"]}},
    ]
    for surface in sorted({canonical_surface(r["surface"]) for r in evidence.get("results", [])}):
        edges.append({"record_type": "edge", "from": run_node, "label": "OBSERVED_SURFACE", "to": f"FingerprintSurface:{surface}", "properties": {"status": evidence["status"]}})
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
        for record in kg["nodes"] + kg["edges"]:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    print(str(out))
    return 0

def regenerate_kg(args):
    root = Path(args.evidence_root)
    records = []
    for path in sorted(root.glob("**/*.json")):
        code, errors = validate_evidence_file(path)
        if code:
            for err in errors:
                print(err, file=sys.stderr)
            return code
        kg = kg_edges(load_json(path))
        records.extend(kg["nodes"])
        records.extend(kg["edges"])
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    print(str(out))
    return 0

def normalize_display_mode(display_mode: str) -> str:
    if display_mode.startswith("headed"):
        return "headed"
    if display_mode.startswith("headless"):
        return "headless"
    return display_mode

def observed_matrix_key(evidence: dict) -> tuple[str, str, str, bool]:
    matrix = evidence.get("matrix", {})
    return (
        evidence["target"]["platform"],
        evidence["detector"]["detector_id"],
        normalize_display_mode(str(matrix.get("display_mode", ""))),
        str(matrix.get("network_mode", "")),
        bool(matrix.get("container")),
    )

def validate_external_proxy_coherence(evidence: dict) -> list[str]:
    matrix = evidence.get("matrix", {})
    if matrix.get("network_mode") != "proxy":
        return []
    errors = []
    proxy_mode = matrix.get("proxy")
    if proxy_mode in {None, "", "none", "local-connect-observer"}:
        errors.append("proxy matrix evidence requires redacted external proxy configuration")
    target_proxy_region = evidence.get("target", {}).get("proxy_region_redacted")
    if target_proxy_region in {None, "", "local-loopback-observer"}:
        errors.append("proxy matrix evidence requires external proxy region/geolocation metadata")
    for result in evidence.get("results", []):
        if canonical_surface(result.get("surface", "")) != "proxy_ip_coherence":
            continue
        if result.get("status") != "pass":
            continue
        values = result.get("normalized_values", {})
        if values.get("proxy_exit_region_redacted") and values.get("detector_geolocation_region_redacted"):
            return errors
    errors.append("proxy matrix evidence requires sanitized external proxy exit-IP/geolocation values")
    return errors


def required_matrix_evidence(display: str, network: str, container: bool) -> str:
    parts = [display, "Docker/container" if container else "native/host"]
    if network == "proxy":
        parts.append("external proxy exit-IP/geolocation")
    else:
        parts.append("direct network")
    return " / ".join(parts) + " sanitized detector evidence"

def required_matrix_rows(platform: str) -> list[dict]:
    rows = []
    for det in sorted(detectors_manifest()["detectors"], key=lambda d: d["detector_id"]):
        if det.get("required") is not True:
            continue
        matrix = det.get("matrix", {})
        display_modes = matrix.get("display_modes") or ["headed"]
        network_modes = matrix.get("network_modes") or ["direct"]
        container_modes = matrix.get("container_modes") or []
        containers = [False, True] if platform == "linux-x64" and "docker" in container_modes else [False]
        for display in display_modes:
            for network in network_modes:
                for container in containers:
                    rows.append({
                        "matrix_key": f"{platform}:{det['detector_id']}:{display}:{network}:{'container' if container else 'host'}",
                        "platform": platform,
                        "detector_id": det["detector_id"],
                        "display_mode": display,
                        "network_mode": network,
                        "container": container,
                        "required_evidence": required_matrix_evidence(display, network, container),
                    })
    return rows

def matrix_coverage_gaps(evidence_rows: list[dict], platform: str) -> list[dict]:
    observed = {
        observed_matrix_key(evidence)
        for evidence in evidence_rows
        if evidence.get("status") == "passed" and evidence.get("target", {}).get("platform") == platform
    }
    gaps = []
    for row in required_matrix_rows(platform):
        key = (row["platform"], row["detector_id"], row["display_mode"], row["network_mode"], row["container"])
        if key not in observed:
            gaps.append(row)
    return gaps

def _evidence_display(evidence: dict) -> str:
    return normalize_display_mode(str(evidence.get("matrix", {}).get("display_mode", "")))

def _evidence_context(evidence: dict) -> dict:
    matrix = evidence.get("matrix", {})
    target = evidence.get("target", {})
    return {
        "platform": target.get("platform"),
        "network_mode": matrix.get("network_mode"),
        "container": bool(matrix.get("container")),
    }

def _record_context(record: dict) -> tuple[object, object, bool]:
    return (record.get("platform"), record.get("network_mode"), bool(record.get("container")))

def _display_pair_by_context(records: list[dict]) -> tuple[dict | None, dict | None, list[str]]:
    by_context: dict[tuple[object, object, bool], dict[str, dict]] = {}
    observed_displays = set()
    for record in records:
        display = record.get("display_mode")
        observed_displays.add(display)
        by_context.setdefault(_record_context(record), {})[display] = record
    for context in sorted(by_context, key=lambda value: tuple(str(part) for part in value)):
        displays = by_context[context]
        if {"headless", "headed"} <= set(displays):
            return displays["headless"], displays["headed"], []
    missing = sorted({"headless", "headed"} - observed_displays)
    return None, None, missing or ["shared headless/headed context"]

def _comparison_context(record: dict) -> dict:
    return {
        "platform": record.get("platform"),
        "network_mode": record.get("network_mode"),
        "container": bool(record.get("container")),
    }

def _shared_context_pair(left_records: list[dict], right_records: list[dict]) -> tuple[dict | None, dict | None]:
    right_by_context: dict[tuple[object, object, bool], dict] = {}
    for record in right_records:
        right_by_context.setdefault(_record_context(record), record)
    for left in sorted(left_records, key=lambda record: tuple(str(part) for part in _record_context(record))):
        right = right_by_context.get(_record_context(left))
        if right is not None:
            return left, right
    return None, None

def _shared_context_pairs(left_records: list[dict], right_records: list[dict]) -> list[tuple[dict, dict]]:
    right_by_context: dict[tuple[object, object, bool], dict] = {}
    for record in right_records:
        right_by_context.setdefault(_record_context(record), record)
    pairs = []
    for left in sorted(left_records, key=lambda record: tuple(str(part) for part in _record_context(record))):
        right = right_by_context.get(_record_context(left))
        if right is not None:
            pairs.append((left, right))
    return pairs

def _webgl_comparison_id(record: dict) -> str:
    context = _comparison_context(record)
    if context == {"platform": "linux-x64", "network_mode": "direct", "container": True}:
        return "webgl_metadata_cross_detector"
    container = "docker" if context["container"] else "host"
    return f"webgl_metadata_cross_detector:{context['platform']}:{context['network_mode']}:{container}"


def _numeric_metric_deltas(left: dict, right: dict) -> dict:
    deltas = {}
    for key in sorted(set(left) & set(right)):
        if isinstance(left[key], (int, float)) and isinstance(right[key], (int, float)):
            deltas[key] = right[key] - left[key]
    return deltas

def _collect_audio_metric_records(evidence_rows: list[dict]) -> list[dict]:
    records = []
    for evidence in evidence_rows:
        for result in evidence.get("results", []):
            values = result.get("normalized_values", {})
            if canonical_surface(result.get("surface", "")) != "audio":
                continue
            if not all(field in values for field in ("freq", "gain", "sum", "time", "trap", "unique")):
                continue
            records.append({
                "detector_id": evidence["detector"]["detector_id"],
                "display_mode": _evidence_display(evidence),
                **_evidence_context(evidence),
                "run_id": evidence["run_id"],
                "metrics": {key: values[key] for key in ("freq", "gain", "sum", "time", "trap", "unique")},
            })
    return records

def _collect_detector_audio_probe_records(evidence_rows: list[dict], detector_id: str) -> list[dict]:
    records = []
    for evidence in evidence_rows:
        detector = evidence.get("detector", {})
        if detector.get("detector_id") != detector_id:
            continue
        for result in evidence.get("results", []):
            values = result.get("normalized_values", {})
            if canonical_surface(result.get("surface", "")) != "audio":
                continue
            if not all(field in values for field in ("sampleRate", "length", "sum", "sumAbs")):
                continue
            records.append({
                "detector_id": detector_id,
                "display_mode": _evidence_display(evidence),
                **_evidence_context(evidence),
                "run_id": evidence["run_id"],
                "metrics": {key: values[key] for key in ("sampleRate", "length", "sum", "sumAbs")},
            })
    return records


def _collect_browserleaks_audio_probe_records(evidence_rows: list[dict]) -> list[dict]:
    return _collect_detector_audio_probe_records(evidence_rows, "browserleaks")

def _collect_browserleaks_audio_page_context_records(evidence_rows: list[dict]) -> list[dict]:
    records = []
    required = (
        "channelCount",
        "channelCountMode",
        "channelInterpretation",
        "fftSize",
        "frequencyBinCount",
        "maxChannelCount",
        "maxDecibels",
        "minDecibels",
        "numberOfInputs",
        "numberOfOutputs",
        "sampleRate",
        "smoothingTimeConstant",
        "state",
    )
    for evidence in evidence_rows:
        detector = evidence.get("detector", {})
        if detector.get("detector_id") != "browserleaks":
            continue
        for result in evidence.get("results", []):
            values = result.get("normalized_values", {})
            if canonical_surface(result.get("surface", "")) != "audio":
                continue
            context_values = values.get("audioContextValues", {})
            if not all(field in context_values for field in required):
                continue
            records.append({
                "display_mode": _evidence_display(evidence),
                **_evidence_context(evidence),
                "run_id": evidence["run_id"],
                "values": {key: context_values[key] for key in required},
            })
    return records


def _collect_font_metric_records(evidence_rows: list[dict]) -> list[dict]:
    records = []
    for evidence in evidence_rows:
        merged = {
            "detector_id": evidence["detector"]["detector_id"],
            "display_mode": _evidence_display(evidence),
            **_evidence_context(evidence),
            "run_id": evidence["run_id"],
            "candidate_count": None,
            "fonts": [],
            "glyph_sha256": None,
            "metrics_sha256": None,
        }
        for result in evidence.get("results", []):
            values = result.get("normalized_values", {})
            if canonical_surface(result.get("surface", "")) != "fonts":
                continue
            if "candidateCount" in values:
                merged["candidate_count"] = values["candidateCount"]
            if "metricRows" in values:
                merged["fonts"] = sorted(row.get("font") for row in values.get("metricRows", []) if row.get("font"))
            if "glyphSha256" in values:
                merged["glyph_sha256"] = values["glyphSha256"]
            if "metricsSha256" in values:
                merged["metrics_sha256"] = values["metricsSha256"]
        if merged["fonts"] or merged["glyph_sha256"] or merged["metrics_sha256"]:
            records.append(merged)
    return records

def _collect_font_availability_records(evidence_rows: list[dict], detector_id: str) -> list[dict]:
    records = []
    for evidence in evidence_rows:
        detector = evidence.get("detector", {})
        if detector.get("detector_id") != detector_id:
            continue
        for result in evidence.get("results", []):
            values = result.get("normalized_values", {})
            if canonical_surface(result.get("surface", "")) != "fonts":
                continue
            checks = values.get("checks")
            if not isinstance(checks, dict):
                continue
            records.append({
                "detector_id": detector_id,
                "display_mode": _evidence_display(evidence),
                **_evidence_context(evidence),
                "run_id": evidence["run_id"],
                "checks": {key: bool(value) for key, value in sorted(checks.items())},
                "true_count": values.get("true_count"),
                "false_count": values.get("false_count"),
            })
    return records

WEBGL_REQUIRED_METADATA_FIELDS = ("extensionCount", "extensionSha256", "parameterSha256", "precisionSha256", "pixelSha256")
WEBGL_HASH_METADATA_FIELDS = ("extensionSha256", "parameterSha256", "precisionSha256", "pixelSha256")


def _collect_webgl_records(evidence_rows: list[dict]) -> list[dict]:
    records = []
    for evidence in evidence_rows:
        detector = evidence.get("detector", {})
        for result in evidence.get("results", []):
            values = result.get("normalized_values", {})
            if canonical_surface(result.get("surface", "")) != "webgl":
                continue
            evidence_status = evidence.get("status")
            result_status = result.get("status")
            if evidence_status not in {"pass", "passed"} or result_status not in {"pass", "passed"}:
                continue
            if not isinstance(values, dict):
                continue
            records.append({
                "detector_id": detector.get("detector_id"),
                "display_mode": _evidence_display(evidence),
                **_evidence_context(evidence),
                "run_id": evidence["run_id"],
                "status": "passed",
                "vendor": values.get("vendor"),
                "renderer": values.get("renderer"),
                "extension_count": values.get("extensionCount"),
                "hashes": {field: values.get(field) for field in WEBGL_HASH_METADATA_FIELDS},
                "missing_metadata": [field for field in WEBGL_REQUIRED_METADATA_FIELDS if values.get(field) is None],
            })
    return records

def _collect_webrtc_records(evidence_rows: list[dict], detector_id: str) -> list[dict]:
    records = []
    required = ("candidateCount", "types", "ipLiteralCount", "privateIpLiteralCount", "publicIpLiteralCount", "rawCandidateSha256")
    for evidence in evidence_rows:
        detector = evidence.get("detector", {})
        if detector.get("detector_id") != detector_id:
            continue
        for result in evidence.get("results", []):
            values = result.get("normalized_values", {})
            if canonical_surface(result.get("surface", "")) != "webrtc":
                continue
            if not all(field in values for field in required):
                continue
            records.append({
                "detector_id": detector_id,
                "display_mode": _evidence_display(evidence),
                **_evidence_context(evidence),
                "run_id": evidence["run_id"],
                "candidate_count": values["candidateCount"],
                "types": sorted(values.get("types") or []),
                "ip_literal_count": values["ipLiteralCount"],
                "private_ip_literal_count": values["privateIpLiteralCount"],
                "public_ip_literal_count": values["publicIpLiteralCount"],
                "raw_candidate_sha256": values["rawCandidateSha256"],
            })
    return records

PIXELSCAN_PAGE_SCORE_CHECKS = {
    "pixelscan_fingerprint_page_status",
    "pixelscan_page_verdict",
}


PIXELSCAN_ISOLATION_FIELDS = [
    "verdict",
    "fingerprint",
    "botCheck",
    "proxy",
    "location_redacted",
    "audioContextHash",
    "canvasHash",
    "fontHash",
    "webglHash",
]

PIXELSCAN_ISOLATION_VARIANTS = [
    {
        "variant_id": "baseline-current",
        "purpose": "Reproduce the current Pixelscan final-verdict warning with the committed persona unchanged.",
        "fingerprint_overrides": {},
        "isolated_surfaces": [],
        "expected_arg_effect": "keeps current active canvas/audio/WebGL/font knobs",
    },
    {
        "variant_id": "canvas-off",
        "purpose": "Determine whether native Canvas 2D readback/encoding perturbation is the Pixelscan masking trigger.",
        "fingerprint_overrides": {"canvas_noise": 0},
        "isolated_surfaces": ["canvas"],
        "expected_arg_effect": "omits --fingerprint-canvas-noise",
    },
    {
        "variant_id": "audio-off",
        "purpose": "Determine whether native WebAudio AudioBuffer/AnalyserNode perturbation is the Pixelscan masking trigger.",
        "fingerprint_overrides": {"audio_noise": 0},
        "isolated_surfaces": ["audio"],
        "expected_arg_effect": "omits --fingerprint-audio-noise",
    },
    {
        "variant_id": "webgl-native",
        "purpose": "Determine whether WebGL vendor/renderer string spoofing is inconsistent with real params/extensions/precision/pixels.",
        "fingerprint_overrides": {"webgl_vendor": "", "webgl_renderer": ""},
        "isolated_surfaces": ["webgl"],
        "expected_arg_effect": "omits --fingerprint-webgl-vendor and --fingerprint-webgl-renderer",
    },
    {
        "variant_id": "fonts-native",
        "purpose": "Determine whether FontFaceSet.check allowlist spoofing diverges from installed Linux font metrics/glyph corpus.",
        "fingerprint_overrides": {"fonts": [], "fonts_dir": ""},
        "isolated_surfaces": ["fonts"],
        "expected_arg_effect": "omits --fingerprint-fonts-list and --fingerprint-fonts-dir",
    },
    {
        "variant_id": "passive-native-surfaces",
        "purpose": "Disable all currently active Pixelscan masking candidates to test whether the final verdict returns to consistent.",
        "fingerprint_overrides": {
            "audio_noise": 0,
            "canvas_noise": 0,
            "webgl_vendor": "",
            "webgl_renderer": "",
            "fonts": [],
            "fonts_dir": "",
            "native_mode": "strict",
        },
        "isolated_surfaces": ["audio", "canvas", "webgl", "fonts"],
        "expected_arg_effect": "sets native_mode=strict so the wrapper suppresses active audio/canvas/WebGL/font spoofing flags while keeping UA/UA-CH/locale/timezone/screen/hardware unchanged",
    },
    {
        "variant_id": "minimal-native-control",
        "purpose": "Strip BrowseForge persona overrides to test whether the patched headless Docker runtime remains inconsistent before reintroducing fingerprint surfaces.",
        "fingerprint_overrides": {
            "accept_language": "",
            "audio_noise": 0,
            "canvas_noise": 0,
            "device_memory_gb": 0,
            "fonts": [],
            "fonts_dir": "",
            "hardware_concurrency": 0,
            "locale": "",
            "native_mode": "strict",
            "platform": "",
            "plugins_pdf": "",
            "screen_avail_height": 0,
            "screen_avail_width": 0,
            "screen_height": 0,
            "screen_width": 0,
            "storage_quota_mb": 0,
            "timezone": "",
            "ua_architecture": "",
            "ua_bitness": "",
            "ua_full_version": "",
            "ua_model": "",
            "ua_platform": "",
            "ua_platform_version": "",
            "ua_mobile": False,
            "ua_wow64": False,
            "user_agent": "",
            "webgl_renderer": "",
            "webgl_vendor": "",
            "webrtc_ip": "",
        },
        "isolated_surfaces": ["persona", "audio", "canvas", "webgl", "fonts"],
        "expected_arg_effect": "omits BrowseForge persona and high-risk spoofing switches while retaining only browser launch policy needed for collection",
    },
]


def pixelscan_variant_plan(args) -> int:
    generated_at = args.generated_at or dt.datetime.now(dt.timezone.utc).isoformat()
    payload = {
        "runtime_id": "browseforge-chromium",
        "schema_version": "1.0",
        "generated_at": generated_at,
        "detector_id": "pixelscan",
        "decision": "Run direct-network rows first because committed direct evidence already reproduces masking/inconsistent; repeat only decisive rows through an external proxy relay after a trigger is isolated.",
        "secret_policy": {
            "commit_raw_proxy_url": False,
            "commit_raw_ip": False,
            "commit_raw_page_text": False,
            "allowed_committed_fields": PIXELSCAN_ISOLATION_FIELDS,
        },
        "constant_controls": [
            "runtime artifact",
            "profile seed",
            "UA and UA-CH",
            "locale and Accept-Language",
            "timezone",
            "screen and DPR",
            "hardwareConcurrency and deviceMemory",
            "storage quota",
            "navigator.webdriver",
        ],
        "collection_order": [row["variant_id"] for row in PIXELSCAN_ISOLATION_VARIANTS],
        "variants": PIXELSCAN_ISOLATION_VARIANTS,
        "pairwise_followup": [
            ["canvas", "audio"],
            ["canvas", "webgl"],
            ["fonts", "webgl"],
            ["audio", "fonts"],
        ],
    }
    out = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        print(out, end="")
    return 0

def pixelscan_materialize_variants(args) -> int:
    generated_at = args.generated_at or dt.datetime.now(dt.timezone.utc).isoformat()
    base_config_path = Path(args.base_config)
    output_dir = Path(args.output_dir)
    manifest_path = Path(args.manifest_output) if args.manifest_output else output_dir / "manifest.json"
    base_config = json.loads(base_config_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for variant in PIXELSCAN_ISOLATION_VARIANTS:
        variant_id = variant["variant_id"]
        config = copy.deepcopy(base_config)
        fingerprint = config.setdefault("fingerprint", {})
        for key, value in variant["fingerprint_overrides"].items():
            fingerprint[key] = value
        config["profile_id"] = f"{config.get('profile_id', 'pixelscan')}-{variant_id}"
        config_path = output_dir / f"{variant_id}.json"
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        entries.append({
            "variant_id": variant_id,
            "config_path": str(config_path),
            "fingerprint_overrides": variant["fingerprint_overrides"],
            "isolated_surfaces": variant["isolated_surfaces"],
        })
    manifest = {
        "runtime_id": "browseforge-chromium",
        "schema_version": "1.0",
        "generated_at": generated_at,
        "detector_id": "pixelscan",
        "base_config_path": str(base_config_path),
        "secret_policy": {
            "manifest_contains_proxy_secret": False,
            "variant_configs_are_local_only": True,
        },
        "variants": entries,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0

def _pixelscan_variant_raw_path(input_dir: Path, variant_id: str) -> Path | None:
    normalized = variant_id.replace("-", "_")
    matches = sorted(input_dir.glob(f"*{normalized}*.json")) + sorted(input_dir.glob(f"*{variant_id}*.json"))
    return matches[0] if matches else None


def _pixelscan_variant_observation(record: dict) -> dict:
    observed = record.get("observed", {})
    page = observed.get("pixelscanPage") or {}
    return {
        "status": record.get("status"),
        "finding": _bounded_redacted_value(record.get("finding", "")),
        "severity": record.get("severity"),
        "verdict": page.get("verdict"),
        "fingerprint": page.get("fingerprint"),
        "botCheck": page.get("botCheck"),
        "proxy": page.get("proxy"),
        "location_redacted": _bounded_redacted_value(page.get("location", "")),
        "audioContextHash": page.get("audioContextHash"),
        "canvasHash": page.get("canvasHash"),
        "fontHash": page.get("fontHash"),
        "webglHash": page.get("webglHash"),
    }

def _pixelscan_variant_summary_row(input_dir: Path, variant: dict) -> dict:
    variant_id = variant["variant_id"]
    raw_path = _pixelscan_variant_raw_path(input_dir, variant_id)
    row = {
        "variant_id": variant_id,
        "isolated_surfaces": variant["isolated_surfaces"],
        "fingerprint_overrides": variant["fingerprint_overrides"],
        "raw_capture_committed": False,
        "raw_capture_path_committed": False,
    }
    if raw_path is None:
        row["status"] = "missing"
        row["observation"] = {}
    else:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        records = raw.get("records", [])
        row["status"] = "observed" if records else "empty"
        row["observation"] = _pixelscan_variant_observation(records[0]) if records else {}
    return row

def _pixelscan_all_inconsistent(rows: list[dict]) -> bool:
    observed = [row.get("observation", {}) for row in rows if row.get("status") == "observed"]
    return bool(observed) and all(row.get("verdict") == "inconsistent" and row.get("fingerprint") == "Masking detected" for row in observed)

def _pixelscan_all_bot_clean(rows: list[dict]) -> bool:
    observed = [row.get("observation", {}) for row in rows if row.get("status") == "observed"]
    return bool(observed) and all(row.get("botCheck") == "No automated behavior detected" for row in observed)



def pixelscan_variant_summary(args) -> int:
    generated_at = args.generated_at or dt.datetime.now(dt.timezone.utc).isoformat()
    input_dir = Path(args.input_dir)
    payload = {
        "runtime_id": "browseforge-chromium",
        "schema_version": "1.0",
        "generated_at": generated_at,
        "detector_id": "pixelscan",
        "secret_policy": {
            "committed_raw_cdp_capture": False,
            "committed_raw_page_text": False,
            "committed_raw_ip": False,
            "allowed_committed_fields": PIXELSCAN_ISOLATION_FIELDS,
        },
        "variants": [],
        "conclusion": "",
    }
    for variant in PIXELSCAN_ISOLATION_VARIANTS:
        payload["variants"].append(_pixelscan_variant_summary_row(input_dir, variant))
    if getattr(args, "headed_input_dir", None):
        headed_input_dir = Path(args.headed_input_dir)
        payload["headed_controls"] = [
            {
                **_pixelscan_variant_summary_row(headed_input_dir, variant),
                "display_mode": "headed_xvfb",
            }
            for variant in PIXELSCAN_ISOLATION_VARIANTS
        ]
    all_inconsistent = _pixelscan_all_inconsistent(payload["variants"])
    all_bot_clean = _pixelscan_all_bot_clean(payload["variants"])
    if all_inconsistent and all_bot_clean:
        payload["conclusion"] = "UA/UA-CH coherent direct headless Docker variants clear Pixelscan botCheck, but every canvas/audio/WebGL/font isolation variant plus the minimal native control still reports inconsistent/masking."
    elif all_inconsistent:
        payload["conclusion"] = "All current direct headless Docker variants still report Pixelscan inconsistent/masking; active canvas/audio/WebGL/font toggles are not sufficient root-cause isolation."
    else:
        payload["conclusion"] = "Pixelscan variant outcomes are mixed; inspect per-variant verdict, fingerprint, and botCheck fields before changing native surfaces."
    headed_controls = payload.get("headed_controls", [])
    if headed_controls and _pixelscan_all_inconsistent(headed_controls) and _pixelscan_all_bot_clean(headed_controls):
        payload["conclusion"] += " Headed/Xvfb controls also clear botCheck while remaining inconsistent/masking, so the remaining Pixelscan finding is not headless-only."
    out = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        print(out, end="")
    return 0



def _collect_pixelscan_score_records(evidence_rows: list[dict]) -> list[dict]:
    records = []
    required = ("verdict", "fingerprint", "audioContextHash", "fontHash")
    for evidence in evidence_rows:
        detector = evidence.get("detector", {})
        if detector.get("detector_id") != "pixelscan":
            continue
        for result in evidence.get("results", []):
            values = result.get("normalized_values", {})
            if result.get("detector_check") not in PIXELSCAN_PAGE_SCORE_CHECKS:
                continue
            if not all(values.get(field) for field in required):
                continue
            records.append({
                "display_mode": _evidence_display(evidence),
                "run_id": evidence["run_id"],
                "verdict": values["verdict"],
                "fingerprint": values["fingerprint"],
                "bot_check": values.get("botCheck"),
                "audio_context_hash": values["audioContextHash"],
                "font_hash": values["fontHash"],
            })
    return records





def detector_score_comparisons(evidence_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    comparisons = []
    gaps = []

    creepjs_audio_records = [
        record
        for record in _collect_audio_metric_records(evidence_rows)
        if record["detector_id"] == "creepjs"
    ]
    headless, headed, missing = _display_pair_by_context(creepjs_audio_records)
    if headless and headed:
        deltas = _numeric_metric_deltas(headless["metrics"], headed["metrics"])
        identical = all(abs(value) <= 1e-9 for value in deltas.values())
        matching_metrics = sorted(metric for metric, delta in deltas.items() if abs(delta) <= 1e-9)
        drift_metrics = sorted(metric for metric, delta in deltas.items() if abs(delta) > 1e-9)
        trap_only_drift = drift_metrics == ["trap"]
        comparisons.append({
            "comparison_id": "creepjs_audio_headless_vs_headed",
            "detector_id": "creepjs",
            "surface": "audio",
            "status": "pass" if identical else "warning",
            "left_run_id": headless["run_id"],
            "right_run_id": headed["run_id"],
            "left_context": _comparison_context(headless),
            "right_context": _comparison_context(headed),
            "metric_deltas": deltas,
            "matching_metrics": matching_metrics,
            "drift_metrics": drift_metrics,
            "trap_only_drift": trap_only_drift,
            "finding": "CreepJS audio metrics match across headless/headed evidence." if identical else ("CreepJS audio drift is isolated to the trap metric across headless/headed evidence; native AudioContext trap parity remains required." if trap_only_drift else "CreepJS audio metrics differ across headless/headed evidence; release-grade baseline comparison remains required."),
        })
    else:
        gaps.append({
            "gap_id": "creepjs_audio_headless_vs_headed",
            "surface": "audio",
            "missing": missing,
            "finding": "CreepJS audio comparison requires both headless and headed sanitized evidence.",
        })

    browserleaks_audio_records = _collect_browserleaks_audio_probe_records(evidence_rows)
    headless, headed, missing = _display_pair_by_context(browserleaks_audio_records)
    if headless and headed:
        deltas = _numeric_metric_deltas(headless["metrics"], headed["metrics"])
        identical = all(abs(value) <= 1e-9 for value in deltas.values())
        comparisons.append({
            "comparison_id": "browserleaks_audio_headless_vs_headed",
            "detector_id": "browserleaks",
            "surface": "audio",
            "status": "pass" if identical else "warning",
            "left_run_id": headless["run_id"],
            "right_run_id": headed["run_id"],
            "left_context": _comparison_context(headless),
            "right_context": _comparison_context(headed),
            "metric_deltas": deltas,
            "finding": "BrowserLeaks bounded AudioContext summaries match across headless/headed evidence." if identical else "BrowserLeaks bounded AudioContext summaries differ across headless/headed evidence; release-grade BrowserLeaks audio score baseline remains required.",
        })
    else:
        gaps.append({
            "gap_id": "browserleaks_audio_headless_vs_headed",
            "surface": "audio",
            "detector_id": "browserleaks",
            "missing": missing,
            "finding": "BrowserLeaks audio comparison requires both headless and headed sanitized AudioContext summary evidence.",
        })

    browserleaks_audio_page_records = _collect_browserleaks_audio_page_context_records(evidence_rows)
    headless, headed, missing = _display_pair_by_context(browserleaks_audio_page_records)
    if headless and headed:
        value_matches = {
            key: headless["values"].get(key) == headed["values"].get(key)
            for key in sorted(set(headless["values"]) | set(headed["values"]))
        }
        all_match = all(value_matches.values())
        comparisons.append({
            "comparison_id": "browserleaks_javascript_audio_page_context_headless_vs_headed",
            "detector_id": "browserleaks",
            "surface": "audio",
            "status": "pass" if all_match else "warning",
            "left_run_id": headless["run_id"],
            "right_run_id": headed["run_id"],
            "left_context": _comparison_context(headless),
            "right_context": _comparison_context(headed),
            "field_matches": value_matches,
            "finding": "BrowserLeaks JavaScript Web Audio page AudioContext/AnalyserNode fields match across headless/headed evidence." if all_match else "BrowserLeaks JavaScript Web Audio page AudioContext/AnalyserNode fields differ across headless/headed evidence; release-grade BrowserLeaks audio score baseline remains required.",
        })
    else:
        gaps.append({
            "gap_id": "browserleaks_javascript_audio_page_context_headless_vs_headed",
            "surface": "audio",
            "detector_id": "browserleaks",
            "missing": missing,
            "finding": "BrowserLeaks JavaScript Web Audio page comparison requires both headless and headed sanitized AudioContext/AnalyserNode field evidence.",
        })

    pixelscan_audio_records = _collect_detector_audio_probe_records(evidence_rows, "pixelscan")
    headless, headed, missing = _display_pair_by_context(pixelscan_audio_records)
    if headless and headed:
        deltas = _numeric_metric_deltas(headless["metrics"], headed["metrics"])
        identical = all(abs(value) <= 1e-9 for value in deltas.values())
        comparisons.append({
            "comparison_id": "pixelscan_audio_headless_vs_headed",
            "detector_id": "pixelscan",
            "surface": "audio",
            "status": "pass" if identical else "warning",
            "left_run_id": headless["run_id"],
            "right_run_id": headed["run_id"],
            "left_context": _comparison_context(headless),
            "right_context": _comparison_context(headed),
            "metric_deltas": deltas,
            "finding": "Pixelscan bounded AudioContext summaries match across headless/headed evidence." if identical else "Pixelscan bounded AudioContext summaries differ across headless/headed evidence; release-grade Pixelscan baseline remains required.",
        })
    else:
        gaps.append({
            "gap_id": "pixelscan_audio_headless_vs_headed",
            "surface": "audio",
            "detector_id": "pixelscan",
            "missing": missing,
            "finding": "Pixelscan audio comparison requires both headless and headed sanitized AudioContext summary evidence.",
        })

    font_records = _collect_font_metric_records(evidence_rows)
    browserleaks_font_candidates = [record for record in font_records if record["detector_id"] == "browserleaks"]
    creepjs_font_candidates = [record for record in font_records if record["detector_id"] == "creepjs"]
    browserleaks_fonts, creepjs_fonts = _shared_context_pair(browserleaks_font_candidates, creepjs_font_candidates)
    if browserleaks_fonts and creepjs_fonts:
        same_glyph = bool(browserleaks_fonts["glyph_sha256"] and browserleaks_fonts["glyph_sha256"] == creepjs_fonts["glyph_sha256"])
        same_metrics = bool(browserleaks_fonts["metrics_sha256"] and browserleaks_fonts["metrics_sha256"] == creepjs_fonts["metrics_sha256"])
        same_fonts = browserleaks_fonts["fonts"] == creepjs_fonts["fonts"]
        comparisons.append({
            "comparison_id": "browserleaks_creepjs_font_metrics",
            "surface": "fonts",
            "status": "pass" if same_glyph and same_metrics and same_fonts else "warning",
            "left_detector_id": "browserleaks",
            "left_run_id": browserleaks_fonts["run_id"],
            "right_detector_id": "creepjs",
            "right_run_id": creepjs_fonts["run_id"],
            "left_context": _comparison_context(browserleaks_fonts),
            "right_context": _comparison_context(creepjs_fonts),
            "candidate_count_match": browserleaks_fonts["candidate_count"] == creepjs_fonts["candidate_count"],
            "font_list_match": same_fonts,
            "glyph_sha256_match": same_glyph,
            "metrics_sha256_match": same_metrics,
            "finding": "BrowserLeaks/CreepJS font metric evidence matches." if same_glyph and same_metrics and same_fonts else "BrowserLeaks/CreepJS font evidence is only partially comparable; release-grade font corpus parity remains required.",
        })
    else:
        missing = (
            ["shared browserleaks/creepjs context"]
            if browserleaks_font_candidates and creepjs_font_candidates
            else sorted(det for det, record in {"browserleaks": browserleaks_fonts, "creepjs": creepjs_fonts}.items() if record is None)
        )
        gaps.append({
            "gap_id": "browserleaks_creepjs_font_metrics",
            "surface": "fonts",
            "missing": missing,
            "finding": "Font comparison requires sanitized BrowserLeaks and CreepJS font metric evidence from the same platform/network/container context.",
        })

    browserleaks_font_records = [
        record
        for record in font_records
        if record["detector_id"] == "browserleaks"
    ]
    headless, headed, missing = _display_pair_by_context(browserleaks_font_records)
    if headless and headed:
        same_fonts = headless["fonts"] == headed["fonts"]
        same_glyph = bool(headless["glyph_sha256"] and headless["glyph_sha256"] == headed["glyph_sha256"])
        same_metrics = bool(headless["metrics_sha256"] and headless["metrics_sha256"] == headed["metrics_sha256"])
        all_match = same_fonts and same_glyph and same_metrics and headless["candidate_count"] == headed["candidate_count"]
        comparisons.append({
            "comparison_id": "browserleaks_fonts_headless_vs_headed",
            "detector_id": "browserleaks",
            "surface": "fonts",
            "status": "pass" if all_match else "warning",
            "left_run_id": headless["run_id"],
            "right_run_id": headed["run_id"],
            "left_context": _comparison_context(headless),
            "right_context": _comparison_context(headed),
            "candidate_count_match": headless["candidate_count"] == headed["candidate_count"],
            "font_list_match": same_fonts,
            "glyph_sha256_match": same_glyph,
            "metrics_sha256_match": same_metrics,
            "finding": "BrowserLeaks bounded font metric and glyph hashes match across headless/headed evidence." if all_match else "BrowserLeaks bounded font metric or glyph hashes differ across headless/headed evidence; release-grade font corpus parity remains required.",
        })
    else:
        gaps.append({
            "gap_id": "browserleaks_fonts_headless_vs_headed",
            "surface": "fonts",
            "detector_id": "browserleaks",
            "missing": missing,
            "finding": "BrowserLeaks font comparison requires both headless and headed sanitized font metric evidence.",
        })

    pixelscan_font_records = _collect_font_availability_records(evidence_rows, "pixelscan")
    headless, headed, missing = _display_pair_by_context(pixelscan_font_records)
    if headless and headed:
        same_checks = headless["checks"] == headed["checks"]
        comparisons.append({
            "comparison_id": "pixelscan_fonts_headless_vs_headed",
            "detector_id": "pixelscan",
            "surface": "fonts",
            "status": "pass" if same_checks else "warning",
            "left_run_id": headless["run_id"],
            "right_run_id": headed["run_id"],
            "left_context": _comparison_context(headless),
            "right_context": _comparison_context(headed),
            "font_check_match": same_checks,
            "true_count_delta": headed["true_count"] - headless["true_count"] if isinstance(headless["true_count"], int) and isinstance(headed["true_count"], int) else None,
            "false_count_delta": headed["false_count"] - headless["false_count"] if isinstance(headless["false_count"], int) and isinstance(headed["false_count"], int) else None,
            "finding": "Pixelscan font availability checks match across headless/headed evidence." if same_checks else "Pixelscan font availability checks differ across headless/headed evidence; release-grade Pixelscan font baseline remains required.",
        })
    else:
        gaps.append({
            "gap_id": "pixelscan_fonts_headless_vs_headed",
            "surface": "fonts",
            "detector_id": "pixelscan",
            "missing": missing,
            "finding": "Pixelscan font comparison requires both headless and headed sanitized font availability evidence.",
        })

    browserleaks_webrtc_records = _collect_webrtc_records(evidence_rows, "browserleaks")
    headless, headed, missing = _display_pair_by_context(browserleaks_webrtc_records)
    if headless and headed:
        value_matches = {
            "candidateCount": headless["candidate_count"] == headed["candidate_count"],
            "types": headless["types"] == headed["types"],
            "ipLiteralCount": headless["ip_literal_count"] == headed["ip_literal_count"],
            "privateIpLiteralCount": headless["private_ip_literal_count"] == headed["private_ip_literal_count"],
            "publicIpLiteralCount": headless["public_ip_literal_count"] == headed["public_ip_literal_count"],
        }
        all_match = all(value_matches.values())
        comparisons.append({
            "comparison_id": "browserleaks_webrtc_headless_vs_headed",
            "detector_id": "browserleaks",
            "surface": "webrtc",
            "status": "pass" if all_match else "warning",
            "left_run_id": headless["run_id"],
            "right_run_id": headed["run_id"],
            "left_context": _comparison_context(headless),
            "right_context": _comparison_context(headed),
            "field_matches": value_matches,
            "left_raw_candidate_sha256": headless["raw_candidate_sha256"],
            "right_raw_candidate_sha256": headed["raw_candidate_sha256"],
            "finding": "BrowserLeaks bounded WebRTC candidate metadata matches across headless/headed evidence without committed IP literals." if all_match else "BrowserLeaks bounded WebRTC candidate metadata differs across headless/headed evidence; external proxy/geolocation detector evidence remains required.",
        })
    else:
        gaps.append({
            "gap_id": "browserleaks_webrtc_headless_vs_headed",
            "surface": "webrtc",
            "detector_id": "browserleaks",
            "missing": missing,
            "finding": "BrowserLeaks WebRTC comparison requires both headless and headed sanitized ICE candidate metadata evidence.",
        })


    webgl_records = _collect_webgl_records(evidence_rows)
    incomplete_webgl = [record for record in webgl_records if record["status"] == "passed" and record["missing_metadata"]]
    if incomplete_webgl:
        gaps.append({
            "gap_id": "webgl_metadata_hashes_missing",
            "surface": "webgl",
            "detectors": sorted({record["detector_id"] for record in incomplete_webgl if record["detector_id"]}),
            "missing_records": [
                {
                    "detector_id": record["detector_id"],
                    "run_id": record["run_id"],
                    "missing": record["missing_metadata"],
                }
                for record in incomplete_webgl
            ],
            "finding": "WebGL comparison requires sanitized extension count, extension hash, parameter hash, shader precision hash, and rendered pixel hash for each committed WebGL evidence row.",
        })
    complete_webgl = [record for record in webgl_records if not record["missing_metadata"]]
    browserleaks_webgl_candidates = [record for record in complete_webgl if record["detector_id"] == "browserleaks"]
    webgl_peer_candidates = [record for record in complete_webgl if record["detector_id"] != "browserleaks"]
    webgl_pairs = _shared_context_pairs(browserleaks_webgl_candidates, webgl_peer_candidates)
    if webgl_pairs:
        for browserleaks_webgl, comparison_peer in webgl_pairs:
            hash_matches = {
                field: browserleaks_webgl["hashes"][field] == comparison_peer["hashes"][field]
                for field in WEBGL_HASH_METADATA_FIELDS
            }
            extension_count_match = browserleaks_webgl["extension_count"] == comparison_peer["extension_count"]
            extension_profile_match = extension_count_match and hash_matches["extensionSha256"]
            vendor_renderer_match = (
                browserleaks_webgl["vendor"] == comparison_peer["vendor"]
                and browserleaks_webgl["renderer"] == comparison_peer["renderer"]
            )
            all_match = vendor_renderer_match and extension_profile_match and all(hash_matches.values())
            comparisons.append({
                "comparison_id": _webgl_comparison_id(browserleaks_webgl),
                "surface": "webgl",
                "status": "pass" if all_match else "warning",
                "left_detector_id": browserleaks_webgl["detector_id"],
                "left_run_id": browserleaks_webgl["run_id"],
                "right_detector_id": comparison_peer["detector_id"],
                "right_run_id": comparison_peer["run_id"],
                "left_context": _comparison_context(browserleaks_webgl),
                "right_context": _comparison_context(comparison_peer),
                "vendor_renderer_match": vendor_renderer_match,
                "extension_count_match": extension_count_match,
                "extension_profile_match": extension_profile_match,
                "hash_matches": hash_matches,
                "finding": "WebGL vendor/renderer, extension profile, parameter, shader precision, and rendered pixel metadata match across BrowserLeaks and peer detector evidence." if all_match else "WebGL metadata differs across BrowserLeaks and peer detector evidence; release-grade WebGL profile parity remains required.",
            })
    else:
        missing = (
            ["shared browserleaks/peer context"]
            if browserleaks_webgl_candidates and webgl_peer_candidates
            else sorted(
                label
                for label, records in {
                    "browserleaks_complete_webgl_metadata": browserleaks_webgl_candidates,
                    "peer_complete_webgl_metadata": webgl_peer_candidates,
                }.items()
                if not records
            )
        )
        gaps.append({
            "gap_id": "webgl_cross_detector_metadata_comparison_missing",
            "surface": "webgl",
            "missing": missing,
            "finding": "WebGL cross-detector comparison requires complete BrowserLeaks metadata and peer detector metadata from the same platform/network/container context.",
        })
    return comparisons, gaps

def _native_headed_font_corpus_missing(evidence_rows: list[dict]) -> list[str]:
    font_records = _collect_font_metric_records(evidence_rows)
    browserleaks_native = any(
        record["detector_id"] == "browserleaks"
        and record.get("display_mode") == "headed"
        and record.get("platform") in {"linux-x64", "macos-arm64"}
        and record.get("network_mode") == "direct"
        and record.get("container") is False
        for record in font_records
    )
    creepjs_native = any(
        record["detector_id"] == "creepjs"
        and record.get("display_mode") == "headed"
        and record.get("platform") in {"linux-x64", "macos-arm64"}
        and record.get("network_mode") == "direct"
        and record.get("container") is False
        for record in font_records
    )
    pixelscan_native = any(
        record.get("display_mode") == "headed"
        and record.get("platform") in {"linux-x64", "macos-arm64"}
        and record.get("network_mode") == "direct"
        and record.get("container") is False
        for record in _collect_font_availability_records(evidence_rows, "pixelscan")
    )
    missing = []
    if not browserleaks_native:
        missing.append("browserleaks native headed direct font metrics")
    if not creepjs_native:
        missing.append("creepjs native headed direct font metrics")
    if not pixelscan_native:
        missing.append("pixelscan native headed direct font availability")
    return missing

def detector_score_baseline_gaps(evidence_rows: list[dict]) -> list[dict]:
    gaps = []
    missing_native_fonts = _native_headed_font_corpus_missing(evidence_rows)
    if missing_native_fonts:
        gaps.append({
            "gap_id": "native_headed_font_corpus_parity_missing",
            "surface": "fonts",
            "detector_id": "browserleaks,creepjs,pixelscan",
            "missing": missing_native_fonts,
            "finding": "Native headed font corpus parity is incomplete; Linux Docker/Xvfb comparisons are not enough for release-grade font evidence.",
            "required_evidence": "native headed Linux/macOS font corpus and detector-score comparison",
        })
    if not _collect_pixelscan_score_records(evidence_rows):
        gaps.insert(1, {
            "gap_id": "pixelscan_audio_font_score_baseline_missing",
            "surface": "audio,fonts",
            "detector_id": "pixelscan",
            "finding": "Pixelscan AudioContext/fonts score baseline is not yet committed for the packaged runtime.",
            "required_evidence": "sanitized Pixelscan score comparison covering audio/font surfaces",
        })
    return gaps


def compare_scores(args):
    root = Path(args.evidence_root)
    evidence_rows = []
    for path in sorted(root.glob("**/*.json")):
        code, errors = validate_evidence_file(path)
        if code:
            for err in errors:
                print(err, file=sys.stderr)
            return code
        evidence_rows.append(load_json(path))
    comparisons, gaps = detector_score_comparisons(evidence_rows)
    baseline_gaps = detector_score_baseline_gaps(evidence_rows)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runtime_id": "browseforge-chromium",
        "release_grade": False,
        "evidence_count": len(evidence_rows),
        "comparisons": comparisons,
        "gaps": gaps,
        "baseline_gaps": baseline_gaps,
        "decision": "Offline comparisons summarize committed sanitized evidence only; Linux BrowserLeaks WebRTC bounded candidate metadata and WebGL cross-detector metadata now have passing comparisons, while live release-grade detector baselines, external proxy/geolocation evidence, and native/headed WebGL coverage remain required before release claims.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(out))
    return 0

def summary(args):
    root = Path(args.evidence_root)
    files = sorted(root.glob("**/*.json"))
    blocking = []
    rows = []
    evidence_rows = []
    for path in files:
        code, errors = validate_evidence_file(path)
        if code:
            return code
        evidence = load_json(path)
        evidence_rows.append(evidence)
        for result in evidence.get("results", []):
            if result.get("severity") in {"high", "critical"} and result.get("status") in {"fail", "warn"} and not result.get("accepted_risk_id"):
                blocking.append({"path": str(path), "surface": result.get("surface"), "severity": result.get("severity"), "finding": result.get("finding")})
        rows.append({"path": str(path), "detector_id": evidence["detector"]["detector_id"], "platform": evidence["target"]["platform"], "status": evidence["status"]})
    coverage_gaps = matrix_coverage_gaps(evidence_rows, args.platform)
    generated_at = args.generated_at or dt.datetime.now(dt.timezone.utc).isoformat()
    payload = {
        "generated_at": generated_at,
        "evidence_count": len(rows),
        "blocking_findings": blocking,
        "coverage_gap_count": len(coverage_gaps),
        "coverage_gaps": coverage_gaps,
        "coverage_platform": args.platform,
        "rows": rows,
    }
    Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0

def http_json(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read())

def ws_connect(url: str):
    if not url.startswith("ws://"):
        raise ValueError("only ws:// DevTools endpoints are supported")
    rest = url[len("ws://"):]
    hostport, path = rest.split("/", 1)
    host, port_s = hostport.rsplit(":", 1)
    sock = socket.create_connection((host, int(port_s)), timeout=10)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        f"GET /{path} HTTP/1.1\r\n"
        f"Host: {hostport}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode())
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise EOFError("websocket handshake closed")
        data += chunk
    if b" 101 " not in data.split(b"\r\n", 1)[0]:
        raise RuntimeError(data.decode(errors="replace"))
    return sock

def ws_send(sock: socket.socket, payload: object) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode()
    mask = os.urandom(4)
    header = bytearray([0x81])
    n = len(body)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", n))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", n))
    sock.sendall(bytes(header) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(body)))

def ws_recv(sock: socket.socket):
    header = sock.recv(2)
    if not header:
        raise EOFError("websocket closed")
    b1, b2 = header
    opcode = b1 & 0x0F
    masked = b2 & 0x80
    n = b2 & 0x7F
    if n == 126:
        n = struct.unpack("!H", sock.recv(2))[0]
    elif n == 127:
        n = struct.unpack("!Q", sock.recv(8))[0]
    mask = sock.recv(4) if masked else b""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise EOFError("websocket frame truncated")
        data += chunk
    if masked:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    if opcode == 8:
        raise EOFError("websocket closed")
    if opcode == 9:
        return ws_recv(sock)
    return json.loads(data.decode())

class CDPClient:
    def __init__(self, ws_url: str):
        self.sock = ws_connect(ws_url)
        self.next_id = 1

    def call(self, method: str, params: dict | None = None, *, session_id: str | None = None, timeout: int = 20):
        msg_id = self.next_id
        self.next_id += 1
        payload = {"id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params
        if session_id is not None:
            payload["sessionId"] = session_id
        ws_send(self.sock, payload)
        end = time.time() + timeout
        events = []
        while time.time() < end:
            self.sock.settimeout(max(0.1, end - time.time()))
            try:
                message = ws_recv(self.sock)
            except socket.timeout:
                break
            if message.get("id") == msg_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {}), events
            events.append(message)
        raise TimeoutError(method)

    def events_until(self, predicate, *, timeout: int = 30):
        end = time.time() + timeout
        events = []
        while time.time() < end:
            self.sock.settimeout(max(0.1, end - time.time()))
            try:
                msg = ws_recv(self.sock)
            except socket.timeout:
                continue
            events.append(msg)
            if predicate(msg):
                return events
        return events

def classify_sannysoft(value: dict) -> tuple[str, str, str]:
    text = value.get("text", "")
    ua = value.get("ua", "")
    webdriver_false = value.get("webdriver") is False
    webdriver_missing = re.search(r"webdriver\s*\(new\)\s*missing", text, re.IGNORECASE) is not None
    webdriver_present = re.search(r"webdriver\s*\(new\)\s*present|webdriver\s+present\s*:?\s*true", text, re.IGNORECASE) is not None
    if webdriver_false and webdriver_missing and "HeadlessChrome" not in ua:
        return "passed", "SannySoft loaded; webdriver is false and configured UA does not expose HeadlessChrome.", "low"
    if webdriver_false and webdriver_missing:
        return "warning", "SannySoft loaded; webdriver is false, but UA still exposes HeadlessChrome.", "medium"
    if webdriver_present:
        return "failed", "SannySoft page text reports webdriver exposure.", "high"
    return "warning", "SannySoft loaded; manual review required because no site-specific table parser matched.", "medium"

def _brand_name(entry: object) -> str:
    return str(entry.get("brand", "")) if isinstance(entry, dict) else ""

def _brand_version(entry: object) -> str:
    return str(entry.get("version", "")) if isinstance(entry, dict) else ""

def _is_grease_brand(brand: str) -> bool:
    return not brand or "Not" in brand or ";" in brand

def _expected_client_hint_values(value: dict, high: dict) -> tuple[dict, str]:
    ua = str(value.get("ua") or "")
    platform = str(value.get("platform") or "")
    observed_platform = str(high.get("platform") or "")
    if observed_platform == "macOS" or "Macintosh" in ua or platform == "MacIntel":
        return {
            "platform": "macOS",
            "architecture": "arm",
            "bitness": "64",
            "mobile": False,
            "wow64": False,
        }, "macOS arm64 Chromium"
    return {
        "platform": "Linux",
        "architecture": "x86",
        "bitness": "64",
        "mobile": False,
        "wow64": False,
    }, "Linux Chromium"


def classify_browserleaks_client_hints(value: dict) -> tuple[str, str, str]:
    ua_data = value.get("uaData") or {}
    if not ua_data.get("available"):
        return "warning", "BrowserLeaks Client Hints loaded, but navigator.userAgentData is unavailable.", "medium"
    if ua_data.get("highEntropyError"):
        return "failed", f"BrowserLeaks Client Hints high entropy API failed: {ua_data['highEntropyError']}", "high"
    high = ua_data.get("highEntropy") or {}
    full_versions = high.get("fullVersionList") or []
    chromium_versions = [
        _brand_version(entry)
        for entry in full_versions
        if isinstance(entry, dict)
        and not _is_grease_brand(_brand_name(entry))
        and _brand_name(entry) in {"Chromium", "Google Chrome", "Chrome"}
    ]
    if not chromium_versions:
        return "failed", "BrowserLeaks Client Hints high entropy data is missing a non-GREASE Chromium fullVersionList entry.", "high"
    expected, expected_label = _expected_client_hint_values(value, high)
    mismatches = {
        key: {"expected": expected_value, "observed": high.get(key)}
        for key, expected_value in expected.items()
        if high.get(key) != expected_value
    }
    if mismatches:
        return "warning", f"BrowserLeaks Client Hints fullVersionList is present, but high entropy values drifted: {mismatches}", "medium"
    if not any(re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version) for version in chromium_versions):
        return "warning", "BrowserLeaks Client Hints fullVersionList is present, but Chromium version is not full dotted version.", "medium"
    return "passed", f"BrowserLeaks Client Hints loaded with configured {expected_label} high entropy values and fullVersionList.", "low"

def classify_browserleaks_audio_probe(value: dict) -> tuple[str, str, str]:
    audio = value.get("audio") or {}
    if not audio.get("available"):
        return "warning", "BrowserLeaks Audio page loaded, but the bounded AudioContext probe is unavailable.", "medium"
    required = {"sampleRate", "length", "sum", "sumAbs"}
    missing = sorted(required - audio.keys())
    if missing:
        return "warning", f"BrowserLeaks Audio page loaded, but sanitized AudioContext summary is missing fields: {missing}", "medium"
    return "warning", "BrowserLeaks Audio page loaded and produced bounded AudioContext summary values; release-grade BrowserLeaks score baseline remains required.", "medium"


def classify_browserleaks_fonts_probe(value: dict) -> tuple[str, str, str]:
    fonts = value.get("fonts") or {}
    metrics = fonts.get("metrics") or {}
    if not fonts.get("available"):
        return "warning", "BrowserLeaks Fonts page loaded, but document.fonts probing is unavailable.", "medium"
    required = {"candidateCount", "metricRows", "glyphSha256", "metricsSha256"}
    missing = sorted(required - metrics.keys())
    if missing:
        return "warning", f"BrowserLeaks Fonts page loaded, but sanitized font metric summary is missing fields: {missing}", "medium"
    return "warning", "BrowserLeaks Fonts page loaded and produced bounded font metric/glyph summaries; release-grade font corpus parity remains required.", "medium"

def classify_browserleaks_webgl_probe(value: dict) -> tuple[str, str, str]:
    webgl = value.get("webgl") or {}
    if not webgl.get("available", bool(webgl)):
        return "warning", "BrowserLeaks WebGL page loaded, but the bounded WebGL probe is unavailable.", "medium"
    required = {"vendor", "renderer"}
    missing = sorted(field for field in required if not webgl.get(field))
    if missing:
        return "warning", f"BrowserLeaks WebGL page loaded, but sanitized WebGL summary is missing fields: {missing}", "medium"
    renderer = str(webgl.get("renderer", ""))
    vendor = str(webgl.get("vendor", ""))
    if "SwiftShader" in renderer or "Google Inc. (Google)" in vendor:
        return "warning", "BrowserLeaks WebGL bounded probe still exposes SwiftShader/Google software rendering; configured vendor/renderer evidence is required.", "high"
    metadata_missing = sorted(field for field in WEBGL_REQUIRED_METADATA_FIELDS if webgl.get(field) is None)
    if metadata_missing:
        return "warning", f"BrowserLeaks WebGL page reported vendor/renderer strings, but sanitized WebGL metadata is missing fields: {metadata_missing}; release-grade WebGL coherence remains required.", "medium"
    return "warning", "BrowserLeaks WebGL page reported sanitized vendor/renderer, extension count/hash, parameter hash, shader precision hash, and rendered pixel hash; headed/native cross-detector coherence still requires release-grade evidence.", "medium"



def classify_browserleaks_screen_probe(value: dict) -> tuple[str, str, str]:
    screen = value.get("screen") or {}
    required = {"width", "height", "availWidth", "availHeight", "devicePixelRatio"}
    missing = sorted(field for field in required if screen.get(field) is None)
    if missing:
        return "warning", f"BrowserLeaks JavaScript page loaded, but sanitized Screen Object summary is missing fields: {missing}", "medium"
    return "warning", "BrowserLeaks JavaScript page reported bounded Screen Object dimensions and devicePixelRatio; release-grade cross-platform screen parity remains required.", "medium"


def classify_browserleaks_webrtc_probe(value: dict) -> tuple[str, str, str]:
    webrtc = value.get("webrtc") or {}
    if not webrtc.get("available"):
        return "warning", "BrowserLeaks WebRTC page loaded, but the bounded WebRTC probe is unavailable.", "medium"
    required = {"candidateCount", "ipLiteralCount", "privateIpLiteralCount", "publicIpLiteralCount", "types"}
    missing = sorted(required - webrtc.keys())
    if missing:
        return "warning", f"BrowserLeaks WebRTC page loaded, but sanitized WebRTC summary is missing fields: {missing}", "medium"
    if webrtc.get("publicIpLiteralCount", 0) > 0:
        return "warning", "BrowserLeaks WebRTC bounded probe observed public IP literals; external proxy/geolocation coherence remains required.", "high"
    if webrtc.get("privateIpLiteralCount", 0) > 0:
        return "warning", "BrowserLeaks WebRTC bounded probe observed private/local IP literals; native masking policy needs headed detector confirmation.", "medium"
    return "warning", "BrowserLeaks WebRTC page loaded and bounded probe recorded sanitized ICE candidate metadata without committed IP literals; external proxy/geolocation detector evidence remains required.", "medium"




def classify_browserleaks(value: dict, url: str) -> tuple[str, str, str]:
    page_url = value.get("url") or url
    if "/javascript" in page_url and "#audio" in page_url:
        return classify_browserleaks_audio_probe(value)
    if "/javascript" in page_url:
        return classify_browserleaks_screen_probe(value)
    if "/fonts" in page_url:
        return classify_browserleaks_fonts_probe(value)
    if "/webgl" in page_url:
        return classify_browserleaks_webgl_probe(value)
    if "/webrtc" in page_url:
        return classify_browserleaks_webrtc_probe(value)
    return classify_browserleaks_client_hints(value)



def classify_pixelscan_client_hints(value: dict) -> tuple[str, str, str]:
    pixelscan = value.get("pixelscanPage") or {}
    if isinstance(pixelscan, dict) and pixelscan.get("available"):
        verdict = pixelscan.get("verdict")
        fingerprint = str(pixelscan.get("fingerprint") or "")
        if verdict == "inconsistent" or "masking" in fingerprint.lower():
            return "warning", "Pixelscan fingerprint check loaded and reported inconsistent/masking fingerprint status; release-grade score baseline remains required.", "medium"
        if verdict == "consistent":
            return "passed", "Pixelscan fingerprint check loaded and reported consistent fingerprint status.", "low"
    status, finding, severity = classify_browserleaks_client_hints(value)
    return status, finding.replace("BrowserLeaks Client Hints", "Pixelscan fingerprint check"), severity

def classify_iphey_client_hints(value: dict) -> tuple[str, str, str]:
    status, finding, severity = classify_browserleaks_client_hints(value)
    return status, finding.replace("BrowserLeaks Client Hints", "iphey fingerprint check"), severity

def classify_browserscan_client_hints(value: dict) -> tuple[str, str, str]:
    status, finding, severity = classify_browserleaks_client_hints(value)
    return status, finding.replace("BrowserLeaks Client Hints", "BrowserScan fingerprint check"), severity

def classify_creepjs_client_hints(value: dict) -> tuple[str, str, str]:
    status, finding, severity = classify_browserleaks_client_hints(value)
    return status, finding.replace("BrowserLeaks Client Hints", "CreepJS fingerprint check"), severity



def collect_page(cdp: CDPClient, detector_id: str, name: str, url: str, *, wait_seconds: int):
    target, _ = cdp.call("Target.createTarget", {"url": "about:blank"})
    target_id = target["targetId"]
    attached, _ = cdp.call("Target.attachToTarget", {"targetId": target_id, "flatten": True})
    session_id = attached["sessionId"]
    cdp.call("Page.enable", session_id=session_id)
    cdp.call("Runtime.enable", session_id=session_id)
    started = time.time()
    cdp.call("Page.navigate", {"url": url}, session_id=session_id, timeout=30)
    cdp.events_until(lambda msg: msg.get("sessionId") == session_id and msg.get("method") == "Page.loadEventFired", timeout=45)
    time.sleep(wait_seconds)
    expr = """
(async () => {
  const text = (document.body && document.body.innerText || '').slice(0, 12000);
  const title = document.title;
  const ua = navigator.userAgent;
  const uaData = await (async () => {
    if (!navigator.userAgentData) return {available: false};
    const lowEntropy = {
      brands: navigator.userAgentData.brands || [],
      mobile: navigator.userAgentData.mobile,
      platform: navigator.userAgentData.platform,
    };
    if (!navigator.userAgentData.getHighEntropyValues) {
      return {available: true, lowEntropy};
    }
    try {
      const highEntropy = await navigator.userAgentData.getHighEntropyValues([
        'architecture',
        'bitness',
        'brands',
        'fullVersionList',
        'mobile',
        'model',
        'platform',
        'platformVersion',
        'wow64',
      ]);
      return {available: true, lowEntropy, highEntropy};
    } catch (err) {
      return {available: true, lowEntropy, highEntropyError: String(err && err.name || err)};
    }
  })();
  const webdriver = navigator.webdriver;
  const platform = navigator.platform;
  const languages = navigator.languages;
  const hw = navigator.hardwareConcurrency;
  const dm = navigator.deviceMemory;
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const screenData = {
    width: screen.width,
    height: screen.height,
    availWidth: screen.availWidth,
    availHeight: screen.availHeight,
    devicePixelRatio: window.devicePixelRatio,
  };
  const storageEstimate = navigator.storage && navigator.storage.estimate
    ? await navigator.storage.estimate()
    : null;
  const audio = await (async () => {
    try {
      const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
      if (!Offline) return {available: false, reason: 'offline_audio_context_unavailable'};
      const ctx = new Offline(1, 44100, 44100);
      const oscillator = ctx.createOscillator();
      const compressor = ctx.createDynamicsCompressor();
      oscillator.type = 'triangle';
      oscillator.frequency.value = 10000;
      compressor.threshold.value = -50;
      compressor.knee.value = 40;
      compressor.ratio.value = 12;
      compressor.attack.value = 0;
      compressor.release.value = 0.25;
      oscillator.connect(compressor);
      compressor.connect(ctx.destination);
      oscillator.start(0);
      const buffer = await Promise.race([
        ctx.startRendering(),
        new Promise((_, reject) => setTimeout(() => reject({name: 'offline_audio_context_timeout'}), 3000)),
      ]);
      const data = buffer.getChannelData(0);
      let sum = 0;
      let sumAbs = 0;
      for (let i = 0; i < data.length; i += 128) {
        sum += data[i];
        sumAbs += Math.abs(data[i]);
      }
      return {
        available: true,
        length: data.length,
        sampleRate: buffer.sampleRate,
        sum: Number(sum.toFixed(8)),
        sumAbs: Number(sumAbs.toFixed(8)),
        firstSamples: Array.from(data.slice(0, 8)).map((v) => Number(v.toFixed(8))),
      };
    } catch (err) {
      return {available: false, reason: String(err && err.name || err)};
    }
  })();
  const browserleaksAudioPage = (() => {
    if (!(location.href.includes('/javascript') && location.hash === '#audio')) return null;
    const lines = text.split('\\n').map((line) => line.trim()).filter(Boolean);
    const sectionStart = lines.findIndex((line) => line === 'Web Audio API');
    if (sectionStart < 0) return {available: false, reason: 'web_audio_section_missing'};
    const fields = [
      ['apiStatus', 'API Status'],
      ['state', 'State'],
      ['sampleRate', 'Sample Rate'],
      ['maxChannelCount', 'Max Channel Count'],
      ['numberOfInputs', 'Number of Inputs'],
      ['numberOfOutputs', 'Number of Outputs'],
      ['channelCount', 'Channel Count'],
      ['channelCountMode', 'Channel Count Mode'],
      ['channelInterpretation', 'Channel Interpretation'],
      ['fftSize', 'FFT Size'],
      ['frequencyBinCount', 'Frequency Bin Count'],
      ['minDecibels', 'Min Decibels'],
      ['maxDecibels', 'Max Decibels'],
      ['smoothingTimeConstant', 'Smoothing Time Constant'],
    ];
    const values = {};
    for (const [key, label] of fields) {
      const index = lines.findIndex((line, offset) => offset > sectionStart && line === label);
      if (index >= 0 && index + 1 < lines.length) {
        values[key] = lines[index + 1].slice(0, 80);
      }
    }
    const audioContext = (() => {
      try {
        const Audio = window.AudioContext || window.webkitAudioContext;
        if (!Audio) return {available: false, reason: 'audio_context_unavailable'};
        const ctx = new Audio();
        const analyser = ctx.createAnalyser();
        const values = {
          state: ctx.state,
          sampleRate: ctx.sampleRate,
          maxChannelCount: ctx.destination && ctx.destination.maxChannelCount,
          numberOfInputs: ctx.destination && ctx.destination.numberOfInputs,
          numberOfOutputs: ctx.destination && ctx.destination.numberOfOutputs,
          channelCount: ctx.destination && ctx.destination.channelCount,
          channelCountMode: ctx.destination && ctx.destination.channelCountMode,
          channelInterpretation: ctx.destination && ctx.destination.channelInterpretation,
          fftSize: analyser.fftSize,
          frequencyBinCount: analyser.frequencyBinCount,
          minDecibels: analyser.minDecibels,
          maxDecibels: analyser.maxDecibels,
          smoothingTimeConstant: analyser.smoothingTimeConstant,
        };
        if (ctx.close) ctx.close();
        return {available: true, values};
      } catch (err) {
        return {available: false, reason: String(err && err.name || err)};
      }
    })();
    return {
      available: Object.keys(values).length > 0 || Boolean(audioContext.available),
      observedFieldCount: Object.keys(values).length,
      audioContext,
      values,
    };
  })();
  const pixelscanPage = (() => {
    if (!location.hostname.includes('pixelscan.net')) return null;
    const lines = text.split('\\n').map((line) => line.trim()).filter(Boolean);
    const valueAfter = (label) => {
      const index = lines.findIndex((line) => line === label);
      return index >= 0 && index + 1 < lines.length ? lines[index + 1].slice(0, 160) : null;
    };
    const valueBefore = (label) => {
      const index = lines.findIndex((line) => line === label);
      return index > 0 ? lines[index - 1].slice(0, 160) : null;
    };
    const hasText = (needle) => text.toLowerCase().includes(needle.toLowerCase());
    const verdict = hasText('Your Browser Fingerprint is consistent')
      ? 'consistent'
      : hasText('Your Browser Fingerprint is inconsistent')
        ? 'inconsistent'
        : null;
    return {
      available: Boolean(verdict || valueBefore('Fingerprint') || valueBefore('Bot check') || valueAfter('AudioContext Hash')),
      verdict,
      browser: valueBefore('Browser'),
      location: valueBefore('Location'),
      proxy: valueBefore('Proxy'),
      fingerprint: valueBefore('Fingerprint'),
      botCheck: valueBefore('Bot check'),
      fontHash: valueAfter('Font hash'),
      canvasHash: valueAfter('Canvas Hash'),
      audioContextHash: valueAfter('AudioContext Hash'),
      webglHash: valueAfter('WebGL Hash'),
    };
  })();

  const fonts = await (async () => {
    const candidates = ['Arial', 'Calibri', 'Consolas', 'Courier New', 'DejaVu Sans', 'Noto Sans CJK TC', 'Segoe UI', 'Times New Roman'];
    const checks = {};
    const toHex = (buffer) => Array.from(new Uint8Array(buffer)).map((b) => b.toString(16).padStart(2, '0')).join('');
    const hashText = async (text) => crypto && crypto.subtle
      ? toHex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))
      : null;
    const hashBytes = async (bytes) => crypto && crypto.subtle
      ? toHex(await crypto.subtle.digest('SHA-256', bytes))
      : null;
    if (!document.fonts || !document.fonts.check) {
      return {available: false, checks};
    }
    for (const name of candidates) {
      checks[name] = document.fonts.check(`16px "${name}"`);
    }
    const metricRows = [];
    const sampleText = 'BrowseForge Ω 測 0123456789';
    const span = document.createElement('span');
    span.textContent = sampleText;
    span.style.cssText = 'position:absolute;left:-9999px;top:-9999px;font-size:32px;line-height:normal;white-space:nowrap;';
    document.body.appendChild(span);
    try {
      for (const name of candidates) {
        span.style.fontFamily = `"${name}", Arial, sans-serif`;
        const rect = span.getBoundingClientRect();
        metricRows.push({
          font: name,
          width: Number(rect.width.toFixed(3)),
          height: Number(rect.height.toFixed(3)),
          check: Boolean(checks[name]),
        });
      }
    } finally {
      span.remove();
    }
    const canvas = document.createElement('canvas');
    canvas.width = 384;
    canvas.height = 48;
    const ctx = canvas.getContext('2d');
    let glyphImageSha256 = null;
    let glyphSampleCount = 0;
    if (ctx) {
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#111';
      ctx.font = '24px Arial';
      ctx.fillText(sampleText, 4, 30);
      const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
      glyphSampleCount = image.data.length;
      glyphImageSha256 = await hashBytes(image.data);
    }
    return {
      available: true,
      checks,
      metrics: {
        candidateCount: candidates.length,
        metricRows,
        metricsSha256: await hashText(JSON.stringify(metricRows)),
        glyphSha256: glyphImageSha256,
        glyphSampleCount,
      },
    };
  })();
  const canvasProbe = await (async () => {
    try {
      const toHex = (buffer) => Array.from(new Uint8Array(buffer)).map((b) => b.toString(16).padStart(2, '0')).join('');
      const canvas = document.createElement('canvas');
      canvas.width = 64;
      canvas.height = 32;
      const ctx = canvas.getContext('2d');
      if (!ctx) return {available: false, reason: '2d_context_unavailable'};
      const gradient = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
      gradient.addColorStop(0, '#123456');
      gradient.addColorStop(1, '#fedcba');
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = 'rgba(20, 120, 210, 0.73)';
      ctx.font = '13px Arial';
      ctx.fillText('BrowseForge Ω 測', 3, 21);
      const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const imageDataSha256 = crypto && crypto.subtle
        ? toHex(await crypto.subtle.digest('SHA-256', image.data))
        : null;
      const dataUrl = canvas.toDataURL('image/png');
      return {
        available: true,
        width: canvas.width,
        height: canvas.height,
        sampleCount: image.data.length,
        imageDataSha256,
        dataUrlSha256Input: dataUrl,
      };
    } catch (err) {
      return {available: false, reason: String(err && err.name || err)};
    }
  })();
  const features = await (async () => {
    const permissionNames = [
      'geolocation',
      'notifications',
      'camera',
      'microphone',
      'clipboard-read',
      'clipboard-write',
      'midi',
      'push',
      'payment-handler',
      'idle-detection',
      'window-management',
      'local-fonts',
      'background-sync',
      'persistent-storage',
      'accelerometer',
      'gyroscope',
      'magnetometer',
    ];
    const permissionStates = {};
    const permissionsApi = Boolean(navigator.permissions && navigator.permissions.query);
    if (permissionsApi) {
      for (const name of permissionNames) {
        try {
          const status = await navigator.permissions.query({name});
          permissionStates[name] = status && status.state ? status.state : 'unknown';
        } catch (err) {
          permissionStates[name] = `error:${String(err && err.name || err)}`;
        }
      }
    }
    return {
      available: true,
      permissionsApi,
      notificationPermission: typeof Notification !== 'undefined' ? Notification.permission : 'unavailable',
      featureFlags: {
        contactsManager: Boolean(navigator.contacts && navigator.contacts.select),
        contentIndex: Boolean('ContentIndex' in window || (typeof ServiceWorkerRegistration !== 'undefined' && ServiceWorkerRegistration.prototype && 'index' in ServiceWorkerRegistration.prototype)),
        networkInformation: Boolean(navigator.connection),
        storageBuckets: Boolean(navigator.storageBuckets),
        webBluetooth: Boolean(navigator.bluetooth && navigator.bluetooth.getAvailability),
        webHid: Boolean(navigator.hid),
        webNfc: Boolean('NDEFReader' in window),
        webSerial: Boolean(navigator.serial),
        webUsb: Boolean(navigator.usb),
        webShare: Boolean(navigator.share),
        webShareData: Boolean(navigator.canShare),
        idleDetector: Boolean('IdleDetector' in window),
        keyboardLock: Boolean(navigator.keyboard && navigator.keyboard.lock),
        localFonts: Boolean('queryLocalFonts' in window),
        presentation: Boolean(navigator.presentation),
        virtualKeyboard: Boolean(navigator.virtualKeyboard),
        windowControlsOverlay: Boolean(navigator.windowControlsOverlay),
      },
      permissionStates,
    };
  })();
  const webrtc = await (async () => {
    try {
      const RTCPeer = window.RTCPeerConnection || window.webkitRTCPeerConnection;
      if (!RTCPeer) return {available: false, reason: 'rtc_peer_connection_unavailable'};
      const toHex = (buffer) => Array.from(new Uint8Array(buffer)).map((b) => b.toString(16).padStart(2, '0')).join('');
      const hashText = async (text) => globalThis.crypto && globalThis.crypto.subtle
        ? toHex(await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))
        : null;
      const ipLiteralRe = /\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b/g;
      const isPrivateIp = (ip) => /^(10\\.|127\\.|169\\.254\\.|192\\.168\\.|172\\.(1[6-9]|2\\d|3[0-1])\\.)/.test(ip);
      const candidates = [];
      const candidateTypes = new Set();
      const ipLiterals = new Set();
      const privateIps = new Set();
      const publicIps = new Set();
      const trackCandidate = (line) => {
        if (!line || candidates.includes(line)) return;
        candidates.push(line);
        const typeMatch = line.match(/\\styp\\s+([a-z0-9]+)/i);
        if (typeMatch) candidateTypes.add(typeMatch[1].toLowerCase());
        for (const match of line.matchAll(ipLiteralRe)) {
          const ip = match[0];
          ipLiterals.add(ip);
          if (isPrivateIp(ip)) {
            privateIps.add(ip);
          } else {
            publicIps.add(ip);
          }
        }
      };
      const pc = new RTCPeer({iceServers: []});
      try {
        pc.onicecandidate = (event) => {
          if (event.candidate && event.candidate.candidate) trackCandidate(event.candidate.candidate);
        };
        pc.createDataChannel('browseforge-webrtc-probe');
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        await new Promise((resolve) => {
          if (pc.iceGatheringState === 'complete') {
            resolve();
            return;
          }
          const timer = setTimeout(resolve, 1500);
          pc.onicegatheringstatechange = () => {
            if (pc.iceGatheringState === 'complete') {
              clearTimeout(timer);
              resolve();
            }
          };
        });
        if (pc.localDescription && pc.localDescription.sdp) {
          for (const line of pc.localDescription.sdp.split('\\n')) {
            if (line.startsWith('a=candidate:')) trackCandidate(line.slice(2).trim());
          }
        }
      } finally {
        pc.close();
      }
      return {
        available: true,
        candidateCount: candidates.length,
        types: Array.from(candidateTypes).sort(),
        ipLiteralCount: ipLiterals.size,
        privateIpLiteralCount: privateIps.size,
        publicIpLiteralCount: publicIps.size,
        rawCandidateSha256: await hashText(JSON.stringify(candidates.sort())),
      };
    } catch (err) {
      return {available: false, reason: String(err && err.name || err)};
    }
  })();
  const gl = await (async () => {
    try {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (!ctx) return {available: false, reason: 'webgl_context_unavailable'};
      const toHex = (buffer) => Array.from(new Uint8Array(buffer)).map((b) => b.toString(16).padStart(2, '0')).join('');
      const hashText = async (text) => globalThis.crypto && globalThis.crypto.subtle
        ? toHex(await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))
        : null;
      const hashBytes = async (bytes) => globalThis.crypto && globalThis.crypto.subtle
        ? toHex(await globalThis.crypto.subtle.digest('SHA-256', bytes))
        : null;
      const ext = ctx.getExtension('WEBGL_debug_renderer_info');
      const extensions = (ctx.getSupportedExtensions && ctx.getSupportedExtensions() || []).sort();
      const parameters = {
        aliasedLineWidthRange: Array.from(ctx.getParameter(ctx.ALIASED_LINE_WIDTH_RANGE) || []),
        aliasedPointSizeRange: Array.from(ctx.getParameter(ctx.ALIASED_POINT_SIZE_RANGE) || []),
        maxCombinedTextureImageUnits: ctx.getParameter(ctx.MAX_COMBINED_TEXTURE_IMAGE_UNITS),
        maxCubeMapTextureSize: ctx.getParameter(ctx.MAX_CUBE_MAP_TEXTURE_SIZE),
        maxFragmentUniformVectors: ctx.getParameter(ctx.MAX_FRAGMENT_UNIFORM_VECTORS),
        maxRenderbufferSize: ctx.getParameter(ctx.MAX_RENDERBUFFER_SIZE),
        maxTextureImageUnits: ctx.getParameter(ctx.MAX_TEXTURE_IMAGE_UNITS),
        maxTextureSize: ctx.getParameter(ctx.MAX_TEXTURE_SIZE),
        maxVaryingVectors: ctx.getParameter(ctx.MAX_VARYING_VECTORS),
        maxVertexAttribs: ctx.getParameter(ctx.MAX_VERTEX_ATTRIBS),
        maxVertexTextureImageUnits: ctx.getParameter(ctx.MAX_VERTEX_TEXTURE_IMAGE_UNITS),
        maxVertexUniformVectors: ctx.getParameter(ctx.MAX_VERTEX_UNIFORM_VECTORS),
        maxViewportDims: Array.from(ctx.getParameter(ctx.MAX_VIEWPORT_DIMS) || []),
      };
      const precision = {};
      for (const [stageName, stage] of [['vertex', ctx.VERTEX_SHADER], ['fragment', ctx.FRAGMENT_SHADER]]) {
        for (const [typeName, type] of [['lowFloat', ctx.LOW_FLOAT], ['mediumFloat', ctx.MEDIUM_FLOAT], ['highFloat', ctx.HIGH_FLOAT], ['lowInt', ctx.LOW_INT], ['mediumInt', ctx.MEDIUM_INT], ['highInt', ctx.HIGH_INT]]) {
          const p = ctx.getShaderPrecisionFormat(stage, type);
          precision[`${stageName}.${typeName}`] = p ? {rangeMin: p.rangeMin, rangeMax: p.rangeMax, precision: p.precision} : null;
        }
      }
      const renderProbe = (() => {
        const compile = (type, source) => {
          const shader = ctx.createShader(type);
          ctx.shaderSource(shader, source);
          ctx.compileShader(shader);
          if (!ctx.getShaderParameter(shader, ctx.COMPILE_STATUS)) return null;
          return shader;
        };
        const vertex = compile(ctx.VERTEX_SHADER, 'attribute vec2 p; varying vec2 v; void main(){ v=(p+1.0)*0.5; gl_Position=vec4(p,0.0,1.0); }');
        const fragment = compile(ctx.FRAGMENT_SHADER, 'precision mediump float; varying vec2 v; void main(){ gl_FragColor=vec4(v.x,v.y,0.25,1.0); }');
        if (!vertex || !fragment) return null;
        const program = ctx.createProgram();
        ctx.attachShader(program, vertex);
        ctx.attachShader(program, fragment);
        ctx.linkProgram(program);
        if (!ctx.getProgramParameter(program, ctx.LINK_STATUS)) return null;
        const buffer = ctx.createBuffer();
        ctx.bindBuffer(ctx.ARRAY_BUFFER, buffer);
        ctx.bufferData(ctx.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), ctx.STATIC_DRAW);
        const loc = ctx.getAttribLocation(program, 'p');
        ctx.useProgram(program);
        ctx.enableVertexAttribArray(loc);
        ctx.vertexAttribPointer(loc, 2, ctx.FLOAT, false, 0, 0);
        canvas.width = 16;
        canvas.height = 16;
        ctx.viewport(0, 0, canvas.width, canvas.height);
        ctx.drawArrays(ctx.TRIANGLE_STRIP, 0, 4);
        const pixels = new Uint8Array(canvas.width * canvas.height * 4);
        ctx.readPixels(0, 0, canvas.width, canvas.height, ctx.RGBA, ctx.UNSIGNED_BYTE, pixels);
        return {width: canvas.width, height: canvas.height, pixels};
      })();
      return {
        available: true,
        vendor: ext ? ctx.getParameter(ext.UNMASKED_VENDOR_WEBGL) : null,
        renderer: ext ? ctx.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null,
        extensionCount: extensions.length,
        extensionSha256: await hashText(JSON.stringify(extensions)),
        parameterSha256: await hashText(JSON.stringify(parameters)),
        precisionSha256: await hashText(JSON.stringify(precision)),
        pixelSha256: renderProbe ? await hashBytes(renderProbe.pixels) : null,
        pixelWidth: renderProbe ? renderProbe.width : null,
        pixelHeight: renderProbe ? renderProbe.height : null,
        parameters,
      };
    } catch (err) {
      return {available: false, reason: String(err && err.name || err)};
    }
  })();
  return {title, url: location.href, text, ua, uaData, webdriver, platform, languages, hardwareConcurrency: hw, deviceMemory: dm, timezone: tz, screen: screenData, storage: storageEstimate, audio, browserleaksAudioPage, pixelscanPage, fonts, canvas: canvasProbe, features, webgl: gl, webrtc};
})()
"""
    evaluate_timeout = max(60 if detector_id == "iphey" else 30, wait_seconds + 20)
    result, _ = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, session_id=session_id, timeout=evaluate_timeout)
    value = result.get("result", {}).get("value", {})
    elapsed = round(time.time() - started, 2)
    cdp.call("Target.closeTarget", {"targetId": target_id}, timeout=5)
    text = value.pop("text", "")
    canvas = value.get("canvas")
    if isinstance(canvas, dict) and isinstance(canvas.get("dataUrlSha256Input"), str):
        data_url = canvas.pop("dataUrlSha256Input")
        canvas["dataUrlSha256"] = hashlib.sha256(data_url.encode()).hexdigest()
    if detector_id == "creepjs":
        metrics = extract_creepjs_metrics(text)
        if metrics:
            value["detector_metrics"] = metrics
    if detector_id == "sannysoft":
        status, finding, severity = classify_sannysoft({**value, "text": text})
    elif detector_id == "browserleaks":
        status, finding, severity = classify_browserleaks({**value, "text": text}, url)
    elif detector_id == "pixelscan":
        status, finding, severity = classify_pixelscan_client_hints({**value, "text": text})
    elif detector_id == "iphey":
        status, finding, severity = classify_iphey_client_hints({**value, "text": text})
    elif detector_id == "browserscan":
        status, finding, severity = classify_browserscan_client_hints({**value, "text": text})
    elif detector_id == "creepjs":
        status, finding, severity = classify_creepjs_client_hints({**value, "text": text})
    else:
        status, finding, severity = "warning", "Detector loaded; manual review required.", "medium"
    value["text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    value["text_excerpt"] = redact_sensitive_text(" ".join(text.split())[:800])
    value["elapsed_seconds"] = elapsed
    return {
        "detector_id": detector_id,
        "name": name,
        "url": url,
        "status": status,
        "failure_mode": "none",
        "finding": finding,
        "severity": severity,
        "observed": value,
    }

SUPPORTED_COLLECTORS = {
    "sannysoft": ("SannySoft", "https://bot.sannysoft.com/"),
    "browserleaks": ("BrowserLeaks", "https://browserleaks.com/client-hints"),
    "pixelscan": ("Pixelscan", "https://pixelscan.net/fingerprint-check"),
    "iphey": ("iphey", "https://iphey.com/"),
    "browserscan": ("BrowserScan", "https://www.browserscan.net/"),
    "creepjs": ("CreepJS", "https://abrahamjuliot.github.io/creepjs/"),
}
SUPPORTED_COLLECTOR_PAGES = {
    "browserleaks": {
        "client-hints": "https://browserleaks.com/client-hints",
        "audio": "https://browserleaks.com/javascript#audio",
        "fonts": "https://browserleaks.com/fonts",
        "webgl": "https://browserleaks.com/webgl",
        "webrtc": "https://browserleaks.com/webrtc",
        "screen": "https://browserleaks.com/javascript",
    },
}


def resolve_collect_url(detector_id: str, *, page: str | None, url: str | None) -> str:
    if url:
        return url
    _, default_url = SUPPORTED_COLLECTORS[detector_id]
    if page is None:
        return default_url
    detector_pages = SUPPORTED_COLLECTOR_PAGES.get(detector_id, {})
    if page not in detector_pages:
        supported = ", ".join(sorted(detector_pages)) or "none"
        raise ValueError(f"unsupported collector page for {detector_id}: {page}; supported pages: {supported}")
    return detector_pages[page]



def collect(args):
    if args.detector not in SUPPORTED_COLLECTORS:
        print(f"collector not implemented for detector: {args.detector}", file=sys.stderr)
        return EXIT_COLLECT_UNAVAILABLE
    try:
        name, _ = SUPPORTED_COLLECTORS[args.detector]
        url = resolve_collect_url(args.detector, page=args.page, url=args.url)
    except ValueError as err:
        print(str(err), file=sys.stderr)
        return EXIT_UNSUPPORTED
    try:
        version = http_json(args.cdp_url.rstrip("/") + "/json/version")
        cdp = CDPClient(version["webSocketDebuggerUrl"])
        payload = {
            "browser": version,
            "records": [collect_page(cdp, args.detector, name, url, wait_seconds=args.wait_seconds)],
        }
    except Exception as err:
        print(f"collect failed: {err}", file=sys.stderr)
        return EXIT_COLLECT_UNAVAILABLE
    out = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        print(out, end="")
    return 0

def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)
    p = sub.add_parser("list-targets"); p.set_defaults(func=list_targets)
    p = sub.add_parser("plan"); p.add_argument("--runtime-version", required=True); p.add_argument("--platform", required=True); p.add_argument("--format", default="json"); p.set_defaults(func=plan)
    p = sub.add_parser("validate-evidence"); p.add_argument("path"); p.add_argument("--schema", default="detectors/evidence-schema.json"); p.set_defaults(func=validate_evidence)
    p = sub.add_parser("ingest"); p.add_argument("--input", required=True); p.add_argument("--output-root", default="detectors/evidence"); p.add_argument("--kg-out", default="generated/kg/detector-evidence.jsonl"); p.set_defaults(func=ingest)
    p = sub.add_parser("regenerate-kg"); p.add_argument("--evidence-root", default="detectors/evidence"); p.add_argument("--output", default="generated/kg/detector-evidence.jsonl"); p.set_defaults(func=regenerate_kg)
    p = sub.add_parser("summary"); p.add_argument("--evidence-root", default="detectors/evidence"); p.add_argument("--output", default="detector-summary.json"); p.add_argument("--platform", default="linux-x64"); p.add_argument("--generated-at"); p.set_defaults(func=summary)
    p = sub.add_parser("compare-scores"); p.add_argument("--evidence-root", default="detectors/evidence"); p.add_argument("--output", default="knowledge/manifests/detector-score-comparison.json"); p.set_defaults(func=compare_scores)
    p = sub.add_parser("pixelscan-variant-plan"); p.add_argument("--output"); p.add_argument("--generated-at"); p.set_defaults(func=pixelscan_variant_plan)
    p = sub.add_parser("pixelscan-materialize-variants"); p.add_argument("--base-config", required=True); p.add_argument("--output-dir", required=True); p.add_argument("--manifest-output"); p.add_argument("--generated-at"); p.set_defaults(func=pixelscan_materialize_variants)
    p = sub.add_parser("pixelscan-variant-summary"); p.add_argument("--input-dir", required=True); p.add_argument("--headed-input-dir"); p.add_argument("--output"); p.add_argument("--generated-at"); p.set_defaults(func=pixelscan_variant_summary)
    p = sub.add_parser("proxy-preflight"); p.add_argument("--proxy-url"); p.add_argument("--proxy-region-redacted", dest="proxy_region"); p.add_argument("--proxy-region", dest="proxy_region"); p.add_argument("--output"); p.add_argument("--generated-at"); p.set_defaults(func=proxy_preflight)
    p = sub.add_parser("collect"); p.add_argument("--detector", default="sannysoft"); p.add_argument("--page"); p.add_argument("--url"); p.add_argument("--cdp-url", default="http://127.0.0.1:9222"); p.add_argument("--wait-seconds", type=int, default=15); p.add_argument("--output"); p.set_defaults(func=collect)
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
