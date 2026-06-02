# test_cache.py - Automated Integration Test for KV Cache Offloader
import json
import time
import logging
import threading
import urllib.request
import urllib.error
from typing import Dict, Any

import uvicorn
from inference_engine import app

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_cache")

PORT = 8003
BASE_URL = f"http://127.0.0.1:{PORT}"

def make_request(path: str, method: str = "GET", headers: Dict[str, str] = None, data: Dict[str, Any] = None) -> tuple:
    """Helper to dispatch HTTP queries to the local test server."""
    url = f"{BASE_URL}{path}"
    headers = headers or {}
    req_data = json.dumps(data).encode('utf-8') if data else None
    
    if req_data:
        headers["Content-Type"] = "application/json"
        
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode('utf-8'))
        except Exception:
            err_body = e.reason
        return e.code, err_body
    except Exception as e:
        return 500, str(e)

def run_server():
    """Runs uvicorn locally in a test thread."""
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server.run()

def verify_offloading_workflow():
    """Validates HBM boundaries, LRU evictions, and cache-miss PCIe re-paging."""
    logger.info("Starting KV Cache Offload Validation Suite...")
    
    # Clean state
    make_request("/v1/cache/clear", method="POST")

    # 1. Inspect initial empty state
    status_code, body = make_request("/v1/cache/status")
    assert status_code == 200
    assert body["gpu_kv_usage_mb"] == 0.0
    assert body["cpu_ram_usage_mb"] == 0.0
    logger.info("✅ Initial state verified. Memory is clean.\n")

    # 2. Session A: Allocate moderate cache (e.g. 1000 tokens)
    # Token count size = 1000 + 400 (prompt estimate) = 1400 tokens ~ 459 MB
    logger.info("Test Step 2: Querying Session A (moderate memory footprint)...")
    payload_a = {
        "model": "gemma-3-7b-it",
        "session_id": "session-A",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": "Initial conversation seed for Agent A."}]
    }
    status_code, body = make_request("/v1/chat/completions", method="POST", data=payload_a)
    assert status_code == 200
    assert body["memory_diagnostics"]["current_location"] == "GPU"
    logger.info(f"✅ Session A Cache initialized on GPU HBM: {body['memory_diagnostics']['size_mb']:.2f} MB\n")

    # 3. Session B: Allocate heavy cache (e.g. 12000 tokens)
    # 12000 tokens ~ 3.9 GB. Total GPU memory will reach ~ 8.1GB (base) + 3.9GB (B) + 0.4GB (A) = 12.4GB (within 16GB limit, but near)
    logger.info("Test Step 3: Querying Session B (heavy memory footprint)...")
    payload_b = {
        "model": "gemma-3-7b-it",
        "session_id": "session-B",
        "max_tokens": 12000,
        "messages": [{"role": "user", "content": "Establish deep context for Agent B."}]
    }
    status_code, body = make_request("/v1/chat/completions", method="POST", data=payload_b)
    assert status_code == 200
    assert body["memory_diagnostics"]["current_location"] == "GPU"
    logger.info(f"✅ Session B Cache initialized on GPU HBM: {body['memory_diagnostics']['size_mb']:.2f} MB\n")

    # 4. Check Status: Both A and B must be in GPU
    status_code, body = make_request("/v1/cache/status")
    active_sessions = body["active_sessions"]
    assert active_sessions["session-A"]["location"] == "GPU"
    assert active_sessions["session-B"]["location"] == "GPU"
    logger.info(f"✅ Both sessions validated in GPU. GPU Total Footprint: {body['gpu_total_usage_mb']:.2f} MB\n")

    # 5. Session C: Trigger heavy context allocation (e.g. 10000 tokens)
    # This pushes GPU total usage over the safety threshold (90% of 16GB = 14.7GB).
    # Since A is the coldest (LRU), Session A's cache must be evicted to CPU Host RAM.
    logger.info("Test Step 5: Querying Session C (triggers eviction of Session A to Host RAM)...")
    payload_c = {
        "model": "gemma-3-7b-it",
        "session_id": "session-C",
        "max_tokens": 7000,
        "messages": [{"role": "user", "content": "Generate detailed analytics for Agent C."}]
    }
    status_code, body = make_request("/v1/chat/completions", method="POST", data=payload_c)
    assert status_code == 200
    assert body["memory_diagnostics"]["current_location"] == "GPU"
    assert "session-A" in body["memory_diagnostics"]["paged_out_sessions"]
    logger.info("✅ Session C initialized. Eviction logic correctly paged out 'session-A'.\n")

    # 6. Verify Memory Status: Session A is CPU, B and C are GPU
    status_code, body = make_request("/v1/cache/status")
    active_sessions = body["active_sessions"]
    assert active_sessions["session-A"]["location"] == "CPU"
    assert active_sessions["session-B"]["location"] == "GPU"
    assert active_sessions["session-C"]["location"] == "GPU"
    logger.info(f"✅ Active memory layout verified. Session A offloaded to Host CPU RAM ({body['cpu_ram_usage_mb']:.2f} MB).\n")

    # 7. Query Session A again: Trigger cache-miss and page back in from CPU
    # This should page in A, which in turn will trigger eviction of Session B (since B is now the coldest relative to A and C)
    logger.info("Test Step 7: Querying Session A again (triggers cache miss + PCIe Page In + Eviction of Session B)...")
    payload_a_turn2 = {
        "model": "gemma-3-7b-it",
        "session_id": "session-A",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": "Follow up conversation for Agent A."}]
    }
    status_code, body = make_request("/v1/chat/completions", method="POST", data=payload_a_turn2)
    assert status_code == 200
    assert body["memory_diagnostics"]["current_location"] == "GPU"
    assert body["memory_diagnostics"]["pcie_transfer_latency_sec"] > 0.0
    assert "session-B" in body["memory_diagnostics"]["paged_out_sessions"]
    logger.info(f"✅ Session A paged back in. PCIe transfer latency encountered: {body['memory_diagnostics']['pcie_transfer_latency_sec']:.4f}s\n")

    # 8. Final Status check
    status_code, body = make_request("/v1/cache/status")
    active_sessions = body["active_sessions"]
    assert active_sessions["session-A"]["location"] == "GPU"
    assert active_sessions["session-B"]["location"] == "CPU"
    assert active_sessions["session-C"]["location"] == "GPU"
    logger.info("✅ Final layout: Session A & C on GPU HBM, Session B paged out to CPU Host RAM.")
    
    print("\n🎉 ALL KV CACHE OFFLOAD INTEGRATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    # Start server in thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Wait for bind
    time.sleep(2.0)
    
    try:
        verify_offloading_workflow()
    except AssertionError as ae:
        logger.error(f"❌ TEST SUITE FAILED: {ae}")
        exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error in test run: {e}")
        exit(1)
