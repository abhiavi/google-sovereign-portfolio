#!/usr/bin/env python3
"""
Track 11: Vertex ADK Mesh - Stateless Agent Spanner Client
Simulates a Python gRPC client that commits multi-agent context states
to Google Cloud Spanner. Incorporates exponential backoff and jitter
to handle simulated network partitions.
"""
import time
import random
import uuid
from typing import Dict

class MockSpannerStub:
    """Mocks a gRPC Stub connected to Cloud Spanner."""
    def CommitState(self, request, timeout=None):
        # Introduce a 30% chance of a network partition or transient failure
        if random.random() < 0.3:
            raise Exception("gRPC Error: UNAVAILABLE - Network partition detected")
        
        # Simulate successful Paxos commit using TrueTime
        return {
            "success": True,
            "spanner_commit_timestamp": int(time.time() * 1000000), # microseconds
            "error_message": ""
        }

class AgentSpannerClient:
    def __init__(self, stub):
        self.stub = stub
        self.max_retries = 5
        self.base_backoff = 0.1

    def commit_state(self, agent_id: str, session_id: str, sequence_number: int, state: Dict[str, str], intent: str):
        # In a real environment, this dictionary is serialized into a Protobuf payload.
        request = {
            "state": {
                "agent_id": agent_id,
                "session_id": session_id,
                "sequence_number": sequence_number,
                "internal_state": state,
                "current_intent": intent,
                "timestamp_utc": int(time.time() * 1000)
            }
        }
        
        retries = 0
        while retries <= self.max_retries:
            try:
                print(f"[gRPC Client] Attempting to commit state for agent '{agent_id}' (seq {sequence_number})...")
                response = self.stub.CommitState(request, timeout=5.0)
                print(f"  -> [SUCCESS] Spanner committed at TrueTime {response['spanner_commit_timestamp']}")
                return True
            except Exception as e:
                retries += 1
                if retries > self.max_retries:
                    print(f"  -> [FATAL] Failed to commit state after {self.max_retries} retries. Agent pod must crash and restart.")
                    return False
                    
                # Exponential backoff with jitter
                backoff = self.base_backoff * (2 ** retries) + random.uniform(0, 0.1)
                print(f"  -> [FAILED] {str(e)}. Retrying {retries}/{self.max_retries} in {backoff:.2f}s...")
                time.sleep(backoff)

if __name__ == "__main__":
    print("Initializing ADK Mesh Spanner Client Simulation...\n")
    stub = MockSpannerStub()
    client = AgentSpannerClient(stub)
    
    agent_name = "adk-node-492"
    conversation_session = str(uuid.uuid4())
    
    for seq in range(1, 6):
        state_payload = {"memory_buffer": f"processed chunk {seq}", "slot_status": "in_progress"}
        intent = "DataAggregation"
        
        success = client.commit_state(agent_name, conversation_session, seq, state_payload, intent)
        if not success:
            print("\nSimulation aborted due to persistent failure.")
            break
            
        time.sleep(0.5) # Simulate processing delay between state updates
