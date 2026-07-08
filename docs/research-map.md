# Expert Research Map

This is the upfront research scope required before implementation proceeds beyond framework and contracts.

## Runtime implementation research

| Area | Required evidence |
| --- | --- |
| Chromium base | Upstream version, source ref, license notices, build reproducibility, platform support. |
| Patchset | Patch IDs, touched files/symbols, fingerprint surfaces, risk level, detector coverage, upstream status. |
| Wrapper | Entrypoints, flags, env vars, profile directory policy, proxy policy, WebRTC policy, crash/cache policy. |
| Playwright | Persistent context support, bind endpoint support, second-client connect behavior, navigation smoke. |
| Profile storage | Per-profile user-data-dir, lock behavior, cache isolation, migration policy, rollback behavior. |
| Docker | Linux dependencies, sandbox policy, KasmVNC compatibility, `/app/browsers` seed behavior, version markers. |
| Release | Artifact naming, checksums, SBOM, provenance, GitHub Release/GHCR policy. |

## Anti-detect research

The runtime owns these surfaces. Each surface needs implementation notes, detector coverage, risk status, and mitigation evidence.

- user agent and browser version coherence
- client hints and platform metadata
- timezone and locale coherence with direct/proxy geography
- screen/window/device metrics
- hardware concurrency and device memory
- Canvas
- WebGL vendor/renderer/parameters/extensions/shader precision/pixel output
- AudioContext
- fonts and font metrics
- WebRTC local/public IP exposure
- storage quota and persistent/incognito signals
- permissions and feature availability
- CDP/automation signals
- TLS/HTTP network fingerprints when inside project scope

## Detector baseline

Initial detector set:

| Detector | Purpose |
| --- | --- |
| SannySoft | Automation/headless sanity baseline. |
| BrowserLeaks | Canvas, WebGL, audio, fonts, WebRTC, client hints. |
| CreepJS | Cross-surface consistency and bot-likeness. |
| Pixelscan | Fingerprint consistency and font/platform mismatch. |
| iphey | Trustworthiness and high-level identity consistency. |
| BrowserScan | Authenticity deductions, WebGL/audio/incognito/proxy signals. |

Detector results must be sanitized before commit. Raw captures belong in generated artifacts or private storage unless scrubbed.

## Research completeness rule

A runtime feature is not ready when it exists in code. It is ready when the graph links it to:

```text
source implementation -> runtime contract -> BrowseForge consumer point -> test -> detector/evidence or accepted risk
```
