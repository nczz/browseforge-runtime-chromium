# browseforge-runtime-chromium

Open Chromium-family anti-detect runtime package for BrowseForge.

This repository is the source of truth for a BrowseForge-compatible Chromium runtime: Chromium fork/patchset, Cloak-like launcher, fingerprint research, detector evidence, release artifacts, and knowledge-graph material live here. BrowseForge itself consumes this runtime through versioned release artifacts and a small runtime provider adapter.

## Architecture stance

- Keep BrowseForge as the orchestrator: profiles, REST API, MCP, dashboard, workflow, backup/restore, and runtime registry.
- Keep this repository as the Chromium runtime monorepo: browser fork patches, launcher wrapper, build pipeline, detector evidence, KB manifests, and graph schemas.
- Release runtime artifacts independently, then pin them from BrowseForge.
- Commit source, contracts, schemas, and summarized evidence. Do not commit build outputs, browser binaries, secrets, user profiles, cookies, or proxy credentials.

## Repository map

| Path | Purpose |
| --- | --- |
| `contracts/` | Stable runtime contracts consumed by BrowseForge and release tooling. |
| `docs/` | Architecture, BrowseForge integration map, anti-detect research plan, and release gates. |
| `wrapper/` | Cloak-like runtime launcher source and launch-policy implementation. |
| `browser/` | Chromium fork notes, patch inventory, upstream tracking, and source import instructions. |
| `build/` | Reproducible build and packaging scripts. |
| `docker/` | Runtime build/test containers. |
| `detectors/` | Detector harness contracts and sanitized evidence schemas. |
| `knowledge/` | Knowledge-base manifests and indexing scope. |
| `graph/` | Knowledge-graph schema, starter queries, and export policy. |
| `tests/` | Unit, integration, Playwright, Docker, and detector regression tests. |
| `examples/` | BrowseForge config/profile examples for local integration. |

## Runtime identity

Initial runtime contract:

```text
runtime_id: browseforge-chromium
family: chromium
BrowseForge minimum: v2.0.0
primary goal: Chromium-family anti-detect runtime with Playwright bind support
```

The runtime is expected to expose persistent browser sessions, deterministic fingerprint inputs, native proxy support, WebRTC masking controls, profile-isolated user data directories, and Docker-friendly launch behavior.

## Development phases

1. Contract and research baseline: runtime manifest, KB manifest, KG schema, detector evidence schema.
2. Wrapper baseline: launcher command, config parser, profile directory handling, remote debugging endpoint, Playwright bind smoke.
3. Chromium fork baseline: upstream tracking, patch inventory, reproducible build pipeline.
4. Anti-detect baseline: fingerprint surface map, detector harness, sanitized evidence reports.
5. BrowseForge integration: provider adapter, Docker seed/install flow, REST/MCP/dashboard/workflow tests.
6. Release readiness: artifacts, checksums, graph export, KB export, detector summary, CI evidence.

## Open-source hygiene

This project is intended to be open source. Keep sensitive operational material out of git:

- no API tokens
- no proxy credentials
- no cookies or real browser profiles
- no private account data
- no raw detector captures containing identifiable IP/account data

Use sanitized evidence under `detectors/` and release large generated artifacts through GitHub Releases or GHCR.
