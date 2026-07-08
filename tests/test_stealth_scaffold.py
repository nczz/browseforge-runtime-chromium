from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEALTH = ROOT / "browser" / "stealth"


class StealthScaffoldTests(unittest.TestCase):
    def test_gn_target_contains_mojo_and_native_sources(self) -> None:
        build = (STEALTH / "BUILD.gn").read_text(encoding="utf-8")
        for token in ["mojom(\"mojom\")", "source_set(\"stealth\")", "persona_resolver.cc", "persona_snapshot.cc", "stealth_switches.cc"]:
            self.assertIn(token, build)

    def test_native_switch_matches_wrapper_argument(self) -> None:
        wrapper = (ROOT / "internal" / "launcher" / "config.go").read_text(encoding="utf-8")
        switches = (STEALTH / "stealth_switches.cc").read_text(encoding="utf-8")
        self.assertIn('"--browseforge-stealth-config"', wrapper)
        self.assertIn('"browseforge-stealth-config"', switches)
        self.assertIn('"--browseforge-stealth-mode"', wrapper)
        self.assertIn('"browseforge-stealth-mode"', switches)

    def test_persona_snapshot_fail_closed_contract_exists(self) -> None:
        snapshot = (STEALTH / "persona_snapshot.cc").read_text(encoding="utf-8")
        resolver = (STEALTH / "persona_resolver.cc").read_text(encoding="utf-8")
        self.assertIn("bool PersonaSnapshot::IsComplete()", snapshot)
        self.assertIn("bool PersonaSnapshot::IsCoherent()", snapshot)
        self.assertIn("PersonaError::kIncompletePersona", resolver)
        self.assertIn("PersonaError::kIncoherentPersona", resolver)

    def test_mojo_interface_is_internal_projection_only(self) -> None:
        mojom = (STEALTH / "public" / "mojom" / "stealth.mojom").read_text(encoding="utf-8")
        self.assertIn("interface BrowseForgeStealthHost", mojom)
        self.assertIn("GetPersonaSnapshot", mojom)
        self.assertIn("GetOriginSaltKey", mojom)
        self.assertNotIn("Window", mojom)
        self.assertNotIn("Navigator", mojom)


if __name__ == "__main__":
    unittest.main()
