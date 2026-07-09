from __future__ import annotations

import importlib.util
import io
import json
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
    def _run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def _json_from_script(self, *args: str) -> dict:
        completed = self._run_script(*args)
        self.assertEqual(0, completed.returncode, completed.stderr + completed.stdout)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - keeps failures readable.
            self.fail(f"command did not emit JSON: {exc}: {completed.stdout!r}")
        self.assertIsInstance(payload, dict)
        return payload

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
        self.assertEqual("macos-arm64", package_command[package_command.index("--platform") + 1])
        self.assertEqual("macos-arm64", payload["commands"]["package"][package_command.index("--platform") + 1])

    def test_windows_plan_targets_x64_chrome_exe_and_windows_host(self) -> None:
        """The Windows native plan cross-targets win/x64 but declares that execution requires Windows."""
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


if __name__ == "__main__":
    unittest.main()
