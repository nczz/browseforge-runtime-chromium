#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
LINUX_WORKDIR_ENV = "BROWSEFORGE_CHROMIUM_LINUX_WORKDIR"
SHARED_WORKDIR_ENV = "BROWSEFORGE_CHROMIUM_WORKDIR"
DEFAULT_SHARED_WORKDIR = "/Users/chun/Projects/browser-source/browseforge-chromium"
DEFAULT_IMAGE = os.environ.get("BROWSEFORGE_CHROMIUM_BUILD_IMAGE", "browseforge/chromium-build:ubuntu22")
DEFAULT_OUT = os.environ.get("BROWSEFORGE_CHROMIUM_DOCKER_OUT", "out/BrowseForgeLinuxDocker")
DEFAULT_GIT_CACHE = Path(os.environ.get("GIT_CACHE_PATH", "/Users/chun/Projects/browser-source/git-cache"))


def default_workdir() -> Path:
    return Path(os.environ.get(LINUX_WORKDIR_ENV) or os.environ.get(SHARED_WORKDIR_ENV, DEFAULT_SHARED_WORKDIR))


DEFAULT_WORKDIR = default_workdir()
DOCKERFILE = ROOT / "docker" / "chromium-build.Dockerfile"


@dataclass(frozen=True)
class DockerPlan:
    image: str
    deps_image: str
    workdir: str
    chromium_src_dir: str
    git_cache_dir: str
    dockerfile: str
    platform: str
    out_dir: str
    gn_args: str
    output_binary: str
    jobs: int
    commands: dict[str, list[str]]


def dependency_image(image: str) -> str:
    image_name, sep, tag = image.rpartition(":")
    if sep and "/" not in tag:
        return f"{image_name}:{tag}-deps"
    return f"{image}:deps"


def docker_run_base(workdir: Path, git_cache: Path, image: str, platform: str, *, remove: bool = True, name: str | None = None) -> list[str]:
    container_path = "/opt/depot_tools:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    command = ["docker", "run"]
    if remove:
        command.append("--rm")
    if name is not None:
        command.extend(["--name", name])
    command.extend(
        [
            "--platform",
            platform,
            "-e",
            f"PATH={container_path}",
            "-e",
            "DEPOT_TOOLS_UPDATE=0",
            "-e",
            "AI_AGENT=1",
            "-v",
            f"{workdir}:/work/chromium",
            "-v",
            f"{git_cache}:{git_cache}",
            "-v",
            f"{ROOT}:/work/runtime:ro",
            "-w",
            "/work/chromium/src",
            image,
        ]
    )
    return command


def build_plan(
    workdir: Path = DEFAULT_WORKDIR,
    image: str = DEFAULT_IMAGE,
    git_cache: Path = DEFAULT_GIT_CACHE,
    platform: str = "linux/amd64",
    out_dir: str = DEFAULT_OUT,
    jobs: int = 4,
) -> DockerPlan:
    src = workdir / "src"
    deps_image = dependency_image(image)
    deps_container = "browseforge-chromium-build-deps"
    gn_args = " ".join(
        [
            'target_os="linux"',
            'target_cpu="x64"',
            "is_debug=false",
            "symbol_level=1",
            "is_component_build=false",
            "use_remoteexec=false",
            "proprietary_codecs=true",
            'ffmpeg_branding="Chrome"',
        ]
    )
    base_run = docker_run_base(workdir, git_cache, image, platform)
    deps_run = docker_run_base(workdir, git_cache, deps_image, platform)
    install_run = docker_run_base(workdir, git_cache, image, platform, remove=False, name=deps_container)
    install_script = (
        f"set -e; docker rm -f {deps_container} >/dev/null 2>&1 || true; "
        + " ".join(install_run)
        + " bash -lc './build/install-build-deps.sh --no-prompt --no-chromeos-fonts'; "
        + f"docker commit {deps_container} {deps_image}; "
        + f"docker rm {deps_container}"
    )
    return DockerPlan(
        image=image,
        deps_image=deps_image,
        workdir=str(workdir),
        chromium_src_dir=str(src),
        git_cache_dir=str(git_cache),
        dockerfile=str(DOCKERFILE),
        platform=platform,
        out_dir=out_dir,
        gn_args=gn_args,
        output_binary=str(src / out_dir / "chrome"),
        jobs=jobs,
        commands={
            "build-image": ["docker", "build", "--platform", platform, "-f", str(DOCKERFILE), "-t", image, str(ROOT)],
            "check-container": base_run + ["bash", "-lc", "python3 --version && git --version && gclient help >/dev/null && test -f DEPS"],
            "sync-linux-deps": base_run + ["bash", "-lc", "cd /work/chromium && gclient sync --nohooks --with_branch_heads --with_tags"],
            "install-linux-deps": ["bash", "-lc", install_script],
            "run-hooks": deps_run + ["bash", "-lc", "/opt/depot_tools/ensure_bootstrap && cd /work/chromium && gclient runhooks"],
            "gn-gen": deps_run + ["bash", "-lc", f"./buildtools/linux64/gn gen {out_dir} --args='{gn_args}'"],
            "build-chrome": deps_run + ["bash", "-lc", f"/opt/depot_tools/ensure_bootstrap && autoninja -j{jobs} -C {out_dir} chrome"],
        },
    )


def docker_image_exists(image: str) -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def check(plan: DockerPlan) -> dict[str, object]:
    return {
        "linux_gn_exists": (Path(plan.chromium_src_dir) / "buildtools" / "linux64" / "gn").is_file(),
        "docker": shutil.which("docker"),
        "deps_image_exists": docker_image_exists(plan.deps_image),
        "dockerfile_exists": Path(plan.dockerfile).is_file(),
        "chromium_src_exists": Path(plan.chromium_src_dir).is_dir(),
        "chromium_deps_exists": (Path(plan.chromium_src_dir) / "DEPS").is_file(),
        "out_args_exists": (Path(plan.chromium_src_dir) / plan.out_dir / "args.gn").is_file(),
        "output_binary": plan.output_binary,
        "output_binary_exists": Path(plan.output_binary).is_file(),
    }


def emit_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_command(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="BrowseForge Chromium Linux/Docker build helper")
    parser.add_argument("command", choices=["plan", "check", "build-image", "check-container", "sync-linux-deps", "install-linux-deps", "run-hooks", "gn-gen", "build-chrome"])
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--git-cache", type=Path, default=DEFAULT_GIT_CACHE)
    parser.add_argument("--platform", default="linux/amd64")
    parser.add_argument("--out-dir", default=DEFAULT_OUT)
    parser.add_argument("--jobs", type=int, default=4, help="local compile jobs for build-chrome")
    parser.add_argument("--execute", action="store_true", help="required for commands that run Docker")
    args = parser.parse_args()

    plan = build_plan(args.workdir, args.image, args.git_cache, args.platform, args.out_dir, args.jobs)
    if args.command == "plan":
        emit_json(asdict(plan))
        return
    if args.command == "check":
        emit_json({"plan": asdict(plan), "status": check(plan)})
        return
    if not args.execute:
        raise SystemExit(f"{args.command} requires --execute")
    run_command(plan.commands[args.command])


if __name__ == "__main__":
    main()
