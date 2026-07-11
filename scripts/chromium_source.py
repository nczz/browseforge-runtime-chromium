#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "knowledge" / "manifests" / "source-acquisition.json"
HOST_WORKDIR_ENV = "BROWSEFORGE_CHROMIUM_HOST_WORKDIR"
SHARED_WORKDIR_ENV = "BROWSEFORGE_CHROMIUM_WORKDIR"
DEFAULT_SHARED_WORKDIR = "/Users/chun/Projects/browser-source/browseforge-chromium"
DEFAULT_GIT_CACHE = Path(os.environ.get("GIT_CACHE_PATH", "/Users/chun/Projects/browser-source/git-cache"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build.package_runtime import LINUX_CHROMIUM_RUNTIME_DIRS, LINUX_CHROMIUM_RUNTIME_FILES



def default_workdir() -> Path:
    return Path(os.environ.get(HOST_WORKDIR_ENV) or os.environ.get(SHARED_WORKDIR_ENV, DEFAULT_SHARED_WORKDIR))


DEFAULT_WORKDIR = default_workdir()

PATCH_CHECKS = [
    {
        "patch_id": "scaffold-browseforge-stealth-substrate",
        "surface": "stealth_substrate",
        "script": "scripts/apply_stealth_scaffold.py",
    },
    {
        "patch_id": "surface-webdriver-native-gate",
        "surface": "automation_webdriver",
        "script": "scripts/apply_webdriver_patch.py",
    },
    {
        "patch_id": "surface-hardware-native-overrides",
        "surface": "hardware",
        "script": "scripts/apply_hardware_patch.py",
    },
    {
        "patch_id": "surface-screen-native-overrides",
        "surface": "screen",
        "script": "scripts/apply_screen_patch.py",
    },
    {
        "patch_id": "surface-platform-native-override",
        "surface": "platform",
        "script": "scripts/apply_platform_patch.py",
    },
    {
        "patch_id": "surface-timezone-native-override",
        "surface": "timezone",
        "script": "scripts/apply_timezone_patch.py",
    },
    {
        "patch_id": "surface-locale-native-override",
        "surface": "locale",
        "script": "scripts/apply_locale_patch.py",
    },
    {
        "patch_id": "surface-user-agent-native-overrides",
        "surface": "user_agent",
        "script": "scripts/apply_user_agent_patch.py",
    },
    {
        "patch_id": "surface-storage-quota-native-override",
        "surface": "storage_quota",
        "script": "scripts/apply_storage_quota_patch.py",
    },
    {
        "patch_id": "surface-plugins-pdf-native-override",
        "surface": "plugins_pdf",
        "script": "scripts/apply_plugins_patch.py",
    },
    {
        "patch_id": "surface-webrtc-ice-candidate-native-override",
        "surface": "webrtc",
        "script": "scripts/apply_webrtc_patch.py",
    },
    {
        "patch_id": "surface-audio-native-noise-override",
        "surface": "audio",
        "script": "scripts/apply_audio_patch.py",
    },
    {
        "patch_id": "surface-canvas-native-noise-override",
        "surface": "canvas",
        "script": "scripts/apply_canvas_patch.py",
    },
    {
        "patch_id": "surface-webgl-vendor-renderer-native-override",
        "surface": "webgl",
        "script": "scripts/apply_webgl_patch.py",
    },
    {
        "patch_id": "surface-feature-parity-native-defaults",
        "surface": "permissions_features",
        "script": "scripts/apply_feature_parity_patch.py",
    },
    {
        "patch_id": "surface-font-face-set-native-list-override",
        "surface": "fonts",
        "script": "scripts/apply_fonts_patch.py",
    },
    {
        "patch_id": "surface-process-priority-native-adjustment",
        "surface": "process_priority",
        "script": "scripts/apply_process_priority_patch.py",
    },
    {
        "patch_id": "surface-switch-propagation-native-audit",
        "surface": "switch_propagation",
        "script": "scripts/apply_switch_propagation_patch.py",
    },
]


@dataclass(frozen=True)
class Step:
    id: str
    description: str
    cwd: str
    command: list[str]
    creates: str | None = None


@dataclass(frozen=True)
class SourcePlan:
    runtime_id: str
    base_version: str
    base_ref: str
    base_commit: str
    workdir: str
    depot_tools_dir: str
    chromium_src_dir: str
    git_cache_dir: str
    path_prefix: str
    steps: list[Step]


def load_manifest(path: Path = MANIFEST) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def host_deps_argument() -> str | None:
    if sys.platform == "darwin":
        return "--deps=mac"
    if sys.platform.startswith("win"):
        return "--deps=win"
    return None


def build_plan(workdir: Path = DEFAULT_WORKDIR, git_cache: Path = DEFAULT_GIT_CACHE) -> SourcePlan:
    manifest = load_manifest()
    chromium = manifest["chromium_base"]
    depot_tools = workdir / "depot_tools"
    src = workdir / "src"
    path_prefix = str(depot_tools) + os.pathsep + os.environ.get("PATH", "")
    sync_command = ["gclient", "sync", "--with_branch_heads", "--with_tags"]
    deps_arg = host_deps_argument()
    if deps_arg:
        sync_command.append(deps_arg)
    return SourcePlan(
        runtime_id=manifest["runtime_id"],
        base_version=chromium["base_version"],
        base_ref=chromium["base_ref"],

        base_commit=chromium["base_commit"],
        workdir=str(workdir),
        depot_tools_dir=str(depot_tools),
        chromium_src_dir=str(src),
        git_cache_dir=str(git_cache),
        path_prefix=path_prefix,
        steps=[
            Step(
                id="prepare-workdir",
                description="Create external Chromium workspace outside the runtime repo",
                cwd=str(workdir.parent),
                command=["python3", "-c", f"from pathlib import Path; Path({str(workdir)!r}).mkdir(parents=True, exist_ok=True)"],
                creates=str(workdir),
            ),
            Step(
                id="clone-depot-tools",
                description="Install Chromium depot_tools next to the external source checkout",
                cwd=str(workdir),
                command=["git", "clone", "https://chromium.googlesource.com/chromium/tools/depot_tools.git", str(depot_tools)],
                creates=str(depot_tools / "fetch"),
            ),
            Step(
                id="fetch-chromium",
                description="Fetch Chromium source without hooks before selecting the pinned ref",
                cwd=str(workdir),
                command=["fetch", "--nohooks", "chromium"],
                creates=str(src / ".git"),
            ),
            Step(
                id="checkout-pinned-ref",
                description="Checkout the BrowseForge-selected Chromium M150 ref",
                cwd=str(src),
                command=["git", "checkout", chromium["base_ref"]],
            ),
            Step(
                id="verify-pinned-commit",
                description="Verify the selected ref resolves to the manifest commit",
                cwd=str(src),
                command=["git", "rev-parse", "HEAD"],
            ),
            Step(
                id="sync-deps",
                description="Sync Chromium DEPS for the pinned ref",
                cwd=str(src),
                command=sync_command,
            ),
            Step(
                id="run-hooks",
                description="Run Chromium hooks after DEPS sync",
                cwd=str(src),
                command=["gclient", "runhooks"],
            ),
            Step(
                id="generate-dev-build",
                description="Generate a non-release BrowseForgeDev build directory",
                cwd=str(src),
                command=[
                    "gn",
                    "gen",
                    "out/BrowseForgeDev",
                    "--args=is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false",
                ],
                creates=str(src / "out" / "BrowseForgeDev" / "build.ninja"),
            ),
        ],
    )

def _bounded_message(text: str, *, limit: int = 500) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "…"


def check_patches(plan: SourcePlan, runner=subprocess.run) -> dict:
    chromium_src = Path(plan.chromium_src_dir)
    checks = []
    for patch in PATCH_CHECKS:
        command = [
            sys.executable,
            patch["script"],
            "--chromium-src",
            str(chromium_src),
            "--check",
        ]
        try:
            result = runner(
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            returncode = result.returncode
            message = _bounded_message((result.stdout or "") + " " + (result.stderr or ""))
        except OSError as err:
            returncode = 127
            message = _bounded_message(str(err))
        checks.append(
            {
                "script_path": patch["script"],
                "patch_id": patch["patch_id"],
                "surface": patch["surface"],
                "command": command,
                "ok": returncode == 0,
                "returncode": returncode,
                "message": message,
            }
        )
    return {
        "all_ok": all(check["ok"] for check in checks),
        "checks": checks,
    }

def git_head(src: Path) -> str | None:
    if not (src / ".git").exists():
        return None
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=src,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None

def platform_gn_binary(chromium_src: Path) -> Path:
    if sys.platform == "darwin":
        return chromium_src / "buildtools" / "mac" / "gn"
    if sys.platform.startswith("linux"):
        return chromium_src / "buildtools" / "linux64" / "gn"
    if sys.platform.startswith("win"):
        return chromium_src / "buildtools" / "win" / "gn.exe"
    return chromium_src / "buildtools" / sys.platform / "gn"


def dependency_profile_tools(chromium_src: Path) -> dict[str, bool]:
    return {
        "linux_gn_exists": (chromium_src / "buildtools" / "linux64" / "gn").is_file(),
        "mac_gn_exists": (chromium_src / "buildtools" / "mac" / "gn").is_file(),
        "windows_gn_exists": (chromium_src / "buildtools" / "win" / "gn.exe").is_file(),
    }


def bounded_message(text: str, *, limit: int = 300) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "…"


def macos_xcode_status() -> dict[str, object]:
    xcodebuild = shutil.which("xcodebuild")
    status: dict[str, object] = {
        "xcodebuild": xcodebuild,
        "xcodebuild_ok": False,
    }
    if xcodebuild is None:
        status["xcodebuild_status"] = "missing"
        status["xcodebuild_error"] = "xcodebuild not found"
        return status
    result = subprocess.run(
        ["xcodebuild", "-version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    output = bounded_message((result.stdout or "") + " " + (result.stderr or ""))
    status["xcodebuild_ok"] = result.returncode == 0
    status["xcodebuild_status"] = "ok" if result.returncode == 0 else "failed"
    if output:
        key = "xcodebuild_version" if result.returncode == 0 else "xcodebuild_error"
        status[key] = output
    return status


def host_toolchain_status() -> dict[str, object]:
    if sys.platform == "darwin":
        return macos_xcode_status()
    return {}


def host_toolchain_preflight_error(status: dict[str, object]) -> str | None:
    if sys.platform != "darwin" or status.get("xcodebuild_ok") is True:
        return None
    detail = status.get("xcodebuild_error") or status.get("xcodebuild_status") or "xcodebuild -version failed"
    return (
        "generate-dev-build requires full Xcode before Chromium GN generation; "
        f"xcodebuild is not ready: {detail}"
    )


def check_tools(plan: SourcePlan) -> dict:
    depot_path = plan.path_prefix
    chromium_src = Path(plan.chromium_src_dir)
    head = git_head(chromium_src)
    platform_gn = platform_gn_binary(chromium_src)
    dependency_profiles = dependency_profile_tools(chromium_src)
    status = {
        "fetch": shutil.which("fetch", path=depot_path),
        "gclient": shutil.which("gclient", path=depot_path),
        "gn": shutil.which("gn", path=depot_path),
        "ninja": shutil.which("ninja", path=depot_path),
        "autoninja": shutil.which("autoninja", path=depot_path),
        "chromium_src_exists": chromium_src.is_dir(),
        "chromium_src_head": head,
        "chromium_src_matches_manifest": head == plan.base_commit if head else False,
        "depot_tools_exists": Path(plan.depot_tools_dir).is_dir(),
        "platform_gn_binary": str(platform_gn),
        "platform_gn_exists": platform_gn.is_file(),
        "dependency_profiles": dependency_profiles,
    }
    status.update(host_toolchain_status())
    return status


def check_build_outputs(plan: SourcePlan) -> dict:
    chromium_src = Path(plan.chromium_src_dir)
    linux_out = chromium_src / "out" / "BrowseForgeLinuxDocker"
    outputs = {
        "dev_gn_args": chromium_src / "out" / "BrowseForgeDev" / "args.gn",
        "dev_build_ninja": chromium_src / "out" / "BrowseForgeDev" / "build.ninja",
        "linux_docker_gn_args": linux_out / "args.gn",
        "linux_docker_build_ninja": linux_out / "build.ninja",
        "linux_docker_chrome": linux_out / "chrome",
    }
    status = {
        key: {
            "path": str(path),
            "exists": path.exists(),
        }
        for key, path in outputs.items()
    }
    missing_sidecars = [
        rel
        for rel in LINUX_CHROMIUM_RUNTIME_FILES
        if not (linux_out / rel).is_file()
    ]
    for rel in LINUX_CHROMIUM_RUNTIME_DIRS:
        sidecar_dir = linux_out / rel
        if not sidecar_dir.is_dir() or not any(path.is_file() for path in sidecar_dir.rglob("*")):
            missing_sidecars.append(f"{rel}/")
    status["linux_docker_runtime_sidecars_exist"] = not missing_sidecars
    status["linux_docker_missing_runtime_sidecars"] = missing_sidecars
    return status


def emit_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def preflight_step(plan: SourcePlan, step: Step) -> None:
    if step.id != "generate-dev-build":
        return
    platform_gn = platform_gn_binary(Path(plan.chromium_src_dir))
    if not platform_gn.is_file():
        raise SystemExit(
            "generate-dev-build requires Chromium platform GN at "
            f"{platform_gn}; run sync-deps and run-hooks for this checkout before generating BrowseForgeDev"
        )
    host_error = host_toolchain_preflight_error(host_toolchain_status())
    if host_error is not None:
        raise SystemExit(host_error)

def run_step(step: Step, env: dict[str, str]) -> None:
    Path(step.cwd).mkdir(parents=True, exist_ok=True)
    if step.creates and Path(step.creates).exists():
        return
    subprocess.run(step.command, cwd=step.cwd, env=env, check=True)


def execute(plan: SourcePlan, step_ids: Sequence[str]) -> None:
    selected = {step.id for step in plan.steps} if not step_ids else set(step_ids)
    env = os.environ.copy()
    env["PATH"] = plan.path_prefix
    env["GIT_CACHE_PATH"] = plan.git_cache_dir
    Path(plan.git_cache_dir).mkdir(parents=True, exist_ok=True)
    for step in plan.steps:
        if step.id in selected:
            preflight_step(plan, step)
            run_step(step, env)


def main() -> None:
    parser = argparse.ArgumentParser(description="BrowseForge Chromium source acquisition planner")
    parser.add_argument("command", choices=["plan", "check", "acquire"])
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    parser.add_argument("--git-cache", type=Path, default=DEFAULT_GIT_CACHE)
    parser.add_argument("--execute", action="store_true", help="required for acquire; prevents accidental large downloads")
    parser.add_argument("--step", action="append", default=[], help="acquire only the selected step id; repeatable")
    args = parser.parse_args()

    plan = build_plan(args.workdir, args.git_cache)
    if args.command == "plan":
        emit_json(asdict(plan))
        return
    if args.command == "check":
        emit_json({
            "plan": asdict(plan),
            "tools": check_tools(plan),
            "patches": check_patches(plan),
            "build_outputs": check_build_outputs(plan),
        })
        return
    if not args.execute:
        raise SystemExit("acquire requires --execute because Chromium checkout/build dependencies are large")
    execute(plan, args.step)


if __name__ == "__main__":
    main()
