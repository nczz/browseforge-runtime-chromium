#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import socket
import struct
import sys
import time
import urllib.request
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
        fh.write(json.dumps(kg, sort_keys=True) + "\n")
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
                "run_id": evidence["run_id"],
                "metrics": {key: values[key] for key in ("freq", "gain", "sum", "time", "trap", "unique")},
            })
    return records

def _collect_font_metric_records(evidence_rows: list[dict]) -> list[dict]:
    records = []
    for evidence in evidence_rows:
        merged = {
            "detector_id": evidence["detector"]["detector_id"],
            "display_mode": _evidence_display(evidence),
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

def detector_score_comparisons(evidence_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    comparisons = []
    gaps = []

    creepjs_audio = {
        record["display_mode"]: record
        for record in _collect_audio_metric_records(evidence_rows)
        if record["detector_id"] == "creepjs"
    }
    if {"headless", "headed"} <= set(creepjs_audio):
        headless = creepjs_audio["headless"]
        headed = creepjs_audio["headed"]
        deltas = _numeric_metric_deltas(headless["metrics"], headed["metrics"])
        identical = all(abs(value) <= 1e-9 for value in deltas.values())
        comparisons.append({
            "comparison_id": "creepjs_audio_headless_vs_headed",
            "detector_id": "creepjs",
            "surface": "audio",
            "status": "pass" if identical else "warning",
            "left_run_id": headless["run_id"],
            "right_run_id": headed["run_id"],
            "metric_deltas": deltas,
            "finding": "CreepJS audio metrics match across headless/headed evidence." if identical else "CreepJS audio metrics differ across headless/headed evidence; release-grade baseline comparison remains required.",
        })
    else:
        gaps.append({
            "gap_id": "creepjs_audio_headless_vs_headed",
            "surface": "audio",
            "missing": sorted({"headless", "headed"} - set(creepjs_audio)),
            "finding": "CreepJS audio comparison requires both headless and headed sanitized evidence.",
        })

    font_records = _collect_font_metric_records(evidence_rows)
    browserleaks_fonts = next((record for record in font_records if record["detector_id"] == "browserleaks"), None)
    creepjs_fonts = next((record for record in font_records if record["detector_id"] == "creepjs"), None)
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
            "candidate_count_match": browserleaks_fonts["candidate_count"] == creepjs_fonts["candidate_count"],
            "font_list_match": same_fonts,
            "glyph_sha256_match": same_glyph,
            "metrics_sha256_match": same_metrics,
            "finding": "BrowserLeaks/CreepJS font metric evidence matches." if same_glyph and same_metrics and same_fonts else "BrowserLeaks/CreepJS font evidence is only partially comparable; release-grade font corpus parity remains required.",
        })
    else:
        gaps.append({
            "gap_id": "browserleaks_creepjs_font_metrics",
            "surface": "fonts",
            "missing": sorted(det for det, record in {"browserleaks": browserleaks_fonts, "creepjs": creepjs_fonts}.items() if record is None),
            "finding": "Font comparison requires sanitized BrowserLeaks and CreepJS font metric evidence.",
        })

    return comparisons, gaps

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
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runtime_id": "browseforge-chromium",
        "release_grade": False,
        "evidence_count": len(evidence_rows),
        "comparisons": comparisons,
        "gaps": gaps,
        "decision": "Offline comparisons summarize committed sanitized evidence only; live release-grade detector baselines remain required before closing AudioContext/fonts blockers.",
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
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
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
            message = ws_recv(self.sock)
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
            msg = ws_recv(self.sock)
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
    expected = {
        "platform": "Linux",
        "architecture": "x86",
        "bitness": "64",
        "mobile": False,
        "wow64": False,
    }
    mismatches = {
        key: {"expected": expected_value, "observed": high.get(key)}
        for key, expected_value in expected.items()
        if high.get(key) != expected_value
    }
    if mismatches:
        return "warning", f"BrowserLeaks Client Hints fullVersionList is present, but high entropy values drifted: {mismatches}", "medium"
    if not any(re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version) for version in chromium_versions):
        return "warning", "BrowserLeaks Client Hints fullVersionList is present, but Chromium version is not full dotted version.", "medium"
    return "passed", "BrowserLeaks Client Hints loaded with configured Linux Chromium high entropy values and fullVersionList.", "low"

def classify_pixelscan_client_hints(value: dict) -> tuple[str, str, str]:
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
    cdp.call("Page.navigate", {"url": url}, session_id=session_id, timeout=10)
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
      const buffer = await ctx.startRendering();
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
  const gl = (() => {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (!ctx) return null;
    const ext = ctx.getExtension('WEBGL_debug_renderer_info');
    return ext ? {vendor: ctx.getParameter(ext.UNMASKED_VENDOR_WEBGL), renderer: ctx.getParameter(ext.UNMASKED_RENDERER_WEBGL)} : null;
  })();
  return {title, url: location.href, text, ua, uaData, webdriver, platform, languages, hardwareConcurrency: hw, deviceMemory: dm, timezone: tz, screen: screenData, storage: storageEstimate, audio, fonts, canvas: canvasProbe, webgl: gl};
})()
"""
    result, _ = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, session_id=session_id, timeout=10)
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
        status, finding, severity = classify_browserleaks_client_hints({**value, "text": text})
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

def collect(args):
    if args.detector not in SUPPORTED_COLLECTORS:
        print(f"collector not implemented for detector: {args.detector}", file=sys.stderr)
        return EXIT_COLLECT_UNAVAILABLE
    try:
        version = http_json(args.cdp_url.rstrip("/") + "/json/version")
        cdp = CDPClient(version["webSocketDebuggerUrl"])
        name, default_url = SUPPORTED_COLLECTORS[args.detector]
        url = args.url or default_url
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
    p = sub.add_parser("summary"); p.add_argument("--evidence-root", default="detectors/evidence"); p.add_argument("--output", default="detector-summary.json"); p.add_argument("--platform", default="linux-x64"); p.set_defaults(func=summary)
    p = sub.add_parser("compare-scores"); p.add_argument("--evidence-root", default="detectors/evidence"); p.add_argument("--output", default="knowledge/manifests/detector-score-comparison.json"); p.set_defaults(func=compare_scores)
    p = sub.add_parser("collect"); p.add_argument("--detector", default="sannysoft"); p.add_argument("--url"); p.add_argument("--cdp-url", default="http://127.0.0.1:9222"); p.add_argument("--wait-seconds", type=int, default=15); p.add_argument("--output"); p.set_defaults(func=collect)
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
