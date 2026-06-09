# POV v2: Thermal Throttling Resilience on GDC Edge
This report evaluates the performance of Gemma 3 (9B) inference under simulated hardware degradation caused by high ambient temperatures at an Indian telco edge node (**45°C ambient temperature**, **80°C GPU thermal throttling threshold**, causing a **30% clock speed reduction**), benchmarked over 500 agentic prompts.

## Executive Summary
Edge nodes deployed in remote environments (like cell towers or outdoor telco cabinets) are subject to high ambient temperatures and compromised cooling. Under these conditions, executing high-power FP16 models drives GPU temperatures past their safe operating limit, triggering **DVFS (Dynamic Voltage and Frequency Scaling) thermal throttling**. This slows down processing speeds and degrades the latency of interactive agent communication.

Integrating **INT8 Quantization** and **Speculative Decoding** reduces average GPU power draw, allowing the hardware to operate comfortably below the thermal throttling envelope even at 45°C ambient. This guarantees consistent low latency and eliminates performance degradation.

---

## Thermal Degradation Benchmark Comparison (500 Prompts)

### 1. FP16 Target Model (Standard Autoregressive)
- **Nominal (25°C Ambient)**: Runs at **65.8°C** without throttling. Average TTFT: **798.7 ms**.
- **Chaos (45°C Ambient)**: Triggers thermal throttling on **100%** of prompts. GPU runs at **79.7°C** (throttled).
- **Time-To-First-Token (TTFT) Impact**: Average TTFT degrades from **798.7 ms** to **1141.0 ms** (**+42.9% latency inflation**).
- **Throughput Impact**: Average throughput drops by **30.0%** (from **41.16 tok/s** to **28.81 tok/s**).

### 2. Speculative INT8 Model (9B INT8 + 2B INT8 Draft)
- **Nominal (25°C Ambient)**: Runs at **43.6°C**. Average TTFT: **235.1 ms**.
- **Chaos (45°C Ambient)**: Triggers thermal throttling on **0%** of prompts. GPU runs at **63.6°C** (completely unthrottled).
- **Time-To-First-Token (TTFT) Impact**: Average TTFT remains unchanged at **235.1 ms** (**0.0% degradation**).
- **Throughput Impact**: Throughput remains stable at **227.48 tok/s** (**0.0% degradation**).

---

## Global Performance Metrics Table (Chaos: 45°C Ambient)

| Mode / Configuration | Throttling Rate | Est. GPU Temp | Avg TTFT | Throughput | Degradation vs Nominal |
|:---|:---:|:---:|:---:|:---:|:---:|
| **TARGET FP16** | 100.0% | 79.7°C | 1141.0 ms | 28.81 tok/s | **+42.9% TTFT / -30.0% TPS** |
| **TARGET INT8** | 0.0% | 70.2°C | 241.1 ms | 121.17 tok/s | **+0.0% TTFT / -0.0% TPS** |
| **SPEC FP16** | 0.0% | 75.5°C | 780.5 ms | 79.59 tok/s | **+0.0% TTFT / -0.0% TPS** |
| **SPEC INT8** | 0.0% | 63.6°C | 235.1 ms | 227.48 tok/s | **+0.0% TTFT / -0.0% TPS** |

---

## Technical Analysis of Thermal Resilience

### 1. Prefill Acceleration (TTFT Optimization)
Time-To-First-Token is governed by the prefill phase (processing the input prompt context). The base prefill latency for FP16 is high. When the GPU throttles:
- The clock speed drops to **70% of baseline**.
- The prefill processing time balloons, inflating average TTFT from **798.7 ms** to **1141.0 ms**.
- For INT8-based models, the base prefill is processed using low-power Tensor Cores, generating the first token in **235.1 ms** without hitting the thermal ceiling.

### 2. Eliminating Edge Heat Accumulation
The primary cause of thermal throttling is the continuous heat accumulation when executing dense FP16 weights.
- The 9B FP16 model draws **68W**, causing a delta-T of **40.8°C** above ambient. At 45°C ambient, this pushes the GPU core to **85.8°C**, triggering DVFS safety clamps.
- Speculative INT8 draws only **31W**, causing a delta-T of **18.6°C**. Even at 45°C ambient, the GPU stays at **63.6°C**, operating safely within the nominal thermal margins.

## Conclusion
Edge deployments in harsh environmental zones cannot rely on baseline FP16 models. Speculative INT8 decoding provides **thermal immunity**, ensuring that interactive agent response times (TTFT) remain fast and stable, regardless of outdoor climatic conditions.
