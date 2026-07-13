from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "package_linux_runtime.py"
RUNTIME_MANIFEST = ROOT / "contracts" / "runtime.manifest.json"
SOURCE_ACQUISITION_MANIFEST = ROOT / "knowledge" / "manifests" / "source-acquisition.json"
PATCHSET_MANIFEST = ROOT / "knowledge" / "manifests" / "patchset.json"


class PackageLinuxRuntimeScriptTests(unittest.TestCase):
    def _run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def _plan(self) -> dict[str, Any]:
        completed = self._run_script("--plan")
        self.assertEqual(0, completed.returncode, completed.stderr + completed.stdout)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - assertion branch keeps failures readable.
            self.fail(f"--plan did not emit JSON: {exc}: {completed.stdout!r}")
        self.assertIsInstance(payload, dict)
        plan = payload.get("plan", payload)
        self.assertIsInstance(plan, dict)
        return plan

    def _manifest_json(self, path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertIsInstance(payload, dict)
        return payload

    def _command_vectors(self, value: Any) -> list[list[str]]:
        vectors: list[list[str]] = []
        if isinstance(value, list):
            if value and all(isinstance(item, str) for item in value):
                vectors.append([str(item) for item in value])
            else:
                for item in value:
                    vectors.extend(self._command_vectors(item))
        elif isinstance(value, dict):
            for item in value.values():
                vectors.extend(self._command_vectors(item))
        return vectors

    def _load_script_module(self) -> Any:
        spec = importlib.util.spec_from_file_location("package_linux_runtime_under_test", SCRIPT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None
        assert spec.loader is not None
        sys.modules["package_linux_runtime_under_test"] = module
        spec.loader.exec_module(module)
        return module

    def test_plan_uses_linux_release_inputs_from_repo_manifests(self) -> None:
        """--plan describes the linux-x64 package inputs resolved from the repo manifests."""
        plan = self._plan()
        runtime_manifest = self._manifest_json(RUNTIME_MANIFEST)
        source_manifest = self._manifest_json(SOURCE_ACQUISITION_MANIFEST)
        patchset_manifest = self._manifest_json(PATCHSET_MANIFEST)

        chromium_base = source_manifest["chromium_base"]
        patchsets = patchset_manifest.get("patchsets", [])
        expected_patchset_id = patchsets[-1]["patchset_id"] if patchsets else "unpatched"

        self.assertEqual("linux-x64", plan["platform"])
        self.assertEqual(runtime_manifest["version"], plan["runtime_version"])
        self.assertEqual(chromium_base["base_version"], plan["browser_version"])
        self.assertEqual(chromium_base["base_commit"], plan["source_ref"])
        self.assertEqual(expected_patchset_id, plan["patchset_id"])

        browser_binary = Path(plan["browser_binary"])
        self.assertEqual(
            Path("/Users/chun/Projects/browser-source/browseforge-chromium/src/out/BrowseForgeLinuxDocker/chrome"),
            browser_binary,
        )
        self.assertEqual("chrome", browser_binary.name)
        self.assertEqual("BrowseForgeLinuxDocker", browser_binary.parent.name)

        wrapper_binary = Path(plan["wrapper_binary"])
        self.assertEqual(ROOT / "dist" / "build" / "browseforge-runtime-chromium-linux-x64", wrapper_binary)
        self.assertEqual(ROOT / "dist", Path(plan["output_dir"]))

    def test_plan_can_target_linux_arm64_runtime(self) -> None:
        completed = self._run_script("--plan", "--platform", "linux-arm64")
        self.assertEqual(0, completed.returncode, completed.stderr + completed.stdout)
        plan = json.loads(completed.stdout)

        self.assertEqual("linux-arm64", plan["platform"])
        self.assertEqual("arm64", plan["goarch"])
        self.assertEqual(
            Path("/Users/chun/Projects/browser-source/browseforge-chromium/src/out/BrowseForgeLinuxArm64Docker/chrome"),
            Path(plan["browser_binary"]),
        )
        self.assertEqual(ROOT / "dist" / "build" / "browseforge-runtime-chromium-linux-arm64", Path(plan["wrapper_binary"]))
        self.assertEqual("linux-arm64", plan["commands"]["package"][plan["commands"]["package"].index("--platform") + 1])

    def test_package_requires_execute_before_touching_build_or_package_steps(self) -> None:
        """The package action is fail-closed unless the caller explicitly passes --execute."""
        completed = self._run_script()

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("requires --execute", completed.stderr + completed.stdout)

    def test_plan_build_commands_and_package_cross_compile_env(self) -> None:
        """The exposed plan and package action build the matching Linux wrapper before packaging."""
        plan_payload = self._plan()
        command_root = plan_payload.get("commands") or plan_payload.get("build_commands") or plan_payload.get("command_list")
        if command_root is None:
            self.skipTest("--plan does not expose build command vectors")

        command_vectors = self._command_vectors(command_root)
        self.assertTrue(command_vectors, "command list exists but contains no argv vectors")
        rendered = [" ".join(command) for command in command_vectors]
        self.assertTrue(any("go build" in command for command in rendered), rendered)
        self.assertTrue(any("package_runtime.py" in command and "package" in command for command in rendered), rendered)

        module = self._load_script_module()
        recorded_commands: list[tuple[list[str], dict[str, str] | None]] = []

        def record_command(command: Any, *, env: dict[str, str] | None = None) -> None:
            recorded_commands.append((list(command), env))

        with tempfile.TemporaryDirectory() as td:
            plan = module.build_plan(
                chromium_src=Path(td) / "chromium" / "src",
                output_dir=Path(td) / "dist",
                runtime_version_value="v-test",
                browser_version_value="150.0.7871.101",
                source_ref_value="51b83660c3609f271ccbbd65785bf7e50a21312d",
                patchset_id_value="surface-font-face-set-native-list-override",
            )
            original_run_command = module.run_command
            try:
                module.run_command = record_command
                module.package(plan)
            finally:
                module.run_command = original_run_command

        self.assertEqual(2, len(recorded_commands))
        wrapper_command, wrapper_env = recorded_commands[0]
        package_command, package_env = recorded_commands[1]
        self.assertEqual(plan.commands["build-wrapper"], wrapper_command)
        self.assertIsNotNone(wrapper_env)
        assert wrapper_env is not None
        self.assertEqual("linux", wrapper_env["GOOS"])
        self.assertEqual("amd64", wrapper_env["GOARCH"])
        self.assertEqual("0", wrapper_env["CGO_ENABLED"])

        arm_plan = module.build_plan(
            chromium_src=Path("/tmp/chromium/src"),
            output_dir=Path("/tmp/dist"),
            runtime_version_value="v-test",
            browser_version_value="150.0.7871.101",
            source_ref_value="51b83660c3609f271ccbbd65785bf7e50a21312d",
            patchset_id_value="surface-font-face-set-native-list-override",
            platform="linux-arm64",
        )
        recorded_commands.clear()
        try:
            module.run_command = record_command
            module.package(arm_plan)
        finally:
            module.run_command = original_run_command
        self.assertEqual("arm64", recorded_commands[0][1]["GOARCH"])
        self.assertIn("linux-arm64", recorded_commands[1][0])
        self.assertEqual(plan.commands["package"], package_command)
        self.assertIsNone(package_env)


if __name__ == "__main__":
    unittest.main()
