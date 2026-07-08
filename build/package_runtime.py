#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as host_platform
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def ensure_file(path: Path, executable: bool = False):
    if not path.is_file():
        raise SystemExit(f'missing file: {path}')
    if executable and os.name != 'nt' and not (path.stat().st_mode & 0o111):
        raise SystemExit(f'not executable: {path}')

def package(args):
    platform_id = args.platform
    out_dir = Path(args.output_dir)
    stage = out_dir / 'stage' / f'browseforge-runtime-chromium-{args.runtime_version}-{platform_id}'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    browser = Path(args.browser_binary)
    wrapper = Path(args.wrapper_binary)
    ensure_file(browser, executable=True)
    ensure_file(wrapper, executable=True)
    shutil.copy2(browser, stage / browser.name)
    shutil.copy2(wrapper, stage / 'browseforge-runtime-chromium')
    shutil.copy2(ROOT / 'contracts/runtime.manifest.json', stage / 'runtime.manifest.json')
    manifest = {
        'artifact_id': f'browseforge-runtime-chromium-{args.runtime_version}-{platform_id}',
        'runtime_id': 'browseforge-chromium',
        'runtime_version': args.runtime_version,
        'platform': platform_id,
        'browser_version': args.browser_version,
        'source_ref': args.source_ref,
        'patchset_id': args.patchset_id,
        'wrapper_version': args.wrapper_version,
        'release_channel': args.release_channel,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'files': []
    }
    for file in sorted(stage.iterdir()):
        if file.is_file():
            manifest['files'].append({'path': file.name, 'sha256': sha256(file), 'size_bytes': file.stat().st_size})
    (stage / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    (stage / 'SBOM.json').write_text(json.dumps({'schema': 'placeholder-spdx-compatible', 'runtime_id': 'browseforge-chromium', 'files': manifest['files']}, indent=2, sort_keys=True) + '\n')
    (stage / 'provenance.json').write_text(json.dumps({'builder': 'build/package_runtime.py', 'host_os': host_platform.platform(), 'source_ref': args.source_ref, 'created_at': manifest['created_at']}, indent=2, sort_keys=True) + '\n')
    archive = out_dir / f'{manifest["artifact_id"]}.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(stage.iterdir()):
            zf.write(file, arcname=f'{stage.name}/{file.name}')
    checksum = sha256(archive)
    (out_dir / 'checksums.txt').write_text(f'{checksum}  {archive.name}\n')
    print(json.dumps({'archive': str(archive), 'sha256': checksum}, indent=2))
    return 0

def plan(args):
    matrix = json.loads((ROOT / 'knowledge/manifests/platform-matrix.json').read_text())
    print(json.dumps({'platforms': matrix['platforms'], 'global_release_requirements': matrix['global_release_requirements']}, indent=2))
    return 0

def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)
    p = sub.add_parser('plan'); p.set_defaults(func=plan)
    p = sub.add_parser('package')
    p.add_argument('--platform', required=True)
    p.add_argument('--browser-binary', required=True)
    p.add_argument('--wrapper-binary', required=True)
    p.add_argument('--output-dir', default='dist')
    p.add_argument('--runtime-version', required=True)
    p.add_argument('--browser-version', required=True)
    p.add_argument('--source-ref', required=True)
    p.add_argument('--patchset-id', default='unpatched')
    p.add_argument('--wrapper-version', default='v0.1.0-alpha.0')
    p.add_argument('--release-channel', default='dev')
    p.set_defaults(func=package)
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main())
