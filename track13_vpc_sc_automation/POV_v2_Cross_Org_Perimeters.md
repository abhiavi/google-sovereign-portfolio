# POV: B2B Perimeter Bridge & Cross-Org Isolation
**Compliance Framework: NIST SP 800-53 (AC-20: Use of External Information Systems) & PCI-DSS 4.0**

## 1. Executive Summary
This document reviews the configuration, threat modeling, and validation of the B2B Perimeter Bridge in our VPC Service Controls (VPC-SC) automation suite. In modern enterprise environments, granting third-party vendors (such as external consulting firms) access to specific datasets is a critical requirement. However, this access must be isolated to prevent the vendor from acting as a vector for wider data exfiltration or calling unauthorized restricted services (e.g., Vertex AI prediction models) inside the sovereign perimeter.

We have enhanced the dynamic Terraform IaC configurations (`main.tf`) and policy definitions (`vpc_sc_perimeter.yaml`) to build a **B2B Perimeter Bridge** using structured ingress rules. Under this design, vendor access is limited to specific BigQuery datasets, is tied to a verified service account identity, and is constrained to trusted network access levels.

Furthermore, this document highlights the **GCP Organization Policy overrides** required in production to allow cross-project service accounts to function across the perimeter boundaries without compromising global security baselines.

---

## 2. B2B Perimeter Bridge Architecture
The bridge is established via a dedicated ingress policy that specifies both **Identity** and **Network Source constraints**:

```
[External Org Vendor Analyst]
           │
           ├── (Identified as SA: vendor-analyst-sa@...)
           ├── (Originates from Access Level: al_vendor_trusted_network)
           │
           ▼
┌──────────────────────────────────────────┐
│   Sovereign VPC-SC Perimeter Boundary     │
│                                          │
│   [BigQuery Dataset (Allowed)] <─── ALLOW│
│   [Vertex AI (Predict API)] <───── DENY  │
└──────────────────────────────────────────┘
```

The dynamic Terraform code automatically generates the corresponding `ingress_policies` block inside `google_access_context_manager_service_perimeter.sovereign_perimeter`.

---

## 3. Production Reality: GCP Organization Policy Constraints

In a production GCP environment, configuring VPC-SC ingress policies is **necessary but not sufficient**. By default, enterprise organizations enforce strict security baselines via GCP Organization Policies. Two specific constraints must be configured to allow external vendor Service Accounts to securely query BigQuery across perimeters:

### 3.1 `constraints/gcp.restrictCrossProjectServiceAccounts`
This policy restricts service accounts in one project from being attached to resources or authorized to act as callers in another project. 
*   **Default Enterprise State**: Set to `Deny All` or restricted to internal projects only.
*   **The Conflict**: Even if VPC-SC allows the external vendor SA ingress, this Org Policy will intercept the call at the IAM boundary and block it with a `Permission Denied` error.
*   **Production Remedy**: Apply a targeted Org Policy override on the hosting project (`projects/my_project`). Add the vendor's project ID (`projects/external_vendor_project`) to the allowed list under this constraint, maintaining a strict whitelist rather than disabling the constraint globally:
    ```hcl
    resource "google_project_organization_policy" "allow_vendor_sa" {
      project    = "my_project"
      constraint = "gcp.restrictCrossProjectServiceAccounts"
      list_policy {
        allow {
          values = ["under:projects/external_vendor_project"]
        }
      }
    }
    ```

### 3.2 `constraints/gcp.restrictServiceUsage`
This policy defines which APIs are allowed to be enabled and consumed within projects.
*   **The Conflict**: If the vendor SA project tries to execute jobs that enable cross-project BigQuery calls, the Org Policy may block service usage if `bigquery.googleapis.com` or other dependent APIs are restricted on either end.
*   **Production Remedy**: Ensure that `bigquery.googleapis.com` is explicitly whitelisted in the service usage policy of both the hosting project and the vendor's caller project.

---

## 4. Threat Modeling & Validation Results
We expanded our test suite from 6 to **9 automated scenarios** to validate the B2B bridge boundaries. The policy engine verified the following new cases:

### 4.1 B2B Bridge Test Cases
*   **TC_07: Authorized B2B Ingress (Vendor SA from Trusted Source)**
    *   *Identity*: `serviceAccount:vendor-analyst-sa@external-consulting-firm.iam.gserviceaccount.com`
    *   *Source Network*: `accessPolicies/123456789/accessLevels/al_vendor_trusted_network`
    *   *Service/Method*: `bigquery.googleapis.com` / `TableService.GetData`
    *   *Decision*: **ALLOW**
    *   *Rationale*: Matches the authorized ingress rule for third-party BigQuery read access.
*   **TC_08: Unauthorized B2B Ingress (Vendor SA from Untrusted Source)**
    *   *Identity*: `serviceAccount:vendor-analyst-sa@external-consulting-firm.iam.gserviceaccount.com`
    *   *Source Network*: Public IP `8.8.8.8` (no access levels)
    *   *Service/Method*: `bigquery.googleapis.com` / `TableService.GetData`
    *   *Decision*: **DENIED** (`VPC_SC_INGRESS_VIOLATION`)
    *   *Rationale*: Prevents compromised vendor credentials from being used from arbitrary public networks.
*   **TC_09: Unauthorized B2B Ingress (Vendor SA Accessing Vertex AI APIs)**
    *   *Identity*: `serviceAccount:vendor-analyst-sa@external-consulting-firm.iam.gserviceaccount.com`
    *   *Source Network*: Trusted Access Level
    *   *Service/Method*: `aiplatform.googleapis.com` / `PredictionService.Predict`
    *   *Decision*: **DENIED** (`VPC_SC_INGRESS_VIOLATION`)
    *   *Rationale*: Prevents lateral movement. The vendor is only authorized for BigQuery, not Vertex AI.

---

## 5. Test Summary Table
The updated validation suite yields the following results:

| Test Case | Description | Expected | Actual | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC_01** | Operator Ingress to Vertex AI | ALLOW | ALLOW | **PASS** |
| **TC_02** | Public Ingress to Vertex AI | DENIED | DENIED | **PASS** |
| **TC_03** | Operator Egress to Shared Analytics | ALLOW | ALLOW | **PASS** |
| **TC_04** | Exfiltration to malicious public bucket | DENIED | DENIED | **PASS** |
| **TC_05** | Cloud Build nested exfiltration to bucket | DENIED | DENIED | **PASS** |
| **TC_06** | Cloud Build egress to external domain | DENIED | DENIED | **PASS** |
| **TC_07** | B2B Ingress to BigQuery (Trusted Source) | ALLOW | ALLOW | **PASS** |
| **TC_08** | B2B Ingress to BigQuery (Public Source) | DENIED | DENIED | **PASS** |
| **TC_09** | B2B Ingress to Vertex AI (Lateral Move) | DENIED | DENIED | **PASS** |

---

## 6. Auditor Conclusion
The B2B Perimeter Bridge successfully balances business collaboration with strict zero-trust isolation.
1.  **Identity + Source Access Bindings**: A vendor service account cannot bypass isolation unless it also originates from a verified network block.
2.  **Strict Service Restriction**: Third-party access is restricted specifically to BigQuery operations; any lateral requests to other APIs (such as Vertex AI) are blocked.
3.  **Organization Policy Coordination**: To deploy this in production, the `gcp.restrictCrossProjectServiceAccounts` organization policy must be overridden to allow the vendor's project identifier.
4.  **Dynamic Governance**: The configuration is declared in `vpc_sc_perimeter.yaml` and audit telemetry is exported to `perimeter_audit_report.json`.
