#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import shlex
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
LINUX_WORKDIR_ENV = "BROWSEFORGE_CHROMIUM_LINUX_WORKDIR"
SHARED_WORKDIR_ENV = "BROWSEFORGE_CHROMIUM_WORKDIR"
DEFAULT_SHARED_WORKDIR = "/Users/chun/Projects/browser-source/browseforge-chromium"
DEFAULT_IMAGE = os.environ.get("BROWSEFORGE_CHROMIUM_BUILD_IMAGE", "browseforge/chromium-build:ubuntu22")
DEFAULT_OUT_BY_RUNTIME_PLATFORM = {
    "linux-x64": os.environ.get("BROWSEFORGE_CHROMIUM_DOCKER_OUT", "out/BrowseForgeLinuxDocker"),
    "linux-arm64": os.environ.get("BROWSEFORGE_CHROMIUM_DOCKER_ARM64_OUT", "out/BrowseForgeLinuxArm64Docker"),
}
DEFAULT_GIT_CACHE = Path(os.environ.get("GIT_CACHE_PATH", "/Users/chun/Projects/browser-source/git-cache"))

ARM64_X64_HOST_PACKAGES = (
    "libasound2:amd64",
    "libgbm1:amd64",
    "libglib2.0-0:amd64",
    "libgtk-3-0:amd64",
    "libnss3:amd64",
    "libxss1:amd64",
)

def arm64_x64_host_deps_script() -> str:
    packages = " ".join(ARM64_X64_HOST_PACKAGES)
    return (
        "dpkg --add-architecture amd64; "
        "sed -i 's/^deb /deb [arch=arm64] /' /etc/apt/sources.list; "
        "printf '%s\\n' "
        "'deb [arch=amd64] http://archive.ubuntu.com/ubuntu jammy main universe multiverse restricted' "
        "'deb [arch=amd64] http://archive.ubuntu.com/ubuntu jammy-updates main universe multiverse restricted' "
        "'deb [arch=amd64] http://security.ubuntu.com/ubuntu jammy-security main universe multiverse restricted' "
        "'deb [arch=amd64] http://archive.ubuntu.com/ubuntu jammy-backports main universe multiverse restricted' "
        ">/etc/apt/sources.list.d/amd64.list; "
        "apt-get update; "
        f"apt-get install -y --no-install-recommends {packages}; "
        "rm -rf /var/lib/apt/lists/*"
    )

def default_workdir() -> Path:
    return Path(os.environ.get(LINUX_WORKDIR_ENV) or os.environ.get(SHARED_WORKDIR_ENV, DEFAULT_SHARED_WORKDIR))


DEFAULT_WORKDIR = default_workdir()

def runtime_platform_from_docker_platform(platform: str) -> str:
    normalized = platform.strip().lower()
    if normalized in {"linux/amd64", "linux/x86_64"}:
        return "linux-x64"
    if normalized in {"linux/arm64", "linux/aarch64"}:
        return "linux-arm64"
    raise SystemExit(f"unsupported Linux Docker platform: {platform}")


def docker_platform_for_runtime_platform(runtime_platform: str) -> str:
    if runtime_platform == "linux-x64":
        return "linux/amd64"
    if runtime_platform == "linux-arm64":
        return "linux/arm64"
    raise SystemExit(f"unsupported Linux runtime platform: {runtime_platform}")


def target_cpu_for_runtime_platform(runtime_platform: str) -> str:
    if runtime_platform == "linux-x64":
        return "x64"
    if runtime_platform == "linux-arm64":
        return "arm64"
    raise SystemExit(f"unsupported Linux runtime platform: {runtime_platform}")


def default_out_dir(runtime_platform: str) -> str:
    return DEFAULT_OUT_BY_RUNTIME_PLATFORM[runtime_platform]


def default_image_for_runtime_platform(runtime_platform: str, image: str) -> str:
    if runtime_platform == "linux-arm64" and image == DEFAULT_IMAGE:
        return f"{DEFAULT_IMAGE}-arm64"
    return image
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
    runtime_platform: str
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
    out_dir: str | None = None,
    jobs: int = 4,
    runtime_platform: str | None = None,
) -> DockerPlan:
    runtime_platform = runtime_platform or runtime_platform_from_docker_platform(platform)
    platform = docker_platform_for_runtime_platform(runtime_platform)
    image = default_image_for_runtime_platform(runtime_platform, image)
    out_dir = out_dir or default_out_dir(runtime_platform)
    target_cpu = target_cpu_for_runtime_platform(runtime_platform)
    src = workdir / "src"
    deps_image = dependency_image(image)
    deps_container = "browseforge-chromium-build-deps"
    gn_args = " ".join(
        [
            'target_os="linux"',
            f'target_cpu="{target_cpu}"',
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
    container_install_command = "./build/install-build-deps.sh --no-prompt --no-chromeos-fonts"
    if runtime_platform == "linux-arm64":
        container_install_command = f"{container_install_command}; {arm64_x64_host_deps_script()}"
    install_script = (
        f"set -e; docker rm -f {deps_container} >/dev/null 2>&1 || true; "
        + " ".join(install_run)
        + f" bash -lc {shlex.quote(container_install_command)}; "
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
        runtime_platform=runtime_platform,
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
    parser.add_argument("--platform", default=None, help="Docker platform, e.g. linux/amd64 or linux/arm64")
    parser.add_argument("--runtime-platform", choices=["linux-x64", "linux-arm64"], default=None, help="BrowseForge runtime platform to build")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--jobs", type=int, default=4, help="local compile jobs for build-chrome")
    parser.add_argument("--execute", action="store_true", help="required for commands that run Docker")
    args = parser.parse_args()

    runtime_platform = args.runtime_platform or (runtime_platform_from_docker_platform(args.platform) if args.platform else "linux-x64")
    docker_platform = args.platform or docker_platform_for_runtime_platform(runtime_platform)
    plan = build_plan(args.workdir, args.image, args.git_cache, docker_platform, args.out_dir, args.jobs, runtime_platform)
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
