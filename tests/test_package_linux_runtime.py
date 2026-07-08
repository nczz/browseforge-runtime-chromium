from __future__ import annotations

import json
import subprocess
import sys
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

    def test_package_requires_execute_before_touching_build_or_package_steps(self) -> None:
        """The package action is fail-closed unless the caller explicitly passes --execute."""
        completed = self._run_script()

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("requires --execute", completed.stderr + completed.stdout)

    def test_plan_build_commands_include_linux_wrapper_and_packager_when_exposed(self) -> None:
        """If --plan exposes command vectors, they include the Linux Go build and packager invocation."""
        plan = self._plan()
        command_root = plan.get("commands") or plan.get("build_commands") or plan.get("command_list")
        if command_root is None:
            self.skipTest("--plan does not expose build command vectors")

        command_vectors = self._command_vectors(command_root)
        self.assertTrue(command_vectors, "command list exists but contains no argv vectors")
        rendered = [" ".join(command) for command in command_vectors]

        self.assertTrue(
            any("go build" in command and "GOOS=linux" in command and "GOARCH=amd64" in command for command in rendered),
            rendered,
        )
        self.assertTrue(
            any("package_runtime.py" in command and "package" in command for command in rendered),
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
