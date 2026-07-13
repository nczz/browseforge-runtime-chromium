from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fingerprint_parity_gates.py"

spec = importlib.util.spec_from_file_location("fingerprint_parity_gates", SCRIPT)
fingerprint_parity_gates = importlib.util.module_from_spec(spec)
sys.modules["fingerprint_parity_gates"] = fingerprint_parity_gates
assert spec.loader is not None
spec.loader.exec_module(fingerprint_parity_gates)

REQUIRED_GATE_SURFACES = {
    "os-math-libm-parity": "OS math/libm parity",
    "css-hyphenation-text-layout-parity": "CSS hyphenation/text layout parity",
    "webaudio-backing-array-semantics": "AudioContext backing-array semantics",
    "wasm-js-numeric-parity": "WASM/JS numeric parity",
}


class FingerprintParityGateTests(unittest.TestCase):
    def minimal_manifest(self) -> dict[str, Any]:
        return {
            "runtime_id": "browseforge-chromium",
            "schema_version": "1.0",
            "gates": [
                {
                    "gate_id": gate_id,
                    "surface": surface,
                    "status": "blocked",
                    "release_blocker": True,
                    "risk_level": "high",
                    "decision": f"Keep {gate_id} blocked until a target-platform oracle is available.",
                    "current_coverage": "not_available_in_test_fixture",
                    "oracle_status": "missing_test_fixture_oracle",
                    "probe": {
                        "candidate_tool": "d8",
                        "command": "python3 scripts/fingerprint_parity_gates.py probe-plan",
                        "minimum_oracle": "target-platform oracle fixture",
                        "probe_body": "run parity probe fixture",
                    },
                    "blocked_by": ["target-platform oracle is not committed"],
                }
                for gate_id, surface in REQUIRED_GATE_SURFACES.items()
            ],
        }

    def test_committed_manifest_validates_with_required_gates(self) -> None:
        """The committed policy manifest keeps every required parity gate explicitly represented."""
        manifest = fingerprint_parity_gates.load_manifest()

        fingerprint_parity_gates.validate_manifest(manifest)

        gates = manifest["gates"]
        by_id = {gate["gate_id"]: gate for gate in gates}
        self.assertEqual(len(gates), len(by_id), "gate_id values must be unique")
        for gate_id, surface in REQUIRED_GATE_SURFACES.items():
            self.assertIn(gate_id, by_id)
            self.assertEqual(surface, by_id[gate_id]["surface"])

    def test_validate_manifest_rejects_missing_required_gate(self) -> None:
        """Validation fails loudly when a required parity surface is silently dropped."""
        manifest = fingerprint_parity_gates.load_manifest()
        malformed = copy.deepcopy(manifest)
        missing_gate = "wasm-js-numeric-parity"
        malformed["gates"] = [gate for gate in malformed["gates"] if gate["gate_id"] != missing_gate]

        with self.assertRaises(SystemExit) as raised:
            fingerprint_parity_gates.validate_manifest(malformed)

        message = str(raised.exception)
        self.assertIn("missing required gates", message)
        self.assertIn(missing_gate, message)

    def test_probe_plan_blocks_gates_when_probe_binaries_are_missing(self) -> None:
        """Probe planning reports every gate as unavailable when d8/content_shell/chrome are absent."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chromium_src = root / "empty-chromium-src"
            chromium_src.mkdir()
            source_manifest = root / "knowledge" / "manifests" / "source-acquisition.json"
            source_manifest.parent.mkdir(parents=True)
            source_manifest.write_text(
                json.dumps({"chromium_base": {"source_dir": str(chromium_src)}}),
                encoding="utf-8",
            )

            plan = fingerprint_parity_gates.probe_plan(root=root, manifest=self.minimal_manifest())

        self.assertIs(plan["ready"], False)
        self.assertEqual(str(chromium_src), plan["chromium_src"])
        for tool_name in ["chrome", "content_shell", "d8"]:
            tool = plan["tools"][tool_name]
            self.assertIs(tool["available"], False, tool_name)
            self.assertIsNone(tool["selected"], tool_name)
            self.assertTrue(tool["candidates"], tool_name)
            for candidate in tool["candidates"]:
                self.assertTrue(candidate.startswith(str(chromium_src)), candidate)
        self.assertEqual(set(REQUIRED_GATE_SURFACES), {gate["gate_id"] for gate in plan["gates"]})
        for gate in plan["gates"]:
            self.assertEqual("blocked_missing_tool", gate["probe_status"], gate["gate_id"])
            self.assertIsNone(gate["selected_binary"], gate["gate_id"])

    def test_list_filters_to_requested_surface_id(self) -> None:
        """The list command emits only the requested parity gate when filtered by surface id."""
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            result = fingerprint_parity_gates.main(["list", "--surface", "wasm-js-numeric-parity"])

        self.assertEqual(0, result)
        payload = json.loads(stdout.getvalue())
        self.assertEqual("browseforge-chromium", payload["runtime_id"])
        self.assertEqual(["wasm-js-numeric-parity"], [gate["gate_id"] for gate in payload["gates"]])
        self.assertEqual("WASM/JS numeric parity", payload["gates"][0]["surface"])


if __name__ == "__main__":
    unittest.main()
