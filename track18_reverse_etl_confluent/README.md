# Track 18: Reverse ETL Confluent Impedance Mismatch

## Overview
This repository contains the architectural blueprints and executable simulation for **Track 18: Reverse ETL Confluent**. The primary objective of this track is to solve a critical architectural vulnerability that occurs when connecting strict streaming engines to stateless delivery systems—specifically, the boundary between Confluent Kafka Connect and Google Cloud Pub/Sub.

## Contents

- **`exactly_once_impedance_mismatch_redis.md`**: A comprehensive, 1,500+ word technical whitepaper. It defines the "Exactly-Once Impedance Mismatch" caused by Kafka's retries colliding with Pub/Sub's at-least-once delivery guarantees. The document architects a solution utilizing a Redis in-memory cache to build an idempotent ingestion layer, complete with a Mermaid sequence diagram mapping out the deduplication pipeline.
- **`redis_idempotent_consumer.py`**: A robust Python simulation (150+ lines). It models a network retry storm generating hundreds of duplicate messages from a mock Pub/Sub queue. It demonstrates connecting to a Redis instance (with a simulated fallback) and utilizing atomic `SETNX` (Set if Not Exists) operations to filter out duplicates, guaranteeing exactly-once execution.

## Running the Simulation

To execute the Redis deduplication simulation and view the pipeline execution audit:

```bash
# Optional: Ensure the redis python package is installed
# pip install redis

python3 redis_idempotent_consumer.py
```

The simulation will artificially inject a massive network storm (60% duplicate probability) and prove that the Redis boundary successfully drops every duplicate payload.
