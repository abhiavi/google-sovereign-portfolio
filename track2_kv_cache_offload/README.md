# Sovereign KV Cache Offloader (Track 2)

This directory contains the production-grade simulation of **Track 2 of the Google Sovereign AI Portfolio: Shattering the LLM Memory Wall via Hierarchical Tiered KV Cache Offloading**.

The KV Cache Manager manages GPU High Bandwidth Memory (HBM) constraints during ultra-long context generation ($128\text{k}+$ tokens) in concurrent multi-agent systems, dynamically offloading cold key-value states to Host CPU RAM (DDR5) and NVMe storage, and retrieving them on-demand.

---

## Architecture Topology

The hierarchical data flow and physical interconnect pathways are represented below:

```mermaid
graph LR
    %% Style definitions
    classDef llm fill:#6D28D9,stroke:#4C1D95,stroke-width:2px,color:#FFF;
    classDef attn fill:#0284C7,stroke:#0369A1,stroke-width:2px,color:#FFF;
    classDef manager fill:#059669,stroke:#047857,stroke-width:2px,color:#FFF;
    classDef tier1 fill:#DC2626,stroke:#991B1B,stroke-width:2px,color:#FFF;
    classDef tier2 fill:#D97706,stroke:#B45309,stroke-width:2px,color:#FFF;
    classDef tier3 fill:#4B5563,stroke:#374151,stroke-width:2px,color:#FFF;

    A[LLM Request] --> B[Attention Mechanism]
    B --> C[KV Cache Manager]
    C --> D[Tier 1: HBM3 GPU]
    D <-->|PCIe Gen 4/5| E[Tier 2: DDR5 Host RAM]
    E <-->|PCIe/NVMe Bus| F[Tier 3: NVMe Storage]

    class A llm;
    class B attn;
    class C manager;
    class D tier1;
    class E tier2;
    class F tier3;
```

---

## 3-Tier LRU Eviction Policy

To prevent Out-Of-Memory (OOM) errors at the GPU level and Host system level during long-context execution, the KV Cache Manager implements a hierarchical Least Recently Used (LRU) paging policy:

```
+--------------------------------------------------------------------------------+
|                                  GPU HBM3                                      |
|  [Active KV Cache Blocks] ---> Limit: 90% GPU HBM Capacity                     |
+-----------------------+--------------------------------------------------------+
                        | (GPU memory > 90% threshold: Evict LRU block)
                        v
+--------------------------------------------------------------------------------+
|                                  DDR5 RAM                                      |
|  [Paged-out CPU Cache] ---> Limit: 90% Host KV Limit                           |
+-----------------------+--------------------------------------------------------+
                        | (CPU memory > 90% threshold: Evict LRU block)
                        v
+--------------------------------------------------------------------------------+
|                                 NVMe Storage                                   |
|  [Serialized Tensors] ---> Disk storage (unlimited capacity)                   |
+--------------------------------------------------------------------------------+
```

### 1. Tier 1: HBM3 (GPU)
* **Role**: Primary hot-cache storage. Provides ultra-high memory bandwidth (e.g., $1.5 \text{ TB/s} - 3.0 \text{ TB/s}$) directly to the GPU Tensor Cores.
* **Eviction Trigger**: When total GPU utilization (model weights + active KV caches) exceeds **90%** of available HBM capacity.
* **LRU Action**: The KV Cache Manager identifies the least recently accessed KV cache block in HBM, allocates corresponding CPU host memory, and pages it out to DDR5 Host RAM.

### 2. Tier 2: DDR5 (Host RAM)
* **Role**: Warm cache storage. Provides medium capacity and intermediate bandwidth (e.g., $16 - 32 \text{ GB/s}$ via PCIe Gen 4 x8/x16 bus).
* **Eviction Trigger**: When the aggregate size of offloaded KV caches stored in Host RAM exceeds its designated safety threshold (e.g., **90%** of CPU cache allocation).
* **LRU Action**: To avoid system-wide swapping or OOM crashes, the manager selects the coldest block in DDR5 Host RAM, serializes the tensors, and writes them to the NVMe filesystem.

### 3. Tier 3: NVMe (Storage)
* **Role**: Cold cache storage. Provides near-infinite capacity but lower bandwidth (e.g., $3.0 - 7.0 \text{ GB/s}$).
* **Action**: KV blocks are stored as serialized binary tensor objects on disk.
* **Page-In Cascade (Cache Miss)**: When a session stored on CPU RAM or NVMe is queried for a new token generation step, a cache miss occurs:
  1. The manager suspends computation.
  2. The block is paged back into GPU HBM (recalled from CPU or read from NVMe).
  3. Paging in increases GPU HBM usage, which may trigger a reactive eviction of other active GPU blocks to CPU RAM, which in turn might cascade and evict CPU blocks to NVMe.

---

## The KV Cache Bottleneck in Gemma 3

In auto-regressive decoding, the Key-Value (KV) cache grows linearly with the prompt sequence length and batch sizes:

$$\text{KV Cache Size} = 2 \times N_{\text{layers}} \times N_{\text{heads}} \times D_{\text{head}} \times L_{\text{context}} \times \text{Bytes per Element}$$

### Gemma 3 Parameter Profile (FP16 Precision):
* **Layers ($N_{\text{layers}}$)**: 42
* **KV Heads ($N_{\text{heads}}$)**: 8 (Grouped-Query Attention)
* **Head Dimension ($D_{\text{head}}$)**: 256
* **Bytes per Element**: 2 bytes (FP16)

Using these parameters, the KV cache allocation size per single token is:
$$\text{Size per Token} = 2 \times 42 \times 8 \times 256 \times 2 = 344,064 \text{ bytes} \approx 0.328 \text{ MB/token}$$

For an agent processing a **128k context window**, the KV Cache memory footprint reaches:
$$\text{Total Context Footprint} = 131,072 \text{ tokens} \times 0.328 \text{ MB/token} \approx 43,008 \text{ MB} \approx 42 \text{ GB}$$

With a model size of 8 GB running on a standard 16 GB GPU MIG slice, handling even a fraction of this context window causes an immediate **GPU Out-Of-Memory (OOM)** error, mandating a tiered hierarchical offloading scheme.

---

## File Structure & Components

1. **[kv_hierarchical_offload.py](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track2_kv_cache_offload/kv_hierarchical_offload.py)**:
   * Main PyTorch-based simulation of the 3-tier KV Cache Manager.
   * Tracks HBM, DDR5, and NVMe limits, triggering evictions at the 90% thresholds.
   * Simulates a multi-session `generate_token` loop.
   * Prints comparative latency logs and efficiency reports.
2. **[kv_offload_manager.py](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track2_kv_cache_offload/kv_offload_manager.py)**:
   * Original async PCIe-only (2-tier) simulation manager.
3. **[inference_engine.py](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track2_kv_cache_offload/inference_engine.py)**:
   * FastAPI gateway wrapping the cache manager.
4. **[test_cache.py](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track2_kv_cache_offload/test_cache.py)**:
   * Integration test script verifying 2-tier page-out/page-in operations.

---

## Running the PyTorch Simulation

Execute the 3-tier hierarchical offloader simulation directly:

```bash
uv run --with torch python3 kv_hierarchical_offload.py
```

This runs the auto-regressive generation loop across multiple concurrent agents, triggers evictions down to the NVMe layer, and displays detailed execution statistics and latency reports in a clean terminal table.
