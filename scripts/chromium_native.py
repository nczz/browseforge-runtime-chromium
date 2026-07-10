#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import datetime as dt
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


def platform_contract(platform_id: str) -> tuple[str, str, str, str]:
    if platform_id == "macos-arm64":
        return (
            "darwin",
            "out/BrowseForgeMacArm64",
            'target_os="mac" target_cpu="arm64" is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false',
            "Chromium.app/Contents/MacOS/Chromium",
        )
    if platform_id == "windows-x64":
        return (
            "windows",
            "out/BrowseForgeWindowsX64",
            'target_os="win" target_cpu="x64" is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false',
            "chrome.exe",
        )
    supported = ", ".join(sorted(SUPPORTED_NATIVE_PLATFORMS))
    raise SystemExit(f"unsupported native platform {platform_id}; supported: {supported}")


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


def build_plan(platform_id: str, workdir: Path = DEFAULT_WORKDIR, out_dir: str | None = None, jobs: int = DEFAULT_JOBS) -> NativeBuildPlan:
    required_host, default_out, gn_args, output_rel = platform_contract(platform_id)
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
    depot_tools = workdir / "depot_tools"
    gn_binary = depot_tools / ("gn.bat" if platform_id == "windows-x64" else "gn")
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
            "gn-gen": ["bash", "-lc", f"{run_env} gn gen {selected_out} --args='{gn_args}'"],
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
    gn_path = Path(plan.depot_tools_dir) / ("gn.bat" if plan.platform_id == "windows-x64" else "gn")
    depot_tools_exists = Path(plan.depot_tools_dir).is_dir()
    gn_binary_exists = gn_path.is_file()
    autoninja = str(Path(plan.depot_tools_dir) / "autoninja") if (Path(plan.depot_tools_dir) / "autoninja").is_file() else shutil.which("autoninja")
    gclient = str(Path(plan.depot_tools_dir) / "gclient") if (Path(plan.depot_tools_dir) / "gclient").is_file() else shutil.which("gclient")
    status = {
        "host_os": plan.host_os,
        "required_host_os": plan.required_host_os,
        "host_supported": plan.host_os == plan.required_host_os,
        "chromium_src_exists": src.is_dir(),
        "chromium_deps_exists": (src / "DEPS").is_file(),
        "gn_binary": str(gn_path),
        "gn_binary_exists": gn_binary_exists,
        "depot_tools_dir": plan.depot_tools_dir,
        "depot_tools_exists": depot_tools_exists,
        "autoninja": autoninja,
        "gclient": gclient,
        "out_args_exists": (src / plan.out_dir / "args.gn").is_file(),
        "build_ninja_exists": (src / plan.out_dir / "build.ninja").is_file(),
        "output_binary": plan.output_binary,
        "output_binary_exists": output.is_file(),
        "package_artifact_id": plan.package_artifact_id,
        "package_zip": str(ROOT / "dist" / f"{plan.package_artifact_id}.zip"),
        "package_zip_exists": (ROOT / "dist" / f"{plan.package_artifact_id}.zip").is_file(),
    }
    toolchain_ready = bool(
        status["host_supported"]
        and status["chromium_src_exists"]
        and status["chromium_deps_exists"]
        and depot_tools_exists
        and gn_binary_exists
        and gclient
        and autoninja
    )
    if plan.platform_id == "macos-arm64":
        xcode_status = macos_xcode_status()
        status.update(xcode_status)
        toolchain_ready = toolchain_ready and bool(xcode_status["xcodebuild_ok"])
    status["native_toolchain_ready"] = toolchain_ready
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


def native_toolchain_error(command: str, status: dict[str, object]) -> str:
    details = []
    for key in (
        "xcodebuild_status",
        "xcodebuild_error",
        "gn_binary_exists",
        "depot_tools_exists",
        "chromium_src_exists",
        "chromium_deps_exists",
    ):
        if key in status:
            details.append(f"{key}={status[key]}")
    suffix = "; ".join(details)
    if suffix:
        suffix = f": {suffix}"
    return f"{command} native toolchain is not ready{suffix}"


def missing_command_preconditions(command: str, status: dict[str, object]) -> list[str]:
    missing: list[str] = []
    if command == "build-chrome" and not status["build_ninja_exists"]:
        missing.append("build_ninja_exists=False")
    if command == "package":
        if not status["output_binary_exists"]:
            missing.append("output_binary_exists=False")
        if "app_bundle_exists" in status and not status["app_bundle_exists"]:
            missing.append("app_bundle_exists=False")
        if "portable_layout_exists" in status and not status["portable_layout_exists"]:
            missing.append("portable_layout_exists=False")
    return missing


def command_precondition_error(command: str, missing: list[str]) -> str:
    return f"{command} preconditions are not satisfied: {'; '.join(missing)}"

def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def generated_at_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def linux_preflight_entry(root: Path, runtime_artifacts: dict[str, object]) -> dict[str, object]:
    artifacts = runtime_artifacts.get("artifacts", [])
    artifact = next((item for item in artifacts if isinstance(item, dict) and item.get("platform") == "linux-x64"), None)
    evidence = ["knowledge/manifests/runtime-artifacts.json"]
    missing: list[str] = []
    artifact_id = None
    if artifact is None:
        missing.append("committed linux-x64 runtime artifact manifest entry")
    else:
        artifact_id = str(artifact.get("artifact_id"))
        archive = root / "dist" / f"{artifact_id}.zip"
        evidence.append(f"dist/{artifact_id}.zip")
        if not archive.is_file():
            missing.append(f"dist/{artifact_id}.zip")
    linux_smoke = root / "knowledge" / "manifests" / "linux-package-smoke.json"
    if linux_smoke.is_file():
        evidence.append("knowledge/manifests/linux-package-smoke.json")
    else:
        missing.append("knowledge/manifests/linux-package-smoke.json")
    detector_smoke = runtime_artifacts.get("detector_smoke_evidence")
    if isinstance(detector_smoke, str) and detector_smoke:
        evidence.append(detector_smoke)
        if not (root / detector_smoke).is_file():
            missing.append(detector_smoke)
    else:
        missing.append("packaged linux-x64 detector evidence")
    entry: dict[str, object] = {
        "evidence": evidence,
        "platform": "linux-x64",
        "ready": not missing,
        "status": "packaged_detector_tested" if not missing else "missing_linux_artifact_evidence",
        "missing_prerequisites": missing,
    }
    if artifact_id is not None:
        entry["artifact_id"] = artifact_id
    return entry


def native_status_evidence(platform_id: str, status: dict[str, object]) -> str:
    parts = [
        f"host_supported={status.get('host_supported')}",
        f"native_toolchain_ready={status.get('native_toolchain_ready')}",
        f"build_ninja_exists={status.get('build_ninja_exists')}",
        f"output_binary_exists={status.get('output_binary_exists')}",
        f"package_zip_exists={status.get('package_zip_exists')}",
    ]
    if platform_id == "macos-arm64":
        parts.append(f"xcodebuild_ok={status.get('xcodebuild_ok')}")
    if platform_id == "windows-x64":
        parts.append(f"portable_layout_exists={status.get('portable_layout_exists')}")
    return f"python3 scripts/chromium_native.py check --platform {platform_id}: " + ", ".join(parts)


def platform_display_name(platform_id: str) -> str:
    if platform_id == "macos-arm64":
        return "macOS"
    if platform_id == "windows-x64":
        return "Windows"
    return platform_id


def native_preflight_entry(platform_id: str, status: dict[str, object]) -> dict[str, object]:
    missing: list[str] = []
    if not status["package_zip_exists"]:
        missing.append(f"dist/browseforge-runtime-chromium-{RUNTIME_VERSION}-{platform_id}.zip")
    if not status["host_supported"]:
        missing.append(
            "Windows host/toolchain selected so Chromium Windows GN generation and native chrome.exe packaging can run"
            if platform_id == "windows-x64"
            else f"{platform_id} host/toolchain selected so native Chromium packaging can run"
        )
    elif platform_id == "macos-arm64" and not status.get("xcodebuild_ok"):
        missing.append("full Xcode selected via xcode-select so Chromium macOS GN generation can read the macosx SDK")
    elif not status["native_toolchain_ready"]:
        missing.append(f"{platform_id} native Chromium toolchain ready")
    if platform_id == "macos-arm64" and not status.get("app_bundle_exists"):
        missing.append("BrowseForge Chromium .app bundle built from refs/tags/150.0.7871.101")
    if platform_id == "windows-x64" and not status.get("portable_layout_exists"):
        missing.append("BrowseForge Chromium portable chrome.exe/DLL runtime built from refs/tags/150.0.7871.101")
    if not status["package_zip_exists"]:
        missing.append(f"native {platform_display_name(platform_id)} detector evidence for the packaged artifact")
    entry: dict[str, object] = {
        "evidence": [
            "knowledge/manifests/platform-matrix.json",
            "contracts/browseforge-integration.contract.json",
            "knowledge/manifests/signing-policy.json",
            native_status_evidence(platform_id, status),
        ],
        "platform": platform_id,
        "ready": not missing,
        "status": "packaged_detector_tested" if not missing else "missing_native_release_artifact",
        "missing_prerequisites": missing,
    }
    if status["package_zip_exists"]:
        entry["artifact_id"] = status["package_artifact_id"]
    return entry


def native_artifact_preflight_manifest(root: Path, workdir: Path, generated_at: str | None = None, jobs: int = DEFAULT_JOBS) -> dict[str, object]:
    runtime_artifacts = load_json(root / "knowledge" / "manifests" / "runtime-artifacts.json")
    supported = list(runtime_artifacts.get("supported_package_platforms", []))
    entries = []
    if "linux-x64" in supported:
        entries.append(linux_preflight_entry(root, runtime_artifacts))
    for platform_id in sorted(set(SUPPORTED_NATIVE_PLATFORMS).intersection(supported)):
        entries.append(native_preflight_entry(platform_id, check(build_plan(platform_id, workdir, None, jobs))))
    return {
        "generated_at": generated_at or generated_at_utc(),
        "release_grade_ready": all(bool(entry.get("ready")) for entry in entries),
        "requirements": [
            "every supported package platform has a committed runtime artifact manifest entry",
            "every supported package platform artifact has sha256 and size metadata",
            "macOS artifacts are BrowseForge Chromium .app bundles built from the selected source ref, not host Chrome dogfood binaries",
            "Windows artifacts are BrowseForge Chromium portable executable/DLL layouts built from the selected source ref",
            "native platform artifacts have detector evidence before release_grade can pass",
        ],
        "runtime_id": "browseforge-chromium",
        "schema_version": "1.0",
        "platforms": entries,
        "supported_package_platforms": supported,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="BrowseForge Chromium native build helper")
    parser.add_argument("command", choices=["plan", "check", "preflight", "run-hooks", "gn-gen", "build-chrome", "package"])
    parser.add_argument("--platform", choices=sorted(SUPPORTED_NATIVE_PLATFORMS))
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    parser.add_argument("--out-dir")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    parser.add_argument("--output", type=Path, default=ROOT / "knowledge" / "manifests" / "native-artifact-preflight.json")
    parser.add_argument("--generated-at")
    parser.add_argument("--execute", action="store_true", help="required for commands that mutate the checkout or package artifacts")
    args = parser.parse_args()

    if args.command == "preflight":
        payload = native_artifact_preflight_manifest(ROOT, args.workdir, args.generated_at, args.jobs)
        if args.execute:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(args.output)
        else:
            emit_json(payload)
        return
    if args.platform is None:
        raise SystemExit(f"{args.command} requires --platform")

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
    if args.command in {"gn-gen", "build-chrome"} and not status["native_toolchain_ready"]:
        raise SystemExit(native_toolchain_error(args.command, status))
    missing = missing_command_preconditions(args.command, status)
    if missing:
        raise SystemExit(command_precondition_error(args.command, missing))
    run_command(plan.commands[args.command], Path(plan.chromium_src_dir))


if __name__ == "__main__":
    main()
