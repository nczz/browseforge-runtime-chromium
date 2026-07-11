import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "detector_harness.py"

def load_harness_module():
    spec = importlib.util.spec_from_file_location("detector_harness", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DetectorHarnessTests(unittest.TestCase):
    def run_harness(self, *args, env=None):
        process_env = os.environ.copy()
        if env:
            for key, value in env.items():
                if value is None:
                    process_env.pop(key, None)
                else:
                    process_env[key] = value
        return subprocess.run(
            [sys.executable, str(HARNESS), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=process_env,
        )

    def fixture_path(self, name):
        return ROOT / "tests" / "fixtures" / "detectors" / name

    def write_synthetic_summary_evidence(self, evidence_root, *, detector_id, display_mode, network_mode, container):
        detector = self.harness_module.detector_by_id(detector_id)
        self.assertIsNotNone(detector)
        platform = "linux-x64"
        container_label = "container" if container else "host"
        display_key = "headed" if display_mode == "headed_xvfb" else display_mode
        network_key = network_mode.replace("_", "-")
        matrix_key = f"{platform}:{detector_id}:{display_key}:{network_key}:{container_label}"
        suffix = f"{detector_id}_{display_mode}_{network_key}_{container_label}".replace("-", "_")
        evidence = json.loads(self.fixture_path("valid-evidence.json").read_text(encoding="utf-8"))
        evidence.update(
            {
                "run_id": f"detrun_summary_{suffix}",
                "evidence_id": f"evidence_summary_{suffix}",
                "artifact_id": f"unpackaged:{platform}:summary-test",
                "runtime_version": "summary-test",
                "detector": {
                    "detector_id": detector_id,
                    "name": detector["name"],
                    "url": detector["url"],
                    "category": detector["category"],
                    "manifest_ref": f"knowledge/manifests/detectors.json#{detector_id}",
                },
                "target": {
                    **evidence["target"],
                    "platform": platform,
                    "container": container,
                    "proxy_region_redacted": "none" if network_mode == "direct" else "redacted",
                },
                "matrix": {
                    "matrix_key": matrix_key,
                    "display_mode": display_mode,
                    "network_mode": network_mode,
                    "container": container,
                    "proxy": "none" if network_mode == "direct" else "redacted",
                    "required": True,
                },
                "status": "passed",
                "failure_mode": "none",
                "results": [
                    {
                        "surface": "automation_signals",
                        "status": "pass",
                        "severity": "info",
                        "finding": "Synthetic summary coverage evidence.",
                        "evidence_ref": "summary-test",
                    }
                ],
            }
        )
        path = evidence_root / detector_id / f"{suffix}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        evidence["storage"]["evidence_path"] = str(path)
        path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def write_synthetic_score_evidence(
        self,
        evidence_root,
        *,
        detector_id,
        display_mode,
        results,
        label,
        status="passed",
        platform="linux-x64",
        network_mode="direct",
        container=True,
    ):
        detector = self.harness_module.detector_by_id(detector_id)
        self.assertIsNotNone(detector)
        display_key = "headed" if display_mode.startswith("headed") else display_mode
        network_key = network_mode.replace("_", "-")
        container_label = "container" if container else "host"
        suffix = f"{platform}_{detector_id}_{label}_{display_key}_{network_key}_{container_label}".replace("-", "_")
        evidence = json.loads(self.fixture_path("valid-evidence.json").read_text(encoding="utf-8"))
        evidence.update(
            {
                "run_id": f"detrun_score_{suffix}",
                "evidence_id": f"evidence_score_{suffix}",
                "artifact_id": f"unpackaged:{platform}:score-test",
                "runtime_version": "score-test",
                "tested_at": "2026-07-09T00:00:00Z",
                "detector": {
                    "detector_id": detector_id,
                    "name": detector["name"],
                    "url": detector["url"],
                    "category": detector["category"],
                    "manifest_ref": f"knowledge/manifests/detectors.json#{detector_id}",
                },
                "target": {
                    **evidence["target"],
                    "platform": platform,
                    "container": container,
                    "proxy_region_redacted": "none" if network_mode == "direct" else "redacted",
                },
                "matrix": {
                    "matrix_key": f"{platform}:{detector_id}:{display_key}:{network_key}:{container_label}",
                    "display_mode": display_mode,
                    "network_mode": network_mode,
                    "container": container,
                    "proxy": "none" if network_mode == "direct" else "redacted",
                    "required": False,
                },
                "status": status,
                "failure_mode": "none",
                "results": results,
            }
        )
        path = evidence_root / detector_id / f"{suffix}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        evidence["storage"]["evidence_path"] = str(path)
        path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def write_synthetic_validation_evidence(
        self,
        evidence_root,
        *,
        label,
        network_mode,
        matrix_proxy,
        target_proxy_region_redacted,
        results,
        required=True,
    ):
        platform = "linux-x64"
        detector_id = "sannysoft"
        display_mode = "headed"
        container = True
        network_key = network_mode.replace("_", "-")
        evidence = json.loads(self.fixture_path("valid-evidence.json").read_text(encoding="utf-8"))
        path = evidence_root / detector_id / f"{label}.json"
        evidence.update(
            {
                "run_id": f"detrun_validate_{label}",
                "evidence_id": f"evidence_validate_{label}",
                "artifact_id": f"unpackaged:{platform}:validate-test",
                "runtime_version": "validate-test",
                "target": {
                    **evidence["target"],
                    "platform": platform,
                    "container": container,
                    "proxy_region_redacted": target_proxy_region_redacted,
                },
                "matrix": {
                    "matrix_key": f"{platform}:{detector_id}:{display_mode}:{network_key}:container",
                    "display_mode": display_mode,
                    "network_mode": network_mode,
                    "container": container,
                    "proxy": matrix_proxy,
                    "required": required,
                },
                "status": "passed",
                "failure_mode": "none",
                "results": results,
            }
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        evidence["storage"]["evidence_path"] = str(path)
        path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


    def audio_score_result(self, *, detector_check, metrics):
        return {
            "detector_check": detector_check,
            "evidence_ref": "sanitized_score_comparison_fixture",
            "finding": "Synthetic sanitized CreepJS audio metric evidence.",
            "normalized_values": metrics,
            "severity": "info",
            "status": "pass",
            "surface": "audio",
        }

    def browserleaks_audio_summary_result(self, *, detector_check, metrics):
        return {
            "detector_check": detector_check,
            "evidence_ref": "sanitized_score_comparison_fixture",
            "finding": "Synthetic sanitized BrowserLeaks AudioContext summary evidence.",
            "normalized_values": metrics,
            "severity": "info",
            "status": "pass",
            "surface": "audio",
        }

    def browserleaks_audio_page_context_result(self, *, detector_check, values):
        return {
            "detector_check": detector_check,
            "evidence_ref": "sanitized_score_comparison_fixture",
            "finding": "Synthetic sanitized BrowserLeaks JavaScript Web Audio page-context evidence.",
            "normalized_values": {
                "audioContextValues": values,
                "available": True,
                "length": 44100,
                "sampleRate": 44100,
                "sum": 0.00000072,
                "sumAbs": 0.00017846,
            },
            "severity": "info",
            "status": "pass",
            "surface": "audio",
        }

    def font_availability_result(self, *, detector_check, checks):
        true_count = sum(1 for value in checks.values() if value)
        false_count = sum(1 for value in checks.values() if not value)
        return {
            "detector_check": detector_check,
            "evidence_ref": "sanitized_score_comparison_fixture",
            "finding": "Synthetic sanitized font availability evidence.",
            "normalized_values": {
                "available": True,
                "checks": checks,
                "true_count": true_count,
                "false_count": false_count,
            },
            "severity": "info",
            "status": "pass",
            "surface": "fonts",
        }


    def font_score_result(self, *, detector_check, metrics_sha256, glyph_sha256=None):
        values = {
            "candidateCount": 2,
            "metricRows": [
                {"check": True, "font": "Arial", "height": 19, "width": 241.859},
                {"check": True, "font": "Courier New", "height": 19, "width": 241.859},
            ],
            "metricsSha256": metrics_sha256,
        }
        if glyph_sha256 is not None:
            values.update({"glyphSampleCount": 73728, "glyphSha256": glyph_sha256})
        return {
            "detector_check": detector_check,
            "evidence_ref": "sanitized_score_comparison_fixture",
            "finding": "Synthetic sanitized font metric hash evidence.",
            "normalized_values": values,
            "severity": "info",
            "status": "pass",
            "surface": "fonts",
        }

    def glyph_score_result(self, *, detector_check, glyph_sha256):
        return {
            "detector_check": detector_check,
            "evidence_ref": "sanitized_score_comparison_fixture",
            "finding": "Synthetic sanitized font glyph hash evidence.",
            "normalized_values": {"glyphSampleCount": 73728, "glyphSha256": glyph_sha256},
            "severity": "info",
            "status": "pass",
            "surface": "fonts",
        }

    def webrtc_candidate_result(self, *, detector_check, raw_candidate_sha256="d" * 64):
        return {
            "detector_check": detector_check,
            "evidence_ref": "sanitized_score_comparison_fixture",
            "finding": "Synthetic sanitized WebRTC ICE candidate metadata evidence.",
            "normalized_values": {
                "available": True,
                "candidateCount": 2,
                "ipLiteralCount": 0,
                "privateIpLiteralCount": 0,
                "publicIpLiteralCount": 0,
                "rawCandidateSha256": raw_candidate_sha256,
                "types": ["host"],
            },
            "severity": "info",
            "status": "pass",
            "surface": "webrtc",
        }

    def pixelscan_page_status_result(self, *, detector_check="pixelscan_fingerprint_page_status"):
        return {
            "detector_check": detector_check,
            "evidence_ref": "sanitized_score_comparison_fixture",
            "finding": "Synthetic sanitized Pixelscan page status and score hash evidence.",
            "normalized_values": {
                "audioContextHash": "a" * 32,
                "botCheck": "No automated behavior detected",
                "browser": "Chrome 150.0.7871.101 on Linux",
                "canvasHash": "b" * 32,
                "fingerprint": "Masking detected",
                "fontHash": "c" * 32,
                "location": "Taiwan / Taipei",
                "proxy": "No proxy detected",
                "verdict": "inconsistent",
                "webglHash": "-",
            },
            "severity": "medium",
            "status": "warn",
            "surface": "audio",
        }


    def webgl_score_result(self, *, vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine", hashes=None):
        if hashes is None:
            hashes = {
                "extensionSha256": "1" * 64,
                "parameterSha256": "2" * 64,
                "precisionSha256": "3" * 64,
                "pixelSha256": "4" * 64,
            }
        values = {"vendor": vendor, "renderer": renderer, "extensionCount": 42, **hashes}
        return {
            "detector_check": "webgl_metadata_probe",
            "evidence_ref": "sanitized_score_comparison_fixture",
            "finding": "Synthetic sanitized WebGL metadata hash evidence.",
            "normalized_values": values,
            "severity": "info",
            "status": "pass",
            "surface": "webgl",
        }


    def run_compare_scores(self, evidence_root, output):
        proc = self.run_harness("compare-scores", "--evidence-root", str(evidence_root), "--output", str(output))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(output.is_file())
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertIs(payload.get("release_grade"), False)
        self.assertIn("generated_at", payload)
        self.assertIn("evidence_count", payload)
        self.assertIsInstance(payload.get("comparisons"), list)
        self.assertIsInstance(payload.get("gaps"), list)
        return payload

    def score_comparison(self, payload, *, surface, detector_id=None, detectors=None):
        for comparison in payload["comparisons"]:
            if comparison.get("surface") != surface:
                continue
            if detector_id is not None and comparison.get("detector_id") != detector_id:
                continue
            if detectors is not None:
                observed_detectors = set(comparison.get("detectors", []))
                if not observed_detectors:
                    observed_detectors = {
                        comparison.get("left_detector_id"),
                        comparison.get("right_detector_id"),
                    } - {None}
                if observed_detectors != set(detectors):
                    continue
            return comparison
        self.fail(f"missing {surface} comparison in {payload['comparisons']!r}")


    def collect_page_expression(self):
        for const in self.harness_module.collect_page.__code__.co_consts:
            if isinstance(const, str) and const.lstrip().startswith("(async"):
                return const
        self.fail("collect_page JavaScript expression constant not found")

    @classmethod
    def setUpClass(cls):
        cls.harness_module = load_harness_module()

    def test_cdp_events_until_tolerates_idle_socket_timeouts(self):
        class FakeSocket:
            def settimeout(self, timeout):
                self.timeout = timeout

        client = self.harness_module.CDPClient.__new__(self.harness_module.CDPClient)
        client.sock = FakeSocket()
        calls = {"count": 0}
        original_ws_recv = self.harness_module.ws_recv

        def fake_ws_recv(sock):
            calls["count"] += 1
            if calls["count"] == 1:
                raise self.harness_module.socket.timeout("timed out")
            return {"method": "Page.loadEventFired"}

        self.harness_module.ws_recv = fake_ws_recv
        try:
            events = client.events_until(lambda msg: msg.get("method") == "Page.loadEventFired", timeout=1)
        finally:
            self.harness_module.ws_recv = original_ws_recv

        self.assertEqual(events, [{"method": "Page.loadEventFired"}])

    def test_cdp_call_reports_method_on_idle_socket_timeout(self):
        class FakeSocket:
            def settimeout(self, timeout):
                self.timeout = timeout

        client = self.harness_module.CDPClient.__new__(self.harness_module.CDPClient)
        client.sock = FakeSocket()
        client.next_id = 1
        sent = []
        original_ws_recv = self.harness_module.ws_recv
        original_ws_send = self.harness_module.ws_send

        self.harness_module.ws_send = lambda sock, payload: sent.append(payload)
        self.harness_module.ws_recv = lambda sock: (_ for _ in ()).throw(
            self.harness_module.socket.timeout("timed out")
        )
        try:
            with self.assertRaisesRegex(TimeoutError, "Runtime.evaluate"):
                client.call("Runtime.evaluate", timeout=1)
        finally:
            self.harness_module.ws_recv = original_ws_recv
            self.harness_module.ws_send = original_ws_send

        self.assertEqual(sent[0]["method"], "Runtime.evaluate")

    def browserleaks_client_hints_value(self):
        return {
            "title": "BrowserLeaks - Client Hints",
            "url": "https://browserleaks.com/client-hints",
            "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.7871.101 Safari/537.36",
            "uaData": {
                "available": True,
                "lowEntropy": {
                    "brands": [
                        {"brand": "Not A(Brand", "version": "99"},
                        {"brand": "Chromium", "version": "150"},
                    ],
                    "mobile": False,
                    "platform": "Linux",
                },
                "highEntropy": {
                    "architecture": "x86",
                    "bitness": "64",
                    "brands": [
                        {"brand": "Not A(Brand", "version": "99"},
                        {"brand": "Chromium", "version": "150"},
                    ],
                    "fullVersionList": [
                        {"brand": "Not A(Brand", "version": "99.0.0.0"},
                        {"brand": "Chromium", "version": "150.0.7871.101"},
                        {"brand": "Google Chrome", "version": "150.0.7871.101"},
                    ],
                    "mobile": False,
                    "platform": "Linux",
                    "platformVersion": "6.8.0",
                    "wow64": False,
                },
            },
        }

    def browserleaks_audio_value(self):
        value = self.browserleaks_client_hints_value()
        value["title"] = "JavaScript Browser Information - BrowserLeaks"
        value["url"] = "https://browserleaks.com/javascript#audio"
        value["audio"] = {
            "available": True,
            "length": 44100,
            "sampleRate": 44100,
            "sum": 0.77295988,
            "sumAbs": 83.86503121,
        }
        return value

    def browserleaks_fonts_value(self):
        value = self.browserleaks_client_hints_value()
        value["title"] = "BrowserLeaks - Fonts"
        value["url"] = "https://browserleaks.com/fonts"
        value["fonts"] = {
            "available": True,
            "metrics": {
                "candidateCount": 8,
                "metricRows": [{"font": "Arial", "check": True, "width": 483.719, "height": 38}],
                "glyphSha256": "a4497a76714c34ec4e0b277f80671473d6bad7dcedd1981a9738f62cc4441166",
                "metricsSha256": "9919f29f3ba6aac608676987bfe16917d0a790f110cdc8332dfa67e8175943cb",
            },
        }
        return value

    def browserleaks_webgl_value(self):
        value = self.browserleaks_client_hints_value()
        value["title"] = "BrowserLeaks - WebGL Report"
        value["url"] = "https://browserleaks.com/webgl"
        value["webgl"] = {
            "available": True,
            "vendor": "Intel Inc.",
            "renderer": "Intel Iris OpenGL Engine",
            "extensionCount": 42,
            "extensionSha256": "1" * 64,
            "parameterSha256": "2" * 64,
            "precisionSha256": "3" * 64,
            "pixelSha256": "4" * 64,
            "pixelWidth": 16,
            "pixelHeight": 16,
        }
        return value


    def browserleaks_webrtc_value(self):
        value = self.browserleaks_client_hints_value()
        value["title"] = "BrowserLeaks - WebRTC Leak Test"
        value["url"] = "https://browserleaks.com/webrtc"
        value["webrtc"] = {
            "available": True,
            "candidateCount": 1,
            "types": ["host"],
            "ipLiteralCount": 0,
            "privateIpLiteralCount": 0,
            "publicIpLiteralCount": 0,
            "rawCandidateSha256": "0" * 64,
        }
        return value


    def pixelscan_client_hints_value(self):
        value = self.browserleaks_client_hints_value()
        value["title"] = "Pixelscan"
        value["url"] = "https://pixelscan.net/fingerprint-check"
        return value

    def iphey_client_hints_value(self):
        value = self.browserleaks_client_hints_value()
        value["title"] = "iphey"
        value["url"] = "https://iphey.com/"
        return value

    def browserscan_client_hints_value(self):
        value = self.browserleaks_client_hints_value()
        value["title"] = "BrowserScan"
        value["url"] = "https://www.browserscan.net/"
        return value

    def creepjs_client_hints_value(self):
        value = self.browserleaks_client_hints_value()
        value["title"] = "CreepJS"
        value["url"] = "https://abrahamjuliot.github.io/creepjs/"
        return value

    def creepjs_metrics_text(self):
        return "\n".join(
            [
                "CreepJS fingerprint check",
                "0% like headless",
                "0% headless",
                "0% stealth",
                "Audio",
                "sum: 124.04347527516074",
                "gain: 0.0000000432",
                "freq: 10000",
                "time: 0.024",
                "trap: 0",
                "unique: 34",
                "Fonts",
                "Fonts load(137): detected",
                "debug source 203.0.113.42 token ghp_abcdEFGH1234567890secret",
            ]
        )


    def test_classify_browserleaks_client_hints_accepts_configured_chromium_ua_ch(self):
        status, finding, severity = self.harness_module.classify_browserleaks_client_hints(
            self.browserleaks_client_hints_value()
        )

        self.assertEqual((status, severity), ("passed", "low"))
        self.assertIn("Linux", finding)

    def test_classify_browserleaks_client_hints_flags_missing_high_entropy_data(self):
        missing_full_version = self.browserleaks_client_hints_value()
        del missing_full_version["uaData"]["highEntropy"]["fullVersionList"]
        high_entropy_error = self.browserleaks_client_hints_value()
        high_entropy_error["uaData"].pop("highEntropy")
        high_entropy_error["uaData"]["highEntropyError"] = "NotAllowedError"

        cases = [
            {
                "name": "missing fullVersionList cannot prove the Chromium build",
                "value": missing_full_version,
                "finding": "fullVersionList",
            },
            {
                "name": "high entropy collection error is surfaced",
                "value": high_entropy_error,
                "finding": "NotAllowedError",
            },
        ]
        for case in cases:
            with self.subTest(case["name"]):
                status, finding, severity = self.harness_module.classify_browserleaks_client_hints(case["value"])
                self.assertIn(status, {"warning", "failed"})
                self.assertIn(severity, {"medium", "high", "critical"})
                self.assertIn(case["finding"], finding)

    def test_classify_browserleaks_dispatches_audio_page_without_claiming_release_pass(self):
        status, finding, severity = self.harness_module.classify_browserleaks(
            self.browserleaks_audio_value(),
            "https://browserleaks.com/javascript#audio",
        )

        self.assertEqual((status, severity), ("warning", "medium"))
        self.assertIn("Audio", finding)
        self.assertIn("release-grade", finding)

    def test_classify_browserleaks_dispatches_fonts_page_without_claiming_release_pass(self):
        status, finding, severity = self.harness_module.classify_browserleaks(
            self.browserleaks_fonts_value(),
            "https://browserleaks.com/fonts",
        )

        self.assertEqual((status, severity), ("warning", "medium"))
        self.assertIn("Fonts", finding)
        self.assertIn("font corpus", finding)

    def test_classify_browserleaks_dispatches_webgl_page_without_claiming_release_pass(self):
        status, finding, severity = self.harness_module.classify_browserleaks(
            self.browserleaks_webgl_value(),
            "https://browserleaks.com/webgl",
        )
        self.assertIn("rendered pixel", finding)

        self.assertEqual((status, severity), ("warning", "medium"))
        self.assertIn("WebGL", finding)
        self.assertIn("shader precision", finding)

    def test_classify_browserleaks_webgl_flags_swiftshader(self):
        value = self.browserleaks_webgl_value()
        value["webgl"]["vendor"] = "Google Inc. (Google)"
        value["webgl"]["renderer"] = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)"

        status, finding, severity = self.harness_module.classify_browserleaks(value, "https://browserleaks.com/webgl")

        self.assertEqual((status, severity), ("warning", "high"))
        self.assertIn("SwiftShader", finding)


    def test_classify_browserleaks_dispatches_webrtc_page_without_claiming_release_pass(self):
        status, finding, severity = self.harness_module.classify_browserleaks(
            self.browserleaks_webrtc_value(),
            "https://browserleaks.com/webrtc",
        )

        self.assertEqual((status, severity), ("warning", "medium"))
        self.assertIn("WebRTC", finding)
        self.assertIn("external proxy/geolocation", finding)

    def test_classify_browserleaks_webrtc_flags_ip_literals(self):
        public_leak = self.browserleaks_webrtc_value()
        public_leak["webrtc"]["ipLiteralCount"] = 1
        public_leak["webrtc"]["publicIpLiteralCount"] = 1
        private_leak = self.browserleaks_webrtc_value()
        private_leak["webrtc"]["ipLiteralCount"] = 1
        private_leak["webrtc"]["privateIpLiteralCount"] = 1

        cases = [
            (public_leak, "public IP", "high"),
            (private_leak, "private/local IP", "medium"),
        ]
        for value, finding_fragment, severity in cases:
            with self.subTest(finding_fragment):
                status, finding, observed_severity = self.harness_module.classify_browserleaks(value, "https://browserleaks.com/webrtc")
                self.assertEqual((status, observed_severity), ("warning", severity))
                self.assertIn(finding_fragment, finding)

    def test_classify_browserleaks_surface_pages_report_missing_summaries(self):
        audio = self.browserleaks_audio_value()
        del audio["audio"]["sumAbs"]
        fonts = self.browserleaks_fonts_value()
        del fonts["fonts"]["metrics"]["glyphSha256"]

        webgl = self.browserleaks_webgl_value()
        del webgl["webgl"]["parameterSha256"]


        webrtc = self.browserleaks_webrtc_value()
        del webrtc["webrtc"]["candidateCount"]

        cases = [
            (audio, "https://browserleaks.com/javascript#audio", "sumAbs"),
            (fonts, "https://browserleaks.com/fonts", "glyphSha256"),
            (webgl, "https://browserleaks.com/webgl", "parameter"),
            (webrtc, "https://browserleaks.com/webrtc", "candidateCount"),
        ]
        for value, url, missing in cases:
            with self.subTest(missing):
                status, finding, severity = self.harness_module.classify_browserleaks(value, url)
                self.assertEqual((status, severity), ("warning", "medium"))
                self.assertIn(missing, finding)


    def test_classify_pixelscan_client_hints_accepts_configured_chromium_ua_ch(self):
        status, finding, severity = self.harness_module.classify_pixelscan_client_hints(
            self.pixelscan_client_hints_value()
        )

        self.assertEqual((status, severity), ("passed", "low"))
        self.assertIn("Pixelscan", finding)
        self.assertIn("Linux", finding)
        self.assertNotIn("BrowserLeaks", finding)

    def test_classify_pixelscan_client_hints_flags_missing_high_entropy_data(self):
        missing_full_version = self.pixelscan_client_hints_value()
        del missing_full_version["uaData"]["highEntropy"]["fullVersionList"]
        high_entropy_error = self.pixelscan_client_hints_value()
        high_entropy_error["uaData"].pop("highEntropy")
        high_entropy_error["uaData"]["highEntropyError"] = "NotAllowedError"

        cases = [
            {
                "name": "missing fullVersionList cannot prove the Chromium build",
                "value": missing_full_version,
                "finding": "fullVersionList",
            },
            {
                "name": "high entropy collection error is surfaced",
                "value": high_entropy_error,
                "finding": "NotAllowedError",
            },
        ]
        for case in cases:
            with self.subTest(case["name"]):
                status, finding, severity = self.harness_module.classify_pixelscan_client_hints(case["value"])
                self.assertIn(status, {"warning", "failed"})
                self.assertIn(severity, {"medium", "high", "critical"})
                self.assertIn("Pixelscan", finding)
                self.assertIn(case["finding"], finding)

    def test_classify_iphey_client_hints_accepts_configured_chromium_ua_ch(self):
        status, finding, severity = self.harness_module.classify_iphey_client_hints(
            self.iphey_client_hints_value()
        )

        self.assertEqual((status, severity), ("passed", "low"))
        self.assertIn("iphey", finding)
        self.assertIn("Linux", finding)
        self.assertNotIn("BrowserLeaks", finding)
        self.assertNotIn("Pixelscan", finding)

    def test_classify_iphey_client_hints_flags_missing_high_entropy_data(self):
        missing_full_version = self.iphey_client_hints_value()
        del missing_full_version["uaData"]["highEntropy"]["fullVersionList"]
        high_entropy_error = self.iphey_client_hints_value()
        high_entropy_error["uaData"].pop("highEntropy")
        high_entropy_error["uaData"]["highEntropyError"] = "NotAllowedError"

        cases = [
            {
                "name": "missing fullVersionList cannot prove the Chromium build",
                "value": missing_full_version,
                "finding": "fullVersionList",
            },
            {
                "name": "high entropy collection error is surfaced",
                "value": high_entropy_error,
                "finding": "NotAllowedError",
            },
        ]
        for case in cases:
            with self.subTest(case["name"]):
                status, finding, severity = self.harness_module.classify_iphey_client_hints(case["value"])
                self.assertIn(status, {"warning", "failed"})
                self.assertIn(severity, {"medium", "high", "critical"})
                self.assertIn("iphey", finding)
                self.assertIn(case["finding"], finding)
                self.assertNotIn("BrowserLeaks", finding)
                self.assertNotIn("Pixelscan", finding)

    def test_classify_browserscan_client_hints_accepts_configured_chromium_ua_ch(self):
        status, finding, severity = self.harness_module.classify_browserscan_client_hints(
            self.browserscan_client_hints_value()
        )

        self.assertEqual((status, severity), ("passed", "low"))
        self.assertIn("BrowserScan", finding)
        self.assertIn("Linux", finding)
        self.assertNotIn("BrowserLeaks", finding)
        self.assertNotIn("Pixelscan", finding)
        self.assertNotIn("iphey", finding)

    def test_classify_browserscan_client_hints_flags_missing_high_entropy_data(self):
        missing_full_version = self.browserscan_client_hints_value()
        del missing_full_version["uaData"]["highEntropy"]["fullVersionList"]
        high_entropy_error = self.browserscan_client_hints_value()
        high_entropy_error["uaData"].pop("highEntropy")
        high_entropy_error["uaData"]["highEntropyError"] = "NotAllowedError"

        cases = [
            {
                "name": "missing fullVersionList cannot prove the Chromium build",
                "value": missing_full_version,
                "finding": "fullVersionList",
            },
            {
                "name": "high entropy collection error is surfaced",
                "value": high_entropy_error,
                "finding": "NotAllowedError",
            },
        ]
        for case in cases:
            with self.subTest(case["name"]):
                status, finding, severity = self.harness_module.classify_browserscan_client_hints(case["value"])
                self.assertIn(status, {"warning", "failed"})
                self.assertIn(severity, {"medium", "high", "critical"})
                self.assertIn("BrowserScan", finding)
                self.assertIn(case["finding"], finding)
                self.assertNotIn("BrowserLeaks", finding)
                self.assertNotIn("Pixelscan", finding)
                self.assertNotIn("iphey", finding)

    def test_classify_creepjs_client_hints_accepts_configured_chromium_ua_ch(self):
        status, finding, severity = self.harness_module.classify_creepjs_client_hints(
            self.creepjs_client_hints_value()
        )

        self.assertEqual((status, severity), ("passed", "low"))
        self.assertIn("CreepJS", finding)
        self.assertIn("Linux", finding)
        self.assertNotIn("BrowserLeaks", finding)
        self.assertNotIn("Pixelscan", finding)
        self.assertNotIn("iphey", finding)
        self.assertNotIn("BrowserScan", finding)

    def test_classify_creepjs_client_hints_flags_missing_high_entropy_data(self):
        missing_full_version = self.creepjs_client_hints_value()
        del missing_full_version["uaData"]["highEntropy"]["fullVersionList"]
        high_entropy_error = self.creepjs_client_hints_value()
        high_entropy_error["uaData"].pop("highEntropy")
        high_entropy_error["uaData"]["highEntropyError"] = "NotAllowedError"

        cases = [
            {
                "name": "missing fullVersionList cannot prove the Chromium build",
                "value": missing_full_version,
                "finding": "fullVersionList",
            },
            {
                "name": "high entropy collection error is surfaced",
                "value": high_entropy_error,
                "finding": "NotAllowedError",
            },
        ]
        for case in cases:
            with self.subTest(case["name"]):
                status, finding, severity = self.harness_module.classify_creepjs_client_hints(case["value"])
                self.assertIn(status, {"warning", "failed"})
                self.assertIn(severity, {"medium", "high", "critical"})
                self.assertIn("CreepJS", finding)
                self.assertIn(case["finding"], finding)
                self.assertNotIn("BrowserLeaks", finding)
                self.assertNotIn("Pixelscan", finding)
                self.assertNotIn("iphey", finding)
                self.assertNotIn("BrowserScan", finding)


    def test_extract_creepjs_metrics_returns_bounded_scores_without_raw_text(self):
        metrics = self.harness_module.extract_creepjs_metrics(self.creepjs_metrics_text())

        self.assertEqual(
            metrics,
            {
                "headless": {
                    "like_headless_percent": 0.0,
                    "headless_percent": 0.0,
                    "stealth_percent": 0.0,
                },
                "audio": {
                    "sum": 124.04347527516074,
                    "gain": 0.0000000432,
                    "freq": 10000.0,
                    "time": 0.024,
                    "trap": 0.0,
                    "unique": 34.0,
                },
                "fonts": {"load_count": 137},
            },
        )
        for percent in metrics["headless"].values():
            self.assertGreaterEqual(percent, 0.0)
            self.assertLessEqual(percent, 100.0)
        for audio_value in metrics["audio"].values():
            self.assertIsInstance(audio_value, float)
        metrics_payload = json.dumps(metrics, sort_keys=True)
        self.assertNotIn("CreepJS fingerprint check", metrics_payload)
        self.assertNotIn("debug source", metrics_payload)
        self.assertNotIn("203.0.113.42", metrics_payload)
        self.assertNotIn("ghp_abcdEFGH1234567890secret", metrics_payload)
        self.assertIsNone(self.harness_module.SENSITIVE_RE.search(metrics_payload))

    def test_extract_creepjs_metrics_omits_missing_sections(self):
        metrics = self.harness_module.extract_creepjs_metrics("CreepJS fingerprint check\n0% headless")

        self.assertEqual(metrics, {"headless": {"headless_percent": 0.0}})
        self.assertNotIn("audio", metrics)
        self.assertNotIn("fonts", metrics)

    def test_collect_page_uses_pixelscan_classifier_without_raw_text_payload(self):
        value = self.pixelscan_client_hints_value()
        value["text"] = "Pixelscan fingerprint check\nChromium 150.0.7871.101\nLinux x86 64"

        class FakeCDP:
            def __init__(self, page_value):
                self.page_value = page_value

            def call(self, method, params=None, *, session_id=None, timeout=20):
                if method == "Target.createTarget":
                    return {"targetId": "target-1"}, []
                if method == "Target.attachToTarget":
                    return {"sessionId": "session-1"}, []
                if method in {"Page.enable", "Runtime.enable", "Page.navigate", "Target.closeTarget"}:
                    return {}, []
                if method == "Runtime.evaluate":
                    return {"result": {"value": json.loads(json.dumps(self.page_value))}}, []
                raise AssertionError(f"unexpected CDP method: {method}")

            def events_until(self, predicate, *, timeout=30):
                return []

        record = self.harness_module.collect_page(
            FakeCDP(value),
            "pixelscan",
            "Pixelscan",
            "https://pixelscan.net/fingerprint-check",
            wait_seconds=0,
        )

        self.assertEqual(record["detector_id"], "pixelscan")
        self.assertEqual((record["status"], record["severity"]), ("passed", "low"))
        self.assertEqual(record["failure_mode"], "none")
        self.assertIn("Pixelscan", record["finding"])
        self.assertIn("uaData", record["observed"])
        self.assertNotIn("text", record["observed"])
        self.assertRegex(record["observed"]["text_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("Pixelscan fingerprint check", record["observed"]["text_excerpt"])

    def test_collect_page_uses_bounded_extended_runtime_evaluate_timeout(self):
        value = self.pixelscan_client_hints_value()
        value["text"] = "Pixelscan fingerprint check"

        class FakeCDP:
            def __init__(self, page_value):
                self.page_value = page_value
                self.evaluate_timeout = None

            def call(self, method, params=None, *, session_id=None, timeout=20):
                if method == "Target.createTarget":
                    return {"targetId": "target-1"}, []
                if method == "Target.attachToTarget":
                    return {"sessionId": "session-1"}, []
                if method in {"Page.enable", "Runtime.enable", "Page.navigate", "Target.closeTarget"}:
                    return {}, []
                if method == "Runtime.evaluate":
                    self.evaluate_timeout = timeout
                    return {"result": {"value": json.loads(json.dumps(self.page_value))}}, []
                raise AssertionError(f"unexpected CDP method: {method}")

            def events_until(self, predicate, *, timeout=30):
                return []

        cdp = FakeCDP(value)
        self.harness_module.collect_page(
            cdp,
            "pixelscan",
            "Pixelscan",
            "https://pixelscan.net/fingerprint-check",
            wait_seconds=30,
        )

        self.assertEqual(cdp.evaluate_timeout, 50)

    def test_collect_page_uses_iphey_classifier_without_raw_text_payload(self):
        value = self.iphey_client_hints_value()
        value["text"] = "iphey fingerprint check\nChromium 150.0.7871.101\nLinux x86 64"

        class FakeCDP:
            def __init__(self, page_value):
                self.page_value = page_value

            def call(self, method, params=None, *, session_id=None, timeout=20):
                if method == "Target.createTarget":
                    return {"targetId": "target-1"}, []
                if method == "Target.attachToTarget":
                    return {"sessionId": "session-1"}, []
                if method in {"Page.enable", "Runtime.enable", "Page.navigate", "Target.closeTarget"}:
                    return {}, []
                if method == "Runtime.evaluate":
                    return {"result": {"value": json.loads(json.dumps(self.page_value))}}, []
                raise AssertionError(f"unexpected CDP method: {method}")

            def events_until(self, predicate, *, timeout=30):
                return []

        record = self.harness_module.collect_page(
            FakeCDP(value),
            "iphey",
            "iphey",
            "https://iphey.com/",
            wait_seconds=0,
        )

        self.assertEqual(record["detector_id"], "iphey")
        self.assertEqual((record["status"], record["severity"]), ("passed", "low"))
        self.assertEqual(record["failure_mode"], "none")
        self.assertIn("iphey", record["finding"])
        self.assertNotIn("BrowserLeaks", record["finding"])
        self.assertNotIn("Pixelscan", record["finding"])
        self.assertIn("uaData", record["observed"])
        self.assertNotIn("text", record["observed"])
        self.assertRegex(record["observed"]["text_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("iphey fingerprint check", record["observed"]["text_excerpt"])

    def test_collect_page_uses_browserscan_classifier_without_raw_text_payload(self):
        value = self.browserscan_client_hints_value()
        value["text"] = "BrowserScan fingerprint check\nChromium 150.0.7871.101\nLinux x86 64"

        class FakeCDP:
            def __init__(self, page_value):
                self.page_value = page_value

            def call(self, method, params=None, *, session_id=None, timeout=20):
                if method == "Target.createTarget":
                    return {"targetId": "target-1"}, []
                if method == "Target.attachToTarget":
                    return {"sessionId": "session-1"}, []
                if method in {"Page.enable", "Runtime.enable", "Page.navigate", "Target.closeTarget"}:
                    return {}, []
                if method == "Runtime.evaluate":
                    return {"result": {"value": json.loads(json.dumps(self.page_value))}}, []
                raise AssertionError(f"unexpected CDP method: {method}")

            def events_until(self, predicate, *, timeout=30):
                return []

        record = self.harness_module.collect_page(
            FakeCDP(value),
            "browserscan",
            "BrowserScan",
            "https://www.browserscan.net/",
            wait_seconds=0,
        )

        self.assertEqual(record["detector_id"], "browserscan")
        self.assertEqual((record["status"], record["severity"]), ("passed", "low"))
        self.assertEqual(record["failure_mode"], "none")
        self.assertIn("BrowserScan", record["finding"])
        self.assertNotIn("BrowserLeaks", record["finding"])
        self.assertNotIn("Pixelscan", record["finding"])
        self.assertNotIn("iphey", record["finding"])
        self.assertIn("uaData", record["observed"])
        self.assertNotIn("text", record["observed"])
        self.assertRegex(record["observed"]["text_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("BrowserScan fingerprint check", record["observed"]["text_excerpt"])

    def test_collect_page_uses_creepjs_classifier_without_raw_text_payload(self):
        value = self.creepjs_client_hints_value()
        value["text"] = self.creepjs_metrics_text()

        class FakeCDP:
            def __init__(self, page_value):
                self.page_value = page_value

            def call(self, method, params=None, *, session_id=None, timeout=20):
                if method == "Target.createTarget":
                    return {"targetId": "target-1"}, []
                if method == "Target.attachToTarget":
                    return {"sessionId": "session-1"}, []
                if method in {"Page.enable", "Runtime.enable", "Page.navigate", "Target.closeTarget"}:
                    return {}, []
                if method == "Runtime.evaluate":
                    return {"result": {"value": json.loads(json.dumps(self.page_value))}}, []
                raise AssertionError(f"unexpected CDP method: {method}")

            def events_until(self, predicate, *, timeout=30):
                return []

        record = self.harness_module.collect_page(
            FakeCDP(value),
            "creepjs",
            "CreepJS",
            "https://abrahamjuliot.github.io/creepjs/",
            wait_seconds=0,
        )

        self.assertEqual(record["detector_id"], "creepjs")
        self.assertEqual((record["status"], record["severity"]), ("passed", "low"))
        self.assertEqual(record["failure_mode"], "none")
        self.assertIn("CreepJS", record["finding"])
        self.assertNotIn("BrowserLeaks", record["finding"])
        self.assertNotIn("Pixelscan", record["finding"])
        self.assertNotIn("iphey", record["finding"])
        self.assertNotIn("BrowserScan", record["finding"])
        self.assertIn("uaData", record["observed"])
        self.assertNotIn("text", record["observed"])
        self.assertRegex(record["observed"]["text_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("CreepJS fingerprint check", record["observed"]["text_excerpt"])
        metrics = record["observed"]["detector_metrics"]
        self.assertEqual(metrics["headless"]["like_headless_percent"], 0.0)
        self.assertEqual(metrics["headless"]["headless_percent"], 0.0)
        self.assertEqual(metrics["headless"]["stealth_percent"], 0.0)
        self.assertEqual(
            metrics["audio"],
            {
                "sum": 124.04347527516074,
                "gain": 0.0000000432,
                "freq": 10000.0,
                "time": 0.024,
                "trap": 0.0,
                "unique": 34.0,
            },
        )
        self.assertEqual(metrics["fonts"]["load_count"], 137)
        metrics_payload = json.dumps(metrics, sort_keys=True)
        self.assertNotIn("text", metrics)
        self.assertNotIn("CreepJS fingerprint check", metrics_payload)
        self.assertNotIn("debug source", metrics_payload)
        self.assertNotIn("203.0.113.42", metrics_payload)
        self.assertNotIn("ghp_abcdEFGH1234567890secret", metrics_payload)
        self.assertIsNone(self.harness_module.SENSITIVE_RE.search(metrics_payload))

    def test_collect_page_preserves_sanitized_font_metrics_without_raw_payloads(self):
        value = self.creepjs_client_hints_value()
        value["text"] = self.creepjs_metrics_text()
        value["fonts"] = {
            "available": True,
            "checks": {
                "Arial": True,
                "Courier New": True,
            },
            "metrics": {
                "metricRows": [
                    {"font": "Arial", "width": 126.5, "height": 19.0},
                    {"font": "Courier New", "width": 144.25, "height": 17},
                ],
                "metricsSha256": "a" * 64,
                "glyphSha256": "b" * 64,
            },
        }

        class FakeCDP:
            def __init__(self, page_value):
                self.page_value = page_value

            def call(self, method, params=None, *, session_id=None, timeout=20):
                if method == "Target.createTarget":
                    return {"targetId": "target-1"}, []
                if method == "Target.attachToTarget":
                    return {"sessionId": "session-1"}, []
                if method in {"Page.enable", "Runtime.enable", "Page.navigate", "Target.closeTarget"}:
                    return {}, []
                if method == "Runtime.evaluate":
                    return {"result": {"value": json.loads(json.dumps(self.page_value))}}, []
                raise AssertionError(f"unexpected CDP method: {method}")

            def events_until(self, predicate, *, timeout=30):
                return []

        record = self.harness_module.collect_page(
            FakeCDP(value),
            "creepjs",
            "CreepJS",
            "https://abrahamjuliot.github.io/creepjs/",
            wait_seconds=0,
        )

        font_metrics = record["observed"]["fonts"]["metrics"]
        self.assertEqual(
            font_metrics["metricRows"],
            [
                {"font": "Arial", "width": 126.5, "height": 19.0},
                {"font": "Courier New", "width": 144.25, "height": 17},
            ],
        )
        for row in font_metrics["metricRows"]:
            with self.subTest(font=row["font"]):
                for dimension in ("width", "height"):
                    self.assertIsInstance(row[dimension], (int, float))
                    self.assertNotIsInstance(row[dimension], bool)
        for hash_field, expected_hash in (
            ("metricsSha256", "a" * 64),
            ("glyphSha256", "b" * 64),
        ):
            with self.subTest(hash_field=hash_field):
                self.assertEqual(font_metrics[hash_field], expected_hash)
                self.assertRegex(font_metrics[hash_field], r"^[0-9a-f]{64}$")

        raw_payload_keys = {
            "dataUrl",
            "data_url",
            "dataUrlSha256Input",
            "imageData",
            "image_data",
            "pixels",
            "pixel_data",
            "raw_pixels",
            "rawGlyphs",
            "raw_glyphs",
        }

        def raw_keys_under(node, path="$"):
            if isinstance(node, dict):
                matches = []
                for key, child in node.items():
                    child_path = f"{path}.{key}"
                    if key in raw_payload_keys:
                        matches.append(child_path)
                    matches.extend(raw_keys_under(child, child_path))
                return matches
            if isinstance(node, list):
                matches = []
                for index, child in enumerate(node):
                    matches.extend(raw_keys_under(child, f"{path}[{index}]"))
                return matches
            return []

        self.assertEqual(raw_keys_under(font_metrics), [])

    def test_collect_page_uses_browserleaks_classifier_without_raw_text_payload(self):
        value = self.browserleaks_client_hints_value()
        value["text"] = "BrowserLeaks Client Hints\nChromium 150.0.7871.101\nLinux x86 64"

        class FakeCDP:
            def __init__(self, page_value):
                self.page_value = page_value

            def call(self, method, params=None, *, session_id=None, timeout=20):
                if method == "Target.createTarget":
                    return {"targetId": "target-1"}, []
                if method == "Target.attachToTarget":
                    return {"sessionId": "session-1"}, []
                if method in {"Page.enable", "Runtime.enable", "Page.navigate", "Target.closeTarget"}:
                    return {}, []
                if method == "Runtime.evaluate":
                    return {"result": {"value": json.loads(json.dumps(self.page_value))}}, []
                raise AssertionError(f"unexpected CDP method: {method}")

            def events_until(self, predicate, *, timeout=30):
                return []

        record = self.harness_module.collect_page(
            FakeCDP(value),
            "browserleaks",
            "BrowserLeaks",
            "https://browserleaks.com/client-hints",
            wait_seconds=0,
        )

        self.assertEqual(record["detector_id"], "browserleaks")
        self.assertEqual((record["status"], record["severity"]), ("passed", "low"))
        self.assertEqual(record["failure_mode"], "none")
        self.assertIn("uaData", record["observed"])
        self.assertNotIn("text", record["observed"])
        self.assertRegex(record["observed"]["text_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("BrowserLeaks Client Hints", record["observed"]["text_excerpt"])

    def test_collect_page_redacts_sensitive_values_from_text_excerpt(self):
        value = self.browserleaks_client_hints_value()
        value["text"] = (
            "BrowserLeaks Client Hints observed from office network 203.0.113.42 "
            "with session token ghp_abcdEFGH1234567890secret and final verdict harmless."
        )

        class FakeCDP:
            def __init__(self, page_value):
                self.page_value = page_value

            def call(self, method, params=None, *, session_id=None, timeout=20):
                if method == "Target.createTarget":
                    return {"targetId": "target-1"}, []
                if method == "Target.attachToTarget":
                    return {"sessionId": "session-1"}, []
                if method in {"Page.enable", "Runtime.enable", "Page.navigate", "Target.closeTarget"}:
                    return {}, []
                if method == "Runtime.evaluate":
                    return {"result": {"value": json.loads(json.dumps(self.page_value))}}, []
                raise AssertionError(f"unexpected CDP method: {method}")

            def events_until(self, predicate, *, timeout=30):
                return []

        record = self.harness_module.collect_page(
            FakeCDP(value),
            "browserleaks",
            "BrowserLeaks",
            "https://browserleaks.com/client-hints",
            wait_seconds=0,
        )

        observed = record["observed"]
        excerpt = observed["text_excerpt"]
        self.assertNotIn("text", observed)
        self.assertRegex(observed["text_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("BrowserLeaks Client Hints observed from office network", excerpt)
        self.assertIn("with session token", excerpt)
        self.assertIn("and final verdict harmless.", excerpt)
        self.assertNotIn("203.0.113.42", excerpt)
        self.assertNotIn("ghp_abcdEFGH1234567890secret", excerpt)
        self.assertIsNone(self.harness_module.SENSITIVE_RE.search(excerpt))

    def test_redact_sensitive_text_removes_creepjs_page_identifiers(self):
        fp_id = "0123456789abcdef" * 4
        host_candidate = "489cd75f-cdb2-416e-8693-b4fed20cd482.local"
        ipv4_literal = "203.0.113.42"
        github_token = "ghp_" + "abcdEFGH1234567890secret"
        excerpt = (
            f"CreepJS FP ID {fp_id} host connection candidate {host_candidate} "
            f"from relay {ipv4_literal} using token {github_token}; detector prose stays harmless."
        )

        redacted = self.harness_module.redact_sensitive_text(excerpt)
        for label in ("FP ID", "host connection", "candidate"):
            with self.subTest(label=label):
                if label not in redacted:
                    self.fail(f"harmless label was removed: {label}")
        for label, identifier in (
            ("FP ID", fp_id),
            ("UUID local host candidate", host_candidate),
            ("IPv4 literal", ipv4_literal),
            ("GitHub token", github_token),
        ):
            with self.subTest(label=label):
                if identifier in redacted:
                    self.fail(f"{label} was not redacted")
        if self.harness_module.SENSITIVE_RE.search(redacted) is not None:
            self.fail("redacted excerpt still matches the sensitive-value pattern")

    def test_classify_sannysoft_maps_automation_signals_to_statuses(self):
        cases = [
            {
                "name": "passes when webdriver is false, row is missing, and UA is headed",
                "value": {
                    "text": "WebDriver (New) missing\nChrome (New) present",
                    "webdriver": False,
                    "ua": "Mozilla/5.0 AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
                },
                "expected": ("passed", "low"),
                "finding": "webdriver is false",
            },
            {
                "name": "warns when HeadlessChrome remains in the UA",
                "value": {
                    "text": "WebDriver (New) missing\nChrome (New) present",
                    "webdriver": False,
                    "ua": "Mozilla/5.0 AppleWebKit/537.36 HeadlessChrome/126.0.0.0 Safari/537.36",
                },
                "expected": ("warning", "medium"),
                "finding": "HeadlessChrome",
            },
            {
                "name": "fails when page text reports webdriver exposure",
                "value": {
                    "text": "Webdriver present: true\nChrome (New) present",
                    "webdriver": True,
                    "ua": "Mozilla/5.0 AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
                },
                "expected": ("failed", "high"),
                "finding": "webdriver exposure",
            },
        ]
        for case in cases:
            with self.subTest(case["name"]):
                status, finding, severity = self.harness_module.classify_sannysoft(case["value"])
                self.assertEqual((status, severity), case["expected"])
                self.assertIn(case["finding"], finding)

    def test_supported_collectors_includes_pixelscan_fingerprint_check(self):
        self.assertEqual(
            self.harness_module.SUPPORTED_COLLECTORS.get("pixelscan"),
            ("Pixelscan", "https://pixelscan.net/fingerprint-check"),
        )

    def test_classify_pixelscan_uses_page_status_when_available(self):
        status, finding, severity = self.harness_module.classify_pixelscan_client_hints({
            "pixelscanPage": {
                "available": True,
                "verdict": "inconsistent",
                "fingerprint": "Masking detected",
            }
        })
        self.assertEqual((status, severity), ("warning", "medium"))
        self.assertIn("inconsistent/masking", finding)


    def test_supported_collectors_includes_iphey(self):
        self.assertEqual(
            self.harness_module.SUPPORTED_COLLECTORS.get("iphey"),
            ("iphey", "https://iphey.com/"),
        )

    def test_supported_collectors_includes_browserscan(self):
        self.assertEqual(
            self.harness_module.SUPPORTED_COLLECTORS.get("browserscan"),
            ("BrowserScan", "https://www.browserscan.net/"),
        )

    def test_supported_collectors_includes_creepjs(self):
        self.assertEqual(
            self.harness_module.SUPPORTED_COLLECTORS.get("creepjs"),
            ("CreepJS", "https://abrahamjuliot.github.io/creepjs/"),
        )


    def test_collect_page_expression_escapes_sdp_newline_for_javascript(self):
        expr = self.collect_page_expression()
        self.assertIn("pc.localDescription.sdp.split('\\n')", expr)
        self.assertNotIn("pc.localDescription.sdp.split('\n')", expr)

    def test_collect_page_expression_bounds_offline_audio_rendering_with_timeout(self):
        expr = self.collect_page_expression()
        self.assertIn("offline_audio_context_timeout", expr)
        self.assertRegex(
            expr,
            r"Promise\.race\s*\(\s*\[[\s\S]*(ctx\.startRendering\(\)[\s\S]*setTimeout|setTimeout[\s\S]*ctx\.startRendering\(\))[\s\S]*\]\s*\)",
        )

    def test_collect_page_expression_records_permission_feature_surface(self):
        expr = self.collect_page_expression()
        self.assertIn("const features = await (async () => {", expr)
        self.assertIn("'geolocation'", expr)
        self.assertIn("'notifications'", expr)
        self.assertIn("'idle-detection'", expr)
        self.assertIn("'local-fonts'", expr)
        self.assertIn("navigator.permissions.query({name})", expr)
        self.assertIn("contactsManager", expr)
        self.assertIn("contentIndex", expr)
        self.assertIn("localFonts", expr)
        self.assertIn("webShare", expr)
        self.assertIn("webShareData", expr)
        self.assertIn("windowControlsOverlay", expr)
        self.assertIn("return {title, url: location.href", expr)
        self.assertIn("canvas: canvasProbe, features, webgl: gl", expr)

    def test_collect_page_expression_records_browserleaks_audio_page_fields(self):
        expr = self.collect_page_expression()
        self.assertIn("const browserleaksAudioPage = (() => {", expr)
        self.assertIn("location.hash === '#audio'", expr)
        self.assertIn("text.split('\\n')", expr)
        self.assertNotIn("text.split('\n')", expr)
        self.assertIn("'Web Audio API'", expr)
        self.assertIn("['sampleRate', 'Sample Rate']", expr)
        self.assertIn("const audioContext = (() => {", expr)
        self.assertIn("ctx.createAnalyser()", expr)
        self.assertIn("observedFieldCount", expr)
        self.assertIn("audio, browserleaksAudioPage, pixelscanPage, fonts", expr)

    def test_collect_page_expression_records_pixelscan_page_fields(self):
        expr = self.collect_page_expression()
        self.assertIn("const pixelscanPage = (() => {", expr)
        self.assertIn("location.hostname.includes('pixelscan.net')", expr)
        self.assertIn("Your Browser Fingerprint is inconsistent", expr)
        self.assertIn("valueAfter('AudioContext Hash')", expr)
        self.assertIn("audio, browserleaksAudioPage, pixelscanPage, fonts", expr)

    def test_collect_rejects_unsupported_detector_before_cdp_connection(self):
        unsupported_detector = "unknown-detector"
        self.assertNotIn(unsupported_detector, self.harness_module.SUPPORTED_COLLECTORS)
        proc = self.run_harness(
            "collect",
            "--detector",
            unsupported_detector,
            "--cdp-url",
            "http://127.0.0.1:9",
            "--wait-seconds",
            "0",
        )
        self.assertEqual(proc.returncode, self.harness_module.EXIT_COLLECT_UNAVAILABLE)
        self.assertEqual(proc.stdout, "")
        self.assertIn(f"collector not implemented for detector: {unsupported_detector}", proc.stderr)

    def test_collect_uses_url_override_without_changing_browserleaks_identity(self):
        module = self.harness_module
        original_http_json = module.http_json
        original_cdp_client = module.CDPClient
        original_collect_page = module.collect_page
        self.addCleanup(setattr, module, "http_json", original_http_json)
        self.addCleanup(setattr, module, "CDPClient", original_cdp_client)
        self.addCleanup(setattr, module, "collect_page", original_collect_page)

        calls = []

        class FakeCDP:
            def __init__(self, websocket_url):
                self.websocket_url = websocket_url

        def fake_http_json(url):
            self.assertEqual(url, "http://127.0.0.1:9222/json/version")
            return {"webSocketDebuggerUrl": "ws://127.0.0.1/devtools/browser/test"}

        def fake_collect_page(cdp, detector_id, name, url, *, wait_seconds):
            calls.append(
                {
                    "websocket_url": cdp.websocket_url,
                    "detector_id": detector_id,
                    "name": name,
                    "url": url,
                    "wait_seconds": wait_seconds,
                }
            )
            return {
                "detector_id": detector_id,
                "name": name,
                "url": url,
                "status": "passed",
                "failure_mode": "none",
                "finding": "stubbed BrowserLeaks collection",
                "severity": "low",
                "observed": {},
            }

        module.http_json = fake_http_json
        module.CDPClient = FakeCDP
        module.collect_page = fake_collect_page

        def run_collect(*extra_args):
            with tempfile.TemporaryDirectory() as td:
                output = Path(td) / "evidence.json"
                code = module.main(
                    [
                        "collect",
                        "--detector",
                        "browserleaks",
                        "--wait-seconds",
                        "0",
                        "--output",
                        str(output),
                        *extra_args,
                    ]
                )
                self.assertEqual(code, 0)
                return json.loads(output.read_text(encoding="utf-8"))

        override_url = "https://browserleaks.com/fonts"
        override_payload = run_collect("--url", override_url)
        default_payload = run_collect()

        self.assertEqual(
            calls,
            [
                {
                    "websocket_url": "ws://127.0.0.1/devtools/browser/test",
                    "detector_id": "browserleaks",
                    "name": "BrowserLeaks",
                    "url": override_url,
                    "wait_seconds": 0,
                },
                {
                    "websocket_url": "ws://127.0.0.1/devtools/browser/test",
                    "detector_id": "browserleaks",
                    "name": "BrowserLeaks",
                    "url": module.SUPPORTED_COLLECTORS["browserleaks"][1],
                    "wait_seconds": 0,
                },
            ],
        )
        self.assertEqual(override_payload["records"][0]["url"], override_url)
        self.assertEqual(default_payload["records"][0]["url"], module.SUPPORTED_COLLECTORS["browserleaks"][1])

    def test_collect_page_alias_selects_browserleaks_surface_url(self):
        module = self.harness_module

        self.assertEqual(
            module.resolve_collect_url("browserleaks", page="audio", url=None),
            "https://browserleaks.com/javascript#audio",
        )
        self.assertNotEqual(
            module.resolve_collect_url("browserleaks", page="audio", url=None),
            "https://browserleaks.com/javascript/audio",
        )
        self.assertEqual(
            module.resolve_collect_url("browserleaks", page="fonts", url=None),
            "https://browserleaks.com/fonts",
        )

    def test_collect_page_alias_rejects_unknown_page_before_cdp_connection(self):
        module = self.harness_module
        original_http_json = module.http_json
        self.addCleanup(setattr, module, "http_json", original_http_json)

        def fail_http_json(url):
            self.fail("unsupported collector page should be rejected before CDP lookup")

        module.http_json = fail_http_json

        code = module.main(
            [
                "collect",
                "--detector",
                "browserleaks",
                "--page",
                "unknown-surface",
                "--wait-seconds",
                "0",
            ]
        )

        self.assertEqual(code, module.EXIT_UNSUPPORTED)

    def test_collect_url_override_wins_over_page_alias(self):
        module = self.harness_module
        override_url = "https://browserleaks.com/client-hints"

        self.assertEqual(
            module.resolve_collect_url("browserleaks", page="audio", url=override_url),
            override_url,
        )

    def test_proxy_preflight_reports_missing_proxy_inputs_as_json(self):
        proc = self.run_harness(
            "proxy-preflight",
            env={
                "BROWSEFORGE_DETECTOR_PROXY_URL": None,
                "BROWSEFORGE_DETECTOR_PROXY_REGION": None,
            },
        )

        self.assertEqual(proc.returncode, self.harness_module.EXIT_PREFLIGHT)
        self.assertEqual(proc.stderr, "")
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "failed")
        self.assertIs(payload["ready"], False)
        self.assertCountEqual(
            payload["missing"],
            [
                "BROWSEFORGE_DETECTOR_PROXY_URL",
                "BROWSEFORGE_DETECTOR_PROXY_REGION",
            ],
        )
        self.assertEqual(payload["errors"], [])
        self.assertIsNone(payload["proxy"])

    def test_proxy_preflight_output_writes_manifest_schema_fields(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "proxy-preflight.json"
            proc = self.run_harness(
                "proxy-preflight",
                "--output",
                str(output),
                "--generated-at",
                "2026-07-10T00:00:00Z",
                env={
                    "BROWSEFORGE_DETECTOR_PROXY_URL": None,
                    "BROWSEFORGE_DETECTOR_PROXY_REGION": None,
                },
            )

            self.assertEqual(proc.returncode, self.harness_module.EXIT_PREFLIGHT)
            self.assertEqual(proc.stderr, "")
            self.assertEqual(str(output), proc.stdout.strip())
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["runtime_id"], "browseforge-chromium")
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["generated_at"], "2026-07-10T00:00:00Z")
        self.assertEqual(payload["status"], "failed")
        self.assertIs(payload["ready"], False)
        self.assertCountEqual(
            payload["missing"],
            [
                "BROWSEFORGE_DETECTOR_PROXY_URL",
                "BROWSEFORGE_DETECTOR_PROXY_REGION",
            ],
        )

    def test_proxy_preflight_rejects_loopback_and_localhost_proxy_authorities(self):
        cases = [
            ("loopback IPv4", "http://127.0.0.1:8080", "127.0.0.1"),
            ("localhost", "http://localhost:8080", "localhost"),
        ]
        for name, proxy_url, raw_authority in cases:
            with self.subTest(name):
                proc = self.run_harness(
                    "proxy-preflight",
                    "--proxy-url",
                    proxy_url,
                    "--proxy-region-redacted",
                    "redacted-region",
                    env={
                        "BROWSEFORGE_DETECTOR_PROXY_URL": None,
                        "BROWSEFORGE_DETECTOR_PROXY_REGION": None,
                    },
                )

                self.assertEqual(proc.returncode, self.harness_module.EXIT_PREFLIGHT)
                self.assertEqual(proc.stderr, "")
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["status"], "failed")
                self.assertIs(payload["ready"], False)
                self.assertEqual(payload["missing"], [])
                self.assertIsNone(payload["proxy"])
                self.assertTrue(any("loopback/private/local" in error for error in payload["errors"]))
                self.assertNotIn(raw_authority, proc.stdout)

    def test_proxy_preflight_sanitizes_credentials_and_ip_literal_proxy_url(self):
        proc = self.run_harness(
            "proxy-preflight",
            "--proxy-url",
            "socks5://proxy-user:ghp_abcdEFGH1234567890secret@8.8.8.8:1080",
            "--proxy-region-redacted",
            "external-region-redacted",
            env={
                "BROWSEFORGE_DETECTOR_PROXY_URL": None,
                "BROWSEFORGE_DETECTOR_PROXY_REGION": None,
            },
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertIs(payload["ready"], True)
        self.assertEqual(payload["missing"], [])
        self.assertEqual(payload["errors"], [])
        self.assertEqual(
            payload["proxy"],
            {
                "scheme": "socks5",
                "host_redacted": "[REDACTED_PROXY_HOST]",
                "port_redacted": "[REDACTED_PROXY_PORT]",
                "has_credentials": True,
            },
        )
        self.assertNotIn("proxy-user", proc.stdout)
        self.assertNotIn("ghp_abcdEFGH1234567890secret", proc.stdout)
        self.assertNotIn("8.8.8.8", proc.stdout)

    def test_proxy_preflight_redacts_domain_host_and_port(self):
        proc = self.run_harness(
            "proxy-preflight",
            "--proxy-url",
            "socks5://user:secret@proxy.example.net:54321",
            "--proxy-region-redacted",
            "external-region-redacted",
            env={
                "BROWSEFORGE_DETECTOR_PROXY_URL": None,
                "BROWSEFORGE_DETECTOR_PROXY_REGION": None,
            },
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["proxy"]["host_redacted"], "[REDACTED_PROXY_HOST]")
        self.assertEqual(payload["proxy"]["port_redacted"], "[REDACTED_PROXY_PORT]")
        self.assertNotIn("proxy.example.net", proc.stdout)
        self.assertNotIn("54321", proc.stdout)
        self.assertNotIn("secret", proc.stdout)

    def test_proxy_preflight_accepts_valid_external_hostname_and_region(self):
        proc = self.run_harness(
            "proxy-preflight",
            "--proxy-url",
            "https://proxy.example.net:8443",
            "--proxy-region-redacted",
            "europe-redacted",
            env={
                "BROWSEFORGE_DETECTOR_PROXY_URL": None,
                "BROWSEFORGE_DETECTOR_PROXY_REGION": None,
            },
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertIs(payload["ready"], True)
        self.assertEqual(payload["missing"], [])
        self.assertEqual(payload["errors"], [])
        self.assertEqual(
            payload["proxy"],
            {
                "scheme": "https",
                "host_redacted": "[REDACTED_PROXY_HOST]",
                "port_redacted": "[REDACTED_PROXY_PORT]",
                "has_credentials": False,
            },
        )
        self.assertNotIn("proxy.example.net", proc.stdout)
        self.assertNotIn("8443", proc.stdout)
        self.assertEqual(payload["proxy_region_redacted"], "europe-redacted")

    def test_list_targets_reads_current_manifest(self):
        proc = self.run_harness("list-targets")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        ids = {d["detector_id"] for d in data["detectors"]}
        self.assertEqual(ids, {"sannysoft", "browserleaks", "creepjs", "pixelscan", "iphey", "browserscan"})
        self.assertIn("automation_signals", data["canonical_surfaces"])

    def test_plan_linux_matrix_is_deterministic(self):
        first = self.run_harness("plan", "--runtime-version", "v0.1.0-alpha.0", "--platform", "linux-x64")
        second = self.run_harness("plan", "--runtime-version", "v0.1.0-alpha.0", "--platform", "linux-x64")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        rows = json.loads(first.stdout)["rows"]
        self.assertTrue(any(r["detector_id"] == "sannysoft" and r["network_mode"] == "proxy" for r in rows))
        bad = self.run_harness("plan", "--runtime-version", "v0.1.0-alpha.0", "--platform", "amiga")
        self.assertEqual(bad.returncode, 5)

    def test_compare_scores_command_writes_creepjs_audio_display_mode_deltas(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="creepjs",
                display_mode="headless",
                label="audio_headless",
                results=[
                    self.audio_score_result(
                        detector_check="creepjs_audio_score_metrics",
                        metrics={
                            "sum": 100.0,
                            "gain": 2.0,
                            "freq": 300.0,
                            "time": 4.0,
                            "trap": 5.0,
                            "unique": 6.0,
                        },
                    )
                ],
            )
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="creepjs",
                display_mode="headed_xvfb",
                label="audio_headed",
                results=[
                    self.audio_score_result(
                        detector_check="creepjs_headed_audio_metrics",
                        metrics={
                            "sum": 101.25,
                            "gain": 2.0,
                            "freq": 303.5,
                            "time": 4.0,
                            "trap": 8.0,
                            "unique": 6.0,
                        },
                    )
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            self.assertEqual(payload["evidence_count"], 2)
            comparison = self.score_comparison(payload, surface="audio", detector_id="creepjs")
            self.assertEqual(comparison["status"], "warning")
            deltas = comparison["metric_deltas"]
            self.assertEqual(deltas["sum"], 1.25)
            self.assertEqual(deltas["freq"], 3.5)
            self.assertEqual(deltas["trap"], 3.0)
            self.assertEqual(deltas["gain"], 0.0)
            for metric in ("sum", "gain", "freq", "time", "trap", "unique"):
                with self.subTest(metric=metric):
                    self.assertIsInstance(deltas[metric], (int, float))
                    self.assertNotIsInstance(deltas[metric], bool)
            self.assertEqual(comparison["matching_metrics"], ["gain", "time", "unique"])
            self.assertEqual(comparison["drift_metrics"], ["freq", "sum", "trap"])
            self.assertIs(comparison["trap_only_drift"], False)
            self.assertIn("differ", comparison["finding"].lower())

    def test_compare_scores_identifies_creepjs_trap_only_audio_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            base_metrics = {
                "sum": 100.0,
                "gain": 2.0,
                "freq": 300.0,
                "time": 4.0,
                "trap": 5.0,
                "unique": 6.0,
            }
            for display_mode, label, trap_value in [
                ("headless", "audio_headless_trap_only", 5.0),
                ("headed_xvfb", "audio_headed_trap_only", 8.0),
            ]:
                metrics = {**base_metrics, "trap": trap_value}
                self.write_synthetic_score_evidence(
                    evidence_root,
                    detector_id="creepjs",
                    display_mode=display_mode,
                    label=label,
                    results=[
                        self.audio_score_result(
                            detector_check=f"creepjs_{label}",
                            metrics=metrics,
                        )
                    ],
                )

            payload = self.run_compare_scores(evidence_root, output)

            comparison = self.score_comparison(payload, surface="audio", detector_id="creepjs")
            self.assertEqual(comparison["drift_metrics"], ["trap"])
            self.assertEqual(comparison["matching_metrics"], ["freq", "gain", "sum", "time", "unique"])
            self.assertIs(comparison["trap_only_drift"], True)
            self.assertIn("trap metric", comparison["finding"])


    def test_compare_scores_command_writes_browserleaks_audio_summary_deltas(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="browserleaks",
                display_mode="headless",
                label="browserleaks_audio_headless",
                results=[
                    self.browserleaks_audio_summary_result(
                        detector_check="browserleaks_audio_headless_summary",
                        metrics={
                            "sampleRate": 44100,
                            "length": 44100,
                            "sum": 0.77295988,
                            "sumAbs": 83.86503121,
                        },
                    )
                ],
            )
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="browserleaks",
                display_mode="headed_xvfb",
                label="browserleaks_audio_headed",
                results=[
                    self.browserleaks_audio_summary_result(
                        detector_check="browserleaks_audio_headed_summary",
                        metrics={
                            "sampleRate": 44100,
                            "length": 44100,
                            "sum": 0.77295988,
                            "sumAbs": 84.01503121,
                        },
                    )
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            comparison = self.score_comparison(payload, surface="audio", detector_id="browserleaks")
            self.assertEqual(comparison["comparison_id"], "browserleaks_audio_headless_vs_headed")
            self.assertEqual(comparison["status"], "warning")
            self.assertEqual(comparison["metric_deltas"]["sampleRate"], 0)
            self.assertEqual(comparison["metric_deltas"]["length"], 0)
            self.assertAlmostEqual(comparison["metric_deltas"]["sumAbs"], 0.15)
            self.assertIn("BrowserLeaks bounded AudioContext", comparison["finding"])

    def test_compare_scores_command_writes_pixelscan_audio_and_font_deltas(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            headless_checks = {"Arial": True, "Calibri": True, "Consolas": True}
            headed_checks = {"Arial": True, "Calibri": False, "Consolas": True}
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="pixelscan",
                display_mode="headless",
                label="pixelscan_audio_fonts_headless",
                results=[
                    self.browserleaks_audio_summary_result(
                        detector_check="pixelscan_audio_headless_summary",
                        metrics={
                            "sampleRate": 44100,
                            "length": 44100,
                            "sum": 0.5,
                            "sumAbs": 10.0,
                        },
                    ),
                    self.font_availability_result(
                        detector_check="pixelscan_fonts_headless_availability",
                        checks=headless_checks,
                    ),
                ],
            )
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="pixelscan",
                display_mode="headed_xvfb",
                label="pixelscan_audio_fonts_headed",
                results=[
                    self.browserleaks_audio_summary_result(
                        detector_check="pixelscan_audio_headed_summary",
                        metrics={
                            "sampleRate": 44100,
                            "length": 44100,
                            "sum": 0.75,
                            "sumAbs": 9.5,
                        },
                    ),
                    self.font_availability_result(
                        detector_check="pixelscan_fonts_headed_availability",
                        checks=headed_checks,
                    ),
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            audio = self.score_comparison(payload, surface="audio", detector_id="pixelscan")
            self.assertEqual(audio["comparison_id"], "pixelscan_audio_headless_vs_headed")
            self.assertEqual(audio["status"], "warning")
            self.assertEqual(audio["metric_deltas"]["sampleRate"], 0)
            self.assertEqual(audio["metric_deltas"]["sum"], 0.25)
            self.assertEqual(audio["metric_deltas"]["sumAbs"], -0.5)
            fonts = self.score_comparison(payload, surface="fonts", detector_id="pixelscan")
            self.assertEqual(fonts["comparison_id"], "pixelscan_fonts_headless_vs_headed")
            self.assertEqual(fonts["status"], "warning")
            self.assertIs(fonts["font_check_match"], False)
            self.assertEqual(fonts["true_count_delta"], -1)

    def test_compare_scores_reports_pixelscan_audio_and_font_counterpart_gaps(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="pixelscan",
                display_mode="headless",
                label="pixelscan_audio_fonts_headless_only",
                results=[
                    self.browserleaks_audio_summary_result(
                        detector_check="pixelscan_audio_headless_summary",
                        metrics={
                            "sampleRate": 44100,
                            "length": 44100,
                            "sum": 0.5,
                            "sumAbs": 10.0,
                        },
                    ),
                    self.font_availability_result(
                        detector_check="pixelscan_fonts_headless_availability",
                        checks={"Arial": True, "Calibri": True},
                    ),
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            gaps = {
                (item.get("gap_id"), tuple(item.get("missing", [])))
                for item in payload["gaps"]
                if item.get("detector_id") == "pixelscan"
            }
            self.assertIn(("pixelscan_audio_headless_vs_headed", ("headed",)), gaps)
            self.assertIn(("pixelscan_fonts_headless_vs_headed", ("headed",)), gaps)

    def test_compare_scores_writes_webgl_cross_detector_metadata_comparison(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="browserleaks",
                display_mode="headless",
                label="webgl_browserleaks",
                results=[self.webgl_score_result()],
            )
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="pixelscan",
                display_mode="headless",
                label="webgl_pixelscan",
                results=[self.webgl_score_result()],
            )

            payload = self.run_compare_scores(evidence_root, output)

            comparison = self.score_comparison(payload, surface="webgl", detectors={"browserleaks", "pixelscan"})
            self.assertEqual(comparison["comparison_id"], "webgl_metadata_cross_detector")
            self.assertEqual(comparison["status"], "pass")
            self.assertIs(comparison["vendor_renderer_match"], True)
            self.assertTrue(all(comparison["hash_matches"].values()))
            self.assertIs(comparison["extension_count_match"], True)
            self.assertIs(comparison["extension_profile_match"], True)
            self.assertFalse(
                any(gap.get("gap_id") == "webgl_metadata_hashes_missing" for gap in payload["gaps"]),
                payload["gaps"],
            )

    def test_compare_scores_passes_pixelscan_audio_and_font_counterparts_when_headed_matches(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            audio = {
                "sampleRate": 44100,
                "length": 44100,
                "sum": 0.00000072,
                "sumAbs": 0.00017846,
            }
            checks = {"Arial": True, "Calibri": True, "Consolas": True}
            for display_mode, label in [
                ("headless", "pixelscan_audio_fonts_headless"),
                ("headed_xvfb", "pixelscan_audio_fonts_headed"),
            ]:
                self.write_synthetic_score_evidence(
                    evidence_root,
                    detector_id="pixelscan",
                    display_mode=display_mode,
                    label=label,
                    results=[
                        self.browserleaks_audio_summary_result(
                            detector_check=f"{label}_audio",
                            metrics=audio,
                        ),
                        self.font_availability_result(
                            detector_check=f"{label}_fonts",
                            checks=checks,
                        ),
                    ],
                )

            payload = self.run_compare_scores(evidence_root, output)

            audio_comparison = self.score_comparison(payload, surface="audio", detector_id="pixelscan")
            self.assertEqual(audio_comparison["comparison_id"], "pixelscan_audio_headless_vs_headed")
            self.assertEqual(audio_comparison["status"], "pass")
            font_comparison = self.score_comparison(payload, surface="fonts", detector_id="pixelscan")
            self.assertEqual(font_comparison["comparison_id"], "pixelscan_fonts_headless_vs_headed")
            self.assertEqual(font_comparison["status"], "pass")
            self.assertTrue(font_comparison["font_check_match"])
            self.assertFalse(
                {"pixelscan_audio_headless_vs_headed", "pixelscan_fonts_headless_vs_headed"}
                & {gap.get("gap_id") for gap in payload["gaps"]}
            )

    def test_compare_scores_warns_on_webgl_extension_profile_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="browserleaks",
                display_mode="headless",
                label="webgl_browserleaks",
                results=[self.webgl_score_result()],
            )
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="pixelscan",
                display_mode="headless",
                label="webgl_pixelscan_drift",
                results=[
                    self.webgl_score_result(
                        hashes={
                            "extensionSha256": "9" * 64,
                            "parameterSha256": "2" * 64,
                            "precisionSha256": "3" * 64,
                            "pixelSha256": "4" * 64,
                        }
                    )
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            comparison = self.score_comparison(payload, surface="webgl", detectors={"browserleaks", "pixelscan"})
            self.assertEqual(comparison["status"], "warning")
            self.assertIs(comparison["extension_count_match"], True)
            self.assertIs(comparison["extension_profile_match"], False)
            self.assertIs(comparison["hash_matches"]["extensionSha256"], False)

    def test_compare_scores_reports_webgl_metadata_hash_gaps(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="browserleaks",
                display_mode="headless",
                label="webgl_browserleaks_incomplete",
                results=[
                    self.webgl_score_result(
                        hashes={
                            "extensionSha256": "1" * 64,
                            "parameterSha256": "2" * 64,
                        }
                    )
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            metadata_gap = next(
                (item for item in payload["gaps"] if item.get("gap_id") == "webgl_metadata_hashes_missing"),
                None,
            )
            self.assertIsNotNone(metadata_gap, payload["gaps"])
            self.assertEqual(metadata_gap["missing_records"][0]["missing"], ["precisionSha256", "pixelSha256"])
            comparison_gap = next(
                (item for item in payload["gaps"] if item.get("gap_id") == "webgl_cross_detector_metadata_comparison_missing"),
                None,
            )
            self.assertIsNotNone(comparison_gap, payload["gaps"])

    def test_compare_scores_ignores_warning_webgl_rows_for_metadata_gaps(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="sannysoft",
                display_mode="headless",
                label="webgl_sannysoft_warning_incomplete",
                status="warning",
                results=[
                    self.webgl_score_result(
                        hashes={
                            "extensionSha256": "1" * 64,
                            "parameterSha256": "2" * 64,
                        }
                    )
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            self.assertFalse(
                any(gap.get("gap_id") == "webgl_metadata_hashes_missing" for gap in payload["gaps"]),
                payload["gaps"],
            )

    def test_compare_scores_ignores_warning_webgl_result_under_passed_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="sannysoft",
                display_mode="headed",
                label="webgl_sannysoft_result_warning_incomplete",
                status="passed",
                results=[
                    {
                        "detector_check": "webgl_page_loaded_only",
                        "evidence_ref": "sanitized_score_comparison_fixture",
                        "finding": "Synthetic smoke loaded a WebGL page but did not claim metadata coherence.",
                        "severity": "low",
                        "status": "warn",
                        "surface": "webgl",
                    }
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            self.assertFalse(
                any(gap.get("gap_id") == "webgl_metadata_hashes_missing" for gap in payload["gaps"]),
                payload["gaps"],
            )

    def test_compare_scores_reports_gap_when_browserleaks_audio_counterpart_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="browserleaks",
                display_mode="headless",
                label="browserleaks_audio_headless_only",
                results=[
                    self.browserleaks_audio_summary_result(
                        detector_check="browserleaks_audio_headless_summary",
                        metrics={
                            "sampleRate": 44100,
                            "length": 44100,
                            "sum": 0.77295988,
                            "sumAbs": 83.86503121,
                        },
                    )
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            gap = next(
                (
                    item
                    for item in payload["gaps"]
                    if item.get("surface") == "audio"
                    and item.get("gap_id") == "browserleaks_audio_headless_vs_headed"
                    and item.get("missing") == ["headed"]
                ),
                None,
            )
            self.assertIsNotNone(gap, payload["gaps"])
            self.assertIn("BrowserLeaks audio comparison requires both headless and headed", gap["finding"])

    def test_compare_scores_passes_browserleaks_audio_when_headed_counterpart_matches(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            metrics = {
                "sampleRate": 44100,
                "length": 44100,
                "sum": 0.00000072,
                "sumAbs": 0.00017846,
            }
            for display_mode, label in [
                ("headless", "browserleaks_audio_headless"),
                ("headed_xvfb", "browserleaks_audio_headed"),
            ]:
                self.write_synthetic_score_evidence(
                    evidence_root,
                    detector_id="browserleaks",
                    display_mode=display_mode,
                    label=label,
                    results=[
                        self.browserleaks_audio_summary_result(
                            detector_check=f"{label}_summary",
                            metrics=metrics,
                        )
                    ],
                )

            payload = self.run_compare_scores(evidence_root, output)

            comparison = self.score_comparison(payload, surface="audio", detector_id="browserleaks")
            self.assertEqual(comparison["comparison_id"], "browserleaks_audio_headless_vs_headed")
            self.assertEqual(comparison["status"], "pass")
            self.assertEqual(comparison["metric_deltas"], {"length": 0, "sampleRate": 0, "sum": 0.0, "sumAbs": 0.0})
            self.assertNotIn(
                "browserleaks_audio_headless_vs_headed",
                {gap.get("gap_id") for gap in payload["gaps"]},
            )

    def test_compare_scores_passes_browserleaks_audio_page_context_when_fields_match(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            context_values = {
                "channelCount": 2,
                "channelCountMode": "explicit",
                "channelInterpretation": "speakers",
                "fftSize": 2048,
                "frequencyBinCount": 1024,
                "maxChannelCount": 2,
                "maxDecibels": -30,
                "minDecibels": -100,
                "numberOfInputs": 1,
                "numberOfOutputs": 0,
                "sampleRate": 44100,
                "smoothingTimeConstant": 0.8,
                "state": "suspended",
            }
            for display_mode, label in [
                ("headless", "browserleaks_audio_page_headless"),
                ("headed_xvfb", "browserleaks_audio_page_headed"),
            ]:
                self.write_synthetic_score_evidence(
                    evidence_root,
                    detector_id="browserleaks",
                    display_mode=display_mode,
                    label=label,
                    results=[
                        self.browserleaks_audio_page_context_result(
                            detector_check=f"{label}_context",
                            values=context_values,
                        )
                    ],
                )

            payload = self.run_compare_scores(evidence_root, output)

            comparison = next(
                (
                    item
                    for item in payload["comparisons"]
                    if item.get("comparison_id") == "browserleaks_javascript_audio_page_context_headless_vs_headed"
                ),
                None,
            )
            self.assertIsNotNone(comparison, payload["comparisons"])
            self.assertEqual(comparison["status"], "pass")
            self.assertTrue(all(comparison["field_matches"].values()))
            self.assertNotIn(
                "browserleaks_javascript_audio_page_context_headless_vs_headed",
                {gap.get("gap_id") for gap in payload["gaps"]},
            )

    def test_compare_scores_passes_browserleaks_webrtc_when_candidate_metadata_matches(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            for display_mode, label in [
                ("headless", "browserleaks_webrtc_headless"),
                ("headed_xvfb", "browserleaks_webrtc_headed"),
            ]:
                self.write_synthetic_score_evidence(
                    evidence_root,
                    detector_id="browserleaks",
                    display_mode=display_mode,
                    label=label,
                    results=[
                        self.webrtc_candidate_result(
                            detector_check=f"{label}_candidate_metadata",
                        )
                    ],
                )

            payload = self.run_compare_scores(evidence_root, output)

            comparison = next(
                (
                    item
                    for item in payload["comparisons"]
                    if item.get("comparison_id") == "browserleaks_webrtc_headless_vs_headed"
                ),
                None,
            )
            self.assertIsNotNone(comparison, payload["comparisons"])
            self.assertEqual(comparison["status"], "pass")
            self.assertTrue(all(comparison["field_matches"].values()))
            self.assertNotIn(
                "browserleaks_webrtc_headless_vs_headed",
                {gap.get("gap_id") for gap in payload["gaps"]},
            )


    def test_compare_scores_recognizes_matching_font_glyphs_but_warns_on_metric_hash_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            glyph_hash = "c" * 64
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="browserleaks",
                display_mode="headed_xvfb",
                label="fonts_browserleaks",
                results=[
                    self.font_score_result(
                        detector_check="browserleaks_fonts_headed_metrics",
                        metrics_sha256="a" * 64,
                        glyph_sha256=glyph_hash,
                    )
                ],
            )
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="creepjs",
                display_mode="headed_xvfb",
                label="fonts_creepjs",
                results=[
                    self.font_score_result(
                        detector_check="creepjs_font_metric_probe",
                        metrics_sha256="b" * 64,
                    ),
                    self.glyph_score_result(
                        detector_check="creepjs_font_glyph_probe",
                        glyph_sha256=glyph_hash,
                    ),
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            self.assertEqual(payload["evidence_count"], 2)
            comparison = self.score_comparison(payload, surface="fonts", detectors={"browserleaks", "creepjs"})
            self.assertEqual(comparison["status"], "warning")
            self.assertIs(comparison["glyph_sha256_match"], True)
            self.assertIs(comparison["metrics_sha256_match"], False)
            self.assertIn("partial", comparison["finding"].lower())

    def test_compare_scores_passes_browserleaks_fonts_when_headed_counterpart_matches(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            for display_mode, label in [
                ("headless", "browserleaks_fonts_headless"),
                ("headed_xvfb", "browserleaks_fonts_headed"),
            ]:
                self.write_synthetic_score_evidence(
                    evidence_root,
                    detector_id="browserleaks",
                    display_mode=display_mode,
                    label=label,
                    results=[
                        self.font_score_result(
                            detector_check=f"{label}_metrics",
                            metrics_sha256="a" * 64,
                            glyph_sha256="c" * 64,
                        )
                    ],
                )

            payload = self.run_compare_scores(evidence_root, output)

            comparison = next(
                (
                    item
                    for item in payload["comparisons"]
                    if item.get("comparison_id") == "browserleaks_fonts_headless_vs_headed"
                ),
                None,
            )
            self.assertIsNotNone(comparison, payload["comparisons"])
            self.assertEqual(comparison["status"], "pass")
            self.assertIs(comparison["candidate_count_match"], True)
            self.assertIs(comparison["font_list_match"], True)
            self.assertIs(comparison["glyph_sha256_match"], True)
            self.assertIs(comparison["metrics_sha256_match"], True)
            self.assertNotIn(
                "browserleaks_fonts_headless_vs_headed",
                {gap.get("gap_id") for gap in payload["gaps"]},
            )


    def test_compare_scores_does_not_pair_browserleaks_fonts_across_target_contexts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            font_result = self.font_score_result(
                detector_check="browserleaks_fonts_metrics",
                metrics_sha256="a" * 64,
                glyph_sha256="c" * 64,
            )
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="browserleaks",
                display_mode="headless",
                label="browserleaks_fonts_linux_docker_headless",
                results=[font_result],
            )
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="browserleaks",
                display_mode="headed",
                label="browserleaks_fonts_macos_host_headed",
                platform="macos-arm64",
                network_mode="proxy",
                container=False,
                results=[
                    font_result,
                    {
                        "surface": "proxy_ip_coherence",
                        "status": "pass",
                        "severity": "info",
                        "finding": "Detector geolocation matched the sanitized external proxy exit region.",
                        "evidence_ref": "sanitized_score_comparison_fixture",
                        "normalized_values": {
                            "proxy_exit_region_redacted": "redacted-region",
                            "detector_geolocation_region_redacted": "redacted-region",
                        },
                    },
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            self.assertNotIn(
                "browserleaks_fonts_headless_vs_headed",
                {item.get("comparison_id") for item in payload["comparisons"]},
            )
            gap = next(
                (
                    item
                    for item in payload["gaps"]
                    if item.get("gap_id") == "browserleaks_fonts_headless_vs_headed"
                    and item.get("detector_id") == "browserleaks"
                ),
                None,
            )
            self.assertIsNotNone(gap, payload["gaps"])

    def test_compare_scores_reports_gap_when_required_counterpart_evidence_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="creepjs",
                display_mode="headless",
                label="audio_headless_only",
                results=[
                    self.audio_score_result(
                        detector_check="creepjs_audio_score_metrics",
                        metrics={
                            "sum": 100.0,
                            "gain": 2.0,
                            "freq": 300.0,
                            "time": 4.0,
                            "trap": 5.0,
                            "unique": 6.0,
                        },
                    )
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            gap = next(
                (
                    item
                    for item in payload["gaps"]
                    if item.get("surface") == "audio"
                    and item.get("gap_id") == "creepjs_audio_headless_vs_headed"
                    and item.get("missing") == ["headed"]
                ),
                None,
            )
            self.assertIsNotNone(gap, payload["gaps"])
            self.assertIn("both headless and headed", gap["finding"].lower())
            self.assertNotIn(
                "passed",
                {comparison.get("status") for comparison in payload["comparisons"] if comparison.get("surface") == "audio"},
            )


    def test_compare_scores_reports_release_baseline_gaps_after_counterpart_evidence_matches(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            audio_metrics = {
                "sum": 100.0,
                "gain": 2.0,
                "freq": 300.0,
                "time": 4.0,
                "trap": 5.0,
                "unique": 6.0,
            }
            glyph_hash = "d" * 64
            metrics_hash = "e" * 64
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="creepjs",
                display_mode="headless",
                label="audio_headless_release_gap",
                results=[
                    self.audio_score_result(
                        detector_check="creepjs_audio_score_metrics",
                        metrics=audio_metrics,
                    )
                ],
            )
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="creepjs",
                display_mode="headed_xvfb",
                label="audio_fonts_headed_release_gap",
                results=[
                    self.audio_score_result(
                        detector_check="creepjs_headed_audio_metrics",
                        metrics=audio_metrics,
                    ),
                    self.font_score_result(
                        detector_check="creepjs_font_metric_probe",
                        metrics_sha256=metrics_hash,
                        glyph_sha256=glyph_hash,
                    ),
                ],
            )
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="browserleaks",
                display_mode="headed_xvfb",
                label="fonts_browserleaks_release_gap",
                results=[
                    self.font_score_result(
                        detector_check="browserleaks_fonts_headed_metrics",
                        metrics_sha256=metrics_hash,
                        glyph_sha256=glyph_hash,
                    )
                ],
            )

            payload = self.run_compare_scores(evidence_root, output)

            self.assertIs(payload["release_grade"], False)
            self.assertNotIn(
                "creepjs_audio_headless_vs_headed",
                {gap.get("gap_id") for gap in payload["gaps"]},
            )
            self.assertNotIn(
                "browserleaks_creepjs_font_metrics",
                {gap.get("gap_id") for gap in payload["gaps"]},
            )
            self.assertEqual(
                self.score_comparison(payload, surface="audio", detector_id="creepjs")["status"],
                "pass",
            )
            self.assertEqual(
                self.score_comparison(payload, surface="fonts", detectors={"browserleaks", "creepjs"})["status"],
                "pass",
            )
            baseline_gaps = payload.get("baseline_gaps")
            self.assertIsInstance(baseline_gaps, list)
            baseline_gap_by_id = {gap.get("gap_id"): gap for gap in baseline_gaps}
            expected_baseline_gaps = {
                "pixelscan_audio_font_score_baseline_missing": {
                    "surface": "audio,fonts",
                    "detector_id": "pixelscan",
                    "finding": "Pixelscan AudioContext/fonts score baseline",
                },
                "native_headed_font_corpus_parity_missing": {
                    "surface": "fonts",
                    "detector_id": "browserleaks,creepjs,pixelscan",
                    "finding": "native headed platform corpus evidence is missing",
                },
            }
            for gap_id, expected in expected_baseline_gaps.items():
                with self.subTest(gap_id=gap_id):
                    gap = baseline_gap_by_id.get(gap_id)
                    self.assertIsNotNone(gap, baseline_gaps)
                    self.assertEqual(gap["surface"], expected["surface"])
                    self.assertEqual(gap["detector_id"], expected["detector_id"])
                    self.assertIn(expected["finding"], gap["finding"])
            self.assertNotIn("browserleaks_audio_score_baseline_missing", baseline_gap_by_id)

    def test_compare_scores_omits_pixelscan_baseline_gap_when_page_status_hashes_exist(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="pixelscan",
                display_mode="headed_xvfb",
                label="pixelscan_page_status",
                results=[self.pixelscan_page_status_result()],
            )

            payload = self.run_compare_scores(evidence_root, output)

            baseline_gap_ids = {gap.get("gap_id") for gap in payload["baseline_gaps"]}
            self.assertNotIn("pixelscan_audio_font_score_baseline_missing", baseline_gap_ids)
            self.assertIn("native_headed_font_corpus_parity_missing", baseline_gap_ids)

    def test_compare_scores_accepts_pixelscan_page_verdict_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-score-comparison.json"
            self.write_synthetic_score_evidence(
                evidence_root,
                detector_id="pixelscan",
                display_mode="headed_xvfb",
                label="pixelscan_page_verdict",
                results=[self.pixelscan_page_status_result(detector_check="pixelscan_page_verdict")],
            )

            payload = self.run_compare_scores(evidence_root, output)

            baseline_gap_ids = {gap.get("gap_id") for gap in payload["baseline_gaps"]}
            self.assertNotIn("pixelscan_audio_font_score_baseline_missing", baseline_gap_ids)
            self.assertIn("native_headed_font_corpus_parity_missing", baseline_gap_ids)


    def test_pixelscan_variant_plan_emits_secret_safe_isolation_matrix(self):
        proc = self.run_harness(
            "pixelscan-variant-plan",
            "--generated-at",
            "2026-07-10T00:00:00+00:00",
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["runtime_id"], "browseforge-chromium")
        self.assertEqual(payload["detector_id"], "pixelscan")
        self.assertFalse(payload["secret_policy"]["commit_raw_proxy_url"])
        self.assertFalse(payload["secret_policy"]["commit_raw_ip"])
        self.assertFalse(payload["secret_policy"]["commit_raw_page_text"])
        variants = {row["variant_id"]: row for row in payload["variants"]}
        self.assertEqual(
            [
                "baseline-current",
                "canvas-off",
                "audio-off",
                "webgl-native",
                "fonts-native",
                "passive-native-surfaces",
                "minimal-native-control",
            ],
            payload["collection_order"],
        )
        self.assertEqual({"canvas_noise": 0}, variants["canvas-off"]["fingerprint_overrides"])
        self.assertEqual({"audio_noise": 0}, variants["audio-off"]["fingerprint_overrides"])
        self.assertEqual(
            {"webgl_vendor": "", "webgl_renderer": ""},
            variants["webgl-native"]["fingerprint_overrides"],
        )
        self.assertEqual({"fonts": [], "fonts_dir": ""}, variants["fonts-native"]["fingerprint_overrides"])
        passive = variants["passive-native-surfaces"]["fingerprint_overrides"]
        for key in ("audio_noise", "canvas_noise", "webgl_vendor", "webgl_renderer", "fonts", "fonts_dir", "native_mode"):
            self.assertIn(key, passive)
        self.assertEqual("strict", passive["native_mode"])
        minimal = variants["minimal-native-control"]["fingerprint_overrides"]
        self.assertEqual("strict", minimal["native_mode"])
        self.assertEqual("", minimal["user_agent"])
        self.assertEqual("", minimal["ua_full_version"])
        self.assertEqual("", minimal["timezone"])
        self.assertEqual(0, minimal["hardware_concurrency"])
        self.assertEqual(0, minimal["screen_width"])

    def test_pixelscan_materialize_variants_writes_local_configs_and_secret_safe_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base_config = root / "base.json"
            output_dir = root / "variants"
            manifest = root / "manifest.json"
            base_config.write_text(json.dumps({
                "profile_id": "pix",
                "fingerprint": {
                    "canvas_noise": 7,
                    "audio_noise": 11,
                    "webgl_vendor": "SpoofVendor",
                    "webgl_renderer": "SpoofRenderer",
                    "fonts": ["Arial"],
                    "fonts_dir": "/tmp/fonts",
                    "timezone": "Asia/Taipei",
                },
                "proxy": {
                    "server": "socks5://127.0.0.1:57626",
                    "username": "user",
                    "password": "secret",
                },
            }), encoding="utf-8")

            proc = self.run_harness(
                "pixelscan-materialize-variants",
                "--base-config",
                str(base_config),
                "--output-dir",
                str(output_dir),
                "--manifest-output",
                str(manifest),
                "--generated-at",
                "2026-07-10T00:00:00+00:00",
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_text = manifest.read_text(encoding="utf-8")
            self.assertNotIn("socks5://127.0.0.1:57626", manifest_text)
            self.assertNotIn("password", manifest_text)
            self.assertFalse(payload["secret_policy"]["manifest_contains_proxy_secret"])
            variants = {row["variant_id"]: row for row in payload["variants"]}
            canvas_cfg = json.loads((output_dir / "canvas-off.json").read_text(encoding="utf-8"))
            self.assertEqual(canvas_cfg["profile_id"], "pix-canvas-off")
            self.assertEqual(0, canvas_cfg["fingerprint"]["canvas_noise"])
            self.assertEqual(11, canvas_cfg["fingerprint"]["audio_noise"])
            self.assertEqual("secret", canvas_cfg["proxy"]["password"])
            passive_cfg = json.loads((output_dir / "passive-native-surfaces.json").read_text(encoding="utf-8"))
            self.assertEqual(0, passive_cfg["fingerprint"]["canvas_noise"])
            self.assertEqual(0, passive_cfg["fingerprint"]["audio_noise"])
            self.assertEqual("", passive_cfg["fingerprint"]["webgl_vendor"])
            self.assertEqual("", passive_cfg["fingerprint"]["webgl_renderer"])
            self.assertEqual([], passive_cfg["fingerprint"]["fonts"])
            self.assertEqual("", passive_cfg["fingerprint"]["fonts_dir"])
            self.assertEqual("strict", passive_cfg["fingerprint"]["native_mode"])
            minimal_cfg = json.loads((output_dir / "minimal-native-control.json").read_text(encoding="utf-8"))
            self.assertEqual("strict", minimal_cfg["fingerprint"]["native_mode"])
            self.assertEqual("", minimal_cfg["fingerprint"]["user_agent"])
            self.assertEqual("", minimal_cfg["fingerprint"]["ua_full_version"])
            self.assertEqual(0, minimal_cfg["fingerprint"]["hardware_concurrency"])
            self.assertEqual({"canvas_noise": 0}, variants["canvas-off"]["fingerprint_overrides"])

    def test_pixelscan_variant_summary_commits_only_sanitized_detector_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw_dir = root / "raw"
            raw_dir.mkdir()
            headed_dir = root / "headed"
            headed_dir.mkdir()
            output = root / "summary.json"
            (raw_dir / "detrun_linux_x64_pixelscan_canvas_off_headless_docker_direct.json").write_text(json.dumps({
                "records": [
                    {
                        "status": "warning",
                        "finding": "Pixelscan fingerprint check loaded from 192.0.2.44 and reported masking.",
                        "severity": "medium",
                        "observed": {
                            "pixelscanPage": {
                                "verdict": "inconsistent",
                                "fingerprint": "Masking detected",
                                "botCheck": "Automated behavior detected",
                                "proxy": "No proxy detected",
                                "location": "Taiwan / Taipei",
                                "audioContextHash": "audio-hash",
                                "canvasHash": "canvas-hash",
                                "fontHash": "font-hash",
                                "webglHash": "webgl-hash",
                            },
                            "text_excerpt": "raw page text must not be copied",
                        },
                    }
                ]
            }), encoding="utf-8")
            (headed_dir / "detrun_linux_x64_pixelscan_canvas_off_headed_xvfb_docker_direct.json").write_text(json.dumps({
                "records": [
                    {
                        "status": "warning",
                        "finding": "Pixelscan headed fingerprint check reported masking.",
                        "severity": "medium",
                        "observed": {
                            "pixelscanPage": {
                                "verdict": "inconsistent",
                                "fingerprint": "Masking detected",
                                "botCheck": "No automated behavior detected",
                                "proxy": "No proxy detected",
                                "location": "Taiwan / Taipei",
                                "audioContextHash": "headed-audio",
                                "canvasHash": "headed-canvas",
                                "fontHash": "headed-font",
                                "webglHash": "-",
                            },
                        },
                    }
                ]
            }), encoding="utf-8")

            proc = self.run_harness(
                "pixelscan-variant-summary",
                "--input-dir",
                str(raw_dir),
                "--headed-input-dir",
                str(headed_dir),
                "--output",
                str(output),
                "--generated-at",
                "2026-07-10T00:00:00+00:00",
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            summary_text = output.read_text(encoding="utf-8")
            self.assertNotIn("192.0.2.44", summary_text)
            self.assertNotIn("raw page text", summary_text)
            variants = {row["variant_id"]: row for row in payload["variants"]}
            canvas = variants["canvas-off"]
            self.assertEqual("observed", canvas["status"])
            self.assertFalse(canvas["raw_capture_committed"])
            self.assertEqual("inconsistent", canvas["observation"]["verdict"])
            self.assertEqual("[REDACTED]", canvas["observation"]["finding"].split()[-4])
            self.assertEqual("missing", variants["audio-off"]["status"])

            headed = {row["variant_id"]: row for row in payload["headed_controls"]}
            self.assertEqual("headed_xvfb", headed["canvas-off"]["display_mode"])
            self.assertEqual("No automated behavior detected", headed["canvas-off"]["observation"]["botCheck"])

    def test_summary_reports_required_matrix_coverage_gaps_with_normalized_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-summary.json"
            self.write_synthetic_summary_evidence(
                evidence_root,
                detector_id="sannysoft",
                display_mode="headed_xvfb",
                network_mode="direct",
                container=True,
            )
            self.write_synthetic_summary_evidence(
                evidence_root,
                detector_id="sannysoft",
                display_mode="headed",
                network_mode="local-proxy",
                container=True,
            )

            proc = self.run_harness("summary", "--evidence-root", str(evidence_root), "--output", str(output), "--generated-at", "2026-07-10T21:00:00+00:00")

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("2026-07-10T21:00:00+00:00", payload["generated_at"])
            self.assertIn("coverage_gaps", payload)
            self.assertIn("coverage_gap_count", payload)
            self.assertEqual(payload["coverage_gap_count"], len(payload["coverage_gaps"]))
            self.assertGreater(payload["coverage_gap_count"], 0)
            gaps_by_key = {gap["matrix_key"]: gap for gap in payload["coverage_gaps"]}
            self.assertNotIn("linux-x64:sannysoft:headed:direct:container", gaps_by_key)
            self.assertIn("linux-x64:sannysoft:headed:direct:host", gaps_by_key)
            self.assertIn("linux-x64:sannysoft:headed:proxy:host", gaps_by_key)
            self.assertIn("linux-x64:sannysoft:headed:proxy:container", gaps_by_key)

            expected_required_evidence = {
                "linux-x64:sannysoft:headed:direct:host": ("native/host", "direct network"),
                "linux-x64:sannysoft:headed:proxy:host": ("native/host", "external proxy", "exit-IP/geolocation"),
                "linux-x64:sannysoft:headed:proxy:container": ("Docker/container", "external proxy", "exit-IP/geolocation"),
            }
            for matrix_key, expected_terms in expected_required_evidence.items():
                with self.subTest(matrix_key=matrix_key):
                    gap = gaps_by_key[matrix_key]
                    self.assertEqual(
                        {
                            "detector_id": gap["detector_id"],
                            "platform": gap["platform"],
                            "display_mode": gap["display_mode"],
                            "network_mode": gap["network_mode"],
                            "container": gap["container"],
                        },
                        {
                            "detector_id": "sannysoft",
                            "platform": "linux-x64",
                            "display_mode": "headed",
                            "network_mode": "proxy" if ":proxy:" in matrix_key else "direct",
                            "container": matrix_key.endswith(":container"),
                        },
                    )
                    required_evidence = gap.get("required_evidence")
                    self.assertIsInstance(required_evidence, str)
                    for term in expected_terms:
                        self.assertIn(term, required_evidence)

    def test_summary_does_not_count_headless_evidence_for_required_headed_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            output = root / "detector-summary.json"
            self.write_synthetic_summary_evidence(
                evidence_root,
                detector_id="sannysoft",
                display_mode="headless",
                network_mode="direct",
                container=True,
            )

            proc = self.run_harness("summary", "--evidence-root", str(evidence_root), "--output", str(output))

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            gap_keys = {gap.get("matrix_key", gap.get("key")) for gap in payload["coverage_gaps"]}
            self.assertIn("linux-x64:sannysoft:headed:direct:container", gap_keys)

    def test_validate_accepts_valid_sanitized_fixture(self):
        proc = self.run_harness("validate-evidence", "tests/fixtures/detectors/valid-evidence.json")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_evidence_schema_admits_current_harness_matrix_and_storage_contracts(self):
        schema = json.loads((ROOT / "detectors" / "evidence-schema.json").read_text(encoding="utf-8"))
        harness_props = schema["properties"]["harness"]["properties"]
        matrix_props = schema["properties"]["matrix"]["properties"]
        storage_props = schema["properties"]["storage"]["properties"]

        self.assertGreaterEqual(
            set(harness_props["name"]["enum"]),
            {"browseforge-detector-harness", "browseforge-detector-harness + local-connect-proxy"},
        )
        self.assertGreaterEqual(
            set(harness_props["mode"]["enum"]),
            {"manual_ingest", "synthetic_fixture", "live_collect", "live_collect_local_proxy"},
        )
        self.assertGreaterEqual(set(matrix_props["display_mode"]["enum"]), {"headed", "headed_xvfb", "headless", "unknown"})
        self.assertGreaterEqual(set(matrix_props["network_mode"]["enum"]), {"direct", "proxy", "local_proxy", "unknown"})
        self.assertGreaterEqual(
            set(matrix_props["proxy"]["enum"]),
            {"none", "redacted", "public_test_infra", "local-connect-observer"},
        )
        self.assertGreaterEqual(
            set(storage_props),
            {"evidence_path", "sha256", "raw_capture_path", "raw_capture_sha256", "proxy_summary_sha256", "text_sha256", "summary_path"},
        )

    def test_committed_detector_evidence_uses_schema_admitted_contract_values(self):
        schema = json.loads((ROOT / "detectors" / "evidence-schema.json").read_text(encoding="utf-8"))
        harness_props = schema["properties"]["harness"]["properties"]
        matrix_props = schema["properties"]["matrix"]["properties"]
        storage_keys = set(schema["properties"]["storage"]["properties"])
        admitted = {
            "harness.name": set(harness_props["name"]["enum"]),
            "harness.mode": set(harness_props["mode"]["enum"]),
            "matrix.display_mode": set(matrix_props["display_mode"]["enum"]),
            "matrix.network_mode": set(matrix_props["network_mode"]["enum"]),
            "matrix.proxy": set(matrix_props["proxy"]["enum"]),
        }
        missing = {key: set() for key in [*admitted, "storage.keys"]}
        evidence_paths = sorted((ROOT / "detectors" / "evidence").glob("**/*.json"))
        self.assertGreater(len(evidence_paths), 0)

        for path in evidence_paths:
            evidence = json.loads(path.read_text(encoding="utf-8"))
            values = {
                "harness.name": evidence.get("harness", {}).get("name"),
                "harness.mode": evidence.get("harness", {}).get("mode"),
                "matrix.display_mode": evidence.get("matrix", {}).get("display_mode"),
                "matrix.network_mode": evidence.get("matrix", {}).get("network_mode"),
                "matrix.proxy": evidence.get("matrix", {}).get("proxy"),
            }
            for key, value in values.items():
                if value not in admitted[key]:
                    missing[key].add(value)
            for storage_key in evidence.get("storage", {}):
                if storage_key not in storage_keys:
                    missing["storage.keys"].add(storage_key)

        self.assertEqual({key: sorted(values) for key, values in missing.items() if values}, {})

    def test_validate_rejects_proxy_matrix_without_external_proxy_coherence(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.write_synthetic_validation_evidence(
                Path(td),
                label="proxy_matrix_local_observer",
                network_mode="proxy",
                matrix_proxy="local-connect-observer",
                target_proxy_region_redacted="local-loopback-observer",
                results=[
                    {
                        "surface": "proxy_ip_coherence",
                        "status": "pass",
                        "severity": "info",
                        "finding": "Local CONNECT proxy routing observer is not external proxy/IP coherence evidence.",
                        "evidence_ref": "synthetic#local-proxy-observer",
                        "normalized_values": {
                            "connect_count": 2,
                            "observed_route_redacted": "loopback-connect-proxy",
                        },
                    }
                ],
            )

            proc = self.run_harness("validate-evidence", str(path))

            self.assertEqual(proc.returncode, self.harness_module.EXIT_SCHEMA)
            stderr = proc.stderr.lower()
            self.assertIn("redacted external proxy configuration", stderr)
            self.assertIn("external proxy region/geolocation metadata", stderr)
            self.assertIn("external proxy exit-ip/geolocation values", stderr)

    def test_validate_accepts_proxy_matrix_with_sanitized_external_proxy_coherence(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.write_synthetic_validation_evidence(
                Path(td),
                label="proxy_matrix_external_coherence",
                network_mode="proxy",
                matrix_proxy="redacted",
                target_proxy_region_redacted="redacted-region",
                results=[
                    {
                        "surface": "proxy_ip_coherence",
                        "status": "pass",
                        "severity": "info",
                        "finding": "Detector geolocation matched the sanitized external proxy exit region.",
                        "evidence_ref": "synthetic#external-proxy-coherence",
                        "normalized_values": {
                            "proxy_exit_region_redacted": "redacted-region",
                            "detector_geolocation_region_redacted": "redacted-region",
                        },
                    }
                ],
            )

            proc = self.run_harness("validate-evidence", str(path))

            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_validate_accepts_local_proxy_routing_without_proxy_matrix_credit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence_root = root / "evidence"
            path = self.write_synthetic_validation_evidence(
                evidence_root,
                label="local_proxy_routing_observer",
                network_mode="local_proxy",
                matrix_proxy="local-connect-observer",
                target_proxy_region_redacted="local-loopback-observer",
                required=False,
                results=[
                    {
                        "surface": "proxy_ip_coherence",
                        "status": "pass",
                        "severity": "info",
                        "finding": "Local CONNECT proxy observed detector traffic; this proves routing only, not external proxy exit-IP/geolocation coherence.",
                        "evidence_ref": "synthetic#local-proxy-routing",
                        "normalized_values": {
                            "connect_count": 2,
                            "methods": {"CONNECT": 2},
                            "ports": {"443": 2},
                            "total_events": 2,
                        },
                    }
                ],
            )

            validate_proc = self.run_harness("validate-evidence", str(path))

            self.assertEqual(validate_proc.returncode, 0, validate_proc.stderr)

            output = root / "summary.json"
            summary_proc = self.run_harness("summary", "--evidence-root", str(evidence_root), "--output", str(output))

            self.assertEqual(summary_proc.returncode, 0, summary_proc.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            gap_keys = {gap["matrix_key"] for gap in payload["coverage_gaps"]}
            self.assertIn("linux-x64:sannysoft:headed:proxy:container", gap_keys)

    def test_validate_accepts_canvas_evidence_with_only_sanitized_hashes(self):
        fixture = self.fixture_path("valid-evidence.json")
        code, errors = self.harness_module.validate_evidence_file(fixture)
        self.assertEqual((code, errors), (0, []))

        evidence = json.loads(fixture.read_text(encoding="utf-8"))
        canvas = next((r for r in evidence["results"] if r.get("surface") == "canvas"), None)
        self.assertIsNotNone(canvas)
        self.assertEqual(
            set(canvas),
            {
                "surface",
                "status",
                "severity",
                "finding",
                "evidence_ref",
                "fingerprint_hash",
                "data_url_sha256",
                "image_data_sha256",
                "width",
                "height",
                "sample_count",
            },
        )
        self.assertEqual(canvas["status"], "pass")
        self.assertEqual(canvas["width"], 64)
        self.assertEqual(canvas["height"], 32)
        self.assertEqual(canvas["sample_count"], 8192)
        for field in ("fingerprint_hash", "data_url_sha256", "image_data_sha256"):
            self.assertRegex(canvas[field], r"^[0-9a-f]{64}$")

    def test_validate_rejects_canvas_raw_image_payload_fields(self):
        fixture = self.fixture_path("invalid-unsanitized.json")
        evidence = json.loads(fixture.read_text(encoding="utf-8"))
        canvas = next((r for r in evidence["results"] if r.get("surface") == "canvas"), None)
        self.assertIsNotNone(canvas)
        self.assertIn("data_url", canvas)
        self.assertIn("image_data", canvas)
        for key in [
            "ip_redacted",
            "credentials_redacted",
            "profiles_redacted",
            "tokens_redacted",
            "cookies_storage_redacted",
            "screenshot_metadata_redacted",
        ]:
            self.assertIs(evidence["sanitization"][key], True)
        self.assertIs(evidence["sanitization"]["raw_capture_committed"], False)

        code, errors = self.harness_module.validate_evidence_file(fixture)
        self.assertEqual(code, self.harness_module.EXIT_SANITIZATION)
        self.assertRegex("\n".join(errors).lower(), r"(raw|data_url|image_data|canvas|sanitization)")

    def test_validate_rejects_unknown_detector(self):
        proc = self.run_harness("validate-evidence", "tests/fixtures/detectors/invalid-unknown-detector.json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unknown detector_id", proc.stderr)

    def test_validate_cli_rejects_unsanitized_canvas_fixture(self):
        proc = self.run_harness("validate-evidence", "tests/fixtures/detectors/invalid-unsanitized.json")
        self.assertEqual(proc.returncode, 3)
        self.assertRegex(proc.stderr.lower(), r"(raw|data_url|image_data|canvas|sanitization)")

    def test_detector_timeout_is_operational_error(self):
        proc = self.run_harness("validate-evidence", "tests/fixtures/detectors/detector-timeout.json")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_ingest_writes_normalized_path_and_runtime_kg_schema_records(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture = json.loads(self.fixture_path("valid-evidence.json").read_text(encoding="utf-8"))
            proc = self.run_harness("ingest", "--input", "tests/fixtures/detectors/valid-evidence.json", "--output-root", str(root / "evidence"), "--kg-out", str(root / "kg.jsonl"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            written = Path(proc.stdout.strip())
            self.assertTrue(written.is_file())
            self.assertEqual(
                written.relative_to(root / "evidence"),
                Path(f"{fixture['runtime_version']}/{fixture['target']['platform']}/{fixture['detector']['detector_id']}/{fixture['run_id']}.json"),
            )

            records = [json.loads(line) for line in (root / "kg.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertGreater(len(records), 0)
            self.assertTrue(all(record.get("record_type") in {"node", "edge"} for record in records))

            regen_proc = self.run_harness("regenerate-kg", "--evidence-root", str(root / "evidence"), "--output", str(root / "regenerated-kg.jsonl"))
            self.assertEqual(regen_proc.returncode, 0, regen_proc.stderr)
            regenerated_records = [json.loads(line) for line in (root / "regenerated-kg.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records, regenerated_records)

            edge_labels = {record.get("label", record.get("edge")) for record in records if record.get("record_type") == "edge" or "edge" in record}
            self.assertNotIn("EVIDENCES", edge_labels)
            self.assertNotIn("RAN_DETECTOR", edge_labels)
            for record in records:
                self.assertIn(record.get("record_type"), {"node", "edge"})
                self.assertIn("label", record)
                self.assertIn("properties", record)
                if record["record_type"] == "node":
                    self.assertIn("id", record)
                else:
                    self.assertIn("from", record)
                    self.assertIn("to", record)

            run_node_id = f"DetectorRun:{fixture['run_id']}"
            evidence_node_id = f"EvidenceArtifact:{fixture['evidence_id']}"
            artifact_node_id = f"RuntimeArtifact:{fixture['artifact_id']}"
            nodes = {record["id"]: record for record in records if record.get("record_type") == "node"}
            self.assertIn(run_node_id, nodes)
            self.assertIn(evidence_node_id, nodes)
            self.assertEqual(nodes[run_node_id]["label"], "DetectorRun")
            self.assertEqual(nodes[evidence_node_id]["label"], "EvidenceArtifact")

            edge_records = [record for record in records if record.get("record_type") == "edge"]
            self.assertEqual(
                set(),
                {
                    (run_node_id, "RUNS_DETECTOR", f"Detector:{fixture['detector']['detector_id']}"),
                    (run_node_id, "TESTS_ARTIFACT", artifact_node_id),
                    (run_node_id, "TARGETS_ARTIFACT", artifact_node_id),
                    (run_node_id, "PRODUCES_EVIDENCE", evidence_node_id),
                    (evidence_node_id, "SUPPORTS_GATE", "ReleaseGate:live-detector-evidence"),
                }
                - {(record.get("from"), record.get("label"), record.get("to")) for record in edge_records},
            )

if __name__ == "__main__":
    unittest.main()
