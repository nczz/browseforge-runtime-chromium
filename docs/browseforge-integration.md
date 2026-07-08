# BrowseForge Integration Map

This document records the BrowseForge v2 integration seams a Chromium-family runtime must satisfy before it is consumed by BrowseForge.

## Runtime provider contract

Observed BrowseForge contract points:

| BrowseForge path | Contract imposed on this runtime |
| --- | --- |
| `internal/runtime/runtime.go` | Runtime IDs are validated through `Registry`; descriptors expose `id`, `display_name`, `family`, `binary_path`, `enabled`, and capabilities. |
| `internal/config/config.go` | Runtime availability and binary paths flow through `runtimes.<id>`. Current Chromium settings are CloakBrowser-specific and must be generalized or mapped intentionally. |
| `config.default.json` | A new provider needs `runtimes.browseforge-chromium` with `family: chromium`, display name, binary path, enabled policy, and settings. |
| `internal/profile/store.go` | Persisted profiles must carry `runtime_id`; legacy `engine` is rejected. Chromium seed identity uses `fingerprint_seed`. |
| `internal/api/router.go` | REST create/update/import/restore validates enabled runtime IDs and generates seed when `supports_seed_fingerprint` is true. |
| `internal/api/sessions.go` | Session responses must report concrete `runtime_id`; Playwright clients use the session bind endpoint. |
| `internal/mcp/server.go` | MCP tools reject `engine`, validate `runtime_id`, and launch through the same manager. |
| `internal/mcp/web_session_pool.go` | Agent web sessions require `supports_agent_web_sessions` and `supports_playwright_bind`. |
| `internal/workflow/engine.go` | Workflow `create_profile` forwards `runtime_id` and must keep rejecting `engine`. |
| `internal/browser/manager.go` | Registered runtimes require a concrete launcher dispatch path. |
| `internal/browser/launch_chromium.go` | Chromium launch policy owns profile data dir, downloads dir, proxy, seed, timezone, locale, WebRTC, platform, fonts, storage quota, GPU/cache fallback, and Playwright persistent context. |
| `internal/browser/download.go` | Browser cache layout uses `browsers/<runtime_id>/.version`; runtime artifacts require executable discovery and version markers. |
| `cmd/server/cli_runtime.go` | `browsers status` and `browsers install` must enumerate the runtime safely. |
| `docker/entrypoint.sh` | Docker seed logic must include packaged `/opt/browseforge/browsers/<runtime_id>` and `.version`. |
| `scripts/release-preflight.sh` | Release gate needs an enforceable runtime spike analogous to `REQUIRE_CLOAKBROWSER=1`. |

## Minimal BrowseForge adapter work

1. Register `browseforge-chromium` descriptor in BrowseForge runtime registry.
2. Add config defaults and capability advertisement.
3. Add or generalize Chromium runtime settings.
4. Add binary download/install/status and Docker seed behavior.
5. Add launcher dispatch that returns `Session.RuntimeID == browseforge-chromium`.
6. Keep profile/API/MCP/workflow public contract on `runtime_id`; never introduce a new `engine` value.
7. Add tests for registry, REST, MCP, workflow, launch args, Docker install/status, and Playwright Bind spike.

## Release gates before BrowseForge consumes the runtime

- Registry descriptor tests pass.
- REST `/api/runtimes` exposes the runtime and profile create/update accepts it only when enabled.
- MCP `list_runtimes`, `create_profile`, and `open_browser` pass.
- Workflow `create_profile` forwards `runtime_id` unchanged.
- Browser launch unit tests cover managed flags and proxy/fingerprint policies.
- Runtime spike launches a persistent context, binds Playwright, connects a second client, and navigates a page.
- Docker image seeds `/app/browsers/browseforge-chromium` from packaged runtime cache.
- Detector evidence has no unmitigated high/critical risks.
