#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as host_platform
import shutil
import subprocess
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

def file_record(path: Path, *, root: Path | None = None) -> dict[str, object]:
    return {
        'path': path.relative_to(root).as_posix() if root is not None else path.name,
        'sha256': sha256(path),
        'size_bytes': path.stat().st_size,
    }

def optional_file_sha256(path: Path) -> str | None:
    return sha256(path) if path.is_file() else None

def git_commit() -> str | None:
    proc = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if proc.returncode != 0:
        return None
    commit = proc.stdout.strip()
    return commit or None

def build_sbom(manifest: dict[str, object]) -> dict[str, object]:
    artifact_id = str(manifest['artifact_id'])
    files = manifest['files']
    return {
        'artifact_id': artifact_id,
        'runtime_id': manifest['runtime_id'],
        'runtime_version': manifest['runtime_version'],
        'platform': manifest['platform'],
        'browser_version': manifest['browser_version'],
        'source_ref': manifest['source_ref'],
        'patchset_id': manifest['patchset_id'],
        'generated_by': 'build/package_runtime.py',
        'spdxVersion': 'SPDX-2.3',
        'dataLicense': 'CC0-1.0',
        'SPDXID': 'SPDXRef-DOCUMENT',
        'name': artifact_id,
        'documentNamespace': f'https://browseforge.local/sbom/{artifact_id}',
        'creationInfo': {
            'creators': ['Tool: build/package_runtime.py'],
            'created': manifest['created_at'],
        },
        'packages': [
            {
                'name': artifact_id,
                'SPDXID': 'SPDXRef-Package-browseforge-runtime-chromium',
                'versionInfo': manifest['runtime_version'],
                'downloadLocation': 'NOASSERTION',
                'filesAnalyzed': True,
                'checksums': [{'algorithm': 'SHA256', 'checksumValue': f['sha256']} for f in files],
            }
        ],
        'files': [
            {
                'path': f['path'],
                'sha256': f['sha256'],
                'size': f['size_bytes'],
                'fileName': f['path'],
                'SPDXID': f'SPDXRef-File-{idx}',
                'checksums': [{'algorithm': 'SHA256', 'checksumValue': f['sha256']}],
                'fileTypes': ['BINARY'] if f['path'] != 'runtime.manifest.json' else ['TEXT'],
                'sizeBytes': f['size_bytes'],
            }
            for idx, f in enumerate(files, start=1)
        ],
        'relationships': [
            {
                'spdxElementId': 'SPDXRef-DOCUMENT',
                'relationshipType': 'DESCRIBES',
                'relatedSpdxElement': 'SPDXRef-Package-browseforge-runtime-chromium',
            }
        ],
    }

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
    staged_browser = stage / browser.name
    staged_wrapper = stage / 'browseforge-runtime-chromium'
    staged_runtime_manifest = stage / 'runtime.manifest.json'
    source_acquisition = Path(args.source_acquisition_manifest)
    patchset_manifest = Path(args.patchset_manifest)
    shutil.copy2(browser, staged_browser)
    shutil.copy2(wrapper, staged_wrapper)
    shutil.copy2(ROOT / 'contracts/runtime.manifest.json', staged_runtime_manifest)
    created_at = datetime.now(timezone.utc).isoformat()
    files = [file_record(file) for file in sorted(stage.iterdir()) if file.is_file()]
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
        'created_at': created_at,
        'source_acquisition_sha256': optional_file_sha256(source_acquisition),
        'patchset_manifest_sha256': optional_file_sha256(patchset_manifest),
        'runtime_manifest_sha256': sha256(staged_runtime_manifest),
        'browser_binary_sha256': sha256(staged_browser),
        'wrapper_binary_sha256': sha256(staged_wrapper),
        'git_commit': git_commit(),
        'files': files,
    }
    provenance = {
        'builder': 'build/package_runtime.py',
        'host_os': host_platform.platform(),
        'runtime_id': manifest['runtime_id'],
        'runtime_version': manifest['runtime_version'],
        'platform': manifest['platform'],
        'browser_version': manifest['browser_version'],
        'source_ref': manifest['source_ref'],
        'patchset_id': manifest['patchset_id'],
        'source_acquisition_manifest': source_acquisition.as_posix(),
        'source_acquisition_sha256': manifest['source_acquisition_sha256'],
        'patchset_manifest': patchset_manifest.as_posix(),
        'patchset_manifest_sha256': manifest['patchset_manifest_sha256'],
        'runtime_manifest_sha256': manifest['runtime_manifest_sha256'],
        'browser_binary_sha256': manifest['browser_binary_sha256'],
        'wrapper_binary_sha256': manifest['wrapper_binary_sha256'],
        'git_commit': manifest['git_commit'],
        'release_channel': manifest['release_channel'],
        'created_at': created_at,
    }
    (stage / 'artifact-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    (stage / 'SBOM.json').write_text(json.dumps(build_sbom(manifest), indent=2, sort_keys=True) + '\n')
    (stage / 'provenance.json').write_text(json.dumps(provenance, indent=2, sort_keys=True) + '\n')
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
    p.add_argument('--source-acquisition-manifest', default=str(ROOT / 'knowledge/manifests/source-acquisition.json'))
    p.add_argument('--patchset-manifest', default=str(ROOT / 'knowledge/manifests/patchset.json'))
    p.set_defaults(func=package)
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main())
