import os
import json
from policy_engine import VPCPermeterPolicyEngine

def run_perimeter_tests():
    # Path to YAML configuration file
    policy_path = os.path.join(os.path.dirname(__file__), "vpc_sc_perimeter.yaml")
    
    # Initialize the compiler/engine
    print("--- Initializing Declarative VPC-SC Policy Engine ---")
    print(f"Loading rules schema from {policy_path}...")
    engine = VPCPermeterPolicyEngine(policy_path)
    print("Service Perimeter successfully validated.")
    print(f"Protected Resources: {engine.resources}")
    print(f"Restricted APIs: {engine.restricted_services}\n")
    
    # Define test scenarios simulating ingress, egress, and exfiltration attempts
    test_cases = [
        {
            "id": "TC_01_AUTHORIZED_INGRESS_PREDICT",
            "description": "Authorized AI Agent router requests predictions from the secure network.",
            "request": {
                "identity": "serviceAccount:ai-agent-router@my_project.iam.gserviceaccount.com",
                "source_ip": "10.128.0.45",
                "access_levels": ["accessPolicies/123456789/accessLevels/al_secure_operator_network"],
                "service": "aiplatform.googleapis.com",
                "method": "google.cloud.aiplatform.v1.PredictionService.Predict",
                "source_project": "projects/external_caller_location", # Caller is outside the perimeter
                "target_project": "projects/my_project"                 # Target is inside the perimeter
            },
            "expected_decision": "ALLOW"
        },
        {
            "id": "TC_02_UNAUTHORIZED_INGRESS_PUBLIC_IP",
            "description": "External client attempts to call Predict service from public IP (no access level).",
            "request": {
                "identity": "user:external_developer@gmail.com",
                "source_ip": "8.8.8.8",
                "access_levels": [], # No access levels matching
                "service": "aiplatform.googleapis.com",
                "method": "google.cloud.aiplatform.v1.PredictionService.Predict",
                "source_project": "projects/external_caller_location",
                "target_project": "projects/my_project"
            },
            "expected_decision": "DENIED"
        },
        {
            "id": "TC_03_AUTHORIZED_EGRESS_ANALYTICS",
            "description": "Authorized data router exports verified BQ telemetry downstream to shared analytics.",
            "request": {
                "identity": "serviceAccount:ai-agent-router@my_project.iam.gserviceaccount.com",
                "source_ip": "10.240.1.20",
                "access_levels": ["accessPolicies/123456789/accessLevels/al_secure_operator_network"],
                "service": "bigquery.googleapis.com",
                "method": "google.cloud.bigquery.v2.JobService.InsertJob",
                "source_project": "projects/my_project",                  # Caller is inside
                "target_project": "projects/external_shared_analytics"     # Target is outside
            },
            "expected_decision": "ALLOW"
        },
        {
            "id": "TC_04_UNAUTHORIZED_EGRESS_EXFILTRATION",
            "description": "Compromised internal identity attempts to copy storage blobs to a malicious public bucket.",
            "request": {
                "identity": "serviceAccount:malicious-compromised-sa@my_project.iam.gserviceaccount.com",
                "source_ip": "10.240.1.15",
                "access_levels": ["accessPolicies/123456789/accessLevels/al_secure_operator_network"],
                "service": "storage.googleapis.com",
                "method": "google.cloud.storage.v1.Objects.Insert",
                "source_project": "projects/my_project",               # Caller is inside
                "target_project": "projects/malicious_public_bucket"  # Target is outside and unauthorized
            },
            "expected_decision": "DENIED"
        },
        {
            "id": "TC_05_NESTED_EXFILTRATION_CLOUDBUILD",
            "description": "Insider threat uses a Cloud Build job running inside the perimeter to write to an unauthorized external storage bucket.",
            "request": {
                "identity": "serviceAccount:123456789@cloudbuild.gserviceaccount.com",
                "source_ip": "10.240.1.15",
                "access_levels": ["accessPolicies/123456789/accessLevels/al_secure_operator_network"],
                "service": "storage.googleapis.com",
                "method": "google.cloud.storage.v1.Objects.Insert",
                "source_project": "projects/my_project",
                "target_project": "projects/malicious_public_bucket"
            },
            "expected_decision": "DENIED"
        },
        {
            "id": "TC_06_UNAUTHORIZED_CLOUDBUILD_EXTERNAL_EGRESS",
            "description": "Insider threat attempts to trigger Cloud Build to run build steps that egress to an external IP/project.",
            "request": {
                "identity": "serviceAccount:123456789@cloudbuild.gserviceaccount.com",
                "source_ip": "10.240.1.15",
                "access_levels": ["accessPolicies/123456789/accessLevels/al_secure_operator_network"],
                "service": "cloudbuild.googleapis.com",
                "method": "google.devtools.cloudbuild.v1.CreateBuild",
                "source_project": "projects/my_project",
                "target_project": "projects/external_malicious_infrastructure"
            },
            "expected_decision": "DENIED"
        },
        {
            "id": "TC_07_AUTHORIZED_B2B_BRIDGE_INGRESS",
            "description": "Authorized external vendor accesses BigQuery dataset from trusted network location.",
            "request": {
                "identity": "serviceAccount:vendor-analyst-sa@external-consulting-firm.iam.gserviceaccount.com",
                "source_ip": "198.51.100.4",
                "access_levels": ["accessPolicies/123456789/accessLevels/al_vendor_trusted_network"],
                "service": "bigquery.googleapis.com",
                "method": "google.cloud.bigquery.v2.TableService.GetData",
                "source_project": "projects/external_vendor_project",
                "target_project": "projects/my_project"
            },
            "expected_decision": "ALLOW"
        },
        {
            "id": "TC_08_UNAUTHORIZED_B2B_BRIDGE_UNTRUSTED_SOURCE",
            "description": "External vendor SA attempts to access BigQuery dataset from untrusted public IP (no trusted access level).",
            "request": {
                "identity": "serviceAccount:vendor-analyst-sa@external-consulting-firm.iam.gserviceaccount.com",
                "source_ip": "8.8.8.8",
                "access_levels": [],
                "service": "bigquery.googleapis.com",
                "method": "google.cloud.bigquery.v2.TableService.GetData",
                "source_project": "projects/external_vendor_project",
                "target_project": "projects/my_project"
            },
            "expected_decision": "DENIED"
        },
        {
            "id": "TC_09_UNAUTHORIZED_B2B_BRIDGE_UNRESTRICTED_API",
            "description": "External vendor SA attempts to access Vertex AI prediction APIs (unauthorized service).",
            "request": {
                "identity": "serviceAccount:vendor-analyst-sa@external-consulting-firm.iam.gserviceaccount.com",
                "source_ip": "198.51.100.4",
                "access_levels": ["accessPolicies/123456789/accessLevels/al_vendor_trusted_network"],
                "service": "aiplatform.googleapis.com",
                "method": "google.cloud.aiplatform.v1.PredictionService.Predict",
                "source_project": "projects/external_vendor_project",
                "target_project": "projects/my_project"
            },
            "expected_decision": "DENIED"
        }
    ]
    
    results = []
    passed = 0
    
    print("--- Executing Automated Policy Controls Tests ---")
    for tc in test_cases:
        res = engine.evaluate(tc["request"])
        decision = res["decision"]
        
        # Verify result matches expectation
        status = "PASS" if decision == tc["expected_decision"] else "FAIL"
        if status == "PASS":
            passed += 1
            
        print(f"[{tc['id']}] - {tc['description']}")
        print(f"  Request Context: Service={tc['request']['service']} | Method={tc['request']['method']}")
        print(f"  Target: {tc['request']['target_project']}")
        print(f"  Evaluated Decision: {decision}")
        if decision == "DENIED":
            print(f"  Violation Code: {res.get('code')}")
            print(f"  Reason: {res.get('reason')}")
        else:
            print(f"  Allowed Reason: {res.get('reason')}")
        print(f"  Result: {status}\n")
        
        results.append({
            "test_case_id": tc["id"],
            "description": tc["description"],
            "expected": tc["expected_decision"],
            "actual": decision,
            "status": status,
            "evaluation_detail": res
        })
        
    print("--- Test Suite Summary ---")
    print(f"Total Runs: {len(test_cases)} | Passed: {passed} | Failed: {len(test_cases) - passed}")
    
    # Save test results report
    report_path = os.path.join(os.path.dirname(__file__), "perimeter_audit_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Test audit telemetry saved to {report_path}")
    
    return passed == len(test_cases)

if __name__ == "__main__":
    run_perimeter_tests()
