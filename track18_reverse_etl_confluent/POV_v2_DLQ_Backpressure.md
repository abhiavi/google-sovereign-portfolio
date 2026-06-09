# POV v2: Resilient Event Streaming via DLQ Backpressure

## Context: The DLQ Overflow Vulnerability

In high-throughput event streaming architectures (like our Confluent Reverse ETL pipeline), the Dead-Letter Queue (DLQ) is an essential safety valve for malformed data. Setting `errors.tolerance=all` ensures the pipeline doesn't halt on a single bad record. 

However, this creates a vulnerability: **DLQ Overflow**. If an upstream producer pushes a structurally fatal update (e.g., an entirely corrupted batch), the pipeline will frantically route 100% of messages to the DLQ. If millions of messages are routed, the DLQ topic can exceed storage limits, or the broker's I/O overhead can trigger a cascading failure, ultimately crashing the Connect worker nodes.

## Solution: Automatic Backpressure 

In Track 18 (Iteration 2), we implemented a defensive backpressure mechanism within the connector topology test harness.

1. **Capacity Thresholding**: We established a maximum continuous DLQ routing threshold (`MAX_DLQ_CAPACITY = 10,000`).
2. **Circuit Breaking**: The system monitors the rate of DLQ routing. If a continuous stream of malformed payloads hits the threshold, it implies a systemic upstream failure, not an isolated anomaly.
3. **Pausing Ingestion**: Upon reaching the threshold, the system immediately asserts **backpressure**, effectively pausing the source connector. 

## Outcome

By simulating a 50,000 malformed payload barrage, we verified that the circuit breaker trips at exactly 10,000 errors. Instead of overwhelming the cluster or crashing the worker nodes, the pipeline gracefully pauses, alerts the on-call team, and preserves the operational integrity of the underlying infrastructure. This transforms a potential catastrophic outage into a managed, debuggable incident.
