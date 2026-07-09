#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHROMIUM_SRC = Path(os.environ.get("BROWSEFORGE_CHROMIUM_SRC", "/Users/chun/Projects/browser-source/browseforge-chromium/src"))
DEFAULT_OUT_DIR = "out/BrowseForgeLinuxDocker"


@dataclass(frozen=True)
class LinuxPackagePlan:
    platform: str
    browser_binary: str
    wrapper_binary: str
    output_dir: str
    runtime_version: str
    browser_version: str
    source_ref: str
    patchset_id: str
    wrapper_version: str
    release_channel: str
    commands: dict[str, list[str]]


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def runtime_version() -> str:
    manifest = load_json(ROOT / "contracts" / "runtime.manifest.json")
    return str(manifest["version"])


def source_base() -> tuple[str, str]:
    manifest = load_json(ROOT / "knowledge" / "manifests" / "source-acquisition.json")
    chromium_base = manifest["chromium_base"]
    return str(chromium_base["base_version"]), str(chromium_base["base_commit"])


def latest_patchset_id() -> str:
    manifest = load_json(ROOT / "knowledge" / "manifests" / "patchset.json")
    patchsets = manifest.get("patchsets", [])
    if not patchsets:
        return "unpatched"
    return str(patchsets[-1]["patchset_id"])


def build_plan(
    chromium_src: Path = DEFAULT_CHROMIUM_SRC,
    chromium_out_dir: str = DEFAULT_OUT_DIR,
    output_dir: Path = ROOT / "dist",
    runtime_version_value: str | None = None,
    browser_version_value: str | None = None,
    source_ref_value: str | None = None,
    patchset_id_value: str | None = None,
    release_channel: str = "dev",
) -> LinuxPackagePlan:
    browser_version_default, source_ref_default = source_base()
    runtime_version_final = runtime_version_value or runtime_version()
    browser_version_final = browser_version_value or browser_version_default
    source_ref_final = source_ref_value or source_ref_default
    patchset_id_final = patchset_id_value or latest_patchset_id()
    wrapper_binary = output_dir / "build" / "browseforge-runtime-chromium-linux-x64"
    browser_binary = chromium_src / chromium_out_dir / "chrome"
    package_command = [
        sys.executable,
        str(ROOT / "build" / "package_runtime.py"),
        "package",
        "--platform",
        "linux-x64",
        "--browser-binary",
        str(browser_binary),
        "--wrapper-binary",
        str(wrapper_binary),
        "--output-dir",
        str(output_dir),
        "--runtime-version",
        runtime_version_final,
        "--browser-version",
        browser_version_final,
        "--source-ref",
        source_ref_final,
        "--patchset-id",
        patchset_id_final,
        "--wrapper-version",
        runtime_version_final,
        "--release-channel",
        release_channel,
    ]
    return LinuxPackagePlan(
        platform="linux-x64",
        browser_binary=str(browser_binary),
        wrapper_binary=str(wrapper_binary),
        output_dir=str(output_dir),
        runtime_version=runtime_version_final,
        browser_version=browser_version_final,
        source_ref=source_ref_final,
        patchset_id=patchset_id_final,
        wrapper_version=runtime_version_final,
        release_channel=release_channel,
        commands={
            "build-wrapper": [
                "go",
                "build",
                "-o",
                str(wrapper_binary),
                "./cmd/browseforge-runtime-chromium",
            ],
            "package": package_command,
        },
    )


def emit_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_command(command: Sequence[str], *, env: dict[str, str] | None = None) -> None:
    command_env = None
    if env is not None:
        command_env = os.environ.copy()
        command_env.update(env)
    subprocess.run(list(command), cwd=ROOT, env=command_env, check=True)


def package(plan: LinuxPackagePlan) -> None:
    Path(plan.wrapper_binary).parent.mkdir(parents=True, exist_ok=True)
    run_command(plan.commands["build-wrapper"], env={"GOOS": "linux", "GOARCH": "amd64", "CGO_ENABLED": "0"})
    run_command(plan.commands["package"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Package BrowseForge Chromium linux-x64 runtime artifacts")
    parser.add_argument("--plan", action="store_true", help="print package plan JSON")
    parser.add_argument("--execute", action="store_true", help="build wrapper and package artifact")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--chromium-out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--runtime-version")
    parser.add_argument("--browser-version")
    parser.add_argument("--source-ref")
    parser.add_argument("--patchset-id")
    parser.add_argument("--release-channel", default="dev")
    args = parser.parse_args()
    plan = build_plan(
        chromium_src=args.chromium_src,
        chromium_out_dir=args.chromium_out_dir,
        output_dir=args.output_dir,
        runtime_version_value=args.runtime_version,
        browser_version_value=args.browser_version,
        source_ref_value=args.source_ref,
        patchset_id_value=args.patchset_id,
        release_channel=args.release_channel,
    )
    if args.plan:
        emit_json(asdict(plan))
        return
    if not args.execute:
        raise SystemExit("package_linux_runtime requires --execute or --plan")
    package(plan)


if __name__ == "__main__":
    main()
