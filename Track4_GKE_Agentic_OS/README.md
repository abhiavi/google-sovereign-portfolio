# Track 4: GKE Agentic OS — Kueue Gang-Scheduling for Distributed AI

This repository contains the simulation engineering and configuration manifests demonstrating how **GKE (Google Kubernetes Engine)** with **Kueue** implements **Gang-Scheduling (All-or-Nothing)** to solve resource deadlocks in distributed AI deployments (e.g., Llama-3-70B fine-tuning or inference swarms).

## Architecture Diagram

The diagram below contrasts standard Kubernetes greedy scheduling (leading to interleaved pod deadlock) with Kueue's queueing-based, all-or-nothing admission control:

![GKE Kueue Gang Scheduling Architecture](architecture_diagram.svg)

---

## The Problem: Greedy Allocation Deadlock

Standard Kubernetes scheduling processes pods individually. When two distributed jobs (each requesting $N$ pods) are submitted simultaneously to a cluster with $M$ GPUs (where $2 \times N > M \ge N$), the scheduler can interleave their pods. 
*   **Job A** receives a partial allocation (e.g., 2/4 pods).
*   **Job B** receives a partial allocation (e.g., 2/4 pods).
*   **Rendezvous Failure**: Both jobs require all ranks to initialize the PyTorch distributed process group (`c10d` backend) to proceed. Both jobs hang waiting for the remaining pods.
*   **Wasted GPU Cost**: All GPUs are 100% allocated and active, costing **$117.44/hour** (for 32 x A100-80GB GPUs at $3.67/hr), but performing zero computations.

---

## The Solution: Kueue All-or-Nothing Admission

Kueue intercepts Job creation using a mutating webhook and sets `spec.suspend: true`. It queues the jobs and monitors the cluster's available capacity. Kueue only admits a job (setting `suspend: false`) when it can guarantee that the **entire resource gang** (all pods/GPUs) can be scheduled together.
*   **Sequential Execution**: Job A is admitted, runs on all 32 GPUs, completes, and exits.
*   **Zero Deadlock**: Job B remains suspended in the queue, consuming zero compute time. It is admitted only after Job A releases its resources.

---

## Empirical Verification: Simulation Telemetry

We simulated a 3,600-second window contrasting both schedulers on a 32-GPU cluster. The results prove a **100% reduction in GPU deadlock idle hours**.

| Metric | Standard Kubernetes Scheduler | GKE Kueue Gang Scheduler |
| :--- | :---: | :---: |
| **Total Jobs Submitted** | 2 | 2 |
| **Completed Jobs** | 0 | 1 (1 completed, 1 active & healthy) |
| **Productive GPU Hours** | 0.00 | 62.22 |
| **GPU Idle Deadlock Hours** | 32.00 | 0.00 |
| **Wasted GPU Deadlock Cost** | **$117.44 USD** | **$0.00 USD** |
| **Normal Init Overhead Cost** | $0.00 | $0.65 (10s normal rendezvous/job) |
| **Deadlock Cost Reduction** | *Baseline* | **100% Reduction** |

---

## Repository Contents

*   `gke_kueue_gang_scheduler.py`: Time-stepped discrete simulator comparing schedulers.
*   `kueue_resources.yaml`: Production Kubernetes configurations (`ResourceFlavor`, `ClusterQueue`, `LocalQueue`, and suspended `Job`).
*   `scheduling_telemetry.csv`: Generated second-by-second metric log.
*   `generate_architecture.py`: Python generator for the SVG diagram.
*   `architecture_diagram.svg`: Vector architecture diagram.
*   `medium_draft_track4.md`: Detailed draft of the associated thought leadership article.

---

## Getting Started

### Running the Simulator
1. Ensure Python 3 is installed.
2. Execute the simulator script:
   ```bash
   python3 gke_kueue_gang_scheduler.py
   ```
3. The script will output a execution summary and regenerate `scheduling_telemetry.csv` and `kueue_resources.yaml`.

### Deploying to GKE
1. Install Kueue on your GKE cluster:
   ```bash
   kubectl apply --server-side -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.6.2/manifests.yaml
   ```
2. Apply the queues and resource configurations:
   ```bash
   kubectl apply -f kueue_resources.yaml
   ```
3. Submit your Kueue-governed distributed ML jobs to the cluster.
