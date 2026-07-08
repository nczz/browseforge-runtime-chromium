// Knowledge source coverage for release-grade runtime development
// Expected result: no blocking source class is missing before implementation proceeds past skeleton work.
MATCH (p:RuntimeProvider {runtime_id: $runtime_id})
OPTIONAL MATCH (p)-[:REFERENCES_SOURCE]->(s:KnowledgeSource)
WITH p, collect(s.source_id) AS source_ids
RETURN p.runtime_id AS runtime_id,
       source_ids,
       CASE WHEN 'browseforge-consumer' IN source_ids THEN 'ok' ELSE 'missing_browseforge_consumer' END AS browseforge_source,
       CASE WHEN 'cloakbrowser-reference' IN source_ids THEN 'ok' ELSE 'missing_cloakbrowser_reference' END AS cloak_source,
       CASE WHEN 'camoufox-reference' IN source_ids THEN 'ok' ELSE 'missing_camoufox_reference' END AS camoufox_source,
       CASE WHEN 'chromium-upstream' IN source_ids THEN 'ok' ELSE 'missing_chromium_upstream' END AS chromium_source;

// Detector evidence coverage by surface
MATCH (s:FingerprintSurface)
OPTIONAL MATCH (s)<-[:CHECKS_SURFACE]-(d:Detector)<-[:RAN_DETECTOR]-(run:DetectorRun)
RETURN s.surface_id AS surface,
       count(DISTINCT d) AS detector_count,
       count(DISTINCT run) AS runtime_run_count,
       CASE WHEN count(DISTINCT run) = 0 THEN 'missing_runtime_evidence' ELSE 'covered' END AS status
ORDER BY status DESC, surface;

// Platform artifact coverage
MATCH (platform:Platform)
OPTIONAL MATCH (artifact:RuntimeArtifact)-[:BUILT_FOR]->(platform)
RETURN platform.platform_id AS platform,
       count(DISTINCT artifact) AS artifact_count,
       CASE WHEN count(DISTINCT artifact) = 0 THEN 'missing_artifact' ELSE 'covered' END AS status
ORDER BY platform;
