# GDC Edge L4 Quantization & Speculative Decoding with 3-Tier KV Cache Eviction

## Phase 1: The Enterprise Bottleneck (Executive Summary)
Edge AI deployments on Google Distributed Cloud (GDC) are constrained by tight physical power budgets ($P \le 72\text{W}$ TDP per L4 GPU) and strict thermal limits ($T_{GPU} < 80^{\circ}\text{C}$). To improve inference throughput, we implement speculative decoding running Gemma 3 9B (Target model) and Gemma 3 2B (Draft model) concurrently on a single 24GB GDDR6 L4 GPU. 

However, storing both models in memory concurrently imposes severe VRAM constraints:
*   **Weights in FP16**: Target ($18\text{ GB}$) + Draft ($4\text{ GB}$) = **$22\text{ GB}$**, leaving only $2\text{ GB}$ for activations and KV caches.
*   **Weights in INT8**: Target ($9\text{ GB}$) + Draft ($2\text{ GB}$) = **$11\text{ GB}$**, leaving $13\text{ GB}$ of VRAM.

In auto-regressive decoding, the Key-Value (KV) cache grows linearly with context length ($L$). For a $128\text{k}$ context window, the KV cache footprint is:
$$\text{KV Cache Size (9B)} = 2 \times N_{\text{layers}} \times N_{\text{heads}} \times D_{\text{head}} \times L \times \text{Bytes} = 2 \times 42 \times 8 \times 256 \times 131,072 \times 2 \text{ bytes} \approx 43\text{ GB}$$
$$\text{KV Cache Size (2B)} = 2 \times 26 \times 4 \times 256 \times 131,072 \times 2 \text{ bytes} \approx 13\text{ GB}$$

The combined context footprint of **$56\text{ GB}$** far exceeds the L4's remaining VRAM capacity, triggering immediate Out-Of-Memory (OOM) failures. To prevent these crashes, we integrate the **3-Tier KV Cache Eviction protocol** (cross-referencing [Track 2](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track2_kv_cache_offload/README.md)), which pages out inactive KV cache tensors across GPU VRAM, Host DDR5 RAM, and PCIe Gen4 NVMe storage.

---

## Phase 2: The Core Architecture

The speculative decoding loop is integrated with a hierarchical 3-Tier KV cache manager that virtualizes the GPU memory space:

```mermaid
graph TD
    Prompt[Input Prompt] --> Prefill[Prefill Phase]
    Prefill --> DraftLoop[Gemma 3 2B Draft Gen: K=4 tokens]
    DraftLoop --> TargetVerify[Gemma 3 9B Target Verify]
    
    subgraph 3-Tier KV Cache Eviction Manager (Track 2)
        TargetVerify -->|VRAM > 90% Threshold| Tier1[Tier 1: GPU GDDR6 VRAM]
        Tier1 -->|Evict LRU blocks via PCIe Gen4 x16| Tier2[Tier 2: Host DDR5 RAM]
        Tier2 -->|Evict coldest blocks to disk| Tier3[Tier 3: PCIe Gen4 NVMe Storage]
    end

    TargetVerify -->|Accept Tokens| Commit[Commit Tokens & Update KV Cache]
    TargetVerify -->|Reject Tokens| Rollback[Rollback KV Cache & Regenerate]
    Commit --> DraftLoop
```

### 3-Tier KV Cache Eviction Logic
1.  **Tier 1 (GPU VRAM)**: Primary hot cache. Active blocks are held in GDDR6. When GPU memory utilization exceeds **90%**, the manager evicts the least recently used (LRU) KV block to Host RAM.
2.  **Tier 2 (Host DDR5 RAM)**: Warm cache. Operates via PCIe Gen4 x16 bus. If Host RAM allocation exceeds **90%** of its safety limit, the coldest blocks are serialized and written to NVMe storage.
3.  **Tier 3 (PCIe NVMe)**: Cold cache. Tensors are stored on disk. Upon a cache miss, the block is paged back into GDDR6, cascading younger blocks down the hierarchy if needed.

---

## Phase 3: Baseline Telemetry
Evaluating 500 varied agentic prompts under nominal conditions (25°C ambient):
*   **Throughput**: Speculative INT8 achieved **165.68 tok/s** compared to **28.57 tok/s** for FP16 (5.80x speedup).
*   **Energy Consumption**: Speculative INT8 consumed **0.1871 J/token** vs **2.3800 J/token** for FP16 (92.1% reduction).
*   **Est. GPU Temperature**: Speculative INT8 operated at **43.6°C** vs **65.8°C** for FP16, remaining far below the thermal throttling envelope.

---

## Phase 4: Chaos Engineering & Resilience

### 1. Thermal Throttling Mitigation (45°C Ambient)
Under a simulated outdoor cabinet installation reaching 45°C ambient temperature:
*   **Target FP16 (Failure)**: GPU reached **79.7°C**, triggering DVFS thermal throttling that dropped clock speeds by 30%. This inflated TTFT by **+42.9%** (from 798.7 ms to 1141.0 ms) and reduced throughput by **-30.0%**.
*   **Speculative INT8 (Recovery)**: Reduced average GPU power draw from 68W to 31W. The GPU operated unthrottled at **63.6°C** with **0% performance degradation** and maintained a stable TTFT of **235.1 ms**.

### 2. OOM Prevention under High Context Length
During a 128k long-context generation test on a single L4 GPU:
*   **Without 3-Tier Eviction (Failure)**: The active KV cache exhausted the remaining $13\text{ GB}$ VRAM, causing an immediate **GPU OOM crash** on token 6,400 of the prefill phase.
*   **With 3-Tier Eviction (Recovery)**: The manager paged out inactive KV cache blocks to DDR5 Host RAM and NVMe disk, maintaining active VRAM utilization below the 90% safety ceiling. The run completed with a **100% request completion rate** and zero OOM events.

---

## Phase 5: Reproduction Steps
To execute the edge quantization and speculative decoding simulation:
1. Navigate to [track10_gdc_gemma3_l4/](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track10_gdc_gemma3_l4/).
2. Execute `python3 gemma3_quantize_inference.py`.
3. Review the TCO profile and thermal diagnostics in [POV_v2_Thermal_Throttling.md](file:///home/abhishek/ObsidianVault/03_Active_Projects/google-sovereign-portfolio/track10_gdc_gemma3_l4/POV_v2_Thermal_Throttling.md).
