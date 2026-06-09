# sidecar_proxy.py - mTLS Encrypted gRPC Sidecar Proxy & Serialization Helpers
import os
import random
import time
import concurrent.futures
from typing import Dict, Any, Tuple, Generator
import grpc

import agent_state_pb2
import agent_state_pb2_grpc

# Serialization mapping helpers
def dict_to_proto(data: Dict[str, Any], chunk_index: int = 0, is_last_chunk: bool = True) -> agent_state_pb2.AgentStatePayload:
    token_usage_proto = None
    if "token_usage" in data:
        token_usage_proto = agent_state_pb2.TokenUsage(
            prompt_tokens=data["token_usage"].get("prompt_tokens", 0),
            completion_tokens=data["token_usage"].get("completion_tokens", 0),
            total_tokens=data["token_usage"].get("total_tokens", 0)
        )
        
    memory_protos = []
    if "conversational_memory" in data:
        for entry in data["conversational_memory"]:
            memory_protos.append(agent_state_pb2.MemoryEntry(
                role=entry.get("role", ""),
                text=entry.get("text", "")
            ))
            
    tensor_proto = None
    if "tensor_metadata" in data:
        tensor_proto = agent_state_pb2.TensorMetadata(
            layers=data["tensor_metadata"].get("layers", 0),
            heads=data["tensor_metadata"].get("heads", 0),
            head_dim=data["tensor_metadata"].get("head_dim", 0),
            kv_cache_address=data["tensor_metadata"].get("kv_cache_address", ""),
            bytes_allocated=data["tensor_metadata"].get("bytes_allocated", 0)
        )
        
    return agent_state_pb2.AgentStatePayload(
        session_id=data.get("session_id", ""),
        agent_role=data.get("agent_role", ""),
        turn_index=data.get("turn_index", 0),
        token_usage=token_usage_proto,
        active_constraints=data.get("active_constraints", []),
        conversational_memory=memory_protos,
        tensor_metadata=tensor_proto,
        chunk_index=chunk_index,
        is_last_chunk=is_last_chunk
    )


def proto_to_dict(payload: agent_state_pb2.AgentStatePayload) -> Dict[str, Any]:
    data = {
        "session_id": payload.session_id,
        "agent_role": payload.agent_role,
        "turn_index": payload.turn_index,
        "active_constraints": list(payload.active_constraints),
    }
    
    if payload.HasField("token_usage"):
        data["token_usage"] = {
            "prompt_tokens": payload.token_usage.prompt_tokens,
            "completion_tokens": payload.token_usage.completion_tokens,
            "total_tokens": payload.token_usage.total_tokens
        }
        
    if payload.conversational_memory:
        data["conversational_memory"] = [
            {"role": m.role, "text": m.text} for m in payload.conversational_memory
        ]
        
    if payload.HasField("tensor_metadata"):
        data["tensor_metadata"] = {
            "layers": payload.tensor_metadata.layers,
            "heads": payload.tensor_metadata.heads,
            "head_dim": payload.tensor_metadata.head_dim,
            "kv_cache_address": payload.tensor_metadata.kv_cache_address,
            "bytes_allocated": payload.tensor_metadata.bytes_allocated
        }
        
    return data


class AgentStateServiceServicer(agent_state_pb2_grpc.AgentStateServiceServicer):
    def __init__(self, server_instance):
        self.server = server_instance

    def TransferState(self, request_iterator, context):
        last_processed = -1
        session_id = None
        
        try:
            for request in request_iterator:
                session_id = request.session_id
                chunk_idx = request.chunk_index
                
                # Network simulation
                if self.server.simulate_network_issues:
                    # 1. 5% packet loss check
                    if random.random() < 0.05:
                        print(f"[SERVER] [LOSS] Packet loss simulated on chunk {chunk_idx}.")
                        context.abort(grpc.StatusCode.UNAVAILABLE, f"Packet loss simulated on chunk {chunk_idx}")
                        
                    # 2. Network partition simulation at chunk 5
                    if chunk_idx == 5 and not self.server.partition_triggered:
                        self.server.partition_triggered = True
                        print(f"[SERVER] [PARTITION] Network partition triggered on chunk {chunk_idx}.")
                        context.abort(grpc.StatusCode.ABORTED, "Network partition triggered")
                
                # Update checkpoint
                last_processed = chunk_idx
                self.server.checkpoints[session_id] = last_processed
                
                if request.is_last_chunk:
                    return agent_state_pb2.TransferStatus(
                        status_message="State transfer completed successfully.",
                        success=True,
                        last_processed_chunk=last_processed
                    )
        except grpc.RpcError as e:
            # Re-raise to client
            raise e
            
        return agent_state_pb2.TransferStatus(
            status_message="Stream ended prematurely.",
            success=False,
            last_processed_chunk=last_processed
        )

    def GetCheckpoint(self, request, context):
        session_id = request.session_id
        if session_id in self.server.checkpoints:
            return agent_state_pb2.CheckpointResponse(
                last_processed_chunk=self.server.checkpoints[session_id],
                session_exists=True
            )
        else:
            return agent_state_pb2.CheckpointResponse(
                last_processed_chunk=-1,
                session_exists=False
            )


class MTLSSidecarServer:
    def __init__(self, host: str, port: int, cert_dir: str):
        self.host = host
        self.port = port
        self.cert_dir = cert_dir
        self.server = None
        self.checkpoints = {}
        
        # Cert paths
        self.ca_cert = os.path.join(cert_dir, "ca.crt")
        self.server_cert = os.path.join(cert_dir, "server.crt")
        self.server_key = os.path.join(cert_dir, "server.key")
        
        # Simulation flags
        self.simulate_network_issues = False
        self.partition_triggered = False

    def start(self):
        # Load cert bytes
        with open(self.ca_cert, "rb") as f:
            ca_cert_bytes = f.read()
        with open(self.server_cert, "rb") as f:
            server_cert_bytes = f.read()
        with open(self.server_key, "rb") as f:
            server_key_bytes = f.read()
            
        self.server = grpc.server(concurrent.futures.ThreadPoolExecutor(max_workers=5))
        agent_state_pb2_grpc.add_AgentStateServiceServicer_to_server(
            AgentStateServiceServicer(self), self.server
        )
        
        # Create mTLS credentials
        server_credentials = grpc.ssl_server_credentials(
            [(server_key_bytes, server_cert_bytes)],
            root_certificates=ca_cert_bytes,
            require_client_auth=True
        )
        
        self.server.add_secure_port(f"{self.host}:{self.port}", server_credentials)
        self.server.start()

    def stop(self):
        if self.server:
            self.server.stop(0)


class MTLSSidecarClient:
    def __init__(self, host: str, port: int, cert_dir: str):
        self.host = host
        self.port = port
        self.cert_dir = cert_dir
        
        # Cert paths
        self.ca_cert = os.path.join(cert_dir, "ca.crt")
        self.client_cert = os.path.join(cert_dir, "client.crt")
        self.client_key = os.path.join(cert_dir, "client.key")

    def _get_channel(self) -> grpc.Channel:
        with open(self.ca_cert, "rb") as f:
            ca_cert_bytes = f.read()
        with open(self.client_cert, "rb") as f:
            client_cert_bytes = f.read()
        with open(self.client_key, "rb") as f:
            client_key_bytes = f.read()
            
        client_credentials = grpc.ssl_channel_credentials(
            root_certificates=ca_cert_bytes,
            private_key=client_key_bytes,
            certificate_chain=client_cert_bytes
        )
        
        # Overriding authority is necessary when testing locally with IP addresses
        options = (('grpc.ssl_target_name_override', '127.0.0.1'),)
        return grpc.secure_channel(f"{self.host}:{self.port}", client_credentials, options)

    def send_state_stream(self, data: Dict[str, Any], num_chunks: int, simulate_network_issues: bool = False) -> Tuple[bool, float, int]:
        """
        Sends the agent state payload as a stream of chunks.
        Implements self-healing retry logic using GetCheckpoint state recovery.
        Returns: (success, latency_ms, retries_attempted)
        """
        session_id = data.get("session_id", "session-unknown")
        start_time = time.perf_counter()
        
        current_chunk = 0
        retries = 0
        max_retries = 5
        backoff = 0.5
        
        channel = self._get_channel()
        stub = agent_state_pb2_grpc.AgentStateServiceStub(channel)
        
        while current_chunk < num_chunks and retries <= max_retries:
            try:
                # Generator for streaming
                def chunk_generator() -> Generator[agent_state_pb2.AgentStatePayload, None, None]:
                    nonlocal current_chunk
                    for c in range(current_chunk, num_chunks):
                        is_last = (c == num_chunks - 1)
                        # We simulate state content split by tagging chunk indices
                        yield dict_to_proto(data, chunk_index=c, is_last_chunk=is_last)
                        
                # Call stream RPC
                response = stub.TransferState(chunk_generator())
                if response.success:
                    latency = (time.perf_counter() - start_time) * 1000.0
                    channel.close()
                    return True, latency, retries
                    
            except grpc.RpcError as e:
                retries += 1
                print(f"[CLIENT] [ERROR] gRPC Stream failed at chunk {current_chunk}: {e.details()}. Recovering...")
                
                # Wait before checking checkpoint and retrying
                time.sleep(backoff)
                backoff *= 1.5
                
                # Check checkpoint
                try:
                    checkpoint_response = stub.GetCheckpoint(agent_state_pb2.CheckpointRequest(session_id=session_id))
                    if checkpoint_response.session_exists:
                        server_last = checkpoint_response.last_processed_chunk
                        print(f"[CLIENT] [RECOVERY] Checkpoint found. Server last processed chunk: {server_last}. Resuming from chunk {server_last + 1}.")
                        current_chunk = server_last + 1
                    else:
                        print("[CLIENT] [RECOVERY] No session checkpoint found. Restarting stream from chunk 0.")
                        current_chunk = 0
                except grpc.RpcError as checkpoint_err:
                    # Connection is dead, re-establish channel
                    print(f"[CLIENT] [RECOVERY] Checkpoint RPC failed ({checkpoint_err.details()}). Re-establishing secure channel...")
                    channel.close()
                    channel = self._get_channel()
                    stub = agent_state_pb2_grpc.AgentStateServiceStub(channel)
                    
        channel.close()
        latency = (time.perf_counter() - start_time) * 1000.0
        return False, latency, retries
