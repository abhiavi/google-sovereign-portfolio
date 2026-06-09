-- =====================================================================================
-- Track 15: BigQuery Continuous Security Query
-- Description: Persistent streaming query to filter firewall events from tower telemetry
--              using a 10-second tumbling window stateful aggregation.
-- Target: my_project.telco_mesh.tower_telemetry
-- Destination: pubsub://projects/my_project/topics/telco-firewall-alerts
-- =====================================================================================

EXPORT DATA OPTIONS (
  uri = 'pubsub://projects/my_project/topics/telco-firewall-alerts',
  format = 'JSON'
) AS
SELECT
  TO_JSON_STRING(STRUCT(
    window_end AS event_time,
    tower_id,
    cell_id,
    SUM(traffic_bytes) AS window_traffic_bytes,
    SUM(packet_count) AS window_packet_count,
    'CRITICAL_ANOMALY' AS threat_severity,
    -- Architect metadata payload
    'BIGQUERY_CONTINUOUS_SECURITY_V2' AS detection_engine,
    CURRENT_TIMESTAMP() AS processed_at
  )) AS message
FROM
  TUMBLE(
    (SELECT * FROM `my_project.telco_mesh.tower_telemetry`),
    DESCRIPTOR(event_timestamp),
    "INTERVAL 10 SECOND",
    "ALLOW LATE INTERVAL 5 MINUTE"
  )
GROUP BY
  window_end, tower_id, cell_id
HAVING
  SUM(traffic_bytes) > 104857600 -- Anomaly: >100MB in 10s
  OR SUM(packet_count) > 500000; -- Anomaly: >500k packets in 10s
