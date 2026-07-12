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
            (src / "BUILD.gn").write_text('group("gn_all") {\n  deps = [\n      "//url:url_unittests",\n  ]\n}\n', encoding="utf-8")
            copied = apply_stealth_scaffold.apply_scaffold(src)

            self.assertIn(Path("browseforge/stealth/BUILD.gn"), copied)
            self.assertIn(Path("browseforge/stealth/public/mojom/stealth.mojom"), copied)
            self.assertIn(Path("BUILD.gn"), copied)
            self.assertIn('"//browseforge/stealth"', (src / "BUILD.gn").read_text(encoding="utf-8"))
            self.assertTrue((src / "browseforge" / "stealth" / "persona_resolver.cc").is_file())

    def test_check_requires_scaffold_files_and_build_dep(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / ".git").mkdir(parents=True)
            (src / "BUILD.gn").write_text('group("gn_all") {\n  deps = [\n      "//url:url_unittests",\n  ]\n}\n', encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                apply_stealth_scaffold.verify_scaffold_applied(src)

            self.assertIn("stealth scaffold is not fully applied", str(raised.exception))

            apply_stealth_scaffold.apply_scaffold(src)
            apply_stealth_scaffold.verify_scaffold_applied(src)


if __name__ == "__main__":
    unittest.main()
