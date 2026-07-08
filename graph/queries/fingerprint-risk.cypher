// High-risk fingerprint surfaces without passing detector evidence for a release
MATCH (r:Release {version: $release})-[:INCLUDES_ARTIFACT]->(a:RuntimeArtifact)
MATCH (s:FingerprintSurface)<-[:MODIFIES_SURFACE]-(:Patch)<-[:INCLUDES_PATCH]-(:PatchSet)<-[:HAS_PATCHSET]-(:RuntimeProvider)-[:PRODUCES_ARTIFACT]->(a)
WHERE s.risk_level IN ['high', 'critical']
  AND NOT EXISTS {
    MATCH (run:DetectorRun)-[:TESTS_ARTIFACT]->(a),
          (run)-[:RUNS_DETECTOR]->(:Detector)-[:CHECKS_SURFACE]->(s)
    WHERE run.status = 'passed'
  }
RETURN a.artifact_id AS artifact,
       s.surface_id AS surface,
       s.risk_level AS risk_level
ORDER BY risk_level DESC, surface;

// Known detector risks without mitigation or accepted risk record
MATCH (risk:Risk)
WHERE risk.status IN ['open', 'regressed']
  AND risk.severity IN ['high', 'critical']
  AND NOT (risk)<-[:MITIGATES]-(:Mitigation)
  AND coalesce(risk.accepted, false) = false
RETURN risk.risk_id AS risk,
       risk.severity AS severity,
       risk.summary AS summary,
       risk.surface AS surface
ORDER BY severity DESC, risk;

// Patchset surfaces with no BrowseForge-visible configuration or profile input
MATCH (p:Patch)-[:MODIFIES_SURFACE]->(s:FingerprintSurface)
WHERE NOT EXISTS { MATCH (:RuntimeFlag)-[:CONTROLS_SURFACE]->(s) }
  AND NOT EXISTS { MATCH (:ConfigField)-[:CONTROLS_SURFACE]->(s) }
  AND NOT EXISTS { MATCH (:ProfileField)-[:CONTROLS_SURFACE]->(s) }
RETURN s.surface_id AS hidden_surface,
       collect(p.patch_id) AS patches
ORDER BY hidden_surface;
