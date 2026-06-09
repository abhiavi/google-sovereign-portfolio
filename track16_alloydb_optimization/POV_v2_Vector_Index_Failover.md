# Track 16 POV: HNSW Vector Index Failover (Iteration 2)

## Context
This Point-of-View (POV) evaluates the data reliability and system integrity of AlloyDB when executing a Cross-Region Failover during an intense maintenance operation: the rebuilding of a massive `pgvector` HNSW (Hierarchical Navigable Small World) index.

## The Chaos Engineering Test
We simulated an environment running heavy hybrid workloads (HTAP). During the test:
1. Massive amounts of vector embeddings were ingested.
2. The Database initiated a multi-gigabyte HNSW index rebuild across the active node.
3. Mid-rebuild, we triggered an unexpected **Cross-Region Replica Promotion (Failover)** simulating a primary region outage.

## Reliability Observations
In standard PostgreSQL, interrupting an index rebuild mid-flight often results in catastrophic WAL (Write-Ahead Log) corruption, requiring full physical backups to restore consistency.

**AlloyDB Behavior:**
- **Promoted Cleanly:** The secondary cross-region replica promoted to Primary flawlessly.
- **No WAL Corruption:** Because AlloyDB separates the storage layer from the compute layer, the WAL is handled autonomously by the storage tier. The failover did not corrupt the transaction log.
- **Seamless Resume:** Once promoted, the new Primary recognized the incomplete index build. It safely paused, validated the WAL checksums, and cleanly resumed the HNSW index compilation exactly where it left off.

## Conclusion
AlloyDB transforms `pgvector` workloads from experimental, fragile operations into true enterprise-grade reliable deployments. Its decoupled storage architecture ensures that even complex, multi-layered vector operations cannot corrupt the underlying transactional state during high-availability failovers.
