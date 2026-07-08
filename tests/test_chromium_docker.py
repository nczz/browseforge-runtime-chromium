from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "chromium_docker.py"

spec = importlib.util.spec_from_file_location("chromium_docker", SCRIPT)
chromium_docker = importlib.util.module_from_spec(spec)
sys.modules["chromium_docker"] = chromium_docker
assert spec.loader is not None
spec.loader.exec_module(chromium_docker)


class ChromiumDockerPlanTests(unittest.TestCase):
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
        self.assertIn("PATH=/opt/depot_tools:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", gn)
        self.assertIn("./buildtools/linux64/gn", gn[-1])
        self.assertIn("sync-linux-deps", plan.commands)
        self.assertEqual("bf-test:deps", plan.deps_image)
        self.assertIn('target_os="linux"', plan.gn_args)
        self.assertIn('target_cpu="x64"', plan.gn_args)

    def test_check_reports_source_and_dockerfile_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td) / "chromium"
            src = workdir / "src"
            src.mkdir(parents=True)
            (src / "DEPS").write_text("deps = {}\n", encoding="utf-8")
            plan = chromium_docker.build_plan(workdir=workdir)
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
