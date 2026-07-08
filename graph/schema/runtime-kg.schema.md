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
(RuntimeProvider)-[:DECLARES_CAPABILITY]->(Capability)
(RuntimeProvider)-[:REFERENCES_SOURCE]->(KnowledgeSource)
(PatchSet)-[:INCLUDES_PATCH]->(Patch)
(Patch)-[:MODIFIES_SOURCE]->(SourceFile)
(Patch)-[:MODIFIES_SOURCE]->(Symbol)
(Patch)-[:CONTROLS_SURFACE]->(FingerprintSurface)
(RuntimeProvider)<-[:GENERATED_FROM]-(RuntimeArtifact)
(RuntimeArtifact)-[:TARGETS_PLATFORM]->(Platform)
(RuntimeArtifact)-[:BUILT_FOR]->(Platform)
```

### Anti-detection

```text
(RuntimeFlag)-[:CONTROLS_SURFACE]->(FingerprintSurface)
(Detector)-[:CHECKS_SURFACE]->(FingerprintSurface)
(DetectorRun)-[:RUNS_DETECTOR]->(Detector)
(DetectorRun)-[:TARGETS_ARTIFACT]->(RuntimeArtifact)
(DetectorRun)-[:PRODUCES_EVIDENCE]->(EvidenceArtifact)
(DetectorRun)-[:OBSERVED_RISK]->(Risk)
(EvidenceArtifact)-[:SUPPORTS_GATE]->(ReleaseGate)
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

Graph materializations are generated from source manifests and should be published as release artifacts unless intentionally small. The source-controlled seed files represent contract and blocker state; they are not live detector evidence and must not be used as release proof:

```text
graph.db.zst
generated/kg/runtime.graph.jsonl
generated/kg/runtime.ttl
generated/kg/detector-evidence.jsonl
```
