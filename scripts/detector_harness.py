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
  const fonts = (() => {
    const candidates = ['Arial', 'Calibri', 'Consolas', 'Courier New', 'DejaVu Sans', 'Noto Sans CJK TC', 'Segoe UI', 'Times New Roman'];
    const out = {};
    if (!document.fonts || !document.fonts.check) {
      return {available: false, checks: out};
    }
    for (const name of candidates) {
      out[name] = document.fonts.check(`16px "${name}"`);
    }
    return {available: true, checks: out};
  })();
  const gl = (() => {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (!ctx) return null;
    const ext = ctx.getExtension('WEBGL_debug_renderer_info');
    return ext ? {vendor: ctx.getParameter(ext.UNMASKED_VENDOR_WEBGL), renderer: ctx.getParameter(ext.UNMASKED_RENDERER_WEBGL)} : null;
  })();
  return {title, url: location.href, text, ua, webdriver, platform, languages, hardwareConcurrency: hw, deviceMemory: dm, timezone: tz, screen: screenData, storage: storageEstimate, audio, fonts, webgl: gl};
})()
"""
    result, _ = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True}, session_id=session_id, timeout=10)
    value = result.get("result", {}).get("value", {})
    elapsed = round(time.time() - started, 2)
    cdp.call("Target.closeTarget", {"targetId": target_id}, timeout=5)
    text = value.pop("text", "")
    status, finding, severity = classify_sannysoft({**value, "text": text}) if detector_id == "sannysoft" else ("warning", "Detector loaded; manual review required.", "medium")
    value["text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    value["text_excerpt"] = " ".join(text.split())[:800]
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
}

def collect(args):
    if args.detector not in SUPPORTED_COLLECTORS:
        print(f"collector not implemented for detector: {args.detector}", file=sys.stderr)
        return EXIT_COLLECT_UNAVAILABLE
    try:
        version = http_json(args.cdp_url.rstrip("/") + "/json/version")
        cdp = CDPClient(version["webSocketDebuggerUrl"])
        name, url = SUPPORTED_COLLECTORS[args.detector]
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
    p = sub.add_parser("summary"); p.add_argument("--evidence-root", default="detectors/evidence"); p.add_argument("--output", default="detector-summary.json"); p.set_defaults(func=summary)
    p = sub.add_parser("collect"); p.add_argument("--detector", default="sannysoft"); p.add_argument("--cdp-url", default="http://127.0.0.1:9222"); p.add_argument("--wait-seconds", type=int, default=15); p.add_argument("--output"); p.set_defaults(func=collect)
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
