from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "chromium_docker.py"

spec = importlib.util.spec_from_file_location("chromium_docker", SCRIPT)
chromium_docker = importlib.util.module_from_spec(spec)
sys.modules["chromium_docker"] = chromium_docker
assert spec.loader is not None
spec.loader.exec_module(chromium_docker)


class ChromiumDockerPlanTests(unittest.TestCase):
    def _run_script(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def test_plan_exposes_run_hooks_and_build_chrome_commands_for_deps_image(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td) / "chromium"
            git_cache = Path(td) / "git-cache"
            completed = self._run_script(
                "plan",
                "--workdir",
                str(workdir),
                "--image",
                "bf-test",
                "--git-cache",
                str(git_cache),
                "--platform",
                "linux/amd64",
                "--out-dir",
                "out/BrowseForgeLinuxDocker",
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        build_chrome = payload["commands"]["build-chrome"]
        run_hooks = payload["commands"]["run-hooks"]
        self.assertEqual("bf-test:deps", payload["deps_image"])
        self.assertIn("bf-test:deps", run_hooks)
        self.assertIn(f"{workdir}:/work/chromium", run_hooks)
        self.assertEqual("/work/chromium/src", run_hooks[run_hooks.index("-w") + 1])
        self.assertEqual(
            ["bash", "-lc", "/opt/depot_tools/ensure_bootstrap && cd /work/chromium && gclient runhooks"],
            run_hooks[-3:],
        )
        self.assertIn("bf-test:deps", build_chrome)
        self.assertIn(f"{workdir}:/work/chromium", build_chrome)
        self.assertEqual("/work/chromium/src", build_chrome[build_chrome.index("-w") + 1])
        self.assertEqual(["bash", "-lc", "/opt/depot_tools/ensure_bootstrap && autoninja -j4 -C out/BrowseForgeLinuxDocker chrome"], build_chrome[-3:])
        self.assertEqual(4, payload["jobs"])


    def test_cli_default_workdir_can_use_linux_profile_env(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            linux_workdir = Path(td) / "chromium-linux"
            env = os.environ.copy()
            env["BROWSEFORGE_CHROMIUM_LINUX_WORKDIR"] = str(linux_workdir)
            env["BROWSEFORGE_CHROMIUM_WORKDIR"] = str(Path(td) / "chromium-shared")
            completed = self._run_script(
                "plan",
                "--git-cache",
                str(Path(td) / "git-cache"),
                env=env,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(str(linux_workdir), payload["workdir"])
        self.assertEqual(str(linux_workdir / "src"), payload["chromium_src_dir"])

    def test_plan_allows_higher_build_job_count(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td) / "chromium"
            completed = self._run_script(
                "plan",
                "--workdir",
                str(workdir),
                "--jobs",
                "8",
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(8, payload["jobs"])
        self.assertEqual(
            ["bash", "-lc", "/opt/depot_tools/ensure_bootstrap && autoninja -j8 -C out/BrowseForgeLinuxDocker chrome"],
            payload["commands"]["build-chrome"][-3:],
        )

    def test_check_reports_chrome_output_binary_status(self) -> None:
        env = os.environ.copy()
        env["PATH"] = ""
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td) / "chromium"
            src = workdir / "src"
            output_binary = src / "out" / "BrowseForgeLinuxDocker" / "chrome"
            output_binary.parent.mkdir(parents=True)
            output_binary.write_bytes(b"chrome")
            completed = self._run_script(
                "check",
                "--workdir",
                str(workdir),
                "--git-cache",
                str(Path(td) / "git-cache"),
                "--out-dir",
                "out/BrowseForgeLinuxDocker",
                env=env,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(str(output_binary), payload["status"]["output_binary"])
        self.assertIs(payload["status"]["output_binary_exists"], True)
        self.assertEqual(str(output_binary), payload["plan"]["output_binary"])

    def test_build_chrome_requires_execute_before_running_docker(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            completed = self._run_script(
                "build-chrome",
                "--workdir",
                str(Path(td) / "chromium"),
                "--git-cache",
                str(Path(td) / "git-cache"),
                "--out-dir",
                "out/BrowseForgeLinuxDocker",
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("build-chrome requires --execute", completed.stderr + completed.stdout)

    def test_run_hooks_requires_execute_before_running_docker(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            completed = self._run_script(
                "run-hooks",
                "--workdir",
                str(Path(td) / "chromium"),
                "--git-cache",
                str(Path(td) / "git-cache"),
                "--out-dir",
                "out/BrowseForgeLinuxDocker",
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("run-hooks requires --execute", completed.stderr + completed.stdout)

    def test_plan_mounts_external_workdir_and_runtime_readonly(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td) / "chromium"
            plan = chromium_docker.build_plan(workdir=workdir, image="bf-test", git_cache=workdir.parent / "git-cache", platform="linux/amd64")

        gn = plan.commands["gn-gen"]
        self.assertIn("docker", gn[0])
        self.assertIn("linux/amd64", gn)
        self.assertIn(f"{workdir}:/work/chromium", gn)
        self.assertIn(f"{workdir.parent / 'git-cache'}:{workdir.parent / 'git-cache'}", gn)
        self.assertIn(f"{ROOT}:/work/runtime:ro", gn)
        self.assertIn("AI_AGENT=1", gn)
        path_env = next(value.removeprefix("PATH=") for value in gn if value.startswith("PATH="))
        path_entries = path_env.split(":")
        self.assertEqual("/opt/depot_tools", path_entries[0])
        self.assertNotEqual("/work/chromium/depot_tools", path_entries[0])
        self.assertIn("./buildtools/linux64/gn", gn[-1])
        self.assertIn("sync-linux-deps", plan.commands)
        self.assertEqual("bf-test:deps", plan.deps_image)
        self.assertIn('target_os="linux"', plan.gn_args)
        self.assertIn('target_cpu="x64"', plan.gn_args)
        self.assertIn("proprietary_codecs=true", plan.gn_args)
        self.assertIn('ffmpeg_branding="Chrome"', plan.gn_args)

    def test_check_reports_source_and_dockerfile_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td) / "chromium"
            src = workdir / "src"
            src.mkdir(parents=True)
            (src / "DEPS").write_text("deps = {}\n", encoding="utf-8")
            plan = chromium_docker.build_plan(workdir=workdir)
            with mock.patch.object(chromium_docker, "docker_image_exists", return_value=False):
                status = chromium_docker.check(plan)

        self.assertTrue(status["dockerfile_exists"])
        self.assertTrue(status["chromium_src_exists"])
        self.assertTrue(status["chromium_deps_exists"])
        self.assertFalse(status["out_args_exists"])
        self.assertFalse(status["linux_gn_exists"])
        self.assertIn("docker", status)
        self.assertIn("deps_image_exists", status)

    def test_dockerfile_uses_ubuntu_and_no_repo_source_copy(self) -> None:
        dockerfile = (ROOT / "docker" / "chromium-build.Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM ubuntu:22.04", dockerfile)
        self.assertIn("python3", dockerfile)
        self.assertIn("depot_tools", dockerfile)
        self.assertNotIn("COPY browser", dockerfile)
        self.assertNotIn("COPY .", dockerfile)


if __name__ == "__main__":
    unittest.main()
