# sidecar_proxy.py - mTLS Stateless gRPC Sidecar Proxy with Cloud Spanner persistence
import os
import random
import time
import concurrent.futures
from typing import Dict, Any, Tuple, Generator
import grpc

import agent_state_pb2
import agent_state_pb2_grpc

# Global Mock Cloud Spanner Database (highly available, multi-region cluster)
class MockSpannerDatabase:
    def __init__(self):
        self.tables = {} # table_name -> key_value_store
        self.checkpoints = {} # session_id -> last_chunk_index
        # Node connectivity to Spanner: maps node_port -> boolean
        self.connectivity = {}

    def is_node_connected(self, port: int) -> bool:
        return self.connectivity.get(port, True)

    def write_state(self, node_port: int, session_id: str, data: Dict[str, Any], last_chunk: int):
        if not self.is_node_connected(node_port):
            raise RuntimeError("Cloud Spanner database cluster is unreachable from this compute node.")
        
        # Simulate transactional write in Spanner
        time.sleep(0.005) # Spanner multi-region write latency (~5ms)
        self.tables[session_id] = data
        self.checkpoints[session_id] = last_chunk

    def read_state(self, node_port: int, session_id: str) -> Dict[str, Any]:
        if not self.is_node_connected(node_port):
            raise RuntimeError("Cloud Spanner database cluster is unreachable from this compute node.")
        return self.tables.get(session_id, None)

    def get_checkpoint(self, node_port: int, session_id: str) -> int:
        if not self.is_node_connected(node_port):
            raise RuntimeError("Cloud Spanner database cluster is unreachable from this compute node.")
        return self.checkpoints.get(session_id, -1)


# Singleton Spanner instance
SPANNER_DB = MockSpannerDatabase()


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
        buffered_payload = None
        
        try:
            for request in request_iterator:
                session_id = request.session_id
                chunk_idx = request.chunk_index
                
                # Dynamic network drop simulation (for packet loss test)
                if self.server.simulate_packet_loss:
                    if random.random() < 0.05:
                        print(f"[SERVER:{self.server.port}] [LOSS] Simulating random packet loss on chunk {chunk_idx}.")
                        context.abort(grpc.StatusCode.UNAVAILABLE, "Random packet loss occurred.")
                
                # Buffer the dict payload
                buffered_payload = proto_to_dict(request)
                last_processed = chunk_idx
                
                # Write to Cloud Spanner only when the last chunk is successfully received (guarantees transaction boundary)
                if request.is_last_chunk:
                    try:
                        SPANNER_DB.write_state(self.server.port, session_id, buffered_payload, last_processed)
                        return agent_state_pb2.TransferStatus(
                            status_message="State successfully written to Cloud Spanner.",
                            success=True,
                            last_processed_chunk=last_processed
                        )
                    except RuntimeError as e:
                        print(f"[SERVER:{self.server.port}] [DB_ERROR] Spanner transaction aborted: {str(e)}")
                        context.abort(grpc.StatusCode.ABORTED, str(e))
                        
        except grpc.RpcError as e:
            raise e
            
        return agent_state_pb2.TransferStatus(
            status_message="Stream interrupted before completion.",
            success=False,
            last_processed_chunk=last_processed
        )

    def GetCheckpoint(self, request, context):
        session_id = request.session_id
        try:
            chk = SPANNER_DB.get_checkpoint(self.server.port, session_id)
            return agent_state_pb2.CheckpointResponse(
                last_processed_chunk=chk,
                session_exists=(chk != -1)
            )
        except RuntimeError as e:
            context.abort(grpc.StatusCode.UNAVAILABLE, str(e))


class MTLSSidecarServer:
    def __init__(self, host: str, port: int, cert_dir: str):
        self.host = host
        self.port = port
        self.cert_dir = cert_dir
        self.server = None
        
        # Cert paths
        self.ca_cert = os.path.join(cert_dir, "ca.crt")
        self.server_cert = os.path.join(cert_dir, "server.crt")
        self.server_key = os.path.join(cert_dir, "server.key")
        
        # Simulation flags
        self.simulate_packet_loss = False

    def start(self):
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
        
        options = (('grpc.ssl_target_name_override', '127.0.0.1'),)
        return grpc.secure_channel(f"{self.host}:{self.port}", client_credentials, options)

    def send_state_stream(self, data: Dict[str, Any], num_chunks: int, simulate_packet_loss: bool = False) -> Tuple[bool, float, int]:
        """
        Streams the agent state payload to the sidecar proxy.
        Implements self-healing retry logic using Spanner checkpointing.
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
                def chunk_generator() -> Generator[agent_state_pb2.AgentStatePayload, None, None]:
                    nonlocal current_chunk
                    for c in range(current_chunk, num_chunks):
                        is_last = (c == num_chunks - 1)
                        yield dict_to_proto(data, chunk_index=c, is_last_chunk=is_last)
                        
                response = stub.TransferState(chunk_generator())
                if response.success:
                    latency = (time.perf_counter() - start_time) * 1000.0
                    channel.close()
                    return True, latency, retries
                    
            except grpc.RpcError as e:
                retries += 1
                print(f"[CLIENT] [ERROR] Stream failed at chunk {current_chunk}: {e.details()}. Recovering...")
                time.sleep(backoff)
                backoff *= 1.5
                
                # Check database checkpoint
                try:
                    checkpoint_response = stub.GetCheckpoint(agent_state_pb2.CheckpointRequest(session_id=session_id))
                    if checkpoint_response.session_exists:
                        server_last = checkpoint_response.last_processed_chunk
                        print(f"[CLIENT] [RECOVERY] Checkpoint found in Cloud Spanner. Resuming from chunk {server_last + 1}.")
                        current_chunk = server_last + 1
                    else:
                        print("[CLIENT] [RECOVERY] No session checkpoint found. Restarting from chunk 0.")
                        current_chunk = 0
                except grpc.RpcError as checkpoint_err:
                    print(f"[CLIENT] [RECOVERY] Checkpoint fetch failed: {checkpoint_err.details()}. Re-establishing connection...")
                    channel.close()
                    channel = self._get_channel()
                    stub = agent_state_pb2_grpc.AgentStateServiceStub(channel)
                    
        channel.close()
        latency = (time.perf_counter() - start_time) * 1000.0
        return False, latency, retries
