# POV v2: Resolving Semantic Collisions in Distributed Data Catalogs

## Context: The Multi-Producer Collision Problem

In a federated data mesh architecture, multiple domain teams or automated agents might attempt to publish schema updates for the same data entity simultaneously. Without strict concurrency controls, these "semantic collisions" can corrupt the catalog state. For example, if Team A pushes a v2 schema update at T=1, but a delayed webhook from Team B pushes a conflicting v1 schema update at T=2 (where the actual event occurred at T=0), a naive catalog will overwrite the newer v2 schema with the stale v1 schema.

## Solution: Deterministic Timestamp-Based Resolution

In Track 17 (Iteration 2), we enhanced the `SchemaEventHandler` to implement deterministic collision resolution using a **Last-Writer-Wins (LWW) mechanism based on event origin timestamps**:

1. **Origin Timestamps**: Audit logs provide an exact UTC `timestamp` representing when the event *actually occurred* at the source.
2. **Entity-Level Monotonicity**: When a schema update arrives, the handler scans the existing catalog for that specific resource. 
3. **Stale Update Rejection**: If *any* existing field within that resource possesses a `last_modified` timestamp newer than the incoming event's timestamp, the handler detects a stale out-of-order event. It rejects the *entire* update to prevent partial, interleaved schema application.

## Outcome

By enforcing temporal monotonicity, the unified metadata catalog guarantees eventual consistency. Agentic systems reading from the catalog are assured that the recorded schema strictly represents the latest known physical state of the data product, completely insulated from network delays and out-of-order message delivery inherent in distributed systems.
