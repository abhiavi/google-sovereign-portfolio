# deploy_gdc.tf - Terraform deployment mapping for an air-gapped Google Distributed Cloud (GDC) rack.

provider "google" {
  project = "google-sovereign-gdc-project"
  region  = "us-east1"
}

# 1. Establish Sovereign Virtual Private Cloud (VPC)
resource "google_compute_network" "gdc_sovereign_vpc" {
  name                    = "gdc-sovereign-vpc"
  auto_create_subnetworks = false
}

# 2. Strict Subnetting: Sovereign Compute Enclave Subnet (No Internet Router/NAT attached)
resource "google_compute_subnetwork" "gdc_secure_subnet" {
  name                     = "gdc-secure-subnet"
  ip_cidr_range            = "10.240.10.0/24"
  network                  = google_compute_network.gdc_sovereign_vpc.self_link
  private_ip_google_access = true # Local access only to GDC APIs
}

# 3. Absolute Egress Denial Rule: All traffic heading outbound must be explicitly blocked
resource "google_compute_firewall" "gdc_block_all_egress" {
  name    = "gdc-block-all-egress"
  network = google_compute_network.gdc_sovereign_vpc.name

  direction = "EGRESS"
  priority  = 1000

  # Deny all destinations unconditionally
  deny {
    protocol = "all"
  }

  destination_ranges = ["0.0.0.0/0"]
  description        = "Sovereign boundary security: absolute block of all outbound internet egress traffic."
}

# 3b. Tailscale Overlay Egress Whitelist: Allow internal traffic strictly to the Tailscale subnet (100.64.0.0/10)
# This enables secure routing to the Proxmox environment hosts (e.g. LiteLLM proxy at 100.116.70.21:4000)
resource "google_compute_firewall" "gdc_allow_tailscale_egress" {
  name    = "gdc-allow-tailscale-egress"
  network = google_compute_network.gdc_sovereign_vpc.name

  direction = "EGRESS"
  priority  = 950 # Higher priority than catch-all block

  allow {
    protocol = "tcp"
    ports    = ["4000"] # LiteLLM Gateway
  }

  destination_ranges = ["100.64.0.0/10"]
  description        = "Sovereign communication: allow outbound egress to Tailscale IP space on LiteLLM ports."
}


# 4. Strict Ingress Whitelist: Only local enclaves can trigger inference gateway endpoints
resource "google_compute_firewall" "gdc_allow_local_ingress" {
  name    = "gdc-allow-local-ingress"
  network = google_compute_network.gdc_sovereign_vpc.name

  direction = "INGRESS"
  priority  = 900

  # Only allow HTTP/HTTPS traffic from within GDC VPC subnet
  allow {
    protocol = "tcp"
    ports    = ["80", "443", "8000"]
  }

  source_ranges = ["10.240.10.0/24"]
  description   = "Inbound restriction: only local verified clients in secure subnet can access GDC API."
}

# 5. Provision GDC Hardware Node Node Pool (Simulated AMD SEV-SNP hardware hosts)
# In standard GDC Air-Gapped, the hardware is provisioned via the gdc-client CLI.
# This terraform model provisions the underlying virtual enclaves hosting Google Confidential Space.
resource "google_compute_instance_template" "confidential_gemma_node" {
  name_prefix  = "confidential-gemma-node-"
  machine_type = "n2d-standard-32" # AMD EPYC machine type supporting SEV-SNP

  disk {
    source_image = "projects/confidential-space-images/global/images/confidential-space-24-04-0"
    auto_delete  = true
    boot         = true
  }

  network_interface {
    network    = google_compute_network.gdc_sovereign_vpc.self_link
    subnetwork = google_compute_subnetwork.gdc_secure_subnet.self_link
  }

  # Enable Google Confidential VM properties (attestation verification hooks)
  confidential_instance_config {
    enable_confidential_compute = true
  }

  metadata = {
    # Set the workload configuration metadata indicating the target Gemma 3 workload
    "tee-image-reference" = "us-east1-docker.pkg.dev/google-sovereign-gdc-project/images/gemma3-inference-gateway:latest"
    "tee-container-log-redirect" = "false" # Prevent debug console log leakage
  }

  lifecycle {
    create_before_destroy = true
  }
}
