#!/usr/bin/env python3
"""
Track 17: Metadata Knowledge Catalog Event Handler
This script parses Google Cloud audit log events for BigQuery schema modifications
and maps the structural alterations dynamically into a unified semantic layer.
"""

import os
import json
from datetime import datetime, timezone

SEMANTIC_LAYER_PATH = "unified_semantic_layer.json"

# Data Contracts defined using a JSON Schema structure for strict enforcement
DATA_CONTRACTS = {
    "projects/my_project/datasets/telco_mesh/tables/tower_telemetry": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["event_timestamp", "tower_id", "source_ip", "destination_ip", "traffic_bytes"],
        "properties": {
            "event_timestamp": {"type": "TIMESTAMP"},
            "tower_id": {"type": "STRING"},
            "source_ip": {"type": "STRING"},
            "destination_ip": {"type": "STRING"},
            "traffic_bytes": {"type": "INTEGER"}
        }
    }
}

# Semantic classification rules mapping raw physical columns to business concept classes
SEMANTIC_CLASSIFIER_RULES = {
    r".*_ip$": {
        "concept": "NetworkAddress",
        "description": "Internet Protocol Address (IPv4 or IPv6)",
        "security_classification": "PII_RESTRICTED"
    },
    r"event_timestamp$|.*_time$": {
        "concept": "TemporalMarker",
        "description": "Point-in-time timestamp registration",
        "security_classification": "PUBLIC"
    },
    r"tower_id$|cell_id$": {
        "concept": "InfrastructureIdentifier",
        "description": "Physical asset identifier in the telco mesh",
        "security_classification": "INTERNAL_AUDIT"
    },
    r"traffic_bytes$|packet_count$": {
        "concept": "VolumetricMetric",
        "description": "Network traffic quantitative payload metric",
        "security_classification": "PUBLIC"
    },
    r"threat_severity$|alert_flag$": {
        "concept": "SecuritySignal",
        "description": "Indication of intrusion or anomaly flag",
        "security_classification": "CONFIDENTIAL"
    }
}

class SchemaEventHandler:
    def __init__(self, semantic_layer_path=SEMANTIC_LAYER_PATH):
        self.semantic_layer_path = semantic_layer_path
        self.load_semantic_layer()

    def load_semantic_layer(self):
        """Loads the existing semantic catalog or initializes a new one."""
        if os.path.exists(self.semantic_layer_path):
            with open(self.semantic_layer_path, "r") as f:
                self.catalog = json.load(f)
        else:
            self.catalog = {
                "catalog_metadata": {
                    "version": "1.0.0",
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "total_semantic_entities": 0
                },
                "entities": {}
            }

    def save_semantic_layer(self):
        """Saves the updated semantic catalog back to disk."""
        self.catalog["catalog_metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.catalog["catalog_metadata"]["total_semantic_entities"] = len(self.catalog["entities"])
        with open(self.semantic_layer_path, "w") as f:
            json.dump(self.catalog, f, indent=2)

    def classify_field(self, field_name, data_type):
        """Applies regex rules to classify physical columns into semantic concepts."""
        import re
        for pattern, rule in SEMANTIC_CLASSIFIER_RULES.items():
            if re.match(pattern, field_name, re.IGNORECASE):
                return {
                    "semantic_concept": rule["concept"],
                    "description": rule["description"],
                    "security_tier": rule["security_classification"],
                    "derived_at": datetime.now(timezone.utc).isoformat()
                }
        # Default fallback classification
        return {
            "semantic_concept": "GeneralAttribute",
            "description": f"Attribute of type {data_type}",
            "security_tier": "INTERNAL",
            "derived_at": datetime.now(timezone.utc).isoformat()
        }

    def trigger_rollback_alert(self, resource_name, reason):
        """Simulates triggering an automated rollback and alerting mechanism."""
        print(f"\n[ALERT] CRITICAL SCHEMA DRIFT DETECTED for {resource_name}!")
        print(f"[ALERT] Reason: {reason}")
        print(f"[ACTION] Triggering automated rollback mechanism to revert upstream producer deployment...")
        print(f"[ACTION] Paging Data Engineering on-call team...\n")

    def validate_data_contract(self, resource_name, fields):
        """Validates incoming schema fields against defined JSON Schema data contracts."""
        contract = DATA_CONTRACTS.get(resource_name)
        if not contract:
            return True, "No contract defined."
            
        provided_fields = {f.get("name"): f.get("type") for f in fields}
        
        # Validate Required Columns
        missing_required = [req for req in contract.get("required", []) if req not in provided_fields]
        if missing_required:
            return False, f"Data Contract Violation: Missing required columns: {missing_required}"
            
        # Validate Types for Required Columns
        for req in contract.get("required", []):
            expected_type = contract["properties"][req]["type"]
            actual_type = provided_fields[req]
            if expected_type != actual_type:
                return False, f"Data Contract Violation: Type mismatch for '{req}'. Expected {expected_type}, got {actual_type}"
                
        return True, "Contract validation passed."

    def process_audit_event(self, audit_event_json):
        """
        Parses Google Cloud Audit Logs and extracts schema alterations.
        Matches method: TableService.UpdateTable or TableService.CreateTable
        """
        try:
            event = json.loads(audit_event_json) if isinstance(audit_event_json, str) else audit_event_json
            proto_payload = event.get("protoPayload", {})
            method_name = proto_payload.get("methodName", "")
            
            # Verify if it is a schema modification event
            valid_methods = [
                "google.cloud.bigquery.v2.TableService.UpdateTable",
                "google.cloud.bigquery.v2.TableService.PatchTable",
                "google.cloud.bigquery.v2.TableService.CreateTable"
            ]
            
            if method_name not in valid_methods:
                return {"status": "SKIPPED", "reason": f"Event method {method_name} is not a schema modification."}
            
            resource_name = proto_payload.get("resourceName", "")
            
            # Extract updated schema fields
            service_data = proto_payload.get("serviceData", {})
            table_update = service_data.get("tableUpdateRequest", {})
            resource = table_update.get("resource", {})
            schema = resource.get("schema", {})
            fields = schema.get("fields", [])
            
            if not fields:
                # Fallback check for alternative schema locations in some audit formats
                fields = proto_payload.get("metadata", {}).get("tableCreation", {}).get("table", {}).get("schema", {}).get("fields", [])
            
            if not fields:
                return {"status": "NO_SCHEMA_FOUND", "reason": "No schema fields found in audit payload."}
            
            event_timestamp_str = proto_payload.get("timestamp", datetime.now(timezone.utc).isoformat())
            
            # Enforce Data Contract
            is_valid, validation_msg = self.validate_data_contract(resource_name, fields)
            if not is_valid:
                self.trigger_rollback_alert(resource_name, validation_msg)
                return {"status": "CONTRACT_VIOLATION", "reason": validation_msg}
            
            print(f"[Handler] Processing event '{method_name}' for resource: {resource_name}")
            
            # Entity-level Collision Resolution: Check if any existing field in this resource has a newer timestamp
            # If so, the entire incoming schema update is considered stale and rejected to prevent partial schema application.
            is_stale_update = False
            for entity_key, entity_data in self.catalog["entities"].items():
                if entity_key.startswith(resource_name + "/"):
                    existing_ts = entity_data.get("last_modified")
                    if existing_ts and event_timestamp_str < existing_ts:
                        print(f"[COLLISION RESOLUTION] Rejecting entire stale schema update for {resource_name}. Incoming: {event_timestamp_str}, Existing newer: {existing_ts}")
                        is_stale_update = True
                        break
            
            if is_stale_update:
                return {"status": "STALE_UPDATE_REJECTED", "reason": "A newer schema version already exists for this resource."}
            
            # Update unified catalog
            entities_updated = []
            for field in fields:
                name = field.get("name")
                data_type = field.get("type")
                
                # Combine resource ID and field name for unique semantic tracking
                entity_key = f"{resource_name}/{name}"
                
                
                semantic_meta = self.classify_field(name, data_type)
                
                self.catalog["entities"][entity_key] = {
                    "physical_column": name,
                    "physical_type": data_type,
                    "source_dataset": resource_name,
                    "semantic_concept": semantic_meta["semantic_concept"],
                    "description": semantic_meta["description"],
                    "security_tier": semantic_meta["security_tier"],
                    "last_modified": event_timestamp_str
                }
                entities_updated.append(entity_key)
                
            self.save_semantic_layer()
            return {
                "status": "SUCCESS",
                "resource": resource_name,
                "fields_updated": entities_updated
            }
            
        except Exception as e:
            return {"status": "ERROR", "reason": str(e)}

if __name__ == "__main__":
    # If run directly, output a diagnostic warning
    print("SchemaEventHandler loaded. Run the validation harness to test functionality.")
