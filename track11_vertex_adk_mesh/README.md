# Track 11: Vertex ADK Service Mesh & Stateless Agents

## Overview
This repository contains the blueprints and simulation code for **Track 11: Vertex Agent Development Kit (ADK) Mesh**. 

Historically, distributed agent swarms attempted to manage their own consensus by deploying Raft or Paxos protocols directly within the ephemeral worker pods. This is a severe anti-pattern that leads to split-brain scenarios, unbounded memory growth, and catastrophic failure loops during scale-down events.

In this track, we rip out the flawed in-memory Raft logic. Instead, we architect a **Stateless Compute / Stateful Storage** topology. Agent compute pods remain 100% ephemeral and stateless. All multi-agent context, session history, and checkpoint states are serialized via strict Protocol Buffers and streamed over gRPC mTLS directly into Google Cloud Spanner.

## Contents
- `decoupling_agentic_swarms_spanner.md`: A 1,500+ word deep-dive technical article explaining the architectural shift, complete with a complex Mermaid diagram illustrating the flow from ephemeral agent to Spanner's TrueTime Paxos backend.
- `agent_state.proto`: The Protocol Buffer definitions enforcing strict data contracts for the multi-agent context.
- `agent_spanner_client.py`: A simulated gRPC client demonstrating how an agent pod handles network partitions using exponential backoff and jitter when committing state to the global mesh.

## How to Run the Simulation
To execute the network partition and gRPC backoff simulation:
```bash
python3 agent_spanner_client.py
```
