from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "chromium_native.py"

spec = importlib.util.spec_from_file_location("chromium_native", SCRIPT)
chromium_native = importlib.util.module_from_spec(spec)
sys.modules["chromium_native"] = chromium_native
assert spec.loader is not None
spec.loader.exec_module(chromium_native)


class ChromiumNativePlanTests(unittest.TestCase):
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

    def _json_from_script(self, *args: str, env: dict[str, str] | None = None) -> dict:
        completed = self._run_script(*args, env=env)
        self.assertEqual(0, completed.returncode, completed.stderr + completed.stdout)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - keeps failures readable.
            self.fail(f"command did not emit JSON: {exc}: {completed.stdout!r}")
        self.assertIsInstance(payload, dict)
        return payload

    def _write_native_checkout_fixtures(self, workdir: Path) -> tuple[Path, Path]:
        src = workdir / "src"
        depot_tools = workdir / "depot_tools"
        src.mkdir(parents=True)
        depot_tools.mkdir()
        (src / "DEPS").write_text("deps = {}\n", encoding="utf-8")
        for tool in ("gclient", "autoninja", "gn"):
            (depot_tools / tool).write_text("#!/bin/sh\n", encoding="utf-8")
        return src, depot_tools

    def _macos_check_status(self, workdir: Path, runtime_root: Path) -> dict:
        stdout = io.StringIO()
        argv = [
            "chromium_native.py",
            "check",
            "--platform",
            "macos-arm64",
            "--workdir",
            str(workdir),
            "--out-dir",
            "out/TestMacArm64",
        ]
        with (
            mock.patch.object(chromium_native, "ROOT", runtime_root),
            mock.patch.object(chromium_native, "host_os_name", return_value="darwin"),
            mock.patch.object(sys, "argv", argv),
            mock.patch("sys.stdout", stdout),
        ):
            chromium_native.main()
        return json.loads(stdout.getvalue())["status"]

    def test_macos_plan_targets_arm64_app_bundle_and_package_platform(self) -> None:
        """The macOS native plan targets arm64 Chromium.app and packages the macos-arm64 artifact."""
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td) / "chromium"
            payload = self._json_from_script(
                "plan",
                "--platform",
                "macos-arm64",
                "--workdir",
                str(workdir),
                "--out-dir",
                "out/TestMacArm64",
            )

        self.assertIn('target_os="mac"', payload["gn_args"])
        self.assertIn('target_cpu="arm64"', payload["gn_args"])
        self.assertEqual(
            str(workdir / "src" / "out" / "TestMacArm64" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"),
            payload["output_binary"],
        )
        self.assertEqual(
            f"browseforge-runtime-chromium-{chromium_native.RUNTIME_VERSION}-macos-arm64",
            payload["package_artifact_id"],
        )
        package_command = payload["package_command"]
        self.assertEqual("package", package_command[2])
        self.assertEqual("package", payload["commands"]["package"][2])
        self.assertNotIn("--execute", payload["commands"]["package"])
        self.assertEqual("macos-arm64", package_command[package_command.index("--platform") + 1])
        self.assertEqual("macos-arm64", payload["commands"]["package"][package_command.index("--platform") + 1])
        self.assertEqual(str(ROOT / "dist"), package_command[package_command.index("--output-dir") + 1])
        self.assertEqual("surface-switch-propagation-native-audit", package_command[package_command.index("--patchset-id") + 1])
        self.assertEqual("alpha", package_command[package_command.index("--release-channel") + 1])

    def test_cli_default_workdir_can_use_host_profile_env(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            host_workdir = Path(td) / "chromium-host"
            env = os.environ.copy()
            env["BROWSEFORGE_CHROMIUM_HOST_WORKDIR"] = str(host_workdir)
            env["BROWSEFORGE_CHROMIUM_WORKDIR"] = str(Path(td) / "chromium-shared")
            payload = self._json_from_script(
                "plan",
                "--platform",
                "macos-arm64",
                "--out-dir",
                "out/TestMacArm64",
                env=env,
            )

        self.assertEqual(str(host_workdir), payload["workdir"])
        self.assertEqual(str(host_workdir / "src"), payload["chromium_src_dir"])

    def test_windows_plan_targets_x64_chrome_exe_and_cross_compile_env(self) -> None:
        """The Windows native plan cross-targets win/x64 and carries the macOS cross-toolchain env."""
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td) / "chromium"
            payload = self._json_from_script(
                "plan",
                "--platform",
                "windows-x64",
                "--workdir",
                str(workdir),
                "--out-dir",
                "out/TestWindowsX64",
            )

        self.assertIn('target_os="win"', payload["gn_args"])
        self.assertIn('target_cpu="x64"', payload["gn_args"])
        self.assertEqual("windows", payload["required_host_os"])
        self.assertEqual(str(workdir / "src" / "out" / "TestWindowsX64" / "chrome.exe"), payload["output_binary"])
        package_command = payload["package_command"]
        self.assertEqual("windows-x64", package_command[package_command.index("--platform") + 1])
        gn_command = payload["commands"]["gn-gen"][2]
        self.assertIn("DEPOT_TOOLS_WIN_TOOLCHAIN_BASE_URL=", gn_command)
        self.assertIn("GYP_MSVS_HASH_e66617bc68=6eae1a9f3e", gn_command)
        self.assertIn("DEPOT_TOOLS_WIN_TOOLCHAIN=1", gn_command)

    def test_plan_exposes_checkout_depot_tools_and_wraps_native_commands(self) -> None:
        """Run-hooks/build commands execute with the checkout depot_tools first in PATH."""
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td) / "chromium"
            payload = self._json_from_script(
                "plan",
                "--platform",
                "macos-arm64",
                "--workdir",
                str(workdir),
                "--out-dir",
                "out/TestMacArm64",
                "--jobs",
                "13",
            )

        depot_tools = workdir / "depot_tools"
        expected_path_prefix = f"{depot_tools}:$PATH"
        self.assertEqual(str(depot_tools), payload["depot_tools_dir"])
        self.assertEqual(expected_path_prefix, payload["path_prefix"])

        sync_deps = payload["commands"]["sync-deps"]
        self.assertEqual(["bash", "-lc"], sync_deps[:2])
        self.assertEqual(
            f"PATH={expected_path_prefix} DEPOT_TOOLS_UPDATE=0 gclient sync --with_branch_heads --with_tags",
            sync_deps[2],
        )
        run_hooks = payload["commands"]["run-hooks"]
        self.assertEqual(["bash", "-lc"], run_hooks[:2])
        self.assertEqual(f"PATH={expected_path_prefix} DEPOT_TOOLS_UPDATE=0 gclient runhooks", run_hooks[2])


        gn_gen = payload["commands"]["gn-gen"]
        self.assertEqual(["bash", "-lc"], gn_gen[:2])
        self.assertEqual(
            "PATH={path_prefix} DEPOT_TOOLS_UPDATE=0 gn gen out/TestMacArm64 --args='target_os=\"mac\" target_cpu=\"arm64\" "
            "is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false'".format(
                path_prefix=expected_path_prefix
            ),
            gn_gen[2],
        )
        build_chrome = payload["commands"]["build-chrome"]
        self.assertEqual(["bash", "-lc"], build_chrome[:2])
        self.assertEqual(
            f"PATH={expected_path_prefix} DEPOT_TOOLS_UPDATE=0 autoninja -j13 -C out/TestMacArm64 chrome",
            build_chrome[2],
        )


    def test_check_reports_checkout_depot_tools_and_missing_artifacts(self) -> None:
        """A temp checkout reports local depot_tools paths and absent release outputs accurately."""
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            src = workdir / "src"
            depot_tools = workdir / "depot_tools"
            src.mkdir(parents=True)
            depot_tools.mkdir()
            (src / "DEPS").write_text("deps = {}\n", encoding="utf-8")
            (depot_tools / "gclient").write_text("#!/bin/sh\n", encoding="utf-8")
            (depot_tools / "autoninja").write_text("#!/bin/sh\n", encoding="utf-8")
            (depot_tools / "gn").write_text("#!/bin/sh\n", encoding="utf-8")
            stdout = io.StringIO()
            argv = [
                "chromium_native.py",
                "check",
                "--platform",
                "macos-arm64",
                "--workdir",
                str(workdir),
                "--out-dir",
                "out/TestMacArm64",
            ]
            with (
                mock.patch.object(chromium_native, "ROOT", tmp_path / "runtime"),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(chromium_native.shutil, "which", return_value=None),
                mock.patch("sys.stdout", stdout),
            ):
                chromium_native.main()
            payload = json.loads(stdout.getvalue())
            status = payload["status"]
        self.assertIs(status["chromium_src_exists"], True)
        self.assertIs(status["chromium_deps_exists"], True)
        self.assertEqual(str(depot_tools), status["depot_tools_dir"])
        self.assertIs(status["depot_tools_exists"], True)
        self.assertEqual(str(depot_tools / "gclient"), status["gclient"])
        self.assertEqual(str(depot_tools / "autoninja"), status["autoninja"])
        self.assertEqual(str(depot_tools / "gn"), status["gn_binary"])
        self.assertIs(status["gn_binary_exists"], True)
        self.assertIs(status["build_ninja_exists"], False)
        self.assertIs(status["output_binary_exists"], False)
        self.assertIs(status["package_zip_exists"], False)
        self.assertIs(status["app_bundle_exists"], False)


    def test_macos_check_reports_command_line_tools_xcodebuild_blocker_before_gn(self) -> None:
        """A CommandLineTools-only xcodebuild failure blocks native readiness despite local depot_tools."""
        command_line_tools_error = (
            "xcode-select: error: tool 'xcodebuild' requires Xcode, but active developer directory "
            "'/Library/Developer/CommandLineTools' is a command line tools instance\n"
        )
        long_error = command_line_tools_error + ("x" * 4096)

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(("xcodebuild", ["-version"]), (Path(command[0]).name, command[1:]))
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(1, command, output="", stderr=long_error)
            return subprocess.CompletedProcess(command, 1, stdout="", stderr=long_error)

        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            _, depot_tools = self._write_native_checkout_fixtures(workdir)
            with (
                mock.patch.object(chromium_native.shutil, "which", side_effect=lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None),
                mock.patch.object(chromium_native.subprocess, "run", side_effect=fake_run) as run,
            ):
                status = self._macos_check_status(workdir, tmp_path / "runtime")

        self.assertEqual(str(depot_tools / "gclient"), status["gclient"])
        self.assertEqual(str(depot_tools / "autoninja"), status["autoninja"])
        self.assertEqual(str(depot_tools / "gn"), status["gn_binary"])
        self.assertIs(status["gn_binary_exists"], True)
        self.assertEqual("/usr/bin/xcodebuild", status["xcodebuild"])
        self.assertIs(status["xcodebuild_ok"], False)
        self.assertEqual("failed", status["xcodebuild_status"])
        self.assertIn("requires Xcode", status["xcodebuild_error"])
        self.assertIn("CommandLineTools", status["xcodebuild_error"])
        self.assertLessEqual(len(status["xcodebuild_error"]), 2048)
        self.assertIs(status["native_toolchain_ready"], False)
        run.assert_called_once()

    def test_macos_check_marks_native_toolchain_ready_when_xcodebuild_and_depot_tools_are_available(self) -> None:
        """A supported macOS host with local depot_tools and working xcodebuild is ready for native GN steps."""
        xcodebuild_output = "Xcode 16.4\nBuild version 16F6\n"

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(("xcodebuild", ["-version"]), (Path(command[0]).name, command[1:]))
            return subprocess.CompletedProcess(command, 0, stdout=xcodebuild_output, stderr="")

        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            self._write_native_checkout_fixtures(workdir)
            with (
                mock.patch.object(chromium_native.shutil, "which", side_effect=lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None),
                mock.patch.object(chromium_native.subprocess, "run", side_effect=fake_run) as run,
            ):
                status = self._macos_check_status(workdir, tmp_path / "runtime")

        self.assertEqual("/usr/bin/xcodebuild", status["xcodebuild"])
        self.assertIs(status["xcodebuild_ok"], True)
        self.assertEqual("ok", status["xcodebuild_status"])
        self.assertEqual("Xcode 16.4 Build version 16F6", status["xcodebuild_version"])
        self.assertIs(status["host_supported"], True)
        self.assertIs(status["depot_tools_exists"], True)
        self.assertIs(status["gn_binary_exists"], True)
        self.assertIs(status["native_toolchain_ready"], True)
        run.assert_called_once()

    def test_execute_gn_and_build_fail_before_running_with_command_line_tools_xcodebuild(self) -> None:
        """GN/build execution refuses a CommandLineTools-only macOS toolchain before invoking build commands."""
        command_line_tools_error = (
            "xcode-select: error: tool 'xcodebuild' requires Xcode, but active developer directory "
            "'/Library/Developer/CommandLineTools' is a command line tools instance\n"
        )

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(("xcodebuild", ["-version"]), (Path(command[0]).name, command[1:]))
            return subprocess.CompletedProcess(command, 1, stdout="", stderr=command_line_tools_error)

        for command in ("gn-gen", "build-chrome"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as td:
                tmp_path = Path(td)
                workdir = tmp_path / "chromium"
                self._write_native_checkout_fixtures(workdir)
                argv = [
                    "chromium_native.py",
                    command,
                    "--platform",
                    "macos-arm64",
                    "--workdir",
                    str(workdir),
                    "--out-dir",
                    "out/TestMacArm64",
                    "--execute",
                ]
                with (
                    mock.patch.object(sys, "argv", argv),
                    mock.patch.object(chromium_native, "ROOT", tmp_path / "runtime"),
                    mock.patch.object(chromium_native, "host_os_name", return_value="darwin"),
                    mock.patch.object(chromium_native.shutil, "which", side_effect=lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None),
                    mock.patch.object(chromium_native.subprocess, "run", side_effect=fake_run) as xcodebuild_run,
                    mock.patch.object(chromium_native, "run_command") as run_command,
                ):
                    with self.assertRaises(SystemExit) as raised:
                        chromium_native.main()

                message = str(raised.exception)
                self.assertIn(f"{command} native toolchain is not ready", message)
                self.assertIn("xcodebuild_status=failed", message)
                self.assertIn("xcodebuild_error=", message)
                self.assertIn("CommandLineTools", message)
                xcodebuild_run.assert_called_once()
                run_command.assert_not_called()

    def test_execute_build_chrome_requires_build_ninja_before_running(self) -> None:
        """Build execution refuses a ready checkout with no generated Ninja graph."""

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(("xcodebuild", ["-version"]), (Path(command[0]).name, command[1:]))
            return subprocess.CompletedProcess(command, 0, stdout="Xcode 16.4\nBuild version 16F6\n", stderr="")

        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            src, _ = self._write_native_checkout_fixtures(workdir)
            self.assertFalse((src / "out" / "TestMacArm64" / "build.ninja").exists())
            argv = [
                "chromium_native.py",
                "build-chrome",
                "--platform",
                "macos-arm64",
                "--workdir",
                str(workdir),
                "--out-dir",
                "out/TestMacArm64",
                "--execute",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(chromium_native, "ROOT", tmp_path / "runtime"),
                mock.patch.object(chromium_native, "host_os_name", return_value="darwin"),
                mock.patch.object(chromium_native.shutil, "which", side_effect=lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None),
                mock.patch.object(chromium_native.subprocess, "run", side_effect=fake_run) as xcodebuild_run,
                mock.patch.object(chromium_native, "run_command") as run_command,
            ):
                with self.assertRaises(SystemExit) as raised:
                    chromium_native.main()

        message = str(raised.exception)
        self.assertIn("build-chrome", message)
        self.assertIn("build_ninja_exists=False", message)
        xcodebuild_run.assert_called_once()
        run_command.assert_not_called()

    def test_execute_package_requires_output_binary_and_app_bundle_before_running(self) -> None:
        """Packaging refuses to run package_runtime when the macOS browser app is missing."""

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(("xcodebuild", ["-version"]), (Path(command[0]).name, command[1:]))
            return subprocess.CompletedProcess(command, 0, stdout="Xcode 16.4\nBuild version 16F6\n", stderr="")

        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            src, _ = self._write_native_checkout_fixtures(workdir)
            out_dir = src / "out" / "TestMacArm64"
            out_dir.mkdir(parents=True)
            (out_dir / "build.ninja").write_text("rule chrome\n", encoding="utf-8")
            argv = [
                "chromium_native.py",
                "package",
                "--platform",
                "macos-arm64",
                "--workdir",
                str(workdir),
                "--out-dir",
                "out/TestMacArm64",
                "--execute",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(chromium_native, "ROOT", tmp_path / "runtime"),
                mock.patch.object(chromium_native, "host_os_name", return_value="darwin"),
                mock.patch.object(chromium_native.shutil, "which", side_effect=lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None),
                mock.patch.object(chromium_native.subprocess, "run", side_effect=fake_run) as xcodebuild_run,
                mock.patch.object(chromium_native, "run_command") as run_command,
            ):
                with self.assertRaises(SystemExit) as raised:
                    chromium_native.main()

        message = str(raised.exception)
        self.assertIn("package", message)
        self.assertIn("output_binary_exists=False", message)
        self.assertIn("app_bundle_exists=False", message)
        xcodebuild_run.assert_called_once()
        run_command.assert_not_called()

    def test_execute_gn_gen_delegates_without_build_ninja_when_toolchain_ready(self) -> None:
        """GN generation remains allowed before build.ninja exists."""

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(("xcodebuild", ["-version"]), (Path(command[0]).name, command[1:]))
            return subprocess.CompletedProcess(command, 0, stdout="Xcode 16.4\nBuild version 16F6\n", stderr="")

        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            src, _ = self._write_native_checkout_fixtures(workdir)
            self.assertFalse((src / "out" / "TestMacArm64" / "build.ninja").exists())
            argv = [
                "chromium_native.py",
                "gn-gen",
                "--platform",
                "macos-arm64",
                "--workdir",
                str(workdir),
                "--out-dir",
                "out/TestMacArm64",
                "--execute",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(chromium_native, "ROOT", tmp_path / "runtime"),
                mock.patch.object(chromium_native, "host_os_name", return_value="darwin"),
                mock.patch.object(chromium_native.shutil, "which", side_effect=lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None),
                mock.patch.object(chromium_native.subprocess, "run", side_effect=fake_run) as xcodebuild_run,
                mock.patch.object(chromium_native, "run_command") as run_command,
            ):
                chromium_native.main()

        xcodebuild_run.assert_called_once()
        run_command.assert_called_once()
        delegated_command, delegated_cwd = run_command.call_args.args
        self.assertEqual(chromium_native.build_plan("macos-arm64", workdir, "out/TestMacArm64").commands["gn-gen"], delegated_command)
        self.assertEqual(src, delegated_cwd)

    def test_execute_run_hooks_still_runs_with_command_line_tools_xcodebuild(self) -> None:
        """Run-hooks is allowed under CommandLineTools-only xcodebuild so it can repair checkout buildtools."""
        command_line_tools_error = (
            "xcode-select: error: tool 'xcodebuild' requires Xcode, but active developer directory "
            "'/Library/Developer/CommandLineTools' is a command line tools instance\n"
        )

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(("xcodebuild", ["-version"]), (Path(command[0]).name, command[1:]))
            return subprocess.CompletedProcess(command, 1, stdout="", stderr=command_line_tools_error)

        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            src, _ = self._write_native_checkout_fixtures(workdir)
            argv = [
                "chromium_native.py",
                "run-hooks",
                "--platform",
                "macos-arm64",
                "--workdir",
                str(workdir),
                "--out-dir",
                "out/TestMacArm64",
                "--execute",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(chromium_native, "ROOT", tmp_path / "runtime"),
                mock.patch.object(chromium_native, "host_os_name", return_value="darwin"),
                mock.patch.object(chromium_native.shutil, "which", side_effect=lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None),
                mock.patch.object(chromium_native.subprocess, "run", side_effect=fake_run) as xcodebuild_run,
                mock.patch.object(chromium_native, "run_command") as run_command,
            ):
                chromium_native.main()

        xcodebuild_run.assert_called_once()
        run_command.assert_called_once()
        delegated_command, delegated_cwd = run_command.call_args.args
        self.assertEqual(chromium_native.build_plan("macos-arm64", workdir, "out/TestMacArm64").commands["run-hooks"], delegated_command)
        self.assertEqual(src, delegated_cwd)

    def test_mutating_command_without_execute_exits_nonzero(self) -> None:
        """Native build actions fail closed unless the caller explicitly opts into mutation."""
        with tempfile.TemporaryDirectory() as td:
            completed = self._run_script(
                "build-chrome",
                "--platform",
                "macos-arm64",
                "--workdir",
                str(Path(td) / "chromium"),
                "--out-dir",
                "out/TestMacArm64",
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("build-chrome requires --execute", completed.stderr + completed.stdout)

    def test_execute_windows_command_on_non_windows_host_rejects_before_running(self) -> None:
        """Even with --execute, a Windows native command is rejected on a non-Windows host."""
        with tempfile.TemporaryDirectory() as td:
            argv = [
                "chromium_native.py",
                "gn-gen",
                "--platform",
                "windows-x64",
                "--workdir",
                str(Path(td) / "chromium"),
                "--out-dir",
                "out/TestWindowsX64",
                "--execute",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(chromium_native, "host_os_name", return_value="darwin"),
                mock.patch.object(chromium_native, "run_command") as run_command,
            ):
                with self.assertRaises(SystemExit) as raised:
                    chromium_native.main()

        self.assertIn(
            "gn-gen for windows-x64 requires host_os=windows; current host_os=darwin",
            str(raised.exception),
        )
        run_command.assert_not_called()

    def test_windows_check_accepts_macos_cross_toolchain_fixture(self) -> None:
        """A macOS host can satisfy Windows host support when the pinned toolchain zip and target_os are present."""
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            workdir = tmp_path / "chromium"
            src, depot_tools = self._write_native_checkout_fixtures(workdir)
            (depot_tools / "gn.bat").write_text("@echo off\n", encoding="utf-8")
            (workdir / ".gclient").write_text("target_os = ['win']\n", encoding="utf-8")
            toolchain_dir = tmp_path / "toolchain"
            toolchain_dir.mkdir()
            (toolchain_dir / "6eae1a9f3e.zip").write_text("zip", encoding="utf-8")
            argv = [
                "chromium_native.py",
                "check",
                "--platform",
                "windows-x64",
                "--workdir",
                str(workdir),
                "--out-dir",
                "out/TestWindowsX64",
            ]
            stdout = io.StringIO()
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "DEPOT_TOOLS_WIN_TOOLCHAIN_BASE_URL": str(toolchain_dir),
                        "GYP_MSVS_HASH_e66617bc68": "6eae1a9f3e",
                        "DEPOT_TOOLS_WIN_TOOLCHAIN": "1",
                    },
                ),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(chromium_native, "host_os_name", return_value="darwin"),
                mock.patch("sys.stdout", stdout),
            ):
                chromium_native.main()

        status = json.loads(stdout.getvalue())["status"]
        self.assertIs(status["host_supported"], True)
        self.assertEqual("darwin_windows_cross_compile", status["host_support_mode"])
        self.assertIs(status["windows_cross_compile_supported"], True)
        self.assertIs(status["windows_toolchain_zip_exists"], True)
        self.assertIs(status["gclient_target_os_win"], True)
        self.assertIs(status["native_toolchain_ready"], True)

    def test_preflight_generates_supported_platform_manifest_without_platform_arg(self) -> None:
        """Native preflight emits a full supported-platform manifest from runtime artifacts and native checks."""
        command_line_tools_error = (
            "xcode-select: error: tool 'xcodebuild' requires Xcode, but active developer directory "
            "'/Library/Developer/CommandLineTools' is a command line tools instance\n"
        )

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(("xcodebuild", ["-version"]), (Path(command[0]).name, command[1:]))
            return subprocess.CompletedProcess(command, 1, stdout="", stderr=command_line_tools_error)

        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            runtime_root = tmp_path / "runtime"
            manifests = runtime_root / "knowledge" / "manifests"
            manifests.mkdir(parents=True)
            artifact_id = f"browseforge-runtime-chromium-{chromium_native.RUNTIME_VERSION}-linux-x64"
            (runtime_root / "dist").mkdir()
            (runtime_root / "dist" / f"{artifact_id}.zip").write_text("zip", encoding="utf-8")
            (manifests / "linux-package-smoke.json").write_text("{}", encoding="utf-8")
            detector_path = runtime_root / "detectors" / "evidence" / "linux-smoke.json"
            detector_path.parent.mkdir(parents=True)
            detector_path.write_text("{}", encoding="utf-8")
            (manifests / "runtime-artifacts.json").write_text(
                json.dumps(
                    {
                        "detector_smoke_evidence": "detectors/evidence/linux-smoke.json",
                        "supported_package_platforms": ["linux-x64", "macos-arm64", "windows-x64"],
                        "artifacts": [
                            {
                                "artifact_id": artifact_id,
                                "platform": "linux-x64",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            workdir = tmp_path / "chromium"
            self._write_native_checkout_fixtures(workdir)
            stdout = io.StringIO()
            argv = [
                "chromium_native.py",
                "preflight",
                "--workdir",
                str(workdir),
                "--generated-at",
                "2026-07-10T00:00:00Z",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(chromium_native, "ROOT", runtime_root),
                mock.patch.object(chromium_native, "host_os_name", return_value="darwin"),
                mock.patch.object(chromium_native.shutil, "which", side_effect=lambda name: "/usr/bin/xcodebuild" if name == "xcodebuild" else None),
                mock.patch.object(chromium_native.subprocess, "run", side_effect=fake_run),
                mock.patch("sys.stdout", stdout),
            ):
                chromium_native.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual("2026-07-10T00:00:00Z", payload["generated_at"])
        self.assertIs(payload["release_grade_ready"], False)
        self.assertEqual(["linux-x64", "macos-arm64", "windows-x64"], payload["supported_package_platforms"])
        entries = {entry["platform"]: entry for entry in payload["platforms"]}
        self.assertIs(entries["linux-x64"]["ready"], True)
        self.assertEqual(artifact_id, entries["linux-x64"]["artifact_id"])
        self.assertIs(entries["macos-arm64"]["ready"], False)
        self.assertIn(
            "full Xcode selected via xcode-select so Chromium macOS GN generation can read the macosx SDK",
            entries["macos-arm64"]["missing_prerequisites"],
        )
        self.assertIs(entries["windows-x64"]["ready"], False)
        self.assertIn(
            "Windows host/toolchain selected so Chromium Windows GN generation and native chrome.exe packaging can run",
            entries["windows-x64"]["missing_prerequisites"],
        )
        macos_snapshot = entries["macos-arm64"]["status_snapshot"]
        self.assertIs(macos_snapshot["host_supported"], True)
        self.assertIs(macos_snapshot["native_toolchain_ready"], False)
        self.assertIs(macos_snapshot["package_zip_exists"], False)
        self.assertEqual("failed", macos_snapshot["xcodebuild_status"])
        self.assertIs(macos_snapshot["app_bundle_exists"], False)
        windows_snapshot = entries["windows-x64"]["status_snapshot"]
        self.assertIs(windows_snapshot["host_supported"], False)
        self.assertEqual("windows", windows_snapshot["required_host_os"])
        self.assertIs(windows_snapshot["portable_layout_exists"], False)
        windows_commands = entries["windows-x64"]["next_commands"]
        self.assertTrue(any("sync-deps" in command and "--execute" in command for command in windows_commands))
        self.assertTrue(any("--platform windows-x64" in command for command in windows_commands))
        self.assertTrue(any("GOOS=windows GOARCH=amd64 go build" in command for command in windows_commands))
        self.assertTrue(any("build-chrome" in command and "--execute" in command for command in windows_commands))
        self.assertTrue(any("package" in command and "--execute" in command for command in windows_commands))



    def test_preflight_execute_writes_manifest(self) -> None:
        """The preflight command writes native-artifact-preflight.json only when --execute is explicit."""
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            runtime_root = tmp_path / "runtime"
            manifests = runtime_root / "knowledge" / "manifests"
            manifests.mkdir(parents=True)
            (manifests / "runtime-artifacts.json").write_text(
                json.dumps({"supported_package_platforms": ["linux-x64", "macos-arm64", "windows-x64"], "artifacts": []}),
                encoding="utf-8",
            )
            output = tmp_path / "native-artifact-preflight.json"
            argv = [
                "chromium_native.py",
                "preflight",
                "--workdir",
                str(tmp_path / "chromium"),
                "--generated-at",
                "2026-07-10T00:00:00Z",
                "--output",
                str(output),
                "--execute",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(chromium_native, "ROOT", runtime_root),
                mock.patch.object(chromium_native, "host_os_name", return_value="darwin"),
                mock.patch.object(chromium_native.shutil, "which", return_value=None),
                mock.patch("sys.stdout", io.StringIO()) as stdout,
            ):
                chromium_native.main()

            self.assertEqual(str(output), stdout.getvalue().strip())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("browseforge-chromium", payload["runtime_id"])
            self.assertIs(payload["release_grade_ready"], False)


if __name__ == "__main__":
    unittest.main()
