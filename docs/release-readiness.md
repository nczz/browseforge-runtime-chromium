# Release Readiness Gates

A runtime release is ready for BrowseForge integration only after the source, artifact, detector, KB, and KG gates pass.

## Source gates

- Runtime manifest validates.
- Patchset manifest references committed patch files or explicit external source refs.
- Wrapper entrypoint is documented and tested.
- Managed launch flags are collision-protected.
- Profile directory policy is deterministic and rollback-safe.

## Artifact gates

- Every platform artifact has download URL, SHA-256, size, source ref, patchset ID, wrapper version, SBOM path, and provenance path.
- `build/package_runtime.py` must reject any platform not explicitly listed in `runtime-artifacts.json.supported_package_platforms`; linux-x64, macos-arm64, macos-x64, and windows-x64 are supported alpha package platforms by contract.
- `linux-x64`, `macos-arm64`, and `windows-x64` currently have committed SBOM/provenance/checksum metadata. `macos-x64` must remain blocked until a real package, checksum, SBOM, and provenance exist; launch and detector evidence are explicitly not required for this packaged-only alpha release and must remain disclosed as absent.
- Browser binary path matches `contracts/runtime.manifest.json`.
- `.version` marker behavior is specified.
- Docker install/seed path is tested.

## BrowseForge gates

- `GET /api/runtimes` exposes the descriptor.
- Profile create/update/import/restore persists `runtime_id`.
- Session launch reports concrete `runtime_id`.
- Playwright Bind endpoint accepts a second client.
- MCP agent web sessions are enabled only when Bind/session behavior is proven.
- Docker `browsers status` reports ready.

## Detector gates

- Required detector set has run for release artifacts.
- High/critical fingerprint surfaces have pass evidence or accepted risk.
- Evidence is sanitized and linked to surfaces/patches/flags.
- Detector score comparisons are generated from sanitized evidence and keep release-grade status false while baselines are partial.
- `live-detector-evidence` cannot pass while `detector-summary.json` still has coverage gaps or blocking findings.
- External proxy/IP coherence evidence must include sanitized proxy exit-region and detector geolocation-region fields; local CONNECT proxy routing evidence is accepted only as routing proof.
- `scripts/validate.py` enforces that `detectors/evidence-schema.json` admits every committed sanitized evidence harness, matrix, and storage shape, including headed Xvfb and routing-only local proxy observations.
- `scripts/validate.py` also rejects a release-grade fingerprint surface manifest while any `knowledge/manifests/fingerprint-surface-status.json` surface remains a release blocker, and it rejects a passed `live-detector-evidence` gate while those blockers remain.
- Detector regressions block release unless explicitly accepted.
- `docs/anti-detection-matrix.md` is the operator-facing matrix. Any `not_tested`, `blocked`, or `warn` release risk there must either be resolved or explicitly accepted before release-grade publication.

## Knowledge gates

- KB manifest is current and excludes secrets/build outputs.
- Knowledge base builds from committed source manifests.
- KG schema validates and generated graph has no missing release-critical edges.
- Development-readiness Cypher pack returns no blockers for the release.

## Release payload

Each release should publish:

```text
browseforge-runtime-chromium-<version>-linux-x64.zip
browseforge-runtime-chromium-<version>-macos-arm64.zip
browseforge-runtime-chromium-<version>-macos-x64.zip
browseforge-runtime-chromium-<version>-windows-x64.zip
checksums.txt
SBOM
provenance attestation
runtime.manifest.json
patchset manifest
sanitized detector summary
detector-score-comparison.json
knowledge-export.jsonl
graph.db.zst or equivalent graph export
```

The release workflow fails closed when any expected zip or metadata payload is missing, empty, or absent from `dist/checksums.txt`. Do not replace a missing package with a zero-byte file, placeholder zip, mock binary, or another platform's artifact.

## Unsigned alpha release notes

Release notes for `v0.1.0-alpha.0` must state:

- All packages are unsigned alpha artifacts, not production-ready signed releases.
- Users must verify SHA-256 checksums before running any package.
- macOS users may need to allow the app manually or run `xattr -dr com.apple.quarantine /path/to/Chromium.app`.
- Windows users may see SmartScreen/Defender warnings and must self-authorize until Authenticode signing is configured.
- Linux users must verify the SHA-256 entry in `checksums.txt` before execution.
- macOS x64 remains untested for launch/detectors; release notes may publish it only as packaged-only after a real package, checksum, SBOM, and provenance exist.
