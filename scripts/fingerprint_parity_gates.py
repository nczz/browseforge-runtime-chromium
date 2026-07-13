#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "knowledge" / "manifests" / "fingerprint-parity-gates.json"

REQUIRED_GATES = {
    "os-math-libm-parity": {
        "surface": "OS math/libm parity",
        "tool": "d8",
    },
    "css-hyphenation-text-layout-parity": {
        "surface": "CSS hyphenation/text layout parity",
        "tool": "content_shell",
    },
    "webaudio-backing-array-semantics": {
        "surface": "AudioContext backing-array semantics",
        "tool": "chrome",
    },
    "wasm-js-numeric-parity": {
        "surface": "WASM/JS numeric parity",
        "tool": "d8",
    },
}

CANDIDATE_BINARIES = {
    "d8": [
        "out/BrowseForgeDev/d8",
        "out/BrowseForgeLinuxDocker/d8",
        "out/BrowseForgeLinuxArm64Docker/d8",
    ],
    "content_shell": [
        "out/BrowseForgeDev/content_shell",
        "out/BrowseForgeLinuxDocker/content_shell",
        "out/BrowseForgeLinuxArm64Docker/content_shell",
    ],
    "chrome": [
        "out/BrowseForgeDev/chrome",
        "out/BrowseForgeLinuxDocker/chrome",
        "out/BrowseForgeLinuxArm64Docker/chrome",
    ],
}


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("runtime_id") != "browseforge-chromium":
        raise SystemExit("fingerprint parity gates runtime_id must be browseforge-chromium")
    if manifest.get("schema_version") != "1.0":
        raise SystemExit("fingerprint parity gates schema_version must be 1.0")
    gates = manifest.get("gates")
    if not isinstance(gates, list) or not gates:
        raise SystemExit("fingerprint parity gates manifest must contain gates")
    seen: dict[str, dict[str, Any]] = {}
    for gate in gates:
        if not isinstance(gate, dict):
            raise SystemExit("fingerprint parity gate entries must be objects")
        gate_id = gate.get("gate_id")
        if not isinstance(gate_id, str) or not gate_id:
            raise SystemExit("fingerprint parity gate missing gate_id")
        if gate_id in seen:
            raise SystemExit(f"duplicate fingerprint parity gate: {gate_id}")
        seen[gate_id] = gate
        required_fields = {
            "gate_id",
            "surface",
            "status",
            "release_blocker",
            "risk_level",
            "decision",
            "current_coverage",
            "oracle_status",
            "probe",
            "blocked_by",
        }
        missing = sorted(required_fields - gate.keys())
        if missing:
            raise SystemExit(f"fingerprint parity gate {gate_id} missing fields: {missing}")
        if gate["status"] not in {"blocked", "accepted", "not_applicable"}:
            raise SystemExit(f"fingerprint parity gate {gate_id} uses unsupported status {gate['status']!r}")
        if not isinstance(gate["release_blocker"], bool):
            raise SystemExit(f"fingerprint parity gate {gate_id} release_blocker must be boolean")
        if not isinstance(gate["probe"], dict):
            raise SystemExit(f"fingerprint parity gate {gate_id} probe must be an object")
        if not isinstance(gate["blocked_by"], list) or not gate["blocked_by"]:
            raise SystemExit(f"fingerprint parity gate {gate_id} blocked_by must be a non-empty list")
    missing_required = sorted(set(REQUIRED_GATES) - set(seen))
    if missing_required:
        raise SystemExit(f"fingerprint parity gates missing required gates: {missing_required}")
    for gate_id, expected in REQUIRED_GATES.items():
        surface = seen[gate_id].get("surface")
        if surface != expected["surface"]:
            raise SystemExit(f"fingerprint parity gate {gate_id} surface drifted: {surface!r}")


def _chromium_src(root: Path) -> Path:
    manifest_path = root / "knowledge" / "manifests" / "source-acquisition.json"
    if manifest_path.is_file():
        try:
            source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_dir = source_manifest.get("chromium_base", {}).get("source_dir")
            if isinstance(source_dir, str) and source_dir:
                return Path(source_dir)
        except json.JSONDecodeError:
            pass
    return Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")


def _candidate_status(chromium_src: Path, tool: str) -> dict[str, Any]:
    candidates = [chromium_src / rel for rel in CANDIDATE_BINARIES[tool]]
    available = [path for path in candidates if path.is_file()]
    return {
        "tool": tool,
        "available": bool(available),
        "selected": str(available[0]) if available else None,
        "candidates": [str(path) for path in candidates],
    }


def probe_plan(root: Path = ROOT, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = manifest if manifest is not None else load_manifest(root / "knowledge" / "manifests" / "fingerprint-parity-gates.json")
    validate_manifest(manifest)
    chromium_src = _chromium_src(root)
    tool_status = {
        tool: _candidate_status(chromium_src, tool)
        for tool in sorted({entry["tool"] for entry in REQUIRED_GATES.values()})
    }
    gates = []
    manifest_gates = {gate["gate_id"]: gate for gate in manifest["gates"]}
    for gate_id, expected in REQUIRED_GATES.items():
        gate = manifest_gates[gate_id]
        tool = expected["tool"]
        available = tool_status[tool]["available"]
        gates.append(
            {
                "gate_id": gate_id,
                "surface": gate["surface"],
                "required_tool": tool,
                "probe_status": "ready" if available else "blocked_missing_tool",
                "selected_binary": tool_status[tool]["selected"],
                "oracle_status": gate["oracle_status"],
                "release_blocker": gate["release_blocker"],
            }
        )
    return {
        "runtime_id": manifest["runtime_id"],
        "schema_version": manifest["schema_version"],
        "chromium_src": str(chromium_src),
        "tools": tool_status,
        "gates": gates,
        "ready": all(gate["probe_status"] == "ready" for gate in gates),
    }


def _filtered_gates(manifest: dict[str, Any], surface: str | None) -> list[dict[str, Any]]:
    gates = manifest["gates"]
    if surface is None:
        return gates
    return [gate for gate in gates if gate["gate_id"] == surface or gate["surface"] == surface]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect BrowseForge fingerprint parity policy gates")
    sub = parser.add_subparsers(dest="command", required=True)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--manifest", type=Path, default=MANIFEST)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--manifest", type=Path, default=MANIFEST)
    list_parser.add_argument("--surface")
    probe_parser = sub.add_parser("probe-plan")
    probe_parser.add_argument("--manifest", type=Path, default=MANIFEST)
    probe_parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    validate_manifest(manifest)
    if args.command == "validate":
        print("fingerprint parity gates ok")
        return 0
    if args.command == "list":
        payload = {
            "runtime_id": manifest["runtime_id"],
            "gates": _filtered_gates(manifest, args.surface),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == "probe-plan":
        print(json.dumps(probe_plan(args.root, manifest), indent=2, sort_keys=True))
        return 0
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
