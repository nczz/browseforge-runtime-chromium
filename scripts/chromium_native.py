#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import datetime as dt
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
HOST_WORKDIR_ENV = "BROWSEFORGE_CHROMIUM_HOST_WORKDIR"
SHARED_WORKDIR_ENV = "BROWSEFORGE_CHROMIUM_WORKDIR"
DEFAULT_SHARED_WORKDIR = "/Users/chun/Projects/browser-source/browseforge-chromium"
DEFAULT_JOBS = int(os.environ.get("BROWSEFORGE_CHROMIUM_NATIVE_JOBS", "4"))


def default_workdir() -> Path:
    return Path(os.environ.get(HOST_WORKDIR_ENV) or os.environ.get(SHARED_WORKDIR_ENV, DEFAULT_SHARED_WORKDIR))


DEFAULT_WORKDIR = default_workdir()
RUNTIME_VERSION = "v0.1.3-alpha.0"
SUPPORTED_NATIVE_PLATFORMS = {"macos-arm64", "macos-x64", "windows-x64"}
WINDOWS_TOOLCHAIN_BASE_ENV = "DEPOT_TOOLS_WIN_TOOLCHAIN_BASE_URL"
WINDOWS_TOOLCHAIN_ENABLE_ENV = "DEPOT_TOOLS_WIN_TOOLCHAIN"
WINDOWS_TOOLCHAIN_HASH_ENV = "GYP_MSVS_HASH_e66617bc68"
DEFAULT_WINDOWS_TOOLCHAIN_HASH = "6eae1a9f3e"
DEFAULT_WINDOWS_TOOLCHAIN_BASE = Path.home() / "Projects" / "chromium-win-sdk-prep" / "output"
WINDOWS_MANUAL_VALIDATION_NOTE = (
    "Windows compile/runtime verification is delegated to manual validation on a Windows OS host; "
    "local wine/qemu execution is not required for this preflight."
)



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
            'target_os="mac" target_cpu="arm64" is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false proprietary_codecs=true ffmpeg_branding="Chrome"',
            "Chromium.app/Contents/MacOS/Chromium",
        )
    if platform_id == "macos-x64":
        return (
            "darwin",
            "out/BrowseForgeMacX64",
            'target_os="mac" target_cpu="x64" is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false proprietary_codecs=true ffmpeg_branding="Chrome"',
            "Chromium.app/Contents/MacOS/Chromium",
        )
    if platform_id == "windows-x64":
        return (
            "windows",
            "out/BrowseForgeWindowsX64",
            'target_os="win" target_cpu="x64" is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false proprietary_codecs=true ffmpeg_branding="Chrome"',
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


def windows_cross_toolchain_status(workdir: Path) -> dict[str, object]:
    base = Path(os.environ.get(WINDOWS_TOOLCHAIN_BASE_ENV, str(DEFAULT_WINDOWS_TOOLCHAIN_BASE))).expanduser()
    toolchain_hash = os.environ.get(WINDOWS_TOOLCHAIN_HASH_ENV, DEFAULT_WINDOWS_TOOLCHAIN_HASH)
    zip_path = base / f"{toolchain_hash}.zip"
    gclient_path = workdir / ".gclient"
    gclient_text = gclient_path.read_text(encoding="utf-8") if gclient_path.is_file() else ""
    target_os_win = "target_os" in gclient_text and "win" in gclient_text
    enabled = os.environ.get(WINDOWS_TOOLCHAIN_ENABLE_ENV, "1") == "1"
    return {
        "windows_cross_compile_supported": host_os_name() == "darwin" and enabled and zip_path.is_file() and target_os_win,
        "windows_toolchain_base": str(base),
        "windows_toolchain_zip": str(zip_path),
        "windows_toolchain_zip_exists": zip_path.is_file(),
        "windows_toolchain_hash": toolchain_hash,
        "windows_toolchain_enabled": enabled,
        "gclient_target_os_win": target_os_win,
        "gclient_path": str(gclient_path),
    }


def windows_cross_compile_env() -> str:
    return (
        f"{WINDOWS_TOOLCHAIN_BASE_ENV}={shlex.quote(str(DEFAULT_WINDOWS_TOOLCHAIN_BASE))} "
        f"{WINDOWS_TOOLCHAIN_HASH_ENV}={DEFAULT_WINDOWS_TOOLCHAIN_HASH} "
        f"{WINDOWS_TOOLCHAIN_ENABLE_ENV}=1"
    )


def latest_patchset_id() -> str:
    manifest = load_json(ROOT / "knowledge" / "manifests" / "patchset.json")
    patchsets = manifest.get("patchsets", [])
    if not patchsets:
        return "unpatched"
    return str(patchsets[-1]["patchset_id"])


def build_plan(platform_id: str, workdir: Path = DEFAULT_WORKDIR, out_dir: str | None = None, jobs: int = DEFAULT_JOBS) -> NativeBuildPlan:
    required_host, default_out, gn_args, output_rel = platform_contract(platform_id)
    selected_out = out_dir or default_out
    src = workdir / "src"
    output_binary = src / selected_out / output_rel
    wrapper_name = "browseforge-runtime-chromium.exe" if platform_id == "windows-x64" else "browseforge-runtime-chromium-darwin-amd64" if platform_id == "macos-x64" else "browseforge-runtime-chromium"
    wrapper_binary = ROOT / "bin" / wrapper_name
    artifact_id = f"browseforge-runtime-chromium-{RUNTIME_VERSION}-{platform_id}"
    package_command = [
        sys.executable,
        str(ROOT / "build" / "package_runtime.py"),
        "package",
        "--platform",
        platform_id,
        "--browser-binary",
        str(output_binary),
        "--wrapper-binary",
        str(wrapper_binary),
        "--output-dir",
        str(ROOT / "dist"),
        "--runtime-version",
        RUNTIME_VERSION,
        "--source-ref",
        "51b83660c3609f271ccbbd65785bf7e50a21312d",
        "--browser-version",
        "150.0.7871.101",
        "--patchset-id",
        latest_patchset_id(),
        "--wrapper-version",
        RUNTIME_VERSION,
        "--release-channel",
        "alpha",
        "--source-acquisition-manifest",
        str(ROOT / "knowledge" / "manifests" / "source-acquisition.json"),
        "--patchset-manifest",
        str(ROOT / "knowledge" / "manifests" / "patchset.json"),
    ]
    depot_tools = workdir / "depot_tools"
    gn_binary = depot_tools / ("gn.bat" if platform_id == "windows-x64" else "gn")
    path_prefix = f"{depot_tools}:$PATH"
    run_env = f"PATH={path_prefix} DEPOT_TOOLS_UPDATE=0"
    if platform_id == "windows-x64":
        run_env = f"{windows_cross_compile_env()} {run_env}"
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
            "sync-deps": ["bash", "-lc", f"{run_env} gclient sync --with_branch_heads --with_tags"],
            "run-hooks": ["bash", "-lc", f"{run_env} gclient runhooks"],
            "gn-gen": ["bash", "-lc", f"{run_env} gn gen {selected_out} --args='{gn_args}'"],
            "build-chrome": ["bash", "-lc", f"{run_env} autoninja -j{jobs} -C {selected_out} chrome"],
            "package": package_command,
        },
    )


def check(plan: NativeBuildPlan) -> dict[str, object]:
    src = Path(plan.chromium_src_dir)
    output = Path(plan.output_binary)
    app_bundle = None
    if plan.platform_id.startswith("macos-"):
        app_bundle = str(output.parents[2])
    gn_path = Path(plan.depot_tools_dir) / ("gn.bat" if plan.platform_id == "windows-x64" else "gn")
    depot_tools_exists = Path(plan.depot_tools_dir).is_dir()
    gn_binary_exists = gn_path.is_file()
    autoninja = str(Path(plan.depot_tools_dir) / "autoninja") if (Path(plan.depot_tools_dir) / "autoninja").is_file() else shutil.which("autoninja")
    gclient = str(Path(plan.depot_tools_dir) / "gclient") if (Path(plan.depot_tools_dir) / "gclient").is_file() else shutil.which("gclient")
    status = {
        "workdir": plan.workdir,
        "chromium_src_dir": plan.chromium_src_dir,
        "host_os": plan.host_os,
        "required_host_os": plan.required_host_os,
        "host_supported": plan.host_os == plan.required_host_os,
        "host_support_mode": "native" if plan.host_os == plan.required_host_os else "unsupported_host",
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
    if plan.platform_id == "windows-x64":
        windows_status = windows_cross_toolchain_status(Path(plan.workdir))
        status.update(windows_status)
        if plan.host_os == "darwin" and windows_status["windows_cross_compile_supported"]:
            status["host_supported"] = True
            status["host_support_mode"] = "darwin_windows_cross_compile"
        elif status["host_supported"]:
            status["host_support_mode"] = "native_windows"
    toolchain_ready = bool(
        status["host_supported"]
        and status["chromium_src_exists"]
        and status["chromium_deps_exists"]
        and depot_tools_exists
        and gn_binary_exists
        and gclient
        and autoninja
    )
    if plan.platform_id == "windows-x64":
        toolchain_ready = toolchain_ready and bool(
            status.get("windows_toolchain_zip_exists") and status.get("gclient_target_os_win")
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
        "host_support_mode",
        "windows_toolchain_zip_exists",
        "gclient_target_os_win",
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
        parts.append(f"host_support_mode={status.get('host_support_mode')}")
        parts.append(f"windows_toolchain_zip_exists={status.get('windows_toolchain_zip_exists')}")
        parts.append(f"gclient_target_os_win={status.get('gclient_target_os_win')}")
        parts.append(f"portable_layout_exists={status.get('portable_layout_exists')}")
        parts.append("verification_mode=manual_windows_os")
    return f"python3 scripts/chromium_native.py check --platform {platform_id}: " + ", ".join(parts)

def native_status_snapshot(platform_id: str, status: dict[str, object]) -> dict[str, object]:
    keys = [
        "workdir",
        "chromium_src_dir",
        "host_os",
        "required_host_os",
        "host_supported",
        "chromium_src_exists",
        "chromium_deps_exists",
        "depot_tools_exists",
        "gn_binary_exists",
        "out_args_exists",
        "build_ninja_exists",
        "output_binary_exists",
        "package_zip_exists",
        "native_toolchain_ready",
    ]
    if platform_id == "macos-arm64":
        keys.extend(["xcodebuild_ok", "xcodebuild_status", "app_bundle_exists"])
    if platform_id == "windows-x64":
        keys.extend([
            "host_support_mode",
            "windows_cross_compile_supported",
            "windows_toolchain_base",
            "windows_toolchain_zip",
            "windows_toolchain_zip_exists",
            "windows_toolchain_hash",
            "windows_toolchain_enabled",
            "gclient_target_os_win",
            "gclient_path",
            "portable_layout_exists",
            "verification_mode",
            "manual_windows_os_validation_required",
        ])
    return {key: status[key] for key in keys if key in status}




def platform_display_name(platform_id: str) -> str:
    if platform_id == "macos-arm64":
        return "macOS"
    if platform_id == "windows-x64":
        return "Windows"
    return platform_id


def native_preflight_next_commands(platform_id: str, status: dict[str, object]) -> list[str]:
    workdir = shlex.quote(str(status.get("workdir") or DEFAULT_WORKDIR))
    commands = [
        f"python3 scripts/chromium_native.py plan --platform {platform_id} --workdir {workdir}",
        f"python3 scripts/chromium_native.py check --platform {platform_id} --workdir {workdir}",
        f"python3 scripts/chromium_native.py sync-deps --platform {platform_id} --workdir {workdir} --execute",
        f"python3 scripts/chromium_native.py run-hooks --platform {platform_id} --workdir {workdir} --execute",
        f"python3 scripts/chromium_native.py gn-gen --platform {platform_id} --workdir {workdir} --execute",
        f"python3 scripts/chromium_native.py build-chrome --platform {platform_id} --workdir {workdir} --execute",
    ]
    if platform_id == "windows-x64":
        commands.append("GOOS=windows GOARCH=amd64 go build -o bin/browseforge-runtime-chromium.exe ./cmd/browseforge-runtime-chromium")
    elif platform_id == "macos-x64":
        commands.append("GOOS=darwin GOARCH=amd64 go build -o bin/browseforge-runtime-chromium-darwin-amd64 ./cmd/browseforge-runtime-chromium")
    else:
        commands.append("go build -o bin/browseforge-runtime-chromium ./cmd/browseforge-runtime-chromium")
    commands.append(f"python3 scripts/chromium_native.py package --platform {platform_id} --workdir {workdir} --execute")
    return commands

def native_preflight_entry(platform_id: str, status: dict[str, object]) -> dict[str, object]:
    missing: list[str] = []
    if not status["package_zip_exists"]:
        missing.append(f"dist/browseforge-runtime-chromium-{RUNTIME_VERSION}-{platform_id}.zip")
    if not status["host_supported"] and platform_id != "windows-x64":
        missing.append(f"{platform_id} host/toolchain selected so native Chromium packaging can run")
    elif platform_id == "macos-arm64" and not status.get("xcodebuild_ok"):
        missing.append("full Xcode selected via xcode-select so Chromium macOS GN generation can read the macosx SDK")
    elif platform_id != "windows-x64" and not status["native_toolchain_ready"]:
        missing.append(f"{platform_id} native Chromium toolchain ready")
    if platform_id == "macos-arm64" and not status.get("app_bundle_exists"):
        missing.append("BrowseForge Chromium .app bundle built from refs/tags/150.0.7871.101")
    if platform_id == "windows-x64" and not status.get("portable_layout_exists"):
        missing.append("BrowseForge Chromium portable chrome.exe/DLL runtime built from refs/tags/150.0.7871.101")
    if not status["package_zip_exists"] and platform_id != "macos-x64":
        missing.append(f"native {platform_display_name(platform_id)} detector evidence for the packaged artifact")
    if platform_id == "windows-x64":
        status["verification_mode"] = "manual_windows_os"
        status["manual_windows_os_validation_required"] = True
    evidence = [
        "knowledge/manifests/platform-matrix.json",
        "contracts/browseforge-integration.contract.json",
        "knowledge/manifests/signing-policy.json",
        native_status_evidence(platform_id, status),
    ]
    if platform_id == "windows-x64":
        evidence.append(WINDOWS_MANUAL_VALIDATION_NOTE)
    entry: dict[str, object] = {
        "evidence": evidence,
        "platform": platform_id,
        "ready": not missing,
        "status": "packaged_only_untested" if platform_id == "macos-x64" and not missing else "packaged_detector_tested" if not missing else "missing_native_release_artifact",
        "status_snapshot": native_status_snapshot(platform_id, status),
        "missing_prerequisites": missing,
        "next_commands": native_preflight_next_commands(platform_id, status),
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
            "Windows artifacts are BrowseForge Chromium portable executable/DLL layouts built from the selected source ref; compile/runtime verification is manual on Windows OS, not local wine/qemu emulation",
            "native platform artifacts have detector evidence before release_grade can pass",
        ],
        "runtime_id": "browseforge-chromium",
        "schema_version": "1.0",
        "platforms": entries,
        "supported_package_platforms": supported,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="BrowseForge Chromium native build helper")
    parser.add_argument("command", choices=["plan", "check", "preflight", "sync-deps", "run-hooks", "gn-gen", "build-chrome", "package"])
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
