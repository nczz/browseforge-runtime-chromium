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

    @classmethod
    def setUpClass(cls):
        cls.harness_module = load_harness_module()

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

    def test_collect_rejects_unsupported_detector_before_cdp_connection(self):
        proc = self.run_harness(
            "collect",
            "--detector",
            "creepjs",
            "--cdp-url",
            "http://127.0.0.1:9",
            "--wait-seconds",
            "0",
        )
        self.assertEqual(proc.returncode, self.harness_module.EXIT_COLLECT_UNAVAILABLE)
        self.assertEqual(proc.stdout, "")
        self.assertIn("collector not implemented for detector: creepjs", proc.stderr)

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

    def test_ingest_writes_normalized_path_and_kg_edges(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proc = self.run_harness("ingest", "--input", "tests/fixtures/detectors/valid-evidence.json", "--output-root", str(root / "evidence"), "--kg-out", str(root / "kg.jsonl"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            written = Path(proc.stdout.strip())
            self.assertTrue(written.is_file())
            kg = [json.loads(line) for line in (root / "kg.jsonl").read_text().splitlines()]
            edges = {edge["edge"] for entry in kg for edge in entry["edges"]}
            self.assertIn("RUNS_DETECTOR", edges)
            self.assertIn("TESTS_ARTIFACT", edges)
            self.assertIn("EVIDENCES", edges)
            self.assertNotIn("RAN_DETECTOR", edges)
            self.assertNotIn("BUILT_FOR", edges)

if __name__ == "__main__":
    unittest.main()
