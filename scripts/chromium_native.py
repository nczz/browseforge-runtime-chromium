#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKDIR = Path(os.environ.get("BROWSEFORGE_CHROMIUM_WORKDIR", "/Users/chun/Projects/browser-source/browseforge-chromium"))
DEFAULT_JOBS = int(os.environ.get("BROWSEFORGE_CHROMIUM_NATIVE_JOBS", "4"))
RUNTIME_VERSION = "v0.1.0-alpha.0"
SUPPORTED_NATIVE_PLATFORMS = {"macos-arm64", "windows-x64"}


@dataclass(frozen=True)
class NativeBuildPlan:
    runtime_id: str
    runtime_version: str
    platform_id: str
    required_host_os: str
    host_os: str
    workdir: str
    chromium_src_dir: str
    depot_tools_dir: str
    path_prefix: str
    out_dir: str
    gn_args: str
    output_binary: str
    package_artifact_id: str
    package_command: list[str]
    commands: dict[str, list[str]]


def host_os_name() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith(("win32", "cygwin", "msys")):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def platform_contract(platform_id: str) -> tuple[str, str, str, str, str]:
    if platform_id == "macos-arm64":
        return (
            "darwin",
            "out/BrowseForgeMacArm64",
            'target_os="mac" target_cpu="arm64" is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false',
            "Chromium.app/Contents/MacOS/Chromium",
            "buildtools/mac/gn",
        )
    if platform_id == "windows-x64":
        return (
            "windows",
            "out/BrowseForgeWindowsX64",
            'target_os="win" target_cpu="x64" is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false',
            "chrome.exe",
            "buildtools/win/gn.exe",
        )
    supported = ", ".join(sorted(SUPPORTED_NATIVE_PLATFORMS))
    raise SystemExit(f"unsupported native platform {platform_id}; supported: {supported}")


def build_plan(platform_id: str, workdir: Path = DEFAULT_WORKDIR, out_dir: str | None = None, jobs: int = DEFAULT_JOBS) -> NativeBuildPlan:
    required_host, default_out, gn_args, output_rel, gn_rel = platform_contract(platform_id)
    selected_out = out_dir or default_out
    src = workdir / "src"
    output_binary = src / selected_out / output_rel
    wrapper_binary = ROOT / "bin" / ("browseforge-runtime-chromium.exe" if platform_id == "windows-x64" else "browseforge-runtime-chromium")
    artifact_id = f"browseforge-runtime-chromium-{RUNTIME_VERSION}-{platform_id}"
    package_command = [
        sys.executable,
        str(ROOT / "build" / "package_runtime.py"),
        "--platform",
        platform_id,
        "--browser-binary",
        str(output_binary),
        "--wrapper-binary",
        str(wrapper_binary),
        "--runtime-version",
        RUNTIME_VERSION,
        "--source-ref",
        "51b83660c3609f271ccbbd65785bf7e50a21312d",
        "--browser-version",
        "150.0.7871.101",
        "--source-acquisition-manifest",
        str(ROOT / "knowledge" / "manifests" / "source-acquisition.json"),
        "--patchset-manifest",
        str(ROOT / "knowledge" / "manifests" / "patchset.json"),
    ]
    gn_binary = src / gn_rel
    depot_tools = workdir / "depot_tools"
    path_prefix = f"{depot_tools}:$PATH"
    run_env = f"PATH={path_prefix} DEPOT_TOOLS_UPDATE=0"
    return NativeBuildPlan(
        runtime_id="browseforge-chromium",
        runtime_version=RUNTIME_VERSION,
        platform_id=platform_id,
        required_host_os=required_host,
        host_os=host_os_name(),
        workdir=str(workdir),
        chromium_src_dir=str(src),
        depot_tools_dir=str(depot_tools),
        path_prefix=path_prefix,
        out_dir=selected_out,
        gn_args=gn_args,
        output_binary=str(output_binary),
        package_artifact_id=artifact_id,
        package_command=package_command,
        commands={
            "run-hooks": ["bash", "-lc", f"{run_env} gclient runhooks"],
            "gn-gen": [str(gn_binary), "gen", selected_out, f"--args={gn_args}"],
            "build-chrome": ["bash", "-lc", f"{run_env} autoninja -j{jobs} -C {selected_out} chrome"],
            "package": package_command + ["--execute"],
        },
    )


def check(plan: NativeBuildPlan) -> dict[str, object]:
    src = Path(plan.chromium_src_dir)
    output = Path(plan.output_binary)
    app_bundle = None
    if plan.platform_id == "macos-arm64":
        app_bundle = str(output.parents[2])
    status = {
        "host_os": plan.host_os,
        "required_host_os": plan.required_host_os,
        "host_supported": plan.host_os == plan.required_host_os,
        "chromium_src_exists": src.is_dir(),
        "chromium_deps_exists": (src / "DEPS").is_file(),
        "gn_binary": plan.commands["gn-gen"][0],
        "gn_binary_exists": Path(plan.commands["gn-gen"][0]).is_file(),
        "depot_tools_dir": plan.depot_tools_dir,
        "depot_tools_exists": Path(plan.depot_tools_dir).is_dir(),
        "autoninja": str(Path(plan.depot_tools_dir) / "autoninja") if (Path(plan.depot_tools_dir) / "autoninja").is_file() else shutil.which("autoninja"),
        "gclient": str(Path(plan.depot_tools_dir) / "gclient") if (Path(plan.depot_tools_dir) / "gclient").is_file() else shutil.which("gclient"),
        "out_args_exists": (src / plan.out_dir / "args.gn").is_file(),
        "output_binary": plan.output_binary,
        "output_binary_exists": output.is_file(),
        "package_artifact_id": plan.package_artifact_id,
        "package_zip": str(ROOT / "dist" / f"{plan.package_artifact_id}.zip"),
        "package_zip_exists": (ROOT / "dist" / f"{plan.package_artifact_id}.zip").is_file(),
    }
    if app_bundle is not None:
        status["app_bundle"] = app_bundle
        status["app_bundle_exists"] = Path(app_bundle).is_dir()
    if plan.platform_id == "windows-x64":
        status["portable_layout_dir"] = str(output.parent)
        status["portable_layout_exists"] = output.parent.is_dir()
    return status


def emit_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_command(command: Sequence[str], cwd: Path) -> None:
    subprocess.run(list(command), cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="BrowseForge Chromium native build helper")
    parser.add_argument("command", choices=["plan", "check", "run-hooks", "gn-gen", "build-chrome", "package"])
    parser.add_argument("--platform", choices=sorted(SUPPORTED_NATIVE_PLATFORMS), required=True)
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    parser.add_argument("--out-dir")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    parser.add_argument("--execute", action="store_true", help="required for commands that mutate the checkout or package artifacts")
    args = parser.parse_args()

    plan = build_plan(args.platform, args.workdir, args.out_dir, args.jobs)
    if args.command == "plan":
        emit_json(asdict(plan))
        return
    if args.command == "check":
        emit_json({"plan": asdict(plan), "status": check(plan)})
        return
    if not args.execute:
        raise SystemExit(f"{args.command} requires --execute")
    status = check(plan)
    if not status["host_supported"]:
        raise SystemExit(f"{args.command} for {plan.platform_id} requires host_os={plan.required_host_os}; current host_os={plan.host_os}")
    run_command(plan.commands[args.command], Path(plan.chromium_src_dir))


if __name__ == "__main__":
    main()
