from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_stealth_scaffold.py"

spec = importlib.util.spec_from_file_location("apply_stealth_scaffold", SCRIPT)
apply_stealth_scaffold = importlib.util.module_from_spec(spec)
sys.modules["apply_stealth_scaffold"] = apply_stealth_scaffold
assert spec.loader is not None
spec.loader.exec_module(apply_stealth_scaffold)


class ApplyStealthScaffoldTests(unittest.TestCase):
    def test_refuses_missing_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                apply_stealth_scaffold.validate_chromium_src(Path(td))

    def test_copies_scaffold_into_external_chromium_tree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / ".git").mkdir(parents=True)
            copied = apply_stealth_scaffold.apply_scaffold(src)

            self.assertIn(Path("browseforge/stealth/BUILD.gn"), copied)
            self.assertIn(Path("browseforge/stealth/public/mojom/stealth.mojom"), copied)
            self.assertTrue((src / "browseforge" / "stealth" / "persona_resolver.cc").is_file())


if __name__ == "__main__":
    unittest.main()
