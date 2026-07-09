// BrowseForge compatibility gaps for a proposed runtime artifact
MATCH (bf:BrowseForgeConsumer {consumer_id: 'browseforge-main'})-[:REQUIRES_CAPABILITY]->(cap:Capability)
MATCH (a:RuntimeArtifact {artifact_id: $artifact_id})
WHERE NOT (a)-[:DECLARES_CAPABILITY]->(cap)
RETURN a.artifact_id AS artifact,
       cap.name AS missing_capability
ORDER BY missing_capability;

// Cross-repo impact of changing a runtime flag
MATCH (f:RuntimeFlag {name: $flag})<-[:MANAGES_FLAG]-(bf:BrowseForgeConsumer)
OPTIONAL MATCH (bf)-[:USES_CONFIG_FIELD]->(cfg:ConfigField)-[:EMITS_FLAG]->(f)
OPTIONAL MATCH (bf)-[:USES_PROFILE_FIELD]->(pf:ProfileField)-[:EMITS_FLAG]->(f)
OPTIONAL MATCH (f)-[:CONTROLS_SURFACE]->(surface:FingerprintSurface)<-[:CHECKS_SURFACE]-(det:Detector)
RETURN f.name AS flag,
       collect(DISTINCT cfg.path) AS config_fields,
       collect(DISTINCT pf.path) AS profile_fields,
       collect(DISTINCT surface.surface_id) AS surfaces,
       collect(DISTINCT det.detector_id) AS detectors;

// Required source manifests represented in the runtime seed graph
MATCH (p:RuntimeProvider {runtime_id: $runtime_id})
OPTIONAL MATCH (m:Manifest)-[:DECLARES_SOURCE]->(p)
RETURN p.runtime_id AS runtime_id,
       collect(DISTINCT m.manifest_id) AS manifest_ids,
       CASE WHEN count(DISTINCT m) = 0 THEN 'missing_manifest_sources' ELSE 'covered' END AS manifest_source_status;
