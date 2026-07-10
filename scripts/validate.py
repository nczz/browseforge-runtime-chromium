#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import json
from pathlib import Path
import zipfile
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "go.mod",
    "cmd/browseforge-runtime-chromium/main.go",
    "internal/launcher/config.go",
    "internal/launcher/launch.go",
    "internal/stealth/persona.go",
    "contracts/runtime.manifest.json",
    "contracts/runtime-manifest.schema.json",
    "contracts/browseforge-integration.contract.json",
    "detectors/evidence-schema.json",
    "detector-summary.json",
    "knowledge/kb-manifest.json",
    "knowledge/manifests/detectors.json",
    "knowledge/manifests/patchset.json",
    "knowledge/manifests/runtime-artifacts.json",
    "knowledge/manifests/reference-sources.json",
    "knowledge/manifests/platform-matrix.json",
    "knowledge/manifests/release-gates.json",
    "knowledge/manifests/detector-score-comparison.json",
    "knowledge/manifests/pixelscan-variant-plan.json",
    "knowledge/manifests/pixelscan-variant-summary.json",
    "knowledge/manifests/ua-ch-grease-verification.json",
    "knowledge/manifests/fingerprint-surface-status.json",
    "knowledge/manifests/proxy-preflight.json",
    "knowledge/manifests/native-artifact-preflight.json",
    "knowledge/manifests/signing-policy.json",
    "knowledge/manifests/release-status.json",
    "knowledge/manifests/source-acquisition.json",
    "browser/chromium-base.json",
    "browser/stealth/BUILD.gn",
    "browser/stealth/stealth_switches.h",
    "browser/stealth/stealth_switches.cc",
    "browser/stealth/persona_snapshot.h",
    "browser/stealth/persona_snapshot.cc",
    "browser/stealth/persona_resolver.h",
    "browser/stealth/persona_resolver.cc",
    "browser/stealth/public/mojom/stealth.mojom",
    "build/package_runtime.py",
    "scripts/chromium_source.py",
    "scripts/apply_stealth_scaffold.py",
    "scripts/chromium_docker.py",
    "scripts/chromium_native.py",
    "scripts/release_status.py",
    "scripts/package_linux_runtime.py",
    "scripts/apply_webdriver_patch.py",
    "scripts/patch_ops.py",
    "scripts/apply_hardware_patch.py",
    "scripts/apply_screen_patch.py",
    "scripts/apply_platform_patch.py",
    "scripts/apply_timezone_patch.py",
    "scripts/apply_locale_patch.py",
    "scripts/apply_user_agent_patch.py",
    "scripts/apply_storage_quota_patch.py",
    "scripts/apply_plugins_patch.py",
    "scripts/apply_webrtc_patch.py",
    "scripts/apply_audio_patch.py",
    "scripts/apply_canvas_patch.py",
    "scripts/apply_webgl_patch.py",
    "scripts/apply_feature_parity_patch.py",
    "scripts/apply_fonts_patch.py",
    "scripts/apply_process_priority_patch.py",
    "scripts/apply_switch_propagation_patch.py",
    "scripts/detector_harness.py",
    "docker/chromium-build.Dockerfile",
    "graph/schema/runtime-kg.schema.md",
    "graph/queries/development-readiness.cypher",
    "graph/queries/fingerprint-risk.cypher",
    "graph/queries/cross-repo-impact.cypher",
    "graph/queries/source-coverage.cypher",
    "generated/kg/runtime.graph.jsonl",
    "generated/kg/runtime.ttl",
    "docs/architecture.md",
    "docs/browseforge-integration.md",
    "docs/research-map.md",
    "docs/fingerprint-surfaces.md",
    "docs/release-readiness.md",
    "docs/kb-kg-completeness-assessment.md",
    "tests/test_detector_harness.py",
    "tests/test_package_runtime.py",
    "tests/test_chromium_source.py",
    "tests/test_apply_stealth_scaffold.py",
    "tests/test_apply_webdriver_patch.py",
    "tests/test_apply_hardware_patch.py",
    "tests/test_apply_screen_patch.py",
    "tests/test_apply_platform_patch.py",
    "tests/test_apply_timezone_patch.py",
    "tests/test_apply_locale_patch.py",
    "tests/test_apply_user_agent_patch.py",
    "tests/test_apply_storage_quota_patch.py",
    "tests/test_apply_plugins_patch.py",
    "tests/test_apply_webrtc_patch.py",
    "tests/test_apply_audio_patch.py",
    "tests/test_apply_canvas_patch.py",
    "tests/test_apply_webgl_patch.py",
    "tests/test_apply_feature_parity_patch.py",
    "tests/test_apply_fonts_patch.py",
    "tests/test_apply_process_priority_patch.py",
    "tests/test_apply_switch_propagation_patch.py",
    "tests/test_chromium_docker.py",
    "tests/test_chromium_native.py",
    "tests/test_release_status.py",
    "internal/stealth/persona_test.go",
    "tests/test_stealth_scaffold.py",
]

REQUIRED_GRAPH_MANIFEST_SOURCES = [
    "contracts/runtime.manifest.json",
    "contracts/browseforge-integration.contract.json",
    "detectors/evidence-schema.json",
    "detector-summary.json",
    "knowledge/kb-manifest.json",
    "knowledge/manifests/detectors.json",
    "knowledge/manifests/patchset.json",
    "knowledge/manifests/runtime-artifacts.json",
    "knowledge/manifests/reference-sources.json",
    "knowledge/manifests/platform-matrix.json",
    "knowledge/manifests/release-gates.json",
    "knowledge/manifests/detector-score-comparison.json",
    "knowledge/manifests/fingerprint-surface-status.json",
    "knowledge/manifests/proxy-preflight.json",
    "knowledge/manifests/native-artifact-preflight.json",
    "knowledge/manifests/signing-policy.json",
    "knowledge/manifests/release-status.json",
    "knowledge/manifests/source-acquisition.json",
]


def graph_manifest_node_id(path: str) -> str:
    return f"Manifest:{path.replace('/', '-')}"

REQUIRED_DIRS = [
    "browser",
    "wrapper",
    "build",
    "docker",
    "detectors",
    "knowledge",
    "graph",
    "tests",
    "examples",
]


def load_json(path: str) -> object:
    with (ROOT / path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(path: str) -> list[dict]:
    records = []
    with (ROOT / path).open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSONL: {exc}") from exc
    return records

def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_archive_json(archive: Path, member: str) -> dict:
    with zipfile.ZipFile(archive) as zf:
        try:
            data = zf.read(member)
        except KeyError as exc:
            raise SystemExit(f"artifact archive {archive.relative_to(ROOT)} missing {member}") from exc
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"artifact archive {archive.relative_to(ROOT)} member {member} invalid JSON: {exc}") from exc


def validate_runtime_artifact_consistency(runtime_artifacts: dict, source_acquisition: dict) -> None:
    artifacts = runtime_artifacts.get("artifacts", [])
    if not artifacts:
        raise SystemExit("runtime-artifacts must list at least one packaged artifact")

    source_linux = source_acquisition.get("chromium_base", {}).get("linux_x64_artifact", {})
    for artifact in artifacts:
        artifact_id = artifact["artifact_id"]
        platform = artifact.get("platform")
        archive_rel = Path("dist") / f"{artifact_id}.zip"
        archive_path = ROOT / archive_rel
        if not archive_path.is_file():
            raise SystemExit(f"runtime artifact archive missing: {archive_rel.as_posix()}")

        archive_sha = file_sha256(archive_path)
        archive_size = archive_path.stat().st_size
        if artifact.get("sha256") != archive_sha:
            raise SystemExit(f"runtime artifact {artifact_id} sha256 drifted: {artifact.get('sha256')!r} != {archive_sha!r}")
        if artifact.get("size_bytes") != archive_size:
            raise SystemExit(f"runtime artifact {artifact_id} size_bytes drifted: {artifact.get('size_bytes')!r} != {archive_size!r}")

        if platform == "linux-x64":
            expected_archive = archive_rel.as_posix()
            source_checks = {
                "archive": expected_archive,
                "archive_sha256": archive_sha,
                "archive_size_bytes": archive_size,
                "artifact_id": artifact_id,
                "browser_binary_sha256": artifact.get("browser_binary_sha256"),
                "wrapper_binary_sha256": artifact.get("wrapper_binary_sha256"),
            }
            for key, expected in source_checks.items():
                if source_linux.get(key) != expected:
                    raise SystemExit(f"source-acquisition linux_x64_artifact {key} drifted: {source_linux.get(key)!r} != {expected!r}")

        archive_prefix = f"{artifact_id}/"
        artifact_manifest = load_archive_json(archive_path, f"{archive_prefix}artifact-manifest.json")
        provenance = load_archive_json(archive_path, f"{archive_prefix}provenance.json")

        for key in [
            "artifact_id", "runtime_id", "runtime_version", "platform", "os", "arch",
            "browser_version", "source_ref", "patchset_id", "wrapper_version",
            "release_channel", "browser_binary_sha256", "wrapper_binary_sha256",
        ]:
            if artifact_manifest.get(key) != artifact.get(key):
                raise SystemExit(f"artifact archive {artifact_id} manifest {key} drifted: {artifact_manifest.get(key)!r} != {artifact.get(key)!r}")
            if key != "artifact_id" and provenance.get(key) != artifact.get(key):
                raise SystemExit(f"artifact archive {artifact_id} provenance {key} drifted: {provenance.get(key)!r} != {artifact.get(key)!r}")


def validate_source_build_outputs(source_acquisition: dict, runtime_artifacts: dict) -> None:
    chromium_base = source_acquisition.get("chromium_base", {})
    status = chromium_base.get("build_output_status")
    if not isinstance(status, dict):
        raise SystemExit("source-acquisition must record build_output_status")
    required_bool_keys = {
        "dev_gn_args_exists",
        "dev_build_ninja_exists",
        "linux_docker_gn_args_exists",
        "linux_docker_build_ninja_exists",
        "linux_docker_chrome_exists",
    }
    missing = sorted(required_bool_keys - set(status))
    if missing:
        raise SystemExit(f"source-acquisition build_output_status missing keys: {missing}")
    for key in required_bool_keys:
        if not isinstance(status.get(key), bool):
            raise SystemExit(f"source-acquisition build_output_status {key} must be boolean")
    if any(artifact.get("platform") == "linux-x64" for artifact in runtime_artifacts.get("artifacts", [])):
        for key in ["linux_docker_gn_args_exists", "linux_docker_build_ninja_exists", "linux_docker_chrome_exists"]:
            if not status.get(key):
                raise SystemExit(f"source-acquisition build_output_status {key} must remain true while linux-x64 artifact is packaged")


def validate_native_build_automation(source_acquisition: dict, runtime_artifacts: dict) -> None:
    automation = source_acquisition.get("chromium_base", {}).get("native_build_automation")
    if not isinstance(automation, dict):
        raise SystemExit("source-acquisition must record native_build_automation")
    if automation.get("script") != "scripts/chromium_native.py":
        raise SystemExit("source-acquisition native_build_automation script must be scripts/chromium_native.py")
    if not (ROOT / automation["script"]).is_file():
        raise SystemExit("source-acquisition native_build_automation script is missing")
    platforms = automation.get("platforms", {})
    if not isinstance(platforms, dict):
        raise SystemExit("source-acquisition native_build_automation platforms must be an object")
    expected_platforms = sorted(set(runtime_artifacts.get("supported_package_platforms", [])) - {"linux-x64"})
    missing_platforms = sorted(set(expected_platforms) - set(platforms))
    if missing_platforms:
        raise SystemExit(f"source-acquisition native_build_automation missing platforms: {missing_platforms}")
    required = {
        "macos-arm64": {
            "artifact_id": "browseforge-runtime-chromium-v0.1.0-alpha.0-macos-arm64",
            "gn_args": 'target_os="mac" target_cpu="arm64" is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false',
            "out_dir": "out/BrowseForgeMacArm64",
            "output_binary": "out/BrowseForgeMacArm64/Chromium.app/Contents/MacOS/Chromium",
            "required_host_os": "darwin",
        },
        "windows-x64": {
            "artifact_id": "browseforge-runtime-chromium-v0.1.0-alpha.0-windows-x64",
            "gn_args": 'target_os="win" target_cpu="x64" is_debug=false symbol_level=1 is_component_build=false use_remoteexec=false',
            "out_dir": "out/BrowseForgeWindowsX64",
            "output_binary": "out/BrowseForgeWindowsX64/chrome.exe",
            "required_host_os": "windows",
        },
    }
    for platform_id in expected_platforms:
        platform = platforms.get(platform_id, {})
        for key, expected in required[platform_id].items():
            if platform.get(key) != expected:
                raise SystemExit(f"source-acquisition native_build_automation {platform_id} {key} drifted: {platform.get(key)!r} != {expected!r}")
        if platform.get("status") != "preflight_ready_artifact_missing":
            raise SystemExit(f"source-acquisition native_build_automation {platform_id} must remain preflight_ready_artifact_missing until artifact exists")

def validate_evidence_schema_contract(evidence_schema: dict) -> None:
    properties = evidence_schema.get("properties", {})
    harness_props = properties.get("harness", {}).get("properties", {})
    matrix_props = properties.get("matrix", {}).get("properties", {})
    storage_props = properties.get("storage", {}).get("properties", {})
    required_enums = {
        "harness.name": (harness_props.get("name", {}).get("enum") or [], {"browseforge-detector-harness", "browseforge-detector-harness + local-connect-proxy"}),
        "harness.mode": (harness_props.get("mode", {}).get("enum") or [], {"manual_ingest", "synthetic_fixture", "live_collect", "live_collect_local_proxy"}),
        "matrix.display_mode": (matrix_props.get("display_mode", {}).get("enum") or [], {"headed", "headed_xvfb", "headless", "unknown"}),
        "matrix.network_mode": (matrix_props.get("network_mode", {}).get("enum") or [], {"direct", "proxy", "local_proxy", "unknown"}),
        "matrix.proxy": (matrix_props.get("proxy", {}).get("enum") or [], {"none", "redacted", "public_test_infra", "local-connect-observer"}),
    }
    for field, (actual_values, required_values) in required_enums.items():
        missing_values = sorted(required_values - set(actual_values))
        if missing_values:
            raise SystemExit(f"evidence schema {field} missing admitted values: {missing_values}")

    required_storage_keys = {"evidence_path", "sha256", "raw_capture_path", "raw_capture_sha256", "proxy_summary_sha256", "text_sha256", "summary_path"}
    missing_storage_keys = sorted(required_storage_keys - set(storage_props))
    if missing_storage_keys:
        raise SystemExit(f"evidence schema storage missing properties: {missing_storage_keys}")

    admitted = {
        "harness.name": set(harness_props["name"]["enum"]),
        "harness.mode": set(harness_props["mode"]["enum"]),
        "matrix.display_mode": set(matrix_props["display_mode"]["enum"]),
        "matrix.network_mode": set(matrix_props["network_mode"]["enum"]),
        "matrix.proxy": set(matrix_props["proxy"]["enum"]),
    }
    storage_keys = set(storage_props)
    for path in sorted((ROOT / "detectors" / "evidence").glob("**/*.json")):
        with path.open("r", encoding="utf-8") as fh:
            evidence = json.load(fh)
        values = {
            "harness.name": evidence.get("harness", {}).get("name"),
            "harness.mode": evidence.get("harness", {}).get("mode"),
            "matrix.display_mode": evidence.get("matrix", {}).get("display_mode"),
            "matrix.network_mode": evidence.get("matrix", {}).get("network_mode"),
            "matrix.proxy": evidence.get("matrix", {}).get("proxy"),
        }
        for field, value in values.items():
            if value not in admitted[field]:
                rel = path.relative_to(ROOT)
                raise SystemExit(f"detector evidence {rel} {field} value {value!r} is not admitted by evidence schema")
        for storage_key in evidence.get("storage", {}):
            if storage_key not in storage_keys:
                rel = path.relative_to(ROOT)
                raise SystemExit(f"detector evidence {rel} storage key {storage_key!r} is not admitted by evidence schema")

def validate_surface_status_manifest(surface_status: dict, gate_status: dict[str, str | None]) -> None:
    if surface_status.get("runtime_id") != "browseforge-chromium":
        raise SystemExit("fingerprint surface status runtime_id must be browseforge-chromium")
    allowed_statuses = set(surface_status.get("allowed_status_values", []))
    if not allowed_statuses:
        raise SystemExit("fingerprint surface status must declare allowed_status_values")
    surfaces = surface_status.get("surfaces", [])
    if not surfaces:
        raise SystemExit("fingerprint surface status must contain surfaces")
    required_fields = {"surface", "status", "release_blocker", "result", "evidence", "severity"}
    release_blockers = []
    for surface in surfaces:
        missing_fields = sorted(required_fields - surface.keys())
        if missing_fields:
            raise SystemExit(f"fingerprint surface status entry missing fields: {missing_fields}")
        if surface["status"] not in allowed_statuses:
            raise SystemExit(f"fingerprint surface {surface['surface']} uses unknown status {surface['status']}")
        if not isinstance(surface["release_blocker"], bool):
            raise SystemExit(f"fingerprint surface {surface['surface']} release_blocker must be boolean")
        if surface["release_blocker"]:
            release_blockers.append(surface["surface"])
    if surface_status.get("release_grade") is True and release_blockers:
        raise SystemExit(f"fingerprint surface status cannot be release_grade with blockers: {sorted(release_blockers)}")
    if gate_status.get("live-detector-evidence") == "passed" and release_blockers:
        raise SystemExit(f"live-detector-evidence gate cannot pass while fingerprint surfaces block release: {sorted(release_blockers)}")
    evidence_refs = surface_status.get("evidence_refs", [])
    if not isinstance(evidence_refs, list) or any(not isinstance(path, str) or not path for path in evidence_refs):
        raise SystemExit("fingerprint surface status evidence_refs must be non-empty strings")
    for evidence_ref in evidence_refs:
        if not (ROOT / evidence_ref).is_file():
            raise SystemExit(f"fingerprint surface status references missing evidence_ref: {evidence_ref}")
    for source_path in surface_status.get("updated_from", []):
        if not (ROOT / source_path).is_file():
            raise SystemExit(f"fingerprint surface status references missing evidence source: {source_path}")

def validate_score_comparison_manifest(score_comparison: dict, gate_status: dict[str, str | None]) -> None:
    if score_comparison.get("runtime_id") != "browseforge-chromium":
        raise SystemExit("detector score comparison runtime_id must be browseforge-chromium")
    if score_comparison.get("release_grade") is not False:
        raise SystemExit("offline detector score comparison must not claim release grade")

    comparisons = score_comparison.get("comparisons", [])
    comparison_ids = {comparison.get("comparison_id") for comparison in comparisons}
    for comparison_id in ["creepjs_audio_headless_vs_headed", "browserleaks_creepjs_font_metrics"]:
        if comparison_id not in comparison_ids:
            raise SystemExit(f"detector score comparison missing {comparison_id}")

    baseline_gap_ids = {gap.get("gap_id") for gap in score_comparison.get("baseline_gaps", [])}
    for gap_id in [
        "native_headed_font_corpus_parity_missing",
    ]:
        if gap_id not in baseline_gap_ids:
            raise SystemExit(f"detector score comparison missing baseline gap {gap_id}")

    gap_ids = {gap.get("gap_id") for gap in score_comparison.get("gaps", [])}
    webgl_comparison = next((comparison for comparison in comparisons if comparison.get("comparison_id") == "webgl_metadata_cross_detector"), None)
    if webgl_comparison is None:
        for gap_id in ["webgl_metadata_hashes_missing", "webgl_cross_detector_metadata_comparison_missing"]:
            if gap_id not in gap_ids:
                raise SystemExit(f"detector score comparison missing WebGL comparison blocker {gap_id}")
    else:
        for field in ["vendor_renderer_match", "extension_count_match", "extension_profile_match", "hash_matches"]:
            if field not in webgl_comparison:
                raise SystemExit(f"detector score comparison WebGL comparison missing field {field}")
        hash_matches = webgl_comparison.get("hash_matches")
        if not isinstance(hash_matches, dict):
            raise SystemExit("detector score comparison WebGL hash_matches must be an object")
        for field in ["extensionSha256", "parameterSha256", "precisionSha256", "pixelSha256"]:
            if field not in hash_matches:
                raise SystemExit(f"detector score comparison WebGL hash_matches missing {field}")

    if gate_status.get("live-detector-evidence") == "passed":
        warning_comparisons = [comparison.get("comparison_id") for comparison in comparisons if comparison.get("status") == "warning"]
        if score_comparison.get("baseline_gaps") or score_comparison.get("gaps") or warning_comparisons:
            raise SystemExit("live-detector-evidence gate cannot pass while detector score comparison has baseline gaps, evidence gaps, or warning comparisons")

def contains_raw_url_or_ip(value: object) -> bool:
    if isinstance(value, dict):
        return any(contains_raw_url_or_ip(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_raw_url_or_ip(item) for item in value)
    if not isinstance(value, str):
        return False
    if "://" in value or "@" in value:
        return True
    for token in value.replace("[", " ").replace("]", " ").replace(",", " ").replace(":", " ").split():
        try:
            ipaddress.ip_address(token)
        except ValueError:
            continue
        return True
    return False


def validate_proxy_preflight_manifest(proxy_preflight: dict, gate_status: dict[str, str | None], detector_summary: dict) -> None:
    if proxy_preflight.get("runtime_id") != "browseforge-chromium":
        raise SystemExit("proxy preflight runtime_id must be browseforge-chromium")
    if proxy_preflight.get("schema_version") != "1.0":
        raise SystemExit("proxy preflight schema_version must be 1.0")
    ready = proxy_preflight.get("ready")
    status = proxy_preflight.get("status")
    if not isinstance(ready, bool):
        raise SystemExit("proxy preflight ready must be boolean")
    if status not in {"passed", "failed"}:
        raise SystemExit(f"proxy preflight status must be passed or failed: {status!r}")
    if ready != (status == "passed"):
        raise SystemExit("proxy preflight ready/status mismatch")
    missing = proxy_preflight.get("missing", [])
    errors = proxy_preflight.get("errors", [])
    requirements = proxy_preflight.get("requirements", [])
    for key, value in {"missing": missing, "errors": errors}.items():
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise SystemExit(f"proxy preflight {key} must be a string array")
    if not isinstance(requirements, list) or any(
        not (
            isinstance(item, str)
            or (
                isinstance(item, dict)
                and all(isinstance(k, str) and isinstance(v, str) for k, v in item.items())
            )
        )
        for item in requirements
    ):
        raise SystemExit("proxy preflight requirements must be a string or string-object array")
    if contains_raw_url_or_ip(proxy_preflight.get("proxy")) or contains_raw_url_or_ip(proxy_preflight.get("proxy_region_redacted")):
        raise SystemExit("proxy preflight must not contain raw proxy URL, credentials, or IP literal")
    if not ready and not missing and not errors:
        raise SystemExit("failed proxy preflight must record missing prerequisites or errors")
    proxy_gaps = [gap for gap in detector_summary.get("coverage_gaps", []) if gap.get("network_mode") == "proxy"]
    if ready and (gate_status.get("live-detector-evidence") != "passed" or proxy_gaps):
        raise SystemExit("proxy preflight cannot be ready while live-detector-evidence gate or proxy coverage remains blocked")

def validate_release_gate_artifact_evidence(release_gates: dict, runtime_artifacts: dict) -> None:
    artifacts = runtime_artifacts.get("artifacts", [])
    if not artifacts:
        raise SystemExit("runtime-artifacts manifest must list packaged artifacts")
    primary = artifacts[0]
    required_tokens = [
        str(primary.get("artifact_id")),
        str(primary.get("sha256")),
        str(primary.get("size_bytes")),
    ]
    for gate in release_gates.get("release_candidate_required_gates", []):
        gate_id = gate.get("gate_id")
        if gate_id not in {"runtime-artifact-produced", "sbom-provenance-release-assets"}:
            continue
        if gate.get("status") != "passed":
            continue
        evidence = gate.get("evidence", "")
        if not isinstance(evidence, str):
            raise SystemExit(f"release gate {gate_id} evidence must be a string")
        missing = [token for token in required_tokens if token not in evidence]
        if missing:
            raise SystemExit(f"release gate {gate_id} evidence has stale runtime artifact metadata: {missing}")

def validate_native_status_snapshot(platform: str, entry: dict) -> None:
    if platform == "linux-x64":
        return
    snapshot = entry.get("status_snapshot")
    if not isinstance(snapshot, dict):
        raise SystemExit(f"native artifact preflight {platform} status_snapshot must be an object")
    required_keys = {
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
    }
    if platform == "macos-arm64":
        required_keys.update({"xcodebuild_ok", "xcodebuild_status", "app_bundle_exists"})
    if platform == "windows-x64":
        required_keys.add("portable_layout_exists")
    missing_keys = sorted(required_keys - set(snapshot))
    if missing_keys:
        raise SystemExit(f"native artifact preflight {platform} status_snapshot missing keys: {missing_keys}")
    boolean_keys = required_keys - {"host_os", "required_host_os", "xcodebuild_status"}
    for key in sorted(boolean_keys):
        if not isinstance(snapshot.get(key), bool):
            raise SystemExit(f"native artifact preflight {platform} status_snapshot {key} must be boolean")
    for key in ("host_os", "required_host_os"):
        if not isinstance(snapshot.get(key), str) or not snapshot.get(key):
            raise SystemExit(f"native artifact preflight {platform} status_snapshot {key} must be a non-empty string")
    if platform == "macos-arm64" and snapshot.get("xcodebuild_status") not in {"ok", "failed", "missing"}:
        raise SystemExit(f"native artifact preflight {platform} status_snapshot xcodebuild_status is invalid")


def validate_native_artifact_preflight(native_preflight: dict, runtime_artifacts: dict) -> None:
    if native_preflight.get("runtime_id") != "browseforge-chromium":
        raise SystemExit("native artifact preflight runtime_id must be browseforge-chromium")
    if native_preflight.get("schema_version") != "1.0":
        raise SystemExit("native artifact preflight schema_version must be 1.0")
    release_ready = native_preflight.get("release_grade_ready")
    if not isinstance(release_ready, bool):
        raise SystemExit("native artifact preflight release_grade_ready must be boolean")
    supported = set(runtime_artifacts.get("supported_package_platforms", []))
    declared_supported = set(native_preflight.get("supported_package_platforms", []))
    if declared_supported != supported:
        raise SystemExit(f"native artifact preflight supported_package_platforms drifted: {sorted(declared_supported)} != {sorted(supported)}")
    artifacts_by_platform = {
        artifact.get("platform"): artifact
        for artifact in runtime_artifacts.get("artifacts", [])
    }
    platforms = native_preflight.get("platforms", [])
    if not isinstance(platforms, list):
        raise SystemExit("native artifact preflight platforms must be an array")
    entries = {entry.get("platform"): entry for entry in platforms if isinstance(entry, dict)}
    missing_entries = sorted(supported - entries.keys())
    extra_entries = sorted(entries.keys() - supported)
    if missing_entries or extra_entries:
        raise SystemExit(f"native artifact preflight platform entries drifted: missing={missing_entries} extra={extra_entries}")
    for platform, entry in sorted(entries.items()):
        ready = entry.get("ready")
        if not isinstance(ready, bool):
            raise SystemExit(f"native artifact preflight {platform} ready must be boolean")
        missing = entry.get("missing_prerequisites", [])
        evidence = entry.get("evidence", [])
        if not isinstance(missing, list) or any(not isinstance(item, str) or not item for item in missing):
            raise SystemExit(f"native artifact preflight {platform} missing_prerequisites must be non-empty strings")
        if not isinstance(evidence, list) or any(not isinstance(item, str) or not item for item in evidence):
            raise SystemExit(f"native artifact preflight {platform} evidence must be non-empty strings")
        validate_native_status_snapshot(platform, entry)
        artifact = artifacts_by_platform.get(platform)
        if ready:
            if missing:
                raise SystemExit(f"native artifact preflight {platform} cannot be ready with missing prerequisites")
            if artifact is None:
                raise SystemExit(f"native artifact preflight {platform} cannot be ready without runtime-artifacts entry")
            if entry.get("artifact_id") != artifact.get("artifact_id"):
                raise SystemExit(f"native artifact preflight {platform} artifact_id drifted from runtime-artifacts")
            archive = ROOT / "dist" / f"{artifact['artifact_id']}.zip"
            if not archive.is_file():
                raise SystemExit(f"native artifact preflight {platform} missing archive: {archive.relative_to(ROOT)}")
        elif not missing:
            raise SystemExit(f"native artifact preflight {platform} must record missing prerequisites when not ready")
    if release_ready and any(not entry.get("ready") for entry in entries.values()):
        raise SystemExit("native artifact preflight cannot be release_grade_ready while supported platforms remain blocked")

def validate_signing_policy(signing_policy: dict, runtime_artifacts: dict, platform_matrix: dict) -> None:
    if signing_policy.get("runtime_id") != "browseforge-chromium":
        raise SystemExit("signing policy runtime_id must be browseforge-chromium")
    if signing_policy.get("schema_version") != "1.0":
        raise SystemExit("signing policy schema_version must be 1.0")
    release_ready = signing_policy.get("release_grade_ready")
    if not isinstance(release_ready, bool):
        raise SystemExit("signing policy release_grade_ready must be boolean")
    policies = signing_policy.get("policies", [])
    if not isinstance(policies, list):
        raise SystemExit("signing policy policies must be an array")
    policies_by_platform = {policy.get("platform"): policy for policy in policies if isinstance(policy, dict)}
    signing_required_platforms = {
        platform["id"]
        for platform in platform_matrix.get("platforms", [])
        if any("sign" in item.lower() or "notarization" in item.lower() for item in platform.get("required_evidence", []))
    }
    artifact_platforms = {artifact.get("platform") for artifact in runtime_artifacts.get("artifacts", [])}
    required_platforms = signing_required_platforms | artifact_platforms
    missing_policy_platforms = sorted(required_platforms - policies_by_platform.keys())
    if missing_policy_platforms:
        raise SystemExit(f"signing policy missing platform decisions: {missing_policy_platforms}")
    artifacts_by_platform = {artifact.get("platform"): artifact for artifact in runtime_artifacts.get("artifacts", [])}
    for platform, policy in sorted(policies_by_platform.items()):
        decision = policy.get("decision")
        evidence = policy.get("evidence", [])
        release_grade_allowed = policy.get("release_grade_allowed")
        if not isinstance(decision, str) or not decision:
            raise SystemExit(f"signing policy {platform} decision must be a non-empty string")
        if not isinstance(evidence, list) or any(not isinstance(item, str) or not item for item in evidence):
            raise SystemExit(f"signing policy {platform} evidence must be non-empty strings")
        if not isinstance(release_grade_allowed, bool):
            raise SystemExit(f"signing policy {platform} release_grade_allowed must be boolean")
        artifact = artifacts_by_platform.get(platform)
        if artifact is not None:
            for key in ["artifact_id", "signature", "release_channel"]:
                if policy.get(key) != artifact.get(key):
                    raise SystemExit(f"signing policy {platform} {key} drifted from runtime-artifacts")
    if release_ready and any(not policy.get("release_grade_allowed") for policy in policies_by_platform.values()):
        raise SystemExit("signing policy cannot be release_grade_ready while platform policies block release-grade signing")

RELEASE_STATUS_INPUTS = [
    "knowledge/manifests/release-gates.json",
    "knowledge/manifests/native-artifact-preflight.json",
    "knowledge/manifests/proxy-preflight.json",
    "detector-summary.json",
    "knowledge/manifests/detector-score-comparison.json",
    "knowledge/manifests/fingerprint-surface-status.json",
    "knowledge/manifests/signing-policy.json",
    "knowledge/manifests/source-acquisition.json",
    "contracts/browseforge-integration.contract.json",
]


def validate_release_status(release_status: dict) -> None:
    if release_status.get("runtime_id") != "browseforge-chromium":
        raise SystemExit("release status runtime_id must be browseforge-chromium")
    if release_status.get("schema_version") != "1.0":
        raise SystemExit("release status schema_version must be 1.0")
    generated_at = release_status.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.endswith("Z"):
        raise SystemExit("release status generated_at must be a UTC Z timestamp")
    try:
        parsed_generated_at = dt.datetime.fromisoformat(generated_at[:-1] + "+00:00")
    except ValueError as err:
        raise SystemExit("release status generated_at must be a valid UTC Z timestamp") from err
    if parsed_generated_at.utcoffset() != dt.timedelta(0) or parsed_generated_at.microsecond != 0:
        raise SystemExit("release status generated_at must be a whole-second UTC Z timestamp")
    blockers = release_status.get("blockers", [])
    if not isinstance(blockers, list):
        raise SystemExit("release status blockers must be an array")
    blocker_count = release_status.get("blocker_count")
    if blocker_count != len(blockers):
        raise SystemExit("release status blocker_count must match blockers length")
    if release_status.get("release_grade_ready") != (len(blockers) == 0):
        raise SystemExit("release status release_grade_ready must match blockers")
    seen_blocker_ids: set[str] = set()
    for blocker in blockers:
        if not isinstance(blocker, dict):
            raise SystemExit("release status blockers must be objects")
        for key in ["blocker_id", "source", "severity", "detail"]:
            if not isinstance(blocker.get(key), str) or not blocker.get(key):
                raise SystemExit(f"release status blocker missing {key}")
        blocker_id = blocker["blocker_id"]
        if blocker_id in seen_blocker_ids:
            raise SystemExit(f"release status duplicate blocker_id: {blocker_id}")
        seen_blocker_ids.add(blocker_id)
    inputs = release_status.get("inputs", [])
    blocker_order = [(blocker["source"], blocker["blocker_id"]) for blocker in blockers]
    if blocker_order != sorted(blocker_order):
        raise SystemExit("release status blockers must be sorted by source and blocker_id")
    if inputs != RELEASE_STATUS_INPUTS:
        raise SystemExit(f"release status inputs drifted: {inputs!r}")
    input_sha256 = release_status.get("input_sha256", {})
    if not isinstance(input_sha256, dict):
        raise SystemExit("release status input_sha256 must be an object")
    for path in RELEASE_STATUS_INPUTS:
        expected = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        if input_sha256.get(path) != expected:
            raise SystemExit(f"release status input hash drifted for {path}")

STALE_BROWSEFORGE_INTEGRATION_BLOCKERS = {
    "no runtime graph index",
    "no detector baseline",
    "no docker smoke evidence",
    "no playwright bind evidence",
}


def validate_browseforge_integration_contract(contract: dict, gate_status: dict[str, str | None]) -> None:
    if contract.get("runtime_id") != "browseforge-chromium":
        raise SystemExit("BrowseForge integration contract runtime_id must be browseforge-chromium")
    if contract.get("browseforge_min_version") != "v2.0.0":
        raise SystemExit("BrowseForge integration contract must require BrowseForge v2.0.0")
    required_surfaces = {
        "config.runtimes.<id>",
        "GET /api/runtimes",
        "POST /api/profiles",
        "PUT /api/profiles/{id}",
        "POST /api/profiles/import",
        "POST /api/backup/restore",
        "POST /api/sessions",
        "MCP list_runtimes",
        "MCP create_profile",
        "MCP open_browser",
        "workflow create_profile",
        "dashboard runtime selector",
        "browsers status",
        "browsers install",
        "Docker seed /app/browsers/<runtime>",
    }
    surfaces = set(contract.get("required_browseforge_surfaces", []))
    missing_surfaces = sorted(required_surfaces - surfaces)
    if missing_surfaces:
        raise SystemExit(f"BrowseForge integration contract missing surfaces: {missing_surfaces}")
    blockers = contract.get("release_blockers", [])
    if not blockers or not all(isinstance(blocker, str) and blocker for blocker in blockers):
        raise SystemExit("BrowseForge integration contract release_blockers must be non-empty strings")
    if gate_status.get("browseforge-adapter-merged") == "passed":
        stale = sorted(
            blocker
            for blocker in blockers
            if blocker.strip().lower() in STALE_BROWSEFORGE_INTEGRATION_BLOCKERS
        )
        if stale:
            raise SystemExit(f"stale BrowseForge integration release blockers: {stale}")




def main() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    missing_dirs = [path for path in REQUIRED_DIRS if not (ROOT / path).is_dir()]
    if missing_dirs:
        raise SystemExit(f"missing required directories: {missing_dirs}")

    manifest = load_json("contracts/runtime.manifest.json")
    if manifest["id"] != "browseforge-chromium":
        raise SystemExit("runtime id must be browseforge-chromium")
    if manifest["family"] != "chromium":
        raise SystemExit("runtime family must be chromium")
    if manifest["browseforge"]["profile_field"] != "runtime_id":
        raise SystemExit("BrowseForge profile field must stay runtime_id")

    kb_manifest = load_json("knowledge/kb-manifest.json")
    source_ids = {src["source_id"] for src in kb_manifest["sources"]}
    required_sources = {"runtime-repo-contracts", "runtime-repo-docs", "runtime-repo-detectors", "runtime-repo-graph", "browseforge-consumer-contract", "cloakbrowser-reference", "camoufox-reference", "chromium-upstream"}
    missing_sources = sorted(required_sources - source_ids)
    if missing_sources:
        raise SystemExit(f"missing KB source ids: {missing_sources}")

    detectors = load_json("knowledge/manifests/detectors.json")
    detector_ids = {det["detector_id"] for det in detectors["detectors"]}
    required_detectors = {"sannysoft", "browserleaks", "creepjs", "pixelscan", "iphey", "browserscan"}
    missing_detectors = sorted(required_detectors - detector_ids)
    if missing_detectors:
        raise SystemExit(f"missing detector ids: {missing_detectors}")
    runtime_surfaces = set(manifest["fingerprint"]["surfaces"])
    for det in detectors["detectors"]:
        if det.get("required") is not True:
            raise SystemExit(f"detector {det['detector_id']} must declare required=true")
        matrix = det.get("matrix", {})
        for key in ["display_modes", "network_modes", "container_modes"]:
            if key not in matrix:
                raise SystemExit(f"detector {det['detector_id']} missing matrix.{key}")
        for surface in det.get("canonical_surfaces", []):
            if surface not in runtime_surfaces:
                raise SystemExit(f"detector {det['detector_id']} references unknown canonical surface {surface}")

    evidence_schema = load_json("detectors/evidence-schema.json")
    if evidence_schema["properties"]["schema_version"].get("const") != "1.1":
        raise SystemExit("evidence schema must be 1.1")
    for field in ["run_id", "evidence_id", "artifact_id", "matrix", "status", "failure_mode", "storage", "kg"]:
        if field not in evidence_schema["required"]:
            raise SystemExit(f"evidence schema missing required field {field}")
    validate_evidence_schema_contract(evidence_schema)


    reference_sources = load_json("knowledge/manifests/reference-sources.json")
    source_class_ids = {src["id"] for src in reference_sources["source_classes"]}
    required_source_classes = {"browseforge-consumer", "cloakbrowser-reference", "camoufox-reference", "chromium-upstream", "detector-evidence"}
    missing_source_classes = sorted(required_source_classes - source_class_ids)
    if missing_source_classes:
        raise SystemExit(f"missing reference source classes: {missing_source_classes}")

    patchset = load_json("knowledge/manifests/patchset.json")
    if patchset.get("base_version") == "unselected" or patchset.get("base_ref") == "unselected":
        raise SystemExit("Chromium base version/ref must be selected")
    if not patchset.get("patchsets"):
        raise SystemExit("patchset manifest must contain at least an explicit baseline patchset")

    platform_matrix = load_json("knowledge/manifests/platform-matrix.json")
    platform_ids = {platform["id"] for platform in platform_matrix["platforms"]}
    required_platforms = {"linux-x64", "macos-arm64", "macos-x64", "windows-x64", "linux-arm64"}
    missing_platforms = sorted(required_platforms - platform_ids)
    if missing_platforms:
        raise SystemExit(f"missing platform matrix ids: {missing_platforms}")

    release_gates = load_json("knowledge/manifests/release-gates.json")
    gate_ids = {gate["gate_id"] for gate in release_gates["release_candidate_required_gates"]}
    for gate_id in ["chromium-base-selected", "wrapper-contract-tests", "detector-harness-contract-tests", "packaging-contract-tests", "chromium-source-indexed", "runtime-artifact-produced", "browseforge-adapter-merged", "live-detector-evidence", "sbom-provenance-release-assets"]:
        if gate_id not in gate_ids:
            raise SystemExit(f"release gates missing {gate_id}")
    gate_status = {gate["gate_id"]: gate.get("status") for gate in release_gates["release_candidate_required_gates"]}
    integration_contract = load_json("contracts/browseforge-integration.contract.json")
    validate_browseforge_integration_contract(integration_contract, gate_status)


    surface_status = load_json("knowledge/manifests/fingerprint-surface-status.json")
    validate_surface_status_manifest(surface_status, gate_status)

    detector_summary = load_json("detector-summary.json")
    coverage_gaps = detector_summary.get("coverage_gaps", [])
    coverage_gap_count = detector_summary.get("coverage_gap_count")
    if coverage_gap_count != len(coverage_gaps):
        raise SystemExit("detector summary coverage_gap_count must match coverage_gaps length")
    required_gap_fields = {"matrix_key", "platform", "detector_id", "display_mode", "network_mode", "container", "required_evidence"}
    for gap in coverage_gaps:
        missing_gap_fields = sorted(required_gap_fields - gap.keys())
        if missing_gap_fields:
            raise SystemExit(f"detector summary coverage gap missing fields: {missing_gap_fields}")
        if not isinstance(gap.get("container"), bool):
            raise SystemExit("detector summary coverage gap container must be boolean")
        expected_matrix_key = (
            f"{gap.get('platform')}:{gap.get('detector_id')}:{gap.get('display_mode')}:"
            f"{gap.get('network_mode')}:{'container' if gap.get('container') else 'host'}"
        )
        if gap.get("matrix_key") != expected_matrix_key:
            raise SystemExit(
                f"detector summary coverage gap matrix_key mismatch: {gap.get('matrix_key')!r} != {expected_matrix_key!r}"
            )
    rows = detector_summary.get("rows", [])
    evidence_count = detector_summary.get("evidence_count")
    if not isinstance(rows, list):
        raise SystemExit("detector summary rows must be an array")
    if evidence_count != len(rows):
        raise SystemExit("detector summary evidence_count must match rows length")
    seen_row_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise SystemExit("detector summary rows must contain objects")
        missing_row_fields = sorted({"detector_id", "path", "platform", "status"} - row.keys())
        if missing_row_fields:
            raise SystemExit(f"detector summary row missing fields: {missing_row_fields}")
        row_path = row.get("path")
        if not isinstance(row_path, str) or not row_path:
            raise SystemExit("detector summary row path must be a non-empty string")
        if row_path in seen_row_paths:
            raise SystemExit(f"detector summary duplicate evidence row path: {row_path}")
        seen_row_paths.add(row_path)
        if not (ROOT / row_path).is_file():
            raise SystemExit(f"detector summary row references missing evidence: {row_path}")
        if row.get("status") not in {"passed", "warning", "failed", "blocked"}:
            raise SystemExit(f"detector summary row has invalid status: {row.get('status')!r}")
    if gate_status.get("live-detector-evidence") == "passed" and (
        coverage_gap_count or detector_summary.get("blocking_findings")
    ):
        raise SystemExit("live-detector-evidence gate cannot pass while detector summary has coverage gaps or blocking findings")
    proxy_preflight = load_json("knowledge/manifests/proxy-preflight.json")
    validate_proxy_preflight_manifest(proxy_preflight, gate_status, detector_summary)


    score_comparison = load_json("knowledge/manifests/detector-score-comparison.json")
    validate_score_comparison_manifest(score_comparison, gate_status)

    query_text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in [
        "graph/queries/development-readiness.cypher",
        "graph/queries/fingerprint-risk.cypher",
        "graph/queries/cross-repo-impact.cypher",
        "graph/queries/source-coverage.cypher",
    ])
    for token in ["RuntimeArtifact", "DetectorRun", "BrowseForgeConsumer", "FingerprintSurface", "KnowledgeSource", "Platform", "Manifest", "RUNS_DETECTOR", "TARGETS_PLATFORM", "DECLARES_SOURCE"]:
        if token not in query_text:
            raise SystemExit(f"graph queries missing {token}")
    for stale_token in ["RAN_DETECTOR", "platform_id"]:
        if stale_token in query_text:
            raise SystemExit(f"graph queries contain stale schema token {stale_token}")

    graph_records = load_jsonl("generated/kg/runtime.graph.jsonl")
    node_labels = {record.get("label") for record in graph_records if record.get("record_type") == "node"}
    edge_labels = {record.get("label") for record in graph_records if record.get("record_type") == "edge"}
    required_node_labels = {
        "RuntimeProvider", "RuntimeArtifact", "BrowseForgeConsumer", "FingerprintSurface", "Patch",
        "SourceFile", "Symbol", "Detector", "DetectorRun", "EvidenceArtifact", "Platform",
        "Capability", "ReleaseGate", "KnowledgeSource", "Manifest",
    }
    missing_node_labels = sorted(required_node_labels - node_labels)
    if missing_node_labels:
        raise SystemExit(f"generated KG missing node labels: {missing_node_labels}")
    required_edge_labels = {
        "REQUIRES_CAPABILITY", "DECLARES_CAPABILITY", "BUILT_FOR", "GENERATED_FROM",
        "MODIFIES_SOURCE", "CONTROLS_SURFACE", "CHECKS_SURFACE", "RUNS_DETECTOR",
        "TARGETS_ARTIFACT", "TESTS_ARTIFACT", "PRODUCES_EVIDENCE", "SUPPORTS_GATE",
        "REFERENCES_SOURCE", "DECLARES_SOURCE",
    }
    missing_edge_labels = sorted(required_edge_labels - edge_labels)
    if missing_edge_labels:
        raise SystemExit(f"generated KG missing edge labels: {missing_edge_labels}")

    graph_nodes = {
        record["id"]: record
        for record in graph_records
        if record.get("record_type") == "node" and "id" in record
    }
    for gate in release_gates["release_candidate_required_gates"]:
        gate_id = gate["gate_id"]
        node = graph_nodes.get(f"ReleaseGate:{gate_id}")
        if node is None:
            raise SystemExit(f"generated KG missing ReleaseGate node for {gate_id}")
        props = node.get("properties", {})
        for key in ["gate_id", "status", "evidence"]:
            if props.get(key) != gate.get(key):
                raise SystemExit(f"generated KG ReleaseGate {gate_id} {key} drifted: {props.get(key)!r} != {gate.get(key)!r}")
    for platform in platform_matrix["platforms"]:
        platform_id = platform["id"]
        node = graph_nodes.get(f"Platform:{platform_id}")
        if node is None:
            raise SystemExit(f"generated KG missing Platform node for {platform_id}")
        props = node.get("properties", {})
        for key in ["id", "priority", "required_evidence", "status"]:
            if props.get(key) != platform.get(key):
                raise SystemExit(f"generated KG Platform {platform_id} {key} drifted: {props.get(key)!r} != {platform.get(key)!r}")
        if props.get("key") != platform_id:
            raise SystemExit(f"generated KG Platform {platform_id} key drifted: {props.get('key')!r} != {platform_id!r}")
        if props.get("evidence") != platform.get("evidence"):
            raise SystemExit(f"generated KG Platform {platform_id} evidence drifted: {props.get('evidence')!r} != {platform.get('evidence')!r}")
    graph_edges = {
        (record.get("from"), record.get("label"), record.get("to"))
        for record in graph_records
        if record.get("record_type") == "edge"
    }
    for manifest_path in REQUIRED_GRAPH_MANIFEST_SOURCES:
        node_id = graph_manifest_node_id(manifest_path)
        node = graph_nodes.get(node_id)
        if node is None:
            raise SystemExit(f"generated KG missing Manifest node for {manifest_path}")
        props = node.get("properties", {})
        if props.get("manifest_id") != manifest_path or props.get("repo_path") != manifest_path:
            raise SystemExit(f"generated KG Manifest {manifest_path} metadata drifted")
        if (node_id, "DECLARES_SOURCE", "RuntimeProvider:browseforge-chromium") not in graph_edges:
            raise SystemExit(f"generated KG Manifest {manifest_path} missing DECLARES_SOURCE edge")
    runtime_artifacts = load_json("knowledge/manifests/runtime-artifacts.json")
    source_acquisition = load_json("knowledge/manifests/source-acquisition.json")
    required_artifact_fields = set(runtime_artifacts.get("required_artifact_fields", []))
    supported_package_platforms = set(runtime_artifacts.get("supported_package_platforms", []))
    artifact_platforms = {artifact.get("platform") for artifact in runtime_artifacts.get("artifacts", [])}
    missing_artifact_contracts = sorted(artifact_platforms - supported_package_platforms)
    if missing_artifact_contracts:
        raise SystemExit(f"runtime-artifacts packaged platforms missing runtime asset contracts: {missing_artifact_contracts}")
    unsupported_package_platforms = runtime_artifacts.get("unsupported_package_platforms", {})
    for platform in artifact_platforms:
        if platform in unsupported_package_platforms:
            raise SystemExit(f"runtime-artifacts packages unsupported platform without runtime asset contract: {platform}")
    validate_runtime_artifact_consistency(runtime_artifacts, source_acquisition)
    validate_native_build_automation(source_acquisition, runtime_artifacts)
    validate_source_build_outputs(source_acquisition, runtime_artifacts)
    validate_release_gate_artifact_evidence(release_gates, runtime_artifacts)
    native_artifact_preflight = load_json("knowledge/manifests/native-artifact-preflight.json")
    validate_native_artifact_preflight(native_artifact_preflight, runtime_artifacts)
    signing_policy = load_json("knowledge/manifests/signing-policy.json")
    validate_signing_policy(signing_policy, runtime_artifacts, platform_matrix)
    release_status = load_json("knowledge/manifests/release-status.json")
    validate_release_status(release_status)
    for artifact in runtime_artifacts.get("artifacts", []):
        artifact_id = artifact["artifact_id"]
        node_id = f"RuntimeArtifact:{artifact_id}"
        node = graph_nodes.get(node_id)
        if node is None:
            raise SystemExit(f"generated KG missing RuntimeArtifact node for {artifact_id}")
        props = node.get("properties", {})
        missing_fields = sorted(required_artifact_fields - props.keys())
        if missing_fields:
            raise SystemExit(f"generated KG RuntimeArtifact {artifact_id} missing fields: {missing_fields}")
        for key in ["runtime_id", "runtime_version", "platform", "os", "arch", "browser_version", "source_ref", "patchset_id", "wrapper_version", "sha256", "size_bytes", "sbom_path", "provenance_path", "release_channel"]:
            if props.get(key) != artifact.get(key):
                raise SystemExit(f"generated KG RuntimeArtifact {artifact_id} {key} drifted: {props.get(key)!r} != {artifact.get(key)!r}")
        if props.get("release_grade") is not True or props.get("status") != "packaged":
            raise SystemExit(f"generated KG RuntimeArtifact {artifact_id} must be release_grade packaged")
        for edge in [
            (node_id, "GENERATED_FROM", "RuntimeProvider:browseforge-chromium"),
            (node_id, "BUILT_FOR", f"Platform:{artifact['platform']}"),
            (node_id, "TARGETS_PLATFORM", f"Platform:{artifact['platform']}"),
        ]:
            if edge not in graph_edges:
                raise SystemExit(f"generated KG missing artifact edge: {edge}")
        stale_linux_missing = [
            record for record in graph_records
            if record.get("record_type") == "edge"
            and record.get("to") == f"Platform:{artifact['platform']}"
            and record.get("properties", {}).get("status") == "missing_artifact"
        ]
        if stale_linux_missing:
            raise SystemExit(f"generated KG still links {artifact['platform']} to missing artifact blockers")

    for row in detector_summary.get("rows", []):
        path = ROOT / row["path"]
        evidence = load_json(path)
        if evidence["artifact_id"] not in {artifact["artifact_id"] for artifact in runtime_artifacts.get("artifacts", [])}:
            continue
        run_node = f"DetectorRun:{evidence['run_id']}"
        evidence_node = f"EvidenceArtifact:{evidence['evidence_id']}"
        artifact_node = f"RuntimeArtifact:{evidence['artifact_id']}"
        if run_node not in graph_nodes:
            raise SystemExit(f"generated KG missing DetectorRun node for {evidence['run_id']}")
        if evidence_node not in graph_nodes:
            raise SystemExit(f"generated KG missing EvidenceArtifact node for {evidence['evidence_id']}")
        for edge in [
            (run_node, "RUNS_DETECTOR", f"Detector:{evidence['detector']['detector_id']}"),
            (run_node, "TESTS_ARTIFACT", artifact_node),
            (run_node, "TARGETS_ARTIFACT", artifact_node),
            (run_node, "PRODUCES_EVIDENCE", evidence_node),
            (evidence_node, "SUPPORTS_GATE", "ReleaseGate:live-detector-evidence"),
        ]:
            if edge not in graph_edges:
                raise SystemExit(f"generated KG missing detector evidence edge: {edge}")

    print("runtime framework validation ok")


if __name__ == "__main__":
    main()
