from __future__ import annotations

import io
import importlib.util
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        sync = next(step for step in plan.steps if step.id == "sync-deps")
        if chromium_source.host_deps_argument():
            self.assertIn(chromium_source.host_deps_argument(), sync.command)

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
        self.assertIn("platform_gn_binary", tools)
        self.assertIn("platform_gn_exists", tools)
        self.assertIn("dependency_profiles", tools)

    def test_check_tools_reports_dependency_profile_gn_presence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            src = workdir / "src"
            (src / "buildtools" / "linux64").mkdir(parents=True)
            (src / "buildtools" / "linux64" / "gn").write_text("gn\n", encoding="utf-8")
            (src / "buildtools" / "mac").mkdir(parents=True)
            (src / "buildtools" / "mac" / "gn").write_text("gn\n", encoding="utf-8")
            plan = chromium_source.build_plan(workdir, tmp_path / "git-cache")

            tools = chromium_source.check_tools(plan)

        self.assertEqual(
            {
                "linux_gn_exists": True,
                "mac_gn_exists": True,
                "windows_gn_exists": False,
            },
            tools["dependency_profiles"],
        )

    def test_check_tools_reports_platform_gn_presence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            src = workdir / "src"
            src.mkdir(parents=True)
            platform_gn = chromium_source.platform_gn_binary(src)
            platform_gn.parent.mkdir(parents=True)
            platform_gn.write_text("gn\n", encoding="utf-8")
            plan = chromium_source.build_plan(workdir, tmp_path / "git-cache")

            tools = chromium_source.check_tools(plan)

        self.assertEqual(str(platform_gn), tools["platform_gn_binary"])
        self.assertIs(tools["platform_gn_exists"], True)


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

    def test_check_build_outputs_reports_baseline_and_release_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            src = workdir / "src"
            (src / "out" / "BrowseForgeDev").mkdir(parents=True)
            (src / "out" / "BrowseForgeLinuxDocker").mkdir(parents=True)
            (src / "out" / "BrowseForgeDev" / "args.gn").write_text("is_debug=false\n", encoding="utf-8")
            (src / "out" / "BrowseForgeLinuxDocker" / "args.gn").write_text("is_debug=false\n", encoding="utf-8")
            (src / "out" / "BrowseForgeLinuxDocker" / "build.ninja").write_text("rule noop\n", encoding="utf-8")
            (src / "out" / "BrowseForgeLinuxDocker" / "chrome").write_text("binary\n", encoding="utf-8")
            plan = chromium_source.build_plan(workdir, tmp_path / "git-cache")

            outputs = chromium_source.check_build_outputs(plan)

        self.assertIs(outputs["dev_gn_args"]["exists"], True)
        self.assertIs(outputs["dev_build_ninja"]["exists"], False)
        self.assertIs(outputs["linux_docker_gn_args"]["exists"], True)
        self.assertIs(outputs["linux_docker_build_ninja"]["exists"], True)
        self.assertIs(outputs["linux_docker_chrome"]["exists"], True)



class ChromiumSourcePatchStatusTests(unittest.TestCase):
    def _configured_patch_checks(self) -> dict[str, dict[str, str]]:
        return {
            check["script"]: {
                "patch_id": check["patch_id"],
                "surface": check["surface"],
            }
            for check in chromium_source.PATCH_CHECKS
        }

    def _script_from_command(self, command: object) -> str | None:
        parts = command if isinstance(command, list) else shlex.split(str(command))
        for part in parts:
            path = Path(str(part))
            if path.name.startswith("apply_") and path.name.endswith(".py"):
                if path.is_absolute() and path.is_relative_to(ROOT):
                    return path.relative_to(ROOT).as_posix()
                if "scripts" in path.parts:
                    return Path(*path.parts[path.parts.index("scripts") :]).as_posix()
                return f"scripts/{path.name}"
        return None

    def _run_check_with_stubbed_patch_results(self, failing_script: str | None = None) -> tuple[dict, list[list[str]]]:
        completed_commands: list[list[str]] = []

        def fake_run(command: object, *args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            parts = [str(part) for part in (command if isinstance(command, list) else shlex.split(str(command)))]
            script = self._script_from_command(parts)
            self.assertIsNotNone(script, f"unexpected subprocess command during check: {parts}")
            completed_commands.append(parts)
            if script == failing_script:
                result = subprocess.CompletedProcess(parts, 42, "", f"{Path(script).stem} anchor missing\n")
            else:
                result = subprocess.CompletedProcess(parts, 0, f"ready: {script}\n", "")
            if kwargs.get("check") and result.returncode:
                raise subprocess.CalledProcessError(
                    result.returncode,
                    parts,
                    output=result.stdout,
                    stderr=result.stderr,
                )
            return result

        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            stdout = io.StringIO()
            argv = [
                "chromium_source.py",
                "check",
                "--workdir",
                str(tmp_path / "chromium"),
                "--git-cache",
                str(tmp_path / "git-cache"),
            ]
            check_patches = chromium_source.check_patches
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(chromium_source, "check_patches", side_effect=lambda plan: check_patches(plan, runner=fake_run)),
                mock.patch("sys.stdout", stdout),
            ):
                chromium_source.main()
            payload = json.loads(stdout.getvalue())
        return payload, completed_commands

    def _patch_status(self, payload: dict) -> tuple[list[dict], bool]:
        status = payload.get("patches")
        self.assertIsInstance(status, dict, "check output must include top-level patches status object")
        entries = status.get("checks")
        aggregate = status.get("all_ok")
        self.assertIsInstance(entries, list)
        self.assertIsInstance(aggregate, bool)
        return entries, aggregate

    def _entry_script_path(self, entry: dict) -> str:
        script = entry.get("script_path")
        self.assertIsInstance(script, str)
        path = Path(script)
        if path.is_absolute() and path.is_relative_to(ROOT):
            return path.relative_to(ROOT).as_posix()
        if "scripts" in path.parts:
            return Path(*path.parts[path.parts.index("scripts") :]).as_posix()
        return script

    def _entry_command(self, entry: dict) -> list[str]:
        command = entry.get("command")
        self.assertIsInstance(command, (list, str))
        return [str(part) for part in (command if isinstance(command, list) else shlex.split(str(command)))]

    def _entry_returncode(self, entry: dict) -> int:
        returncode = entry.get("returncode")
        self.assertIsInstance(returncode, int)
        return returncode

    def test_check_reports_patch_status_for_every_configured_check_script(self) -> None:
        expected = self._configured_patch_checks()

        payload, completed_commands = self._run_check_with_stubbed_patch_results()

        entries, all_ok = self._patch_status(payload)
        self.assertIn("build_outputs", payload)
        self.assertIn("linux_docker_build_ninja", payload["build_outputs"])
        self.assertIn("linux_docker_chrome", payload["build_outputs"])
        entries_by_script = {self._entry_script_path(entry): entry for entry in entries}
        self.assertEqual(set(expected), set(entries_by_script))
        self.assertEqual(set(expected), {self._script_from_command(command) for command in completed_commands})
        self.assertIs(all_ok, True)
        for script, metadata in expected.items():
            entry = entries_by_script[script]
            self.assertEqual(metadata["patch_id"], entry["patch_id"])
            self.assertEqual(metadata["surface"], entry["surface"])
            self.assertIs(entry["ok"], True)
            self.assertEqual(0, self._entry_returncode(entry))
            self.assertIsInstance(entry["message"], str)
            command = self._entry_command(entry)
            self.assertIn("--check", command)
            self.assertIn("--chromium-src", command)
            chromium_src = command[command.index("--chromium-src") + 1]
            self.assertEqual(payload["plan"]["chromium_src_dir"], chromium_src)

    def test_check_patch_status_aggregate_fails_when_any_check_fails(self) -> None:
        failing_script = "scripts/apply_webgl_patch.py"

        payload, _ = self._run_check_with_stubbed_patch_results(failing_script=failing_script)

        entries, all_ok = self._patch_status(payload)
        entries_by_script = {self._entry_script_path(entry): entry for entry in entries}
        self.assertIs(all_ok, False)
        failed = entries_by_script[failing_script]
        self.assertIs(failed["ok"], False)
        self.assertEqual(42, self._entry_returncode(failed))
        self.assertIn("apply_webgl_patch anchor missing", failed["message"])
        for script, entry in entries_by_script.items():
            if script != failing_script:
                self.assertIs(entry["ok"], True)

if __name__ == "__main__":
    unittest.main()
