import importlib.util
import json
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
    def run_harness(self, *args):
        return subprocess.run([sys.executable, str(HARNESS), *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

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

    def write_synthetic_score_evidence(self, evidence_root, *, detector_id, display_mode, results, label):
        detector = self.harness_module.detector_by_id(detector_id)
        self.assertIsNotNone(detector)
        platform = "linux-x64"
        network_mode = "direct"
        container = True
        display_key = "headed" if display_mode.startswith("headed") else display_mode
        suffix = f"{detector_id}_{label}_{display_key}_{network_mode}_container"
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
                    "proxy_region_redacted": "none",
                },
                "matrix": {
                    "matrix_key": f"{platform}:{detector_id}:{display_key}:{network_mode}:container",
                    "display_mode": display_mode,
                    "network_mode": network_mode,
                    "container": container,
                    "proxy": "none",
                    "required": False,
                },
                "status": "passed",
                "failure_mode": "none",
                "results": results,
            }
        )
        path = evidence_root / detector_id / f"{suffix}.json"
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


    @classmethod
    def setUpClass(cls):
        cls.harness_module = load_harness_module()

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
            self.assertIn("differ", comparison["finding"].lower())

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
                "browserleaks_audio_score_baseline_missing": {
                    "surface": "audio",
                    "detector_id": "browserleaks",
                    "finding": "BrowserLeaks audio score baseline",
                },
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

            proc = self.run_harness("summary", "--evidence-root", str(evidence_root), "--output", str(output))

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
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

            jsonl_entries = [json.loads(line) for line in (root / "kg.jsonl").read_text(encoding="utf-8").splitlines()]
            records = []
            for entry in jsonl_entries:
                if "nodes" in entry or "edges" in entry:
                    records.extend(entry.get("nodes", []))
                    records.extend(entry.get("edges", []))
                else:
                    records.append(entry)
            self.assertGreater(len(records), 0)

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
