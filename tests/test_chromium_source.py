from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "chromium_source.py"

spec = importlib.util.spec_from_file_location("chromium_source", SCRIPT)
chromium_source = importlib.util.module_from_spec(spec)
sys.modules["chromium_source"] = chromium_source
assert spec.loader is not None
spec.loader.exec_module(chromium_source)


class ChromiumSourcePlanTests(unittest.TestCase):
    def test_build_plan_uses_manifest_ref_and_external_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            plan = chromium_source.build_plan(tmp_path / "chromium", tmp_path / "git-cache")

        self.assertEqual(plan.runtime_id, "browseforge-chromium")
        self.assertEqual(plan.base_ref, "refs/tags/150.0.7871.101")
        self.assertEqual(plan.chromium_src_dir, str(tmp_path / "chromium" / "src"))
        self.assertFalse(Path(plan.chromium_src_dir).is_relative_to(ROOT))
        self.assertIn("depot_tools", plan.path_prefix)

    def test_plan_contains_reproducible_source_steps(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            plan = chromium_source.build_plan(tmp_path / "chromium", tmp_path / "git-cache")
        step_ids = [step.id for step in plan.steps]

        self.assertEqual(
            step_ids[:4],
            [
                "prepare-workdir",
                "clone-depot-tools",
                "fetch-chromium",
                "checkout-pinned-ref",
            ],
        )
        self.assertIn("sync-deps", step_ids)
        self.assertIn("generate-dev-build", step_ids)
        checkout = next(step for step in plan.steps if step.id == "checkout-pinned-ref")
        self.assertEqual(checkout.command, ["git", "checkout", plan.base_ref])

    def test_check_tools_reports_checkout_presence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            (workdir / "src").mkdir(parents=True)
            (workdir / "depot_tools").mkdir(parents=True)
            plan = chromium_source.build_plan(workdir, tmp_path / "git-cache")
            tools = chromium_source.check_tools(plan)

        self.assertIs(tools["chromium_src_exists"], True)
        self.assertIs(tools["depot_tools_exists"], True)
        self.assertTrue(set(["fetch", "gclient", "gn", "ninja", "autoninja"]).issubset(tools))


if __name__ == "__main__":
    unittest.main()
