#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "knowledge" / "manifests" / "source-acquisition.json"
DEFAULT_WORKDIR = Path(os.environ.get("BROWSEFORGE_CHROMIUM_WORKDIR", "/Users/chun/Projects/browser-source/browseforge-chromium"))
DEFAULT_GIT_CACHE = Path(os.environ.get("GIT_CACHE_PATH", "/Users/chun/Projects/browser-source/git-cache"))


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


def build_plan(workdir: Path = DEFAULT_WORKDIR, git_cache: Path = DEFAULT_GIT_CACHE) -> SourcePlan:
    manifest = load_manifest()
    chromium = manifest["chromium_base"]
    depot_tools = workdir / "depot_tools"
    src = workdir / "src"
    path_prefix = str(depot_tools) + os.pathsep + os.environ.get("PATH", "")
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
                command=["gclient", "sync", "--with_branch_heads", "--with_tags"],
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
                creates=str(src / "out" / "BrowseForgeDev" / "args.gn"),
            ),
        ],
    )
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

def check_tools(plan: SourcePlan) -> dict:
    depot_path = plan.path_prefix
    chromium_src = Path(plan.chromium_src_dir)
    head = git_head(chromium_src)
    return {
        "fetch": shutil.which("fetch", path=depot_path),
        "gclient": shutil.which("gclient", path=depot_path),
        "gn": shutil.which("gn", path=depot_path),
        "ninja": shutil.which("ninja", path=depot_path),
        "autoninja": shutil.which("autoninja", path=depot_path),
        "chromium_src_exists": chromium_src.is_dir(),
        "chromium_src_head": head,
        "chromium_src_matches_manifest": head == plan.base_commit if head else False,
        "depot_tools_exists": Path(plan.depot_tools_dir).is_dir(),
    }


def emit_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


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
        emit_json({"plan": asdict(plan), "tools": check_tools(plan)})
        return
    if not args.execute:
        raise SystemExit("acquire requires --execute because Chromium checkout/build dependencies are large")
    execute(plan, args.step)


if __name__ == "__main__":
    main()
