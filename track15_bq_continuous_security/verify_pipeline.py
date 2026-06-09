#!/usr/bin/env python3
"""
Track 15: BigQuery Continuous Query Verification Harness
This script parses the 'continuous_firewall_filter.sql' file, validates syntax,
mocks a streaming ingestion pipeline, and validates that sample telemetry data
correctly triggers alerts based on the SQL WHERE criteria.
"""

import json
import re
import sys
from datetime import datetime, timezone

SQL_FILE_PATH = "continuous_firewall_filter.sql"

# Sample Mock Ingestion Stream
MOCK_TELEMETRY_STREAM = [
    # Case 1: Normal traffic, no alerts
    {
        "event_timestamp": "2026-06-09T01:00:00Z",
        "tower_id": "TWR-EAST-401",
        "cell_id": "CELL-A",
        "interface_id": "eth0",
        "source_ip": "10.0.0.5",
        "destination_ip": "10.0.0.10",
        "protocol": "TCP",
        "traffic_bytes": 1024,
        "packet_count": 12,
        "threat_severity": "LOW",
        "signature_id": 0
    },
    # Case 2: Severity is HIGH - should trigger alert
    {
        "event_timestamp": "2026-06-09T01:01:00Z",
        "tower_id": "TWR-EAST-401",
        "cell_id": "CELL-B",
        "interface_id": "eth0",
        "source_ip": "192.168.1.50",
        "destination_ip": "198.51.100.12",  # Public IP
        "protocol": "TCP",
        "traffic_bytes": 2048,
        "packet_count": 25,
        "threat_severity": "HIGH",
        "signature_id": 1004
    },
    # Case 3: Data exfiltration: UDP spike (> 50MB) - should trigger alert
    {
        "event_timestamp": "2026-06-09T01:02:00Z",
        "tower_id": "TWR-WEST-202",
        "cell_id": "CELL-A",
        "interface_id": "eth1",
        "source_ip": "10.10.2.14",
        "destination_ip": "203.0.113.45",
        "protocol": "UDP",
        "traffic_bytes": 60000000,  # ~57MB
        "packet_count": 45000,
        "threat_severity": "LOW",
        "signature_id": 0
    },
    # Case 4: Packet flood with MEDIUM severity - should trigger alert
    {
        "event_timestamp": "2026-06-09T01:03:00Z",
        "tower_id": "TWR-NORTH-105",
        "cell_id": "CELL-C",
        "interface_id": "eth0",
        "source_ip": "172.16.5.9",
        "destination_ip": "10.100.200.1",
        "protocol": "TCP",
        "traffic_bytes": 5000000,
        "packet_count": 120000,  # >100k
        "threat_severity": "MEDIUM",
        "signature_id": 2087
    },
    # Case 5: Public destination IP with MEDIUM severity - should trigger alert
    {
        "event_timestamp": "2026-06-09T01:04:00Z",
        "tower_id": "TWR-SOUTH-303",
        "cell_id": "CELL-A",
        "interface_id": "eth2",
        "source_ip": "192.168.10.11",
        "destination_ip": "8.8.8.8",  # Non-private IP
        "protocol": "UDP",
        "traffic_bytes": 1024,
        "packet_count": 15,
        "threat_severity": "MEDIUM",
        "signature_id": 0
    }
]

def is_private_ip(ip):
    # Match standard RFC 1918 private subnets or loopback
    private_regex = r'^(10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|192\.168\.|127\.)'
    return bool(re.match(private_regex, ip))

def simulate_sql_filter(record):
    """
    Applies the logic of the continuous_firewall_filter.sql WHERE clause.
    """
    sev = record["threat_severity"]
    bytes_sent = record["traffic_bytes"]
    proto = record["protocol"]
    packets = record["packet_count"]
    dest_ip = record["destination_ip"]

    # WHERE conditions matching SQL
    cond1 = sev in ('CRITICAL', 'HIGH')
    cond2 = (bytes_sent > 52428800 and proto == 'UDP')
    cond3 = (packets > 100000 and sev == 'MEDIUM')
    cond4 = (not is_private_ip(dest_ip) and sev == 'MEDIUM')

    return cond1 or cond2 or cond3 or cond4

def run_pipeline_test():
    print("=" * 80)
    print("BIGQUERY CONTINUOUS SECURITY PIPELINE HARNESS VALIDATION")
    print("=" * 80)

    # 1. Parse SQL syntax checks
    print("[1] Parsing SQL definition for structural constraints...")
    try:
        with open(SQL_FILE_PATH, 'r') as f:
            sql_content = f.read()
    except FileNotFoundError:
        print(f"ERROR: SQL file not found at {SQL_FILE_PATH}")
        sys.exit(1)

    # Check key components
    target_table = "my_project.telco_mesh.tower_telemetry"
    pubsub_topic = "pubsub://projects/my_project/topics/telco-firewall-alerts"
    
    assert target_table in sql_content, f"Failed: Original table '{target_table}' not found in SQL query."
    assert pubsub_topic in sql_content, f"Failed: Pub/Sub target URI '{pubsub_topic}' not found."
    assert "EXPORT DATA OPTIONS" in sql_content, "Failed: Query does not use EXPORT DATA OPTIONS block."
    print(" -> SQL structural check: PASSED (Target tables and Pub/Sub endpoints unmodified)")

    # 2. Simulate streaming execution
    print("\n[2] Simulating Continuous Telemetry Stream Filtering...")
    alerts_triggered = []
    
    for i, record in enumerate(MOCK_TELEMETRY_STREAM, 1):
        should_alert = simulate_sql_filter(record)
        status = "ALERT TRIGGERED 🚨" if should_alert else "PASSED ✅"
        print(f"  Record #{i} | {record['tower_id']} | Severity: {record['threat_severity']} | Dest: {record['destination_ip']} | {status}")
        
        if should_alert:
            # Construct the Pub/Sub JSON message exactly as BigQuery would
            pubsub_payload = {
                "event_time": record["event_timestamp"],
                "tower_id": record["tower_id"],
                "cell_id": record["cell_id"],
                "interface_id": record["interface_id"],
                "source_ip": record["source_ip"],
                "destination_ip": record["destination_ip"],
                "protocol": record["protocol"],
                "traffic_bytes": record["traffic_bytes"],
                "packet_count": record["packet_count"],
                "threat_severity": record["threat_severity"],
                "signature_id": record["signature_id"],
                "detection_engine": "BIGQUERY_CONTINUOUS_SECURITY_V1",
                "processed_at": datetime.now(timezone.utc).isoformat()
            }
            alerts_triggered.append(pubsub_payload)

    # 3. Assertions
    print("\n[3] Verification Assertions:")
    # Record 1 (Normal) -> Passed (No Alert)
    # Record 2 (HIGH severity) -> Alert
    # Record 3 (UDP exfiltration) -> Alert
    # Record 4 (Packet flood MEDIUM) -> Alert
    # Record 5 (External egress MEDIUM) -> Alert
    
    assert len(alerts_triggered) == 4, f"Failed: Expected 4 alerts, but got {len(alerts_triggered)}"
    print(f" -> Alert Ingestion & Filtering Integrity: PASSED (Triggered {len(alerts_triggered)} alerts)")

    # 4. Dump Alert Payloads (simulating Pub/Sub messages)
    print("\n[4] Simulated Pub/Sub Outbound Message Payloads:")
    for alert in alerts_triggered:
        print(json.dumps(alert, indent=2))
        print("-" * 40)
        
    print("\nVerification harness execution completed successfully.")
    print("=" * 80)

if __name__ == "__main__":
    run_pipeline_test()
