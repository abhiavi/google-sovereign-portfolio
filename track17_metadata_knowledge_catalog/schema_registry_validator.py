import os
import json
import time
import jsonschema
from jsonschema import validate
from jsonschema.exceptions import ValidationError, SchemaError

# ==========================================
# 1. Immutable Semantic Versioning Schema Registry
# ==========================================
class ImmutableSchemaRegistry:
    """
    Simulates an immutable schema store. Once a schema version is registered,
    it cannot be modified or overwritten, eliminating Last-Writer-Wins vulnerabilities.
    """
    def __init__(self):
        # Initializing the registry with immutable SemVer schemas
        self._registry = {}
        
        # Define v1.0.1 schema (baseline customer record)
        self.register_schema(
            version="1.0.1",
            schema_definition={
                "$schema": "http://json-schema.org/draft-07/schema#",
                "title": "CustomerRecord_v1.0.1",
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "event_timestamp": {
                        "type": "string",
                        "format": "date-time"
                    }
                },
                "required": ["id", "name", "event_timestamp"],
                "additionalProperties": False
            }
        )
        
        # Define v1.0.2 schema (additive minor update - optional email)
        self.register_schema(
            version="1.0.2",
            schema_definition={
                "$schema": "http://json-schema.org/draft-07/schema#",
                "title": "CustomerRecord_v1.0.2",
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "event_timestamp": {
                        "type": "string",
                        "format": "date-time"
                    },
                    "email": {
                        "type": "string",
                        "format": "email"
                    }
                },
                "required": ["id", "name", "event_timestamp"],
                "additionalProperties": False
            }
        )

    def register_schema(self, version, schema_definition):
        """
        Registers a new schema version. Enforces immutability.
        """
        if version in self._registry:
            raise PermissionError(
                f"[Registry Failure] Schema version '{version}' is already registered. "
                "Schemas are immutable and cannot be overwritten."
            )
        
        # Validate schema structure before registering
        try:
            jsonschema.Draft7Validator.check_schema(schema_definition)
            self._registry[version] = schema_definition
            print(f"[Registry] Successfully registered immutable schema version {version}.")
        except SchemaError as e:
            raise ValueError(f"[Registry Failure] Invalid JSON Schema structure for version {version}: {e}")

    def get_schema(self, version):
        """
        Retrieves the requested schema version.
        """
        if version not in self._registry:
            raise KeyError(f"[Registry Failure] Schema version '{version}' is not registered.")
        return self._registry[version]

# ==========================================
# 2. Active Data Contract Enforcer (Validator)
# ==========================================
class ActiveDataContractValidator:
    """
    Enforces schemas at the ingestion boundary. Validates raw payloads against the registry
    and prevents schema drift from entering the database.
    """
    def __init__(self, registry):
        self.registry = registry

    def validate_payload(self, raw_payload, target_version):
        """
        Validates a payload against the specified schema version.
        Explicitly raises ValidationError on data contract violations.
        """
        try:
            # 1. Fetch schema from the immutable registry
            schema = self.registry.get_schema(target_version)
            
            # 2. Execute validation
            validate(instance=raw_payload, schema=schema)
            return {
                "status": "APPROVED",
                "target_version": target_version,
                "reason": "Payload matches the registered schema contract perfectly."
            }
            
        except KeyError as e:
            return {
                "status": "QUARANTINED",
                "error_type": "UNKNOWN_SCHEMA_VERSION",
                "reason": str(e)
            }
        except ValidationError as e:
            # Capturing validation errors (schema drift)
            error_field = ".".join([str(p) for p in e.absolute_path]) if e.absolute_path else "root"
            error_message = e.message
            
            return {
                "status": "QUARANTINED",
                "error_type": "SCHEMA_CONTRACT_VIOLATION",
                "drift_field": error_field,
                "reason": f"Schema drift detected on '{error_field}': {error_message}"
            }

# ==========================================
# 3. Validation Simulation Test Suite
# ==========================================
def main():
    print("=== Track 17: Active Data Contract Ingestion Validator ===")
    
    # 1. Initialize registry and validator
    registry = ImmutableSchemaRegistry()
    validator = ActiveDataContractValidator(registry)
    
    # Verify immutability check
    print("\nVerifying schema immutability controls...")
    try:
        registry.register_schema("1.0.1", {"type": "object"}) # Attempt LWW overwrite
    except PermissionError as e:
        print(f"[SUCCESS] Blocked Last-Writer-Wins override: {e}")
        
    # 2. Define test payloads simulating different writer versions and drift
    test_scenarios = [
        {
            "id": "TC_01_VALID_V101_PAYLOAD",
            "description": "Producer writes valid v1.0.1 record.",
            "target_version": "1.0.1",
            "payload": {
                "id": 1001,
                "name": "Alice Smith",
                "event_timestamp": "2026-06-09T14:00:00Z"
            },
            "expected_status": "APPROVED"
        },
        {
            "id": "TC_02_VALID_V102_PAYLOAD",
            "description": "Producer writes valid v1.0.2 record (with optional email).",
            "target_version": "1.0.2",
            "payload": {
                "id": 1002,
                "name": "Bob Jones",
                "event_timestamp": "2026-06-09T14:05:00Z",
                "email": "bob@example.com"
            },
            "expected_status": "APPROVED"
        },
        {
            "id": "TC_03_REGRESSION_DRIFT_VIOLATION",
            "description": "Writer submits email field to v1.0.1 endpoint (additionalProperties violation).",
            "target_version": "1.0.1",
            "payload": {
                "id": 1003,
                "name": "Charlie Brown",
                "event_timestamp": "2026-06-09T14:10:00Z",
                "email": "charlie@example.com" # Schema v1.0.1 forbids this field
            },
            "expected_status": "QUARANTINED"
        },
        {
            "id": "TC_04_TYPE_DRIFT_VIOLATION",
            "description": "Writer sends string for id instead of integer.",
            "target_version": "1.0.1",
            "payload": {
                "id": "invalid_integer_id",
                "name": "David Davis",
                "event_timestamp": "2026-06-09T14:15:00Z"
            },
            "expected_status": "QUARANTINED"
        },
        {
            "id": "TC_05_MISSING_REQUIRED_FIELD_VIOLATION",
            "description": "Writer omits required name field.",
            "target_version": "1.0.2",
            "payload": {
                "id": 1005,
                "event_timestamp": "2026-06-09T14:20:00Z"
            },
            "expected_status": "QUARANTINED"
        }
    ]
    
    results = []
    passed = 0
    
    print("\nRunning Active Data Contract Validation Pipeline...")
    for tc in test_scenarios:
        start_time = time.time()
        res = validator.validate_payload(tc["payload"], tc["target_version"])
        execution_time = time.time() - start_time
        
        status = "PASS" if res["status"] == tc["expected_status"] else "FAIL"
        if status == "PASS":
            passed += 1
            
        print(f"\n[{tc['id']}] - {tc['description']}")
        print(f"  Target Contract Version: {tc['target_version']}")
        print(f"  Validation Status: {res['status']}")
        if res["status"] == "APPROVED":
            print(f"  Reason: {res['reason']}")
        else:
            print(f"  Violation: {res.get('reason')}")
            print(f"  Drift Field: {res.get('drift_field', 'N/A')} | Error Type: {res.get('error_type')}")
        print(f"  Execution Time: {execution_time*1000:.4f} ms | Result: {status}")
        
        results.append({
            "test_case_id": tc["id"],
            "description": tc["description"],
            "target_version": tc["target_version"],
            "expected": tc["expected_status"],
            "actual": res["status"],
            "status": status,
            "validation_details": res
        })
        
    print("\n--- Test Suite Summary ---")
    print(f"Total Runs: {len(test_scenarios)} | Passed: {passed} | Failed: {len(test_scenarios) - passed}")
    
    # Save validation reports
    report_path = os.path.join(os.path.dirname(__file__), "schema_audit_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Schema audit telemetry saved successfully to: {report_path}")

if __name__ == "__main__":
    main()
