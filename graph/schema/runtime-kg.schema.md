# Runtime Knowledge Graph Schema

The runtime knowledge graph models source, artifacts, anti-detect surfaces, detector evidence, and BrowseForge consumer contracts.

## Labels

| Label | Key | Purpose |
| --- | --- | --- |
| `RuntimeProvider` | `runtime_id` | Versioned browser runtime provider. |
| `RuntimeArtifact` | `artifact_id` | Release artifact for a platform. |
| `ChromiumBase` | `base_ref` | Upstream Chromium source/version base. |
| `PatchSet` | `patchset_id` | Coherent patch collection. |
| `Patch` | `patch_id` | Individual source patch. |
| `SourceFile` | `repo_path` | Runtime or BrowseForge source file. |
| `Symbol` | `qualified_name` | Function/class/type/constant. |
| `Wrapper` | `wrapper_id` | Runtime launcher/wrapper implementation. |
| `RuntimeFlag` | `name` | Managed launch flag or env-controlled behavior. |
| `ConfigField` | `path` | BrowseForge/runtime config field. |
| `ProfileField` | `path` | Persisted profile field. |
| `Capability` | `name` | Runtime capability exposed to BrowseForge. |
| `Platform` | `key` | OS/arch target. |
| `Detector` | `detector_id` | Detector site or harness. |
| `DetectorRun` | `run_id` | One detector execution. |
| `EvidenceArtifact` | `evidence_id` | Sanitized report, screenshot, DOM extract, or summary. |
| `FingerprintSurface` | `surface_id` | Fingerprintable browser surface. |
| `Risk` | `risk_id` | Open/accepted/resolved anti-detect or integration risk. |
| `Mitigation` | `mitigation_id` | Patch/config/test action that reduces a risk. |
| `BrowseForgeConsumer` | `consumer_id` | BrowseForge side of the contract. |
| `APISurface` | `route` | REST route. |
| `MCPSurface` | `tool` | MCP tool. |
| `Release` | `version` | Runtime release. |
| `Manifest` | `manifest_id` | Source or artifact manifest. |
| `KBChunk` | `chunk_id` | Indexed knowledge chunk. |

## Edge types

### Runtime structure

```text
(RuntimeProvider)-[:BUILDS_ON]->(ChromiumBase)
(RuntimeProvider)-[:HAS_WRAPPER]->(Wrapper)
(RuntimeProvider)-[:HAS_PATCHSET]->(PatchSet)
(PatchSet)-[:INCLUDES_PATCH]->(Patch)
(Patch)-[:TOUCHES_FILE]->(SourceFile)
(Patch)-[:TOUCHES_SYMBOL]->(Symbol)
(RuntimeProvider)-[:PRODUCES_ARTIFACT]->(RuntimeArtifact)
(RuntimeArtifact)-[:TARGETS_PLATFORM]->(Platform)
(RuntimeArtifact)-[:DECLARES_CAPABILITY]->(Capability)
```

### Anti-detection

```text
(Patch)-[:MODIFIES_SURFACE]->(FingerprintSurface)
(RuntimeFlag)-[:CONTROLS_SURFACE]->(FingerprintSurface)
(Detector)-[:CHECKS_SURFACE]->(FingerprintSurface)
(DetectorRun)-[:RUNS_DETECTOR]->(Detector)
(DetectorRun)-[:TESTS_ARTIFACT]->(RuntimeArtifact)
(DetectorRun)-[:OBSERVED_RISK]->(Risk)
(EvidenceArtifact)-[:EVIDENCES]->(DetectorRun)
(Mitigation)-[:MITIGATES]->(Risk)
(Patch)-[:ADDRESSES_RISK]->(Risk)
```

### BrowseForge cross-repo contract

```text
(BrowseForgeConsumer)-[:CONSUMES_PROVIDER]->(RuntimeProvider)
(BrowseForgeConsumer)-[:REQUIRES_CAPABILITY]->(Capability)
(BrowseForgeConsumer)-[:USES_CONFIG_FIELD]->(ConfigField)
(BrowseForgeConsumer)-[:USES_PROFILE_FIELD]->(ProfileField)
(BrowseForgeConsumer)-[:MANAGES_FLAG]->(RuntimeFlag)
(BrowseForgeConsumer)-[:EXPOSES_API]->(APISurface)
(BrowseForgeConsumer)-[:EXPOSES_MCP]->(MCPSurface)
(MCPSurface)-[:DEPENDS_ON_CAPABILITY]->(Capability)
(RuntimeArtifact)-[:COMPATIBLE_WITH]->(BrowseForgeConsumer)
```

### Knowledge provenance

```text
(Manifest)-[:DECLARES_SOURCE]->(SourceFile)
(KBChunk)-[:DERIVED_FROM]->(SourceFile)
(KBChunk)-[:MENTIONS_SYMBOL]->(Symbol)
(KBChunk)-[:MENTIONS_SURFACE]->(FingerprintSurface)
```

## Required seed nodes

Initial seed nodes must include:

- `RuntimeProvider{runtime_id:'browseforge-chromium', family:'chromium'}`
- capabilities from `contracts/runtime.manifest.json`
- managed flags from BrowseForge Chromium launch contract
- fingerprint surfaces from `docs/fingerprint-surfaces.md`
- detectors from `knowledge/manifests/detectors.json`
- `BrowseForgeConsumer{consumer_id:'browseforge-main', min_version:'v2.0.0'}`

## Generated exports

Graph materializations are generated from source manifests and should be published as release artifacts unless intentionally small:

```text
graph.db.zst
generated/kg/runtime.graph.jsonl
generated/kg/runtime.ttl
```
