# Track 17: Active Data Contracts & Immutable Schema Registry

This directory contains the engineering specifications, architectural blueprints, and validation engine for building a strict, **Immutable Semantic Versioning Schema Registry** on Google Cloud.

## 1. Ripping out Last-Writer-Wins (LWW)
In multi-producer streaming and analytics databases, a **Last-Writer-Wins (LWW)** metadata policy updates the global table schema whenever any writer pushes a schema modification. This results in:
*   **Schema Regressions**: A legacy producer running older code pushes data and inadvertently drops recently added fields from the catalog.
*   **Data Corruption**: Incompatible type updates are accepted silently, causing data truncation or query failures for downstream analytics.

This architecture replaces LWW with **Active Data Contracts** enforced at the ingestion boundary. Once a schema version (e.g. `v1.0.1`) is registered, it is **completely immutable** and can never be modified or overwritten.

---

## 2. Event-Driven Validation Pipeline
Validation is enforced before committal using a decoupled, serverless validation gateway:

```
[Producer Write] ──> [Staging Landing Zone (BQ)]
                             │
                             ▼ (Audit Log Trigger)
                 [Cloud Logging / Pub/Sub Broker]
                             │
                             ▼
                 [Validation Cloud Function] <─── [SemVer Schema Registry]
                             │
              ┌──────────────┴──────────────┐
              ▼ (APPROVED)                  ▼ (QUARANTINED)
      [Production BQ Table]        [Quarantine / DLQ Table]
```

1.  **Staging Ingestion**: Data is written to a staging landing zone table, including the metadata attribute declaring its version target (e.g., `_schema_version: "1.0.2"`).
2.  **Audit Event Trigger**: BigQuery audit logs capture the insert job and trigger a Cloud Function via Cloud Logging and Pub/Sub.
3.  **Active Verification**: The Cloud Function fetches the corresponding schema from the registry and validates the payload structure. If it drifts, the payload is routed to a **Quarantine Table (Dead-Letter Queue)** and raises an alert.

---

## 3. Directory Contents
*   [POV_v3_Immutable_Schema_Registry.md](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track17_metadata_knowledge_catalog/POV_v3_Immutable_Schema_Registry.md): Detailed 1,500+ word whitepaper analyzing data contract enforcement, SemVer mathematical compatibility, and GCP pipeline implementation.
*   [schema_registry_validator.py](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track17_metadata_knowledge_catalog/schema_registry_validator.py): Runnable PyTorch-independent Python script utilizing the `jsonschema` library to model registry immutability and payload validation.
*   [schema_audit_report.json](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track17_metadata_knowledge_catalog/schema_audit_report.json): Execution telemetry results recording the 5-case validation run.

---

## 4. Execution Steps
To execute the validation runner and verify schema controls:
```bash
uv run --with jsonschema python3 schema_registry_validator.py
```
The test suite validates:
*   **LWW Overwrite Block**: Confirms that trying to overwrite an existing version (`v1.0.1`) raises a `PermissionError`.
*   **TC_01 / TC_02 (Valid Inputs)**: Verifies that payloads matching `1.0.1` and `1.0.2` schemas are correctly `APPROVED`.
*   **TC_03 (Regression Drift)**: Detects when a producer sends unexpected properties (additionalProperties violation) -> `QUARANTINED`.
*   **TC_04 (Type Drift)**: Detects when a field (e.g., `id`) contains an invalid type -> `QUARANTINED`.
*   **TC_05 (Missing Required Field)**: Detects when required columns are omitted -> `QUARANTINED`.
