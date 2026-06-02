# Sovereign KV Cache Offloader (Track 2)

This directory contains the production-grade simulation of **Track 2 of the Google Sovereign AI Portfolio: Shattering the LLM Memory Wall via Dynamic KV Cache Offloading**.

The gateway manages GPU High Bandwidth Memory (HBM) constraints during ultra-long context generation ($128\text{k}+$ tokens) in concurrent multi-agent systems, dynamically offloading ("paging out") cold key-value states to Host CPU RAM and retrieving them on-demand via PCIe.

---

## The KV Cache Bottleneck

In auto-regressive decoding, the Key-Value (KV) cache grows linearly with the prompt sequence length and batch sizes:

$$\text{KV Cache Size} = 2 \times N_{\text{layers}} \times N_{\text{heads}} \times D_{\text{head}} \times L_{\text{context}} \times \text{Bytes per Element}$$

### Gemma 3 Parameter Profile (FP16 Precision):
* **Layers ($N_{\text{layers}}$)**: 42
* **KV Heads ($N_{\text{heads}}$)**: 8 (Grouped-Query Attention)
* **Head Dimension ($D_{\text{head}}$)**: 256
* **Bytes per Element**: 2 bytes (FP16)

Using these parameters, we compute the KV cache allocation size per single token:
$$\text{Size per Token} = 2 \times 42 \times 8 \times 256 \times 2 = 344,064 \text{ bytes} \approx 0.328 \text{ MB/token}$$

For an agent processing a **128k context window**, the KV Cache memory footprint reaches:
$$\text{Total Context Footprint} = 131,072 \text{ tokens} \times 0.328 \text{ MB/token} \approx 43,008 \text{ MB} \approx 42 \text{ GB}$$

With a model size of 8 GB running on a standard 16 GB GPU MIG slice, handling even a fraction of this context window causes an immediate **GPU Out-Of-Memory (OOM)** error.

---

## Disaggregated Memory & Interconnect Topology

To maintain complete cryptographic isolation while preserving context data, the proxy architecture shifts virtual address mapping entirely out of software-defined space and moves it straight to hardware-constrained boundaries. 

```
The structural topology executes over three distinct physical planes:

```text
+-----------------------------------------------------------------------+
|                       PROXMOX COMPUTE NODE HOST                       |
|                                                                       |
|  +-----------------------+              +--------------------------+  |
|  | NVIDIA Blackwell HBM  |              |   Host System RAM Pool   |  |
|  | (Level-1 L1 Model KV) |              |  (Level-2 L2 Swap Space) |  |
|  +-----------+-----------+              +------------+-------------+  |
|              ^                                       ^                |
|              |         Asynchronous Paging           |                |
|              +=======================================+                |
|                  PCIe Gen 4 x8 Bus (16 GB/s Fabric)                   |
|                                                                       |
+-----------------------------------------------------------------------+
|                 TAILSCALE ENCRYPTED OVERLAY NETWORK                   |
+-----------------------------------------------------------------------+
```

1. **Safety Threshold Enforcement**: Total GPU utilization (model weights + active KV caches) is capped at **90%** of available HBM (14,745.6 MB out of 16 GB).
2. **LRU Page Eviction**: When allocation of a new context or generation turn exceeds the safety limit, the `KVOffloadManager` identifies the **Least Recently Used (LRU)** cache block in HBM and pages it out to CPU Host RAM.
3. **PCIe Transit Emulation**: The offloader models standard PCIe Gen 4 x8 bandwidth ($16 \text{ GB/s}$). Eviction/Paging latency is computed as:
   $$\text{Transit Latency (sec)} = \frac{\text{Block Size (MB)}}{16.0 \times 1024}$$
4. **Cache Miss Recovery**: When a user queries a paged-out session, the engine encounters a cache miss. It suspends execution, issues a dynamic PCIe Page-In, and evicts other active blocks to Host RAM if HBM is exhausted.

---

## Components

1. **[kv_offload_manager.py](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track2_kv_cache_offload/kv_offload_manager.py)**:
   - Evaluates memory allocations.
   - Implements async PCIe transmission loops and LRU cache-management heuristics.
2. **[inference_engine.py](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track2_kv_cache_offload/inference_engine.py)**:
   - FastAPI gateway wrapping the cache manager.
   - Exposes `/v1/chat/completions` (OpenAI-compatible) and `/v1/cache/status` (diagnostics).
3. **[test_cache.py](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track2_kv_cache_offload/test_cache.py)**:
   - Integration test script simulating multi-agent memory spikes and verifying page-out/page-in operations.

---

## Local Setup & Verification

### 1. Execute the Integration Test Suite
To verify the LRU paging mechanism, run the test script:
```bash
/home/abhishek/ObsidianVault/03_Active_Projects/databricks_sovereign_portfolio/track1_supervisor_mcp/.venv/bin/python test_cache.py
```

### 2. Manual Endpoints Verification
Start the engine locally:
```bash
/home/abhishek/ObsidianVault/03_Active_Projects/databricks_sovereign_portfolio/track1_supervisor_mcp/.venv/bin/python -m uvicorn inference_engine:app --host 127.0.0.1 --port 8000
```

#### Run Chat Completion with Persisted KV Cache:
Pass a custom `session_id` to establish a persistent cache block:
```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-3-7b-it",
    "session_id": "agent-session-001",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Begin highly conversational multi-turn generation task."}]
  }'
```

#### Check Cache Manager Diagnostics:
Inspect current HBM / CPU Host allocation details:
```bash
curl http://127.0.0.1:8000/v1/cache/status
```
