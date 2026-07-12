# KB/KG Completeness Assessment

Verdict: the current KB/KG is sufficient for the source/build baseline, BrowseForge adapter handoff, packaged linux-x64/macos-arm64/windows-x64 alpha artifacts, the macOS x64 package blocker, and committed detector-evidence traceability. It is not yet a production-ready release because macOS x64 lacks a real package and all packaged artifacts are still unsigned alpha outputs.

## Current observed state

| Area | Confidence | Evidence | Remaining blocker |
| --- | --- | --- | --- |
| Runtime repository KB | High for repo contracts | `BrowseForge Chromium Runtime Knowledge Base` is ready; repo validation passes. | KB must be refreshed after each source change. |
| Runtime repository KG | Medium-high for runtime evidence | codebase-memory project `Users-chun-Projects-browseforge-runtime-chromium` is ready; source-controlled seed graph exists at `generated/kg/runtime.graph.jsonl` and `generated/kg/runtime.ttl`; committed `RuntimeArtifact`, `DetectorRun`, and `EvidenceArtifact` records are represented. | The MCP graph is still primarily a source-code graph; custom runtime-evidence semantics live in generated seed files until imported by a dedicated runtime graph loader. |
| BrowseForge consumer contract | High | `release-gates.json` records BrowseForge commit `aba5248` dispatching `browseforge-chromium`, writing a profile-scoped native stealth persona config with `persona_id_hash` and `origin_salt_key`, and preserving trimmed proxy region metadata through profile/group storage; adapter smoke passed via `--browseforge-stealth-config` plus `--browseforge-stealth-mode=enabled`; local dogfood evidence covers runtime config, profile create, session launch, runtime_id reporting, profile isolation, and Playwright Bind. | Keep adapter smoke evidence current as BrowseForge changes. |
| CloakBrowser / Camoufox references | Medium-high | Source KBs exist for CloakBrowser v146 and Camoufox v135; reference manifests point to local indexed sources. | Cloak/Camoufox behavior remains reference material, not proof that browseforge-chromium behaves the same. |
| Chromium upstream base | High for pinned baseline | `patchset.json`, `browser/chromium-base.json`, and `source-acquisition.json` select Chromium `refs/tags/150.0.7871.101` / commit `51b83660c3609f271ccbbd65785bf7e50a21312d`; external checkout, Linux Docker baseline, macOS arm64 build output, Windows x64 portable layout, and source-level patches are recorded. | Host-specific dependency profiles must stay isolated with `BROWSEFORGE_CHROMIUM_HOST_WORKDIR` and `BROWSEFORGE_CHROMIUM_LINUX_WORKDIR`. |
| Runtime wrapper and artifacts | High for alpha artifacts | `runtime-artifacts.json` records linux-x64, macos-arm64, and windows-x64 artifacts with SHA-256, size, SBOM, provenance, os, arch, browser version, source ref, patchset ID, and wrapper version; `native-artifact-preflight.json` records the macOS x64 package blocker. | macOS x64 still needs a real Chromium.app package; release asset URL/signature are still dev placeholders; production release needs an explicit signing/notarization policy. |
| Fingerprint surface graph | High for existing alpha detector evidence | Seed graph includes `FingerprintSurface`, `RuntimeFlag`, `Detector`, committed `DetectorRun`, `EvidenceArtifact`, and release-gate support edges. Linux direct/headed evidence and macOS arm64 headed external-proxy evidence cover the committed alpha detector evidence; accepted score-comparison risk remains explicit for non-GA policy. | macOS x64 and Windows x64 release-grade detector evidence remain incomplete. |
| Packaging and provenance | High for existing alpha artifacts | `build/package_runtime.py`, packaging tests, `unzip -t`, JSON metadata checks, and runtime artifact manifests cover packaged artifact/SBOM/provenance mechanics for explicitly supported package platforms. | macOS x64 package/SBOM/provenance are missing; release-grade publishing/signing is not complete. |

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
- `DetectorRun -[:TESTS_ARTIFACT]-> RuntimeArtifact`
- `DetectorRun -[:OBSERVED_SURFACE]-> FingerprintSurface`
- `DetectorRun -[:PRODUCES_EVIDENCE]-> EvidenceArtifact`
- `EvidenceArtifact -[:SUPPORTS_GATE]-> ReleaseGate`
- `RuntimeProvider -[:REFERENCES_SOURCE]-> KnowledgeSource`

The generated graph includes packaged runtime artifacts for linux-x64, macos-arm64, and windows-x64 as alpha evidence, plus the macOS x64 platform/package blocker. Missing-artifact and signing policy nodes are release-status inputs until a real macOS x64 package and release-grade signing policy exist.

## Release-gate state

Current gates:

- `chromium-base-selected`: Chromium M150 tag/ref/base commit selected.
- `wrapper-contract-tests`: wrapper/config/launch contract tests exist.
- `detector-harness-contract-tests`: detector target listing, matrix planning, validation, and sanitized-evidence rejection are covered.
- `packaging-contract-tests`: package planning, missing-browser rejection, zip packaging, platform layout, and checksum behavior are covered.
- `browseforge-adapter-merged`: BrowseForge commit `aba5248` dispatches `browseforge-chromium` and preserves native persona/proxy metadata.
- `chromium-source-indexed`: source acquisition and patch status manifests record the pinned checkout and source-level patchset state.
- `runtime-artifact-produced`: blocked until the macOS x64 package exists; alpha artifacts exist for linux-x64, macos-arm64, and windows-x64.
- `live-detector-evidence`: blocked for release-grade publication while macOS x64 has no detector run and committed detector evidence still has accepted non-GA gaps.
- `sbom-provenance-release-assets`: blocked until macOS x64 has SBOM/provenance/checksum metadata.

Remaining release-grade blockers:

- `signing-policy:linux-x64`: alpha Linux archive is unsigned.
- `signing-policy:macos-arm64`: alpha macOS archive is unsigned and not notarized.
- `signing-policy:windows-x64`: alpha Windows archive is unsigned.
- `signing-policy:macos-x64`: macOS x64 package is missing and still needs Developer ID signing/notarization policy.
## Permitted next work

Allowed now:

1. Replace unsigned alpha policy with a real release-grade signing/notarization policy when credentials and publication process are available.
2. Keep KB/KG manifests current and reindex after changes.
3. Keep BrowseForge adapter smoke evidence current as BrowseForge changes.
4. Extend GA detector coverage, especially Windows native runs and stricter font/audio corpus parity, without reopening alpha release-gate blockers.

Not allowed yet:

1. Claim a production-ready signed cross-platform BrowseForge Chromium runtime.
2. Publish release artifacts as production-ready until `signing-policy.json` allows release-grade publication for every supported package platform.
3. Treat unsigned alpha archives as signed/notarized release assets.

## Shortest unblock path

1. Produce the real macOS x64 Chromium.app package, checksum, SBOM, and provenance; disclose that launch smoke and detector evidence are absent.
2. Decide the release-grade signing policy for Linux archives, macOS Developer ID/notarization, and Windows Authenticode.
3. Repackage or attest signed artifacts, update `runtime-artifacts.json` and `signing-policy.json`, then regenerate release status and objective audit.
4. Re-run `scripts/validate.py`, focused release/status tests, and refresh KB/KG indexes.
