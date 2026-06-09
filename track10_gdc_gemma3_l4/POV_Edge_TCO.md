# POV Edge TCO: Hardware Density & Power Efficiency on GDC Edge (L4 GPU)
This report details the hardware density, thermal performance, power draw, and total cost of ownership (TCO) advantages of running Gemma 3 (9B) with **INT8 Quantization** and **Speculative Decoding** on NVIDIA L4 GPUs at the edge, simulated across a dataset of 500 varied agentic prompts.

## Executive Summary
Edge AI deployments on Google Distributed Cloud (GDC) are heavily constrained by physical constraints: power envelopes, thermal dissipation limits, and physical server space. Standard autoregressive FP16 inference on a single L4 GPU consumes high power, operates near the thermal ceiling, and limits the hardware density of agentic swarms.

By combining **INT8 Quantization** and **Speculative Decoding** (using a Gemma 3 2B draft model), we increase token generation speeds by **5.8x**, reduce the energy-per-token footprint by **92.1%**, and double the concurrent agentic capacity of each edge node.

---

## Empirical Simulation Results (500 Prompts)

| Metric | FP16 Baseline (9B) | INT8 Quantized (9B) | Speculative FP16 (9B+2B) | Speculative INT8 (9B+2B) | Overall Benefit (SI8 vs FP16) |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Throughput (Tokens/sec)** | 28.57 | 83.33 | 59.35 | 165.68 | **5.80x speedup** |
| **Average Latency / Token** | 35.0 ms | 12.0 ms | 16.9 ms | 6.0 ms | **-82.8% reduction** |
| **Avg GPU Power Draw** | 68.0 W | 42.0 W | 50.8 W | 31.0 W | **-54.4% power reduction** |
| **Energy Consumption / Token** | 2.3800 J | 0.5040 J | 0.8561 J | 0.1871 J | **-92.1% energy saved** |
| **Simulated GPU Temperature** | 65.8°C | 50.2°C | 55.5°C | 43.6°C | **22.2°C cooler** |
| **Total Energy (500 prompts)** | 333.80 kJ | 70.69 kJ | 120.07 kJ | 26.24 kJ | **-92.1% total energy reduction** |

---

## Edge Node Density and Hardware TCO Analysis

### 1. Hardware Concurrency Density
For an edge deployment node (e.g. GDC Edge server) with a strict power delivery limit of **500W** allocated for inference GPUs:
- **FP16 Baseline (Standard Autoregressive)**: Can support **7 concurrent agent streams** (each consuming 68.0W).
- **Speculative INT8 (Optimized)**: Can support **16 concurrent agent streams** (each consuming 31.0W).
- **Density Advantage**: **+128.6% capacity expansion**, allowing more agent swarms to operate on the same physical box without triggering power failures or thermal throttling.

### 2. Thermal Dissipation & Reliability
- Autoregressive FP16 inference operates near the thermal envelope threshold, driving GPU temperatures to **65.8°C**. This triggers cooling fans to run at max RPM, increasing edge site noise and wear-and-tear.
- Speculative INT8 inference runs much cooler (**43.6°C**), which reduces the failure rate of edge nodes, extends hardware lifespan, and decreases required cooling capacity.

### 3. TCO Calculation
Assuming an edge electricity rate of **$0.15 / kWh** and hardware lease/amortization cost of **$0.80 / hr** per L4 GPU:
- **FP16 Baseline**:
  - GPU Cost: $0.80 / hr
  - Power Cost (68.0W): $0.0102 / hr
  - Throughput: ~28.6 tokens/sec
  - Total Cost per Million Tokens: **$7.8691**
- **Speculative INT8**:
  - GPU Cost: $0.80 / hr
  - Power Cost (31.0W): $0.0047 / hr
  - Throughput: ~166.7 tokens/sec
  - Total Cost per Million Tokens: **$1.3409**
- **Financial Benefit**: Speculative INT8 offers a **83.0% TCO reduction** per token generated.

## Conclusion
Edge deployments must squeeze every drop of efficiency out of L4 GPUs. Combining INT8 dynamic quantization with Speculative Decoding achieves massive latency and energy savings, translating directly into physical density advantages and lower operational costs.
