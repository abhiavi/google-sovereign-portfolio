# Terraform Deployment for Sovereign VPC-SC B2B Perimeter Bridge
# This file declares Access Context Manager policies, Access Levels, Service Perimeters, and Org Policy Overrides.

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = "my_project"
  region  = "europe-west3"
}

# 1. Access Context Manager Policy (Container for perimeters)
resource "google_access_context_manager_access_policy" "sovereign_policy" {
  parent = "organizations/123456789"
  title  = "Sovereign Security Access Policy"
}

# 2. Access Level: Secure Operator Network (For internal operators)
resource "google_access_context_manager_access_level" "secure_operator" {
  parent = google_access_context_manager_access_policy.sovereign_policy.name
  name   = "accessPolicies/${google_access_context_manager_access_policy.sovereign_policy.name}/accessLevels/al_secure_operator_network"
  title  = "al_secure_operator_network"
  
  basic {
    conditions {
      ip_subnets = ["10.128.0.0/9", "192.168.1.0/24"]
    }
  }
}

# 3. Access Level: B2B Trusted Vendor Network (For external third-party partner)
resource "google_access_context_manager_access_level" "vendor_network" {
  parent = google_access_context_manager_access_policy.sovereign_policy.name
  name   = "accessPolicies/${google_access_context_manager_access_policy.sovereign_policy.name}/accessLevels/al_vendor_trusted_network"
  title  = "al_vendor_trusted_network"
  
  basic {
    conditions {
      ip_subnets = ["198.51.100.4/32"] # Pinned to the vendor's dedicated egress IP gateway
    }
  }
}

# 4. Project-level Organization Policy Override
# This allows the external vendor project to attach service accounts to our resources.
resource "google_project_organization_policy" "allow_cross_project_sa" {
  project    = "my_project"
  constraint = "gcp.restrictCrossProjectServiceAccounts"
  
  list_policy {
    allow {
      values = ["under:projects/external_vendor_project"]
    }
  }
}

# 5. Service Perimeter: Sovereign Security Perimeter
resource "google_access_context_manager_service_perimeter" "sovereign_perimeter" {
  parent      = google_access_context_manager_access_policy.sovereign_policy.name
  name        = "accessPolicies/${google_access_context_manager_access_policy.sovereign_policy.name}/servicePerimeters/sp_sovereign_telco_perimeter"
  title       = "sp_sovereign_telco_perimeter"
  description = "Protects analytical and model inference interfaces from exfiltration."
  perimeter_type = "PERIMETER_TYPE_REGULAR"

  status {
    resources = [
      "projects/my_project"
    ]
    
    restricted_services = [
      "storage.googleapis.com",
      "bigquery.googleapis.com",
      "aiplatform.googleapis.com",
      "cloudbuild.googleapis.com"
    ]

    access_levels = [
      google_access_context_manager_access_level.secure_operator.name,
      google_access_context_manager_access_level.vendor_network.name
    ]

    # Ingress Rule 1: Secure Operator predictions access
    ingress_policies {
      ingress_from {
        identities = [
          "serviceAccount:ai-agent-router@my_project.iam.gserviceaccount.com"
        ]
        sources {
          access_level = google_access_context_manager_access_level.secure_operator.name
        }
      }
      ingress_to {
        resources = [
          "projects/my_project"
        ]
        operations {
          service_name = "aiplatform.googleapis.com"
          method_selectors {
            method = "google.cloud.aiplatform.v1.PredictionService.Predict"
          }
          method_selectors {
            method = "google.cloud.aiplatform.v1.EndpointService.Predict"
          }
        }
      }
    }

    # Ingress Rule 2: B2B Perimeter Bridge - External vendor access to specific BQ operations
    ingress_policies {
      ingress_from {
        identities = [
          "serviceAccount:vendor-analyst-sa@external-consulting-firm.iam.gserviceaccount.com"
        ]
        sources {
          access_level = google_access_context_manager_access_level.vendor_network.name
        }
      }
      ingress_to {
        resources = [
          "projects/my_project"
        ]
        operations {
          service_name = "bigquery.googleapis.com"
          method_selectors {
            method = "google.cloud.bigquery.v2.TableService.GetData"
          }
          method_selectors {
            method = "google.cloud.bigquery.v2.TableService.ListTables"
          }
        }
      }
    }

    # Egress Rule 1: Allow Operator to write telemetry output downstream
    egress_policies {
      egress_from {
        identities = [
          "serviceAccount:ai-agent-router@my_project.iam.gserviceaccount.com"
        ]
      }
      egress_to {
        resources = [
          "projects/external_shared_analytics"
        ]
        operations {
          service_name = "bigquery.googleapis.com"
          method_selectors {
            method = "google.cloud.bigquery.v2.JobService.InsertJob"
          }
          method_selectors {
            method = "google.cloud.bigquery.v2.TableService.GetData"
          }
        }
      }
    }
  }
}
