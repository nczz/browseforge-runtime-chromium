# KB/KG Completeness Assessment

Verdict: the current KB/KG is now sufficient for BrowseForge adapter and local dogfood wiring work. It is not sufficient for release-grade Chromium patch, detector-pass, artifact, or provenance claims.

## Current observed state

| Area | Confidence | Evidence | Remaining blocker |
| --- | --- | --- | --- |
| Runtime repository KB | High for repo contracts | `BrowseForge Chromium Runtime Knowledge Base` is ready; repo validation passes. | KB must be refreshed after each source change. |
| Runtime repository KG | Medium-high for repo entry points | codebase-memory project `Users-chun-Projects-browseforge-runtime-chromium` is ready; source-controlled seed graph exists at `generated/kg/runtime.graph.jsonl` and `generated/kg/runtime.ttl`. | The MCP graph is still a source-code graph; custom runtime-evidence semantics live in generated seed files until imported by a dedicated runtime graph loader. |
| BrowseForge consumer contract | High | `reference-sources.json` links the BrowseForge project KB/KG; BrowseForge runtime registry and launch symbols are searchable. | Current BrowseForge adapter is still blocked in `release-gates.json` until launch dispatch, defaults/install/status/capabilities, and end-to-end smoke evidence are complete. |
| CloakBrowser / Camoufox references | Medium-high | Source KBs exist for CloakBrowser v146 and Camoufox v135; reference manifests point to local indexed sources. | Cloak/Camoufox behavior remains reference material, not proof that browseforge-chromium behaves the same. |
| Chromium upstream base | Medium for decision, low for source evidence | `patchset.json` and `browser/chromium-base.json` select Chromium `refs/tags/150.0.7871.101` / commit `51b83660c3609f271ccbbd65785bf7e50a21312d`. | No Chromium checkout, source index, or build graph exists locally. |
| Runtime wrapper | Medium | `cmd/browseforge-runtime-chromium`, `internal/launcher/config.go`, and `internal/launcher/launch.go` validate wrapper/config/launch planning. | No patched Chromium binary exists; local dogfood can only use an explicitly configured external Chromium-family browser. |
| Fingerprint surface graph | Medium for planned surfaces | Seed graph includes `FingerprintSurface`, `RuntimeFlag`, `Detector`, `DetectorRun`, and blocker `EvidenceArtifact` nodes. | No live detector evidence exists; planned/missing nodes are blockers, not pass evidence. |
| Packaging and provenance | Medium for contract tests | `build/package_runtime.py` and packaging tests cover package plan/checksum/SBOM placeholder mechanics. | Release-grade SBOM/provenance requires a real Chromium artifact and dependency snapshot. |

## Required graph semantics now represented

The source-controlled seed graph contains the required runtime evidence relationship vocabulary:

- `BrowseForgeConsumer -[:REQUIRES_CAPABILITY]-> Capability`
- `RuntimeProvider -[:DECLARES_CAPABILITY]-> Capability`
- `RuntimeArtifact -[:BUILT_FOR]-> Platform`
- `RuntimeArtifact -[:GENERATED_FROM]-> RuntimeProvider`
- `Patch -[:MODIFIES_SOURCE]-> SourceFile/Symbol`
- `Patch/RuntimeFlag -[:CONTROLS_SURFACE]-> FingerprintSurface`
- `Detector -[:CHECKS_SURFACE]-> FingerprintSurface`
- `DetectorRun -[:RUNS_DETECTOR]-> Detector`
- `DetectorRun -[:TARGETS_ARTIFACT]-> RuntimeArtifact`
- `DetectorRun -[:PRODUCES_EVIDENCE]-> EvidenceArtifact`
- `EvidenceArtifact -[:SUPPORTS_GATE]-> ReleaseGate`
- `RuntimeProvider -[:REFERENCES_SOURCE]-> KnowledgeSource`

The generated graph deliberately includes a `RuntimeArtifact` with `status: missing`. That node is a blocker record, not an artifact claim.

## Release-gate state

Passed gates:

- `chromium-base-selected`: Chromium M150 tag/ref/base commit selected.
- `wrapper-contract-tests`: wrapper/config/launch contract tests exist.
- `detector-harness-contract-tests`: detector target listing, matrix planning, validation, and sanitized-evidence rejection are covered.
- `packaging-contract-tests`: package planning, missing-browser rejection, zip packaging, and checksum behavior are covered.

Blocked gates:

- `browseforge-adapter-merged`: BrowseForge has partial runtime_id plumbing, but the adapter is not release-complete until manager dispatch/defaults/install/status/doctor/capabilities and end-to-end smoke evidence exist.
- `chromium-source-indexed`: no local Chromium source checkout/index exists for the selected ref.
- `runtime-artifact-produced`: `runtime-artifacts.json` is empty; no patched browser artifact exists.
- `live-detector-evidence`: detector runs need a real runtime binary.
- `sbom-provenance-release-assets`: release-grade SBOM/provenance needs a real artifact and dependency snapshot.

## Permitted next work

Allowed now:

1. Finish BrowseForge adapter plumbing against a configured external Chromium-family browser.
2. Run local dogfood smoke with an explicitly configured browser binary and mark it as dogfood-only evidence.
3. Keep KG/Kb manifests current and reindex after changes.
4. Package local dogfood wrapper artifacts for checksum/provenance mechanics only.

Not allowed yet:

1. Claim a release-grade BrowseForge Chromium runtime.
2. Claim detector pass, anti-detect resistance, WebGL/font/audio/storage fixes, or cross-platform support.
3. Create a release tag or publish release artifacts as production-ready.
4. Treat local Chrome/Chromium dogfood evidence as a patched BrowseForge runtime artifact.

## Shortest unblock path

1. Complete BrowseForge adapter dispatch/default install/status/capability paths for `runtime_id: browseforge-chromium`.
2. Configure BrowseForge with a real local Chromium-family binary for dogfood only.
3. Run a BrowseForge smoke launch and Playwright bind check.
4. Package the wrapper and record checksums as non-release dogfood artifacts.
5. Acquire/index selected Chromium source, then replace the missing artifact blocker with a real build artifact record only after an actual build succeeds.
