# Dynamic IaC VPC-SC Perimeter Generator
# This configuration parses vpc_sc_perimeter.yaml dynamically and instantiates the Access Context Manager resources.

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = "my-sovereign-project"
  region  = "europe-west3"
}

# Local variables to decode the YAML policy configuration
locals {
  policy_yaml = yamldecode(file("${path.module}/vpc_sc_perimeter.yaml"))
  perimeter   = local.policy_yaml.service_perimeter
}

# Instantiate the service perimeter dynamically
resource "google_access_context_manager_service_perimeter" "sovereign_perimeter" {
  parent      = "accessPolicies/123456789" # Access Policy ID containing this perimeter
  name        = local.perimeter.name
  title       = local.perimeter.title
  description = local.perimeter.description
  perimeter_type = "PERIMETER_TYPE_REGULAR"

  status {
    resources           = local.perimeter.resources
    restricted_services = local.perimeter.restricted_services
    access_levels       = local.perimeter.access_levels

    # Dynamically build Ingress Policies from the YAML definition
    dynamic "ingress_policies" {
      for_each = lookup(local.perimeter, "ingress_policies", [])
      content {
        ingress_from {
          identities = lookup(ingress_policies.value.ingress_from, "identities", [])
          
          dynamic "sources" {
            for_each = lookup(ingress_policies.value.ingress_from, "sources", [])
            content {
              access_level = lookup(sources.value, "access_level", null)
            }
          }
        }

        ingress_to {
          resources = lookup(ingress_policies.value.ingress_to, "resources", [])
          
          dynamic "operations" {
            for_each = lookup(ingress_policies.value.ingress_to, "operations", [])
            content {
              service_name = lookup(operations.value, "service_name", null)
              
              dynamic "method_selectors" {
                for_each = lookup(operations.value, "method_selectors", [])
                content {
                  method = lookup(method_selectors.value, "method", null)
                }
              }
            }
          }
        }
      }
    }

    # Dynamically build Egress Policies from the YAML definition
    dynamic "egress_policies" {
      for_each = lookup(local.perimeter, "egress_policies", [])
      content {
        egress_from {
          identities = lookup(egress_policies.value.egress_from, "identities", [])
        }

        egress_to {
          resources = lookup(egress_policies.value.egress_to, "resources", [])
          
          dynamic "operations" {
            for_each = lookup(egress_policies.value.egress_to, "operations", [])
            content {
              service_name = lookup(operations.value, "service_name", null)
              
              dynamic "method_selectors" {
                for_each = lookup(operations.value, "method_selectors", [])
                content {
                  method = lookup(method_selectors.value, "method", null)
                }
              }
            }
          }
        }
      }
    }
  }
}
