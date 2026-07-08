import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "detector_harness.py"

class DetectorHarnessTests(unittest.TestCase):
    def run_harness(self, *args):
        return subprocess.run([sys.executable, str(HARNESS), *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

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

    def test_validate_rejects_unknown_detector(self):
        proc = self.run_harness("validate-evidence", "tests/fixtures/detectors/invalid-unknown-detector.json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unknown detector_id", proc.stderr)

    def test_validate_rejects_unsanitized_evidence(self):
        proc = self.run_harness("validate-evidence", "tests/fixtures/detectors/invalid-unsanitized.json")
        self.assertEqual(proc.returncode, 3)
        self.assertIn("sanitization failure", proc.stderr)

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
