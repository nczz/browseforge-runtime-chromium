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
- `build/package_runtime.py` must reject any platform not explicitly listed in `runtime-artifacts.json.supported_package_platforms`; add macOS/Windows only after committed runtime asset contracts cover bundle/layout, signing, SBOM/provenance, and detector evidence.
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

## Knowledge gates

- KB manifest is current and excludes secrets/build outputs.
- Knowledge base builds from committed source manifests.
- KG schema validates and generated graph has no missing release-critical edges.
- Development-readiness Cypher pack returns no blockers for the release.

## Release payload

Each release should publish:

```text
runtime artifact(s)
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
