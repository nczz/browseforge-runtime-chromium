# KB/KG Completeness Assessment

Verdict: the current KB/KG is strong enough to start framework and contract work, but not yet strong enough to claim absolute confidence for cross-platform anti-detect browser implementation. The missing material is not project-management polish; it is engineering evidence required before modifying Chromium, shipping binaries, or promising detector resistance.

## Confidence levels

| Area | Current confidence | Reason |
| --- | --- | --- |
| BrowseForge runtime contract | High | BrowseForge v2 seams are mapped: `runtime_id`, descriptor capabilities, REST/MCP/workflow/dashboard, browser manager, Docker seed/install, release preflight. |
| Runtime repo architecture | High | Monorepo boundary, contracts, detector evidence schema, KB manifest, and KG schema exist and validate. |
| Cloak-like wrapper target behavior | Medium | Reference CloakBrowser source KB and KG exist; flag/proxy/WebRTC behavior is known, but this repo has no wrapper implementation yet. |
| Chromium fork implementation | Low | No Chromium base version, upstream source import strategy, build matrix, or patch inventory exists yet. |
| Cross-platform build confidence | Low | No Linux/macOS/Windows runtime artifacts, build scripts, dependency matrix, or signing/provenance evidence exists yet. |
| Detector confidence | Medium-low | Detector model and schema exist; reference findings exist in BrowseForge docs; this runtime has no detector runs. |
| Fingerprint patch confidence | Low | Surface model exists, but no patch-to-surface-to-detector evidence graph exists for this runtime. |
| Playwright compatibility | Medium-low | BrowseForge and Cloak reference behavior are known; this runtime has no bind endpoint spike. |
| Legal/supply-chain confidence | Medium | Apache-2.0 repo policy exists; Chromium license/NOTICE/SBOM/provenance work is not complete. |
| Knowledge graph operational coverage | Medium | Runtime, BrowseForge, CloakBrowser, and Camoufox graphs are indexed; generated cross-repo route edges are zero because the runtime repo is still contract/docs only. |

## Multi-dimensional expert review

### 1. Browser engine and fork strategy

Required before implementation:

- choose Chromium base version and branch policy
- define source acquisition method (`depot_tools`, tarball mirror, or patch-only import)
- define patch format and upstream tracking
- define build cache policy and excluded paths
- map source-level anti-detect surfaces to Chromium subsystems

Missing in KB/KG:

- `ChromiumBase` node with concrete version/ref
- patch inventory with touched files/symbols
- source graph for imported Chromium subset or patch files
- build dependency graph per OS

### 2. Cloak-like wrapper behavior

Required before implementation:

- wrapper entrypoint contract
- supported flags/env vars
- proxy parser and WebRTC exit-IP policy
- user-data-dir ownership and lock handling
- remote debugging / Playwright bind behavior
- default stealth args and collision policy with BrowseForge-managed flags

Current evidence:

- CloakBrowser source KB has launch/proxy/WebRTC/Playwright behavior.
- BrowseForge launch contract records managed flags and collision guard requirements.

Missing in KB/KG:

- `Wrapper` node accepting each managed flag
- tests proving wrapper accepts/rejects collisions
- run traces from actual wrapper execution

### 3. Fingerprint surface completeness

Required surfaces:

- UA and Client Hints
- timezone and locale
- screen/window/DPR
- hardware concurrency/device memory
- Canvas
- WebGL strings, params, extensions, shader precision, rendered pixel output
- AudioContext
- fonts and font metrics
- WebRTC
- permissions/features
- storage quota/incognito signals
- automation/CDP/headless signals
- proxy/IP coherence
- TLS/HTTP fingerprinting if owned by runtime scope

Current evidence:

- surface model exists in docs
- detector schema exists
- reference BrowseForge report identifies WebGL/audio/incognito/fonts gaps

Missing in KB/KG:

- patch nodes for each surface
- detector runs for this runtime
- risk acceptance records
- deterministic replay evidence for seed-driven behavior

### 4. Cross-platform runtime packaging

Required platforms:

- Linux x64 first
- macOS arm64/x64 second
- Windows x64 third
- Linux arm64 only after Docker/KasmVNC/browser runtime validation

Missing in KB/KG:

- platform dependency manifests
- artifact manifests with real SHA-256 values
- notarization/signing policy for macOS/Windows
- SBOM/provenance generation evidence
- runtime install/seed smoke outputs

### 5. BrowseForge integration readiness

Required before BrowseForge consumes artifact:

- runtime descriptor registration
- config defaults
- binary download/install/status
- Docker seed path
- launcher dispatch
- REST/MCP/workflow/dashboard tests
- Playwright bind spike
- release preflight enforcement

Current evidence:

- exact BrowseForge files and symbols are mapped in `docs/browseforge-integration.md`.

Missing in KB/KG:

- actual BrowseForge adapter branch/PR
- `RuntimeArtifact -> CompatibleWith -> BrowseForgeConsumer` graph backed by tests
- integration test evidence

### 6. Detector and benchmark evidence

Required before anti-detect claim:

- sanitized run schema per detector
- reproducible harness
- run matrix by platform, proxy/direct, head/headless if supported
- detector evidence linked to patch/risk/surface nodes
- historical regression comparison

Missing in KB/KG:

- detector runner implementation
- actual detector reports for this runtime
- evidence artifacts and graph edges

### 7. Legal, open-source, and supply-chain

Required before public release:

- Chromium license and NOTICE preservation
- third-party dependency inventory
- patch provenance
- SBOM
- build provenance
- artifact checksums/signatures
- acceptable-use/security policy

Current evidence:

- Apache-2.0 project license and SECURITY policy exist.

Missing in KB/KG:

- Chromium NOTICE plan
- dependency SBOM generation
- provenance attestation
- artifact signing policy

## Must-fill gaps before development beyond contracts

1. Create Chromium base/version decision record.
2. Create wrapper executable contract and starter implementation plan.
3. Import or reference Cloak-like wrapper semantics as graph seed nodes.
4. Create platform dependency manifests.
5. Create detector harness plan and minimal smoke script contract.
6. Create KG seed data for managed flags, surfaces, detectors, and BrowseForge consumer points.
7. Add source manifests for CloakBrowser, Camoufox, BrowseForge, and future Chromium upstream.
8. Add graph queries that fail when source coverage, detector evidence, or artifact metadata is incomplete.

## Development gate

Allowed now:

- contract work
- wrapper skeleton
- manifest/schema work
- detector harness skeleton
- BrowseForge adapter design
- Chromium base selection

Not allowed yet:

- claim production anti-detect readiness
- ship runtime binaries
- integrate into BrowseForge release channel
- claim WebGL/font/audio/storage resistance
- claim cross-platform support

The KB/KG must evolve from planning graph to evidence graph before release-grade development is trusted.
