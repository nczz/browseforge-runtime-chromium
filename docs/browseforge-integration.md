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

## Current handoff status

`browseforge-chromium` is ready for alpha/validation consumption by BrowseForge, not for default production rollout. The current artifact contract supports `linux-x64`, `macos-arm64`, and `windows-x64` alpha packages with SHA-256, SBOM, provenance, detector summary, and generated KG evidence. Release-grade publication remains blocked by platform signing/notarization policy, so BrowseForge should expose this runtime as opt-in until signed artifacts or an explicit unsigned-release policy exist.

BrowseForge should treat `contracts/runtime.manifest.json` as the consumer contract:

| Contract field | BrowseForge behavior |
| --- | --- |
| `browseforge.runtime_id` | Use `browseforge-chromium` in profiles, REST, MCP, workflows, sessions, backups, and dashboard state. |
| `browseforge.profile_field` | Persist `runtime_id`; do not reintroduce `engine`. |
| `binary.<platform>.relative_path` | Point `runtimes.browseforge-chromium.binary_path` at the unpacked browser binary (`chrome`, `Chromium.app/Contents/MacOS/Chromium`, or `chrome.exe`), not at the standalone wrapper. |
| `capabilities.playwright_bind` | Keep Playwright Bind session behavior enabled after smoke evidence passes. |
| `capabilities.seed_fingerprint` | Generate and persist `fingerprint_seed` for Chromium-family profiles. |
| `capabilities.structured_config` | Pass native persona and proxy metadata through the BrowseForge Chromium config switches. |

## BrowseForge user-side setup

1. Publish or place the alpha artifact for the host platform. Until GitHub Release URLs are committed, use a local path or Docker seed path.
2. Unpack the artifact under a runtime-owned directory such as `browsers/browseforge-chromium/`.
3. Set `runtimes.browseforge-chromium.enabled=true`.
4. Set `runtimes.browseforge-chromium.binary_path` to the platform browser binary inside the unpacked artifact:

   ```text
   linux-x64:    browsers/browseforge-chromium/chrome
   macos-arm64:  browsers/browseforge-chromium/Chromium.app/Contents/MacOS/Chromium
   windows-x64:  browsers/browseforge-chromium/chrome.exe
   ```

5. Keep `default_runtime_id` on the existing stable runtime unless the operator explicitly opts into the alpha runtime.
6. Create profiles with `runtime_id=browseforge-chromium`; never use a new `engine` value.
7. If a proxy is configured, set a redacted `proxy.region` such as `us-ny` or `tw-taipei` so the native WebRTC persona can stay coherent without storing raw IPs or credentials.
8. Verify `/api/runtimes`, profile create, session launch, Playwright Bind, MCP `list_runtimes`, MCP `open_browser`, workflow `create_profile`, and Docker `browsers status` before enabling it for shared users.

Minimal local config:

```json
{
  "default_runtime_id": "camoufox",
  "runtimes": {
    "browseforge-chromium": {
      "enabled": true,
      "binary_path": "browsers/browseforge-chromium/chrome",
      "family": "chromium",
      "display_name": "BrowseForge Chromium",
      "settings": {
        "auto_safe_gpu_fallback": true,
        "isolated_runtime_cache": true,
        "repair_transient_cache_on_launch_failure": true,
        "fingerprint_platform": "auto",
        "target_platform_policy": "warn",
        "native_mode": "enabled",
        "plugins_pdf": "enabled",
        "extra_args": []
      }
    }
  }
}
```

Minimal REST profile:

```bash
curl -X POST http://127.0.0.1:19280/api/profiles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Chromium Alpha Profile",
    "runtime_id": "browseforge-chromium",
    "proxy": {
      "type": "socks5",
      "host": "proxy.example.com",
      "port": 1080,
      "username": "user",
      "password": "pass",
      "region": "us-ny"
    }
  }'
```

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
