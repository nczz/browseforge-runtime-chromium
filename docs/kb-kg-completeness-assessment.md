# KB/KG Completeness Assessment

Verdict: the current KB/KG is sufficient for the Linux x64 packaged runtime, source/build baseline, BrowseForge adapter handoff, and committed detector-evidence traceability. It is not yet sufficient for a production-ready cross-platform anti-detect release because the live detector matrix still has accepted warnings/blockers for proxy/IP coherence, full detector score comparison, native/headed parity, and non-Linux artifacts.

## Current observed state

| Area | Confidence | Evidence | Remaining blocker |
| --- | --- | --- | --- |
| Runtime repository KB | High for repo contracts | `BrowseForge Chromium Runtime Knowledge Base` is ready; repo validation passes. | KB must be refreshed after each source change. |
| Runtime repository KG | Medium-high for runtime evidence | codebase-memory project `Users-chun-Projects-browseforge-runtime-chromium` is ready; source-controlled seed graph exists at `generated/kg/runtime.graph.jsonl` and `generated/kg/runtime.ttl`; Linux x64 `RuntimeArtifact` and committed `DetectorRun`/`EvidenceArtifact` records are represented. | The MCP graph is still primarily a source-code graph; custom runtime-evidence semantics live in generated seed files until imported by a dedicated runtime graph loader. |
| BrowseForge consumer contract | High | `release-gates.json` records BrowseForge commit `5dc2749` dispatching `browseforge-chromium` and writing a profile-scoped native stealth persona config with `persona_id_hash` and `origin_salt_key`, passed via `--browseforge-stealth-config` plus `--browseforge-stealth-mode=enabled`; local dogfood evidence covers runtime config, profile create, session launch, runtime_id reporting, profile isolation, and Playwright Bind. | Keep adapter smoke evidence current as BrowseForge changes. |
| CloakBrowser / Camoufox references | Medium-high | Source KBs exist for CloakBrowser v146 and Camoufox v135; reference manifests point to local indexed sources. | Cloak/Camoufox behavior remains reference material, not proof that browseforge-chromium behaves the same. |
| Chromium upstream base | High for Linux x64 baseline | `patchset.json`, `browser/chromium-base.json`, and `source-acquisition.json` select Chromium `refs/tags/150.0.7871.101` / commit `51b83660c3609f271ccbbd65785bf7e50a21312d`; external checkout, Linux deps sync, Docker GN generation, and patched Linux build are recorded. | Native macOS/Windows builds and unpatched baseline comparison remain absent. |
| Runtime wrapper and artifact | High for Linux x64 packaged artifact | `runtime-artifacts.json` records `browseforge-runtime-chromium-v0.1.0-alpha.0-linux-x64` with SHA-256, size, SBOM, provenance, os, arch, browser version, source ref, patchset ID, and wrapper version. | Non-Linux artifacts remain missing; release asset URL/signature are still dev placeholders. |
| Fingerprint surface graph | Medium for Linux detector smoke | Seed graph includes `FingerprintSurface`, `RuntimeFlag`, `Detector`, committed `DetectorRun`, `EvidenceArtifact`, and release-gate support edges. | Audio/fonts still need full detector score comparison; proxy/IP coherence needs external exit/geolocation evidence; cross-platform drift remains open. |
| Packaging and provenance | High for dev Linux x64 artifact | `build/package_runtime.py`, packaging tests, `unzip -t`, and JSON metadata checks cover packaged artifact/SBOM/provenance mechanics. | Release-grade publishing/signing and non-Linux packaging are not complete. |

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

The generated graph includes the packaged Linux x64 `RuntimeArtifact` as release-grade evidence and keeps explicit missing-artifact blocker nodes only for platforms without packaged artifacts.

## Release-gate state

Passed gates:

- `chromium-base-selected`: Chromium M150 tag/ref/base commit selected.
- `wrapper-contract-tests`: wrapper/config/launch contract tests exist.
- `detector-harness-contract-tests`: detector target listing, matrix planning, validation, and sanitized-evidence rejection are covered.
- `packaging-contract-tests`: package planning, missing-browser rejection, zip packaging, and checksum behavior are covered.

Warning/blocking gates:

- `live-detector-evidence`: Linux x64 has committed SannySoft, BrowserLeaks, Pixelscan, iphey, BrowserScan, and CreepJS evidence, including headless and headed/Xvfb coverage for several detectors; `detector-summary.json` now records 13 remaining required matrix coverage gaps with `required_evidence` labels for native/host, Docker/container, direct network, and external proxy exit-IP/geolocation evidence, so the full headed/proxy/native/cross-platform matrix is explicit but incomplete. `scripts/validate.py` now also rejects a passed `live-detector-evidence` gate while `detector-score-comparison.json` still contains baseline gaps, evidence gaps, or warning comparisons.
- `proxy/IP coherence`: local CONNECT proxy routing evidence exists, validator logic rejects release-matrix `proxy` evidence unless it carries sanitized external proxy exit-region and detector geolocation-region fields, and the BrowserLeaks WebRTC collector now records sanitized ICE candidate metadata plus public/private IP-literal counts without committing raw addresses; no external proxy exit-IP/geolocation detector run is recorded.
- `AudioContext` and `fonts`: page-context and CreepJS/BrowserLeaks/Pixelscan bounded probes are recorded; `detector-score-comparison.json` now compares CreepJS headless/headed audio deltas, records passing BrowserLeaks and Pixelscan headless-vs-headed bounded AudioContext comparisons, records a passing Pixelscan headless-vs-headed font availability comparison, and compares BrowserLeaks/CreepJS font glyph/metric hashes while explicitly listing BrowserLeaks/Pixelscan score baselines plus native-headed font-corpus baseline gaps; release-grade BrowserLeaks/CreepJS/Pixelscan score baselines and platform corpus parity remain required.
- `WebGL`: configured vendor/renderer source patch and page-context evidence exist; the shared collector now escapes embedded SDP newlines correctly, so Linux headless BrowserLeaks/Pixelscan/iphey/BrowserScan/CreepJS/SannySoft evidence records sanitized extension count/hash, bounded parameter hash, shader precision hash, rendered pixel hash, and pixel dimensions. `detector-score-comparison.json` now records a passing BrowserLeaks-vs-BrowserScan WebGL metadata comparison with vendor/renderer, extension-profile, parameter, shader precision, and rendered-pixel match booleans. The remaining WebGL metadata gap is the legacy macOS local SannySoft row; headed/native detector confirmation remains required before release-grade WebGL claims.
- `cross-platform drift`: Linux Docker headless/headed evidence exists, and macOS arm64 local host headless SannySoft evidence now records a non-release warning with `HeadlessChrome` still present in UA; Windows plus native headed Linux/macOS release detector matrix remains absent.
- `non-Linux release artifacts`: macOS / Windows packaged runtime artifacts, SBOM, provenance, signing, and detector evidence remain absent; `build/package_runtime.py` rejects non-Linux platforms until a committed runtime asset contract exists.

## Permitted next work

Allowed now:

1. Continue closing detector-surface blockers for Linux x64: external proxy/IP coherence, AudioContext score comparison, font score/corpus parity, and native/headed matrix evidence.
2. Add non-Linux artifact/build evidence only after real macOS/Windows builds exist.
3. Keep KB/KG manifests current and reindex after changes.
4. Keep BrowseForge adapter smoke evidence current while preserving the Linux x64 runtime artifact as dev/alpha until release blockers close.

Not allowed yet:

1. Claim a production-ready cross-platform BrowseForge Chromium runtime.
2. Claim full detector pass, proxy/IP coherence, font/audio parity, or native platform support without direct detector evidence.
3. Create a stable release tag or publish release artifacts as production-ready.
4. Treat local Chrome/Chromium dogfood evidence as equivalent to the patched BrowseForge runtime artifact.

## Shortest unblock path

1. Run an external-proxy detector matrix for BrowserLeaks/Pixelscan/iphey/BrowserScan with sanitized exit-IP/geolocation evidence.
2. Add release-grade BrowserLeaks/CreepJS/Pixelscan score baselines for AudioContext and fonts; BrowserLeaks audio/fonts page classifiers intentionally return warning-level evidence until committed score baselines and corpus comparisons exist.
3. Run native/headed Linux and macOS detector passes, then add Windows only after a real Windows artifact exists.
4. Replace non-Linux missing-artifact blocker nodes with real artifact records only after builds, SBOM, provenance, signatures, and detector runs exist.
