import os
import json
import time

# Mocking Google Cloud SDK Exceptions for offline execution validation
class GoogleAPIError(Exception):
    def __init__(self, message, code=403, reason="Forbidden"):
        super().__init__(message)
        self.code = code
        self.reason = reason

class Forbidden(GoogleAPIError):
    pass

# ==========================================
# 1. VPC Service Controls Policy Evaluator
# ==========================================
class VPCSCPermeterEvaluator:
    """
    Simulates the GCP Access Context Manager enforcement engine.
    Parses network, identity, and target service attributes.
    """
    def __init__(self):
        # Service perimeter configuration based on perimeter_bridge.tf
        self.perimeter_resources = {"projects/my_project"}
        self.restricted_services = {
            "storage.googleapis.com",
            "bigquery.googleapis.com",
            "aiplatform.googleapis.com",
            "cloudbuild.googleapis.com"
        }
        
        # Ingress Policies
        self.ingress_rules = [
            # Rule 1: Secure Operator Predict Access
            {
                "identities": {"serviceAccount:ai-agent-router@my_project.iam.gserviceaccount.com"},
                "access_levels": {"accessPolicies/sovereign_policy/accessLevels/al_secure_operator_network"},
                "services": {"aiplatform.googleapis.com"},
                "methods": {
                    "google.cloud.aiplatform.v1.PredictionService.Predict",
                    "google.cloud.aiplatform.v1.EndpointService.Predict"
                },
                "resources": {"projects/my_project"}
            },
            # Rule 2: B2B Perimeter Bridge (Vendor BigQuery Access)
            {
                "identities": {"serviceAccount:vendor-analyst-sa@external-consulting-firm.iam.gserviceaccount.com"},
                "access_levels": {"accessPolicies/sovereign_policy/accessLevels/al_vendor_trusted_network"},
                "services": {"bigquery.googleapis.com"},
                "methods": {
                    "google.cloud.bigquery.v2.TableService.GetData",
                    "google.cloud.bigquery.v2.TableService.ListTables"
                },
                "resources": {"projects/my_project"}
            }
        ]

        # Egress Policies
        self.egress_rules = [
            # Rule 1: Operator BigQuery Egress to external shared project
            {
                "identities": {"serviceAccount:ai-agent-router@my_project.iam.gserviceaccount.com"},
                "services": {"bigquery.googleapis.com"},
                "methods": {
                    "google.cloud.bigquery.v2.JobService.InsertJob",
                    "google.cloud.bigquery.v2.TableService.GetData"
                },
                "resources": {"projects/external_shared_analytics"}
            }
        ]

    def evaluate(self, request):
        service = request.get("service")
        target_project = request.get("target_project")
        source_project = request.get("source_project")
        identity = request.get("identity")
        request_access_levels = set(request.get("access_levels", []))
        method = request.get("method")
        
        # 1. If service is not restricted by this perimeter, default allow
        if service not in self.restricted_services:
            return {"decision": "ALLOW", "reason": f"Service {service} is outside VPC-SC scope."}

        caller_inside = source_project in self.perimeter_resources
        target_inside = target_project in self.perimeter_resources

        # Scenario A: Intra-perimeter access
        if caller_inside and target_inside:
            return {"decision": "ALLOW", "reason": "Intra-perimeter call is allowed by default."}

        # Scenario B: Ingress Attempt (Outside calling Inside)
        if not caller_inside and target_inside:
            for rule in self.ingress_rules:
                if identity not in rule["identities"]:
                    continue
                # Match access levels
                if not request_access_levels.intersection(rule["access_levels"]):
                    continue
                # Match service & operation
                if service in rule["services"] and method in rule["methods"]:
                    if target_project in rule["resources"]:
                        return {"decision": "ALLOW", "reason": "Authorized B2B Ingress policy match."}
            
            return {
                "decision": "DENIED",
                "code": "VPC_SC_INGRESS_VIOLATION",
                "reason": f"VPC Service Controls: Ingress denied. Request from {identity} to {service}/{method} "
                          f"is blocked. Missing required access level or resource binding."
            }

        # Scenario C: Egress Attempt (Inside calling Outside)
        if caller_inside and not target_inside:
            for rule in self.egress_rules:
                if identity not in rule["identities"]:
                    continue
                # Match service & operation
                if service in rule["services"] and method in rule["methods"]:
                    if target_project in rule["resources"]:
                        return {"decision": "ALLOW", "reason": "Authorized Egress policy match."}
            
            return {
                "decision": "DENIED",
                "code": "VPC_SC_EGRESS_VIOLATION",
                "reason": f"VPC Service Controls: Egress blocked. Exfiltration to project {target_project} "
                          f"via service {service}/{method} is prohibited by egress policies."
            }

        # Scenario D: Outside calling Outside
        return {"decision": "ALLOW", "reason": "Outside-to-outside communication."}

# ==========================================
# 2. Google Cloud SDK Simulation Client
# ==========================================
class SimulatedBigQueryClient:
    def __init__(self, evaluator, request_context):
        self.evaluator = evaluator
        self.request_context = request_context

    def query(self, query_string, dataset_project):
        """
        Simulates executing a BigQuery read operation using the Google Cloud SDK.
        Raises a Forbidden exception if the request is blocked by VPC-SC.
        """
        # Populate project targets
        req = self.request_context.copy()
        req["service"] = "bigquery.googleapis.com"
        req["method"] = "google.cloud.bigquery.v2.TableService.GetData"
        req["target_project"] = dataset_project
        
        # Evaluate policy
        evaluation = self.evaluator.evaluate(req)
        
        if evaluation["decision"] == "DENIED":
            # Throw standard GCP SDK error structure for VPC Service Controls
            raise Forbidden(
                message=f"403 {evaluation['reason']}",
                code=403,
                reason="VPC_SC_POLICY_VIOLATION"
            )
            
        # If allowed, return mock rows
        return [
            {"telemetry_id": "T08-102", "operator_id": "router-01", "avg_latency_ms": 14.2},
            {"telemetry_id": "T08-103", "operator_id": "router-02", "avg_latency_ms": 18.5}
        ]

# ==========================================
# 3. Running Validation Scenarios
# ==========================================
def main():
    print("=== Track 13: B2B Perimeter Bridge Validation Test Runner ===")
    evaluator = VPCSCPermeterEvaluator()
    
    test_cases = [
        {
            "id": "TC_07_AUTHORIZED_B2B_BRIDGE_INGRESS",
            "description": "Authorized external vendor queries BigQuery from trusted network.",
            "request_context": {
                "identity": "serviceAccount:vendor-analyst-sa@external-consulting-firm.iam.gserviceaccount.com",
                "source_project": "projects/external_vendor_project",
                "access_levels": ["accessPolicies/sovereign_policy/accessLevels/al_vendor_trusted_network"]
            },
            "dataset_project": "projects/my_project",
            "expected": "ALLOW"
        },
        {
            "id": "TC_08_UNAUTHORIZED_B2B_BRIDGE_UNTRUSTED_SOURCE",
            "description": "External vendor SA queries BigQuery from public IP (no access levels).",
            "request_context": {
                "identity": "serviceAccount:vendor-analyst-sa@external-consulting-firm.iam.gserviceaccount.com",
                "source_project": "projects/external_vendor_project",
                "access_levels": [] # Untrusted source
            },
            "dataset_project": "projects/my_project",
            "expected": "DENIED"
        },
        {
            "id": "TC_09_UNAUTHORIZED_B2B_BRIDGE_UNRESTRICTED_API",
            "description": "External vendor SA attempts to access Vertex AI prediction APIs.",
            "request_context": {
                "identity": "serviceAccount:vendor-analyst-sa@external-consulting-firm.iam.gserviceaccount.com",
                "source_project": "projects/external_vendor_project",
                "access_levels": ["accessPolicies/sovereign_policy/accessLevels/al_vendor_trusted_network"]
            },
            "dataset_project": "projects/my_project",
            # Evaluate using direct evaluator since it queries aiplatform
            "direct_eval": {
                "service": "aiplatform.googleapis.com",
                "method": "google.cloud.aiplatform.v1.PredictionService.Predict",
                "target_project": "projects/my_project"
            },
            "expected": "DENIED"
        }
    ]
    
    results = []
    passed = 0
    
    for tc in test_cases:
        print(f"\n[{tc['id']}] - {tc['description']}")
        status = "FAIL"
        decision = "UNKNOWN"
        error_thrown = None
        
        try:
            if "direct_eval" in tc:
                # Direct check on non-BigQuery APIs
                req = tc["request_context"].copy()
                req.update(tc["direct_eval"])
                res = evaluator.evaluate(req)
                decision = res["decision"]
                if decision == "DENIED":
                    raise Forbidden(res["reason"])
            else:
                # Use Google Cloud SDK simulated client
                client = SimulatedBigQueryClient(evaluator, tc["request_context"])
                rows = client.query("SELECT * FROM secure_telemetry", tc["dataset_project"])
                decision = "ALLOW"
                print(f"  [SDK Client] Query executed successfully. Returned {len(rows)} rows.")
        except Forbidden as e:
            decision = "DENIED"
            error_thrown = str(e)
            print(f"  [SDK Client] Caught Expected Exception: {e}")
            
        if decision == tc["expected"]:
            status = "PASS"
            passed += 1
            
        print(f"  Result: {status} (Expected: {tc['expected']}, Actual: {decision})")
        
        results.append({
            "test_case_id": tc["id"],
            "description": tc["description"],
            "status": status,
            "expected": tc["expected"],
            "actual_decision": decision,
            "error_message": error_thrown
        })
        
    print("\n--- Test Suite Summary ---")
    print(f"Total: {len(test_cases)} | Passed: {passed} | Failed: {len(test_cases) - passed}")
    
    # Save test telemetry
    report_path = os.path.join(os.path.dirname(__file__), "bridge_validation_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Test audit telemetry saved successfully to: {report_path}")

if __name__ == "__main__":
    main()
