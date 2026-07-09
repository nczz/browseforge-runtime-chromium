from __future__ import annotations

import importlib.util
import sys
import subprocess
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

    def test_check_tools_reports_pinned_checkout_head(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            src = workdir / "src"
            src.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=src, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=src, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=src, check=True)
            (src / "README").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "README"], cwd=src, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=src, check=True, stdout=subprocess.DEVNULL)
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
            plan = chromium_source.build_plan(workdir, tmp_path / "git-cache")
            plan = chromium_source.SourcePlan(
                runtime_id=plan.runtime_id,
                base_version=plan.base_version,
                base_ref=plan.base_ref,
                base_commit=head,
                workdir=plan.workdir,
                depot_tools_dir=plan.depot_tools_dir,
                chromium_src_dir=plan.chromium_src_dir,
                git_cache_dir=plan.git_cache_dir,
                path_prefix=plan.path_prefix,
                steps=plan.steps,
            )

            tools = chromium_source.check_tools(plan)

        self.assertEqual(tools["chromium_src_head"], head)
        self.assertIs(tools["chromium_src_matches_manifest"], True)

    def test_check_tools_reports_manifest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            src = workdir / "src"
            src.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=src, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=src, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=src, check=True)
            (src / "README").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "README"], cwd=src, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=src, check=True, stdout=subprocess.DEVNULL)
            plan = chromium_source.build_plan(workdir, tmp_path / "git-cache")

            tools = chromium_source.check_tools(plan)

        self.assertRegex(tools["chromium_src_head"], r"^[0-9a-f]{40}$")
        self.assertIs(tools["chromium_src_matches_manifest"], False)


if __name__ == "__main__":
    unittest.main()
