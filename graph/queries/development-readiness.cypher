// Runtime artifacts missing release-critical metadata
MATCH (a:RuntimeArtifact)
WHERE a.sha256 IS NULL
   OR a.sbom_path IS NULL
   OR a.provenance_path IS NULL
   OR a.download_url IS NULL
RETURN a.artifact_id AS artifact,
       a.platform AS platform,
       a.browser_version AS browser_version,
       a.sha256 AS sha256,
       a.sbom_path AS sbom,
       a.provenance_path AS provenance,
       a.download_url AS download_url
ORDER BY artifact;

// BrowseForge-managed flags with no runtime wrapper contract
MATCH (bf:BrowseForgeConsumer)-[:MANAGES_FLAG]->(f:RuntimeFlag)
WHERE NOT (f)<-[:ACCEPTS_FLAG]-(:Wrapper)
RETURN bf.consumer_id AS consumer,
       f.name AS missing_wrapper_flag,
       f.value_type AS value_type
ORDER BY missing_wrapper_flag;

// Detector coverage gaps by platform and artifact
MATCH (a:RuntimeArtifact)-[:TARGETS_PLATFORM]->(p:Platform)
MATCH (d:Detector)
WHERE d.required = true
  AND NOT EXISTS {
    MATCH (run:DetectorRun)-[:TESTS_ARTIFACT]->(a),
          (run)-[:RUNS_DETECTOR]->(d)
  }
RETURN a.artifact_id AS artifact,
       p.key AS platform,
       collect(d.detector_id) AS missing_required_detectors
ORDER BY artifact;

// Release readiness rollup
MATCH (rel:Release {version: $release})-[:INCLUDES_ARTIFACT]->(a:RuntimeArtifact)
OPTIONAL MATCH (a)<-[:TESTS_ARTIFACT]-(run:DetectorRun)
OPTIONAL MATCH (run)-[:OBSERVED_RISK]->(risk:Risk)
WITH rel, a,
     count(DISTINCT run) AS detector_runs,
     count(DISTINCT CASE WHEN run.status = 'passed' THEN run END) AS passed_runs,
     count(DISTINCT CASE WHEN risk.severity IN ['high','critical'] AND coalesce(risk.accepted,false)=false THEN risk END) AS blocking_risks
RETURN rel.version AS release,
       a.artifact_id AS artifact,
       a.platform AS platform,
       detector_runs,
       passed_runs,
       blocking_risks,
       CASE
         WHEN a.sha256 IS NULL OR a.sbom_path IS NULL OR a.provenance_path IS NULL THEN 'metadata_incomplete'
         WHEN blocking_risks > 0 THEN 'blocked_by_risk'
         WHEN detector_runs = 0 THEN 'missing_detector_evidence'
         ELSE 'ready_for_review'
       END AS readiness
ORDER BY readiness, artifact;
