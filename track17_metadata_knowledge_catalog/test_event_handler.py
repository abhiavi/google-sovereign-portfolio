#!/usr/bin/env python3
"""
Track 17: Metadata Knowledge Catalog Verification Harness
This script generates mock GCP Cloud Audit Log payloads for schema changes
and tests that the SchemaEventHandler maps them correctly into unified semantic models.
"""

import os
import json
import unittest
from schema_event_handler import SchemaEventHandler

# Mock GCP Audit Log Event representing a BigQuery Schema Update
MOCK_AUDIT_LOG_UPDATE = {
    "protoPayload": {
        "serviceName": "bigquery.googleapis.com",
        "methodName": "google.cloud.bigquery.v2.TableService.UpdateTable",
        "resourceName": "projects/my_project/datasets/telco_mesh/tables/tower_telemetry",
        "serviceData": {
            "tableUpdateRequest": {
                "resource": {
                    "schema": {
                        "fields": [
                            {"name": "event_timestamp", "type": "TIMESTAMP"},
                            {"name": "tower_id", "type": "STRING"},
                            {"name": "source_ip", "type": "STRING"},
                            {"name": "destination_ip", "type": "STRING"},
                            {"name": "traffic_bytes", "type": "INTEGER"},
                            {"name": "threat_severity", "type": "STRING"},
                            {"name": "new_unassigned_field", "type": "STRING"}
                        ]
                    }
                }
            }
        }
    }
}

class TestSchemaMetadataCatalog(unittest.TestCase):
    def setUp(self):
        self.test_layer_path = "test_unified_semantic_layer.json"
        # Cleanup past test files
        if os.path.exists(self.test_layer_path):
            os.remove(self.test_layer_path)
        self.handler = SchemaEventHandler(self.test_layer_path)

    def tearDown(self):
        # Cleanup test files
        if os.path.exists(self.test_layer_path):
            os.remove(self.test_layer_path)

    def test_schema_mapping_integrity(self):
        print("\nRunning schema parsing integrity tests...")
        
        # Ingest mock audit log event
        result = self.handler.process_audit_event(MOCK_AUDIT_LOG_UPDATE)
        
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["resource"], "projects/my_project/datasets/telco_mesh/tables/tower_telemetry")
        
        # Verify catalog output exists
        self.assertTrue(os.path.exists(self.test_layer_path))
        
        # Load and verify semantic classification assertions
        with open(self.test_layer_path, "r") as f:
            catalog = json.load(f)
            
        entities = catalog["entities"]
        
        # Verify total items
        self.assertEqual(len(entities), 7)
        
        # Test Cases: Assertions on classifications
        # 1. source_ip -> NetworkAddress (PII_RESTRICTED)
        key_ip = "projects/my_project/datasets/telco_mesh/tables/tower_telemetry/source_ip"
        self.assertIn(key_ip, entities)
        self.assertEqual(entities[key_ip]["semantic_concept"], "NetworkAddress")
        self.assertEqual(entities[key_ip]["security_tier"], "PII_RESTRICTED")
        
        # 2. event_timestamp -> TemporalMarker (PUBLIC)
        key_time = "projects/my_project/datasets/telco_mesh/tables/tower_telemetry/event_timestamp"
        self.assertIn(key_time, entities)
        self.assertEqual(entities[key_time]["semantic_concept"], "TemporalMarker")
        self.assertEqual(entities[key_time]["security_tier"], "PUBLIC")

        # 3. threat_severity -> SecuritySignal (CONFIDENTIAL)
        key_threat = "projects/my_project/datasets/telco_mesh/tables/tower_telemetry/threat_severity"
        self.assertIn(key_threat, entities)
        self.assertEqual(entities[key_threat]["semantic_concept"], "SecuritySignal")
        self.assertEqual(entities[key_threat]["security_tier"], "CONFIDENTIAL")
        
        # 4. new_unassigned_field -> GeneralAttribute (INTERNAL)
        key_gen = "projects/my_project/datasets/telco_mesh/tables/tower_telemetry/new_unassigned_field"
        self.assertIn(key_gen, entities)
        self.assertEqual(entities[key_gen]["semantic_concept"], "GeneralAttribute")
        self.assertEqual(entities[key_gen]["security_tier"], "INTERNAL")

        print(" -> All assertions passed. Semantic ontology mappings verified.")

    def test_contract_violation_rollback_alert(self):
        print("\nRunning contract violation and rollback alert test...")
        # Simulate dropping a critical column: 'destination_ip' is missing
        MOCK_BREAKING_CHANGE = {
            "protoPayload": {
                "serviceName": "bigquery.googleapis.com",
                "methodName": "google.cloud.bigquery.v2.TableService.UpdateTable",
                "resourceName": "projects/my_project/datasets/telco_mesh/tables/tower_telemetry",
                "serviceData": {
                    "tableUpdateRequest": {
                        "resource": {
                            "schema": {
                                "fields": [
                                    {"name": "event_timestamp", "type": "TIMESTAMP"},
                                    {"name": "tower_id", "type": "STRING"},
                                    {"name": "source_ip", "type": "STRING"},
                                    {"name": "traffic_bytes", "type": "INTEGER"}
                                    # 'destination_ip' is dropped!
                                ]
                            }
                        }
                    }
                }
            }
        }
        
        result = self.handler.process_audit_event(MOCK_BREAKING_CHANGE)
        
        self.assertEqual(result["status"], "CONTRACT_VIOLATION")
        self.assertIn("Missing required columns: ['destination_ip']", result["reason"])
        print(" -> Contract violation correctly detected. Rollback triggered successfully.")

    def test_semantic_collision_resolution(self):
        print("\nRunning semantic collision resolution test...")
        # Team A pushes an update at T1
        TEAM_A_UPDATE = {
            "protoPayload": {
                "timestamp": "2026-06-09T10:00:00Z",
                "methodName": "google.cloud.bigquery.v2.TableService.UpdateTable",
                "resourceName": "projects/my_project/datasets/telco_mesh/tables/tower_telemetry",
                "serviceData": {
                    "tableUpdateRequest": {
                        "resource": {
                            "schema": {
                                "fields": [
                                    {"name": "event_timestamp", "type": "TIMESTAMP"},
                                    {"name": "tower_id", "type": "STRING"},
                                    {"name": "source_ip", "type": "STRING"},
                                    {"name": "destination_ip", "type": "STRING"},
                                    {"name": "traffic_bytes", "type": "INTEGER"}
                                ]
                            }
                        }
                    }
                }
            }
        }
        
        # Team B pushes a conflicting older update at T0 (delayed event)
        TEAM_B_DELAYED_UPDATE = {
            "protoPayload": {
                "timestamp": "2026-06-09T09:00:00Z",  # Older timestamp
                "methodName": "google.cloud.bigquery.v2.TableService.UpdateTable",
                "resourceName": "projects/my_project/datasets/telco_mesh/tables/tower_telemetry",
                "serviceData": {
                    "tableUpdateRequest": {
                        "resource": {
                            "schema": {
                                "fields": [
                                    {"name": "event_timestamp", "type": "TIMESTAMP"},
                                    {"name": "tower_id", "type": "STRING"},
                                    {"name": "source_ip", "type": "STRING"},
                                    {"name": "destination_ip", "type": "STRING"},
                                    {"name": "traffic_bytes", "type": "INTEGER"},
                                    {"name": "rogue_field", "type": "STRING"}
                                ]
                            }
                        }
                    }
                }
            }
        }
        
        # Process Team A (T1) first
        self.handler.process_audit_event(TEAM_A_UPDATE)
        
        # Then process Team B (T0) which arrived late
        self.handler.process_audit_event(TEAM_B_DELAYED_UPDATE)
        
        # Verify that the rogue_field from Team B was rejected because it's an older state
        with open(self.test_layer_path, "r") as f:
            catalog = json.load(f)
            
        entities = catalog["entities"]
        rogue_key = "projects/my_project/datasets/telco_mesh/tables/tower_telemetry/rogue_field"
        
        self.assertNotIn(rogue_key, entities)
        print(" -> Semantic collision resolved correctly. Delayed older schema rejected.")

if __name__ == "__main__":
    unittest.main()
