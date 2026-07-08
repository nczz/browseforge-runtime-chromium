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

// Source manifests that point at stale refs versus latest indexed KG source
MATCH (m:Manifest)-[:DECLARES_SOURCE]->(sf:SourceFile)
WHERE sf.indexed_ref IS NOT NULL
  AND m.ref IS NOT NULL
  AND sf.indexed_ref <> m.ref
RETURN m.manifest_id AS manifest,
       sf.repo_path AS source,
       m.ref AS manifest_ref,
       sf.indexed_ref AS indexed_ref
ORDER BY manifest, source;
