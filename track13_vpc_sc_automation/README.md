# Track 13: VPC Service Controls B2B Perimeter Bridge Automation

This directory contains the security architecture, Terraform configuration, and SDK validation code for building a secure **B2B Service Perimeter Bridge** in Google Cloud.

## 1. The B2B Ingress Boundary
When exposing a secure BigQuery dataset to a trusted third-party vendor, standard network policies are insufficient. Security must be enforced on a zero-trust model combining:
1.  **IAM Identity**: Only the vendor's dedicated Service Account (`vendor-analyst-sa@...`) is granted access.
2.  **Network Origin**: Access is restricted to requests originating from the vendor's trusted IP gateways, mapped to the Access Level `al_vendor_trusted_network` (`198.51.100.4/32`).
3.  **API Constraints**: The vendor SA is permitted to perform only specific BigQuery operations (`GetData`, `ListTables`). Lateral movement to other restricted services (like Vertex AI or Storage) is blocked.

---

## 2. Production Org Policy Overrides
In a real production environment, VPC-SC ingress rules will fail unless the hosting project overrides the global GCP Organization Policy **`constraints/gcp.restrictCrossProjectServiceAccounts`**.

By default, this policy blocks resources from attaching or accepting service accounts belonging to external projects. To resolve this:
*   We apply a project-level override on our hosting project (`projects/my_project`).
*   We add a whitelist list policy allowing service accounts under the vendor's specific project identifier (`under:projects/external_vendor_project`).
*   This is fully declared and deployed in the Terraform setup.

---

## 3. Directory Contents
*   [POV_v3_B2B_Perimeter_Bridge.md](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track13_vpc_sc_automation/POV_v3_B2B_Perimeter_Bridge.md): A detailed, 1,500+ word whitepaper analyzing identity federation, network ingress/egress, and organization policy coordination.
*   [perimeter_bridge.tf](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track13_vpc_sc_automation/perimeter_bridge.tf): Deployable Terraform code declaring the Access Context Manager policy, Access Levels, Service Perimeters, and the project-level Organization Policy override.
*   [validate_bridge.py](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track13_vpc_sc_automation/validate_bridge.py): A Python validation script simulating Google Cloud SDK Client calls and evaluating policy checks.
*   [bridge_validation_report.json](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track13_vpc_sc_automation/bridge_validation_report.json): Execution telemetry metrics exported by the validation runner.

---

## 4. Validation execution
To run the SDK query simulation and generate the validation report:
```bash
uv run python3 validate_bridge.py
```
The script runs three primary scenarios:
1.  **TC_07 (Authorized B2B Ingress)**: Simulates the vendor SA querying BigQuery from the trusted IP address block -> **ALLOW** (mock rows returned).
2.  **TC_08 (Unauthorized B2B Source)**: Simulates the vendor SA attempting query from a public IP (no Access Level) -> **DENIED** (raises a mock GCP `Forbidden` exception).
3.  **TC_09 (Lateral Movement)**: Simulates the vendor SA attempting to call Vertex AI prediction endpoints -> **DENIED** (prohibited by service restrictions).
