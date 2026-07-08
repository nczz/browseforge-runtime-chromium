# Runtime Monorepo Architecture

`browseforge-runtime-chromium` is a focused monorepo for an open Chromium-family anti-detect runtime. BrowseForge remains the orchestrator and consumes versioned runtime artifacts; this repository owns the runtime implementation, patch inventory, detector evidence, knowledge manifests, and graph schema.

## Boundary

```text
BrowseForge main repo
  runtime registry
  profile/API/MCP/dashboard/workflow contracts
  Docker seed/install consumer path
  release gates that prove BrowseForge can drive the runtime

browseforge-runtime-chromium
  Chromium fork/patchset
  Cloak-like wrapper and launch policy
  runtime artifact packaging
  detector benchmark evidence
  KB source manifests
  KG schema, queries, and generated graph exports
```

The two repositories meet at versioned release artifacts and the `runtime_id=browseforge-chromium` provider contract.

## Source of truth

| Concern | Source of truth |
| --- | --- |
| Runtime identity and capabilities | `contracts/runtime.manifest.json` |
| BrowseForge compatibility | `contracts/browseforge-integration.contract.json` |
| Anti-detect surfaces and detector gates | `docs/fingerprint-surfaces.md`, `detectors/evidence-schema.json` |
| KB indexing scope | `knowledge/kb-manifest.json` |
| KG labels, edges, and readiness queries | `graph/schema/runtime-kg.schema.md`, `graph/queries/*.cypher` |
| Large binaries, graph dumps, detector raw outputs | GitHub Releases or generated artifacts, not git source |

## Runtime principles

1. The runtime must be explicit: profiles use `runtime_id`, never legacy `engine`.
2. Browser family is metadata. Chromium-family behavior must not leak into Firefox-family code paths.
3. BrowseForge-managed launch flags must be modeled, tested, and protected from `extra_args` collision.
4. Every high-risk fingerprint surface must connect to a patch, launch flag, detector, evidence record, or accepted risk.
5. Release artifacts require checksums, SBOM/provenance, detector summary, KB export, and KG export.

## Initial architecture decision

Use a runtime monorepo rather than many small repos. This keeps wrapper, Chromium patchset, detector evidence, KB manifests, and KG schema together while keeping BrowseForge clean. BrowseForge should never own Chromium patch internals; it should consume signed/pinned runtime artifacts.
