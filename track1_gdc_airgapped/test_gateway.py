# test_gateway.py - Integration tests for GDC Air-Gapped Inference Gateway
import base64
import json
import time
import socket
import logging
import threading
import os
import urllib.request
import urllib.error
from typing import Dict, Any

from fastapi import FastAPI
import uvicorn
from main import app

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_gateway")

PORT = 8001
BASE_URL = f"http://127.0.0.1:{PORT}"

# Mock LiteLLM server to run locally during unit testing
mock_litellm = FastAPI()

@mock_litellm.post("/v1/chat/completions")
def mock_chat_completions(req: Dict[str, Any]):
    """Simulates the response layout of our Proxmox LiteLLM gateway."""
    messages = req.get("messages", [])
    last_prompt = messages[-1].get("content", "") if messages else ""
    
    # Return mock responses that match expectations of main test suite
    if "kafka" in last_prompt.lower() or "fallback" in last_prompt.lower():
        content = "To configure a fallback handler in Kafka, set a dead-letter queue (DLQ) output sink."
    else:
        content = f"Mocked LLM reply to: '{last_prompt}'"

    return {
        "id": "chatcmpl-mock-172839",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.get("model", "gemma-3-27b"),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content
                },
                "finish_reason": "stop"
            }
        ]
    }

# Standard valid claims matching the EXPECTED values in auth_verifier.py
VALID_CLAIMS = {
    "iss": "https://confidentialcomputing.googleapis.com",
    "sub": "gdc-airgapped-workload@google.com",
    "aud": "https://key-management.gdc-enclave.local",
    "exp": int(time.time()) + 3600,
    "secboot": True,
    "dbgstat": False,
    "hwmodel": "AMD_SEV_SNP",
    "swname": "CONFIDENTIAL_SPACE",
    "swversion": "24.04.0",
    "image_digest": "sha256:1a84f3299723ecb8b98297b8192837d8a98297b8192837d8a98297b8192837d8"
}

def generate_token(claims: Dict[str, Any]) -> str:
    """Generates a mock OIDC JWT token formatted for the simulated verifier."""
    payload_json = json.dumps(claims)
    encoded = base64.b64encode(payload_json.encode('utf-8')).decode('utf-8')
    return f"mock-jwt-{encoded}"

def make_request(path: str, method: str = "GET", headers: Dict[str, str] = None, data: Dict[str, Any] = None) -> tuple:
    """Sends an HTTP request to the local test server and returns status code and response payload/error."""
    url = f"{BASE_URL}{path}"
    headers = headers or {}
    req_data = json.dumps(data).encode('utf-8') if data else None
    
    if req_data:
        headers["Content-Type"] = "application/json"
        
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
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
    """Target function for running the uvicorn server in a separate thread."""
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server.run()

def run_all_tests():
    """Executes the test suite validating RBAC and Google Confidential Space hardware attestation."""
    logger.info("Starting test suite...")
    
    # Generate helper tokens
    valid_token = generate_token(VALID_CLAIMS)
    
    # 1. Test /health success
    logger.info("Test 1: GET /health with valid attestation token")
    headers = {"X-Attestation-Token": valid_token}
    status_code, body = make_request("/health", headers=headers)
    assert status_code == 200, f"Expected 200, got {status_code}"
    assert body.get("status") == "HEALTHY", f"Expected HEALTHY, got {body}"
    assert body.get("enclave_state") == "VERIFIED_HARDWARE"
    print("✅ Test 1 Passed: Health check succeeded with valid attestation.\n")

    # 2. Test /health missing token
    logger.info("Test 2: GET /health with missing attestation token")
    status_code, body = make_request("/health")
    assert status_code == 401, f"Expected 401, got {status_code}"
    assert "Missing X-Attestation-Token" in body.get("detail", ""), f"Unexpected error detail: {body}"
    print("✅ Test 2 Passed: Health check correctly blocked missing attestation.\n")

    # 3. Test /health security violation: Debugging enabled
    logger.info("Test 3: GET /health with compromised attestation (dbgstat = True)")
    compromised_claims = VALID_CLAIMS.copy()
    compromised_claims["dbgstat"] = True
    compromised_token = generate_token(compromised_claims)
    status_code, body = make_request("/health", headers={"X-Attestation-Token": compromised_token})
    assert status_code == 403, f"Expected 403, got {status_code}"
    assert "debugging is enabled" in body.get("detail", ""), f"Unexpected error detail: {body}"
    print("✅ Test 3 Passed: Health check blocked debugging-enabled hardware.\n")

    # 4. Test /health security violation: Secure Boot disabled
    logger.info("Test 4: GET /health with compromised attestation (secboot = False)")
    compromised_claims = VALID_CLAIMS.copy()
    compromised_claims["secboot"] = False
    compromised_token = generate_token(compromised_claims)
    status_code, body = make_request("/health", headers={"X-Attestation-Token": compromised_token})
    assert status_code == 403, f"Expected 403, got {status_code}"
    assert "Secure Boot is disabled" in body.get("detail", ""), f"Unexpected error detail: {body}"
    print("✅ Test 4 Passed: Health check blocked disabled Secure Boot.\n")

    # 5. Test /health security violation: Modified binary image
    logger.info("Test 5: GET /health with modified container image digest")
    compromised_claims = VALID_CLAIMS.copy()
    compromised_claims["image_digest"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    compromised_token = generate_token(compromised_claims)
    status_code, body = make_request("/health", headers={"X-Attestation-Token": compromised_token})
    assert status_code == 403, f"Expected 403, got {status_code}"
    assert "container image is modified" in body.get("detail", ""), f"Unexpected error detail: {body}"
    print("✅ Test 5 Passed: Health check blocked modified container digest.\n")

    # 6. Test completions success
    logger.info("Test 6: POST /v1/chat/completions with valid Admin role and valid attestation")
    headers = {
        "X-Attestation-Token": valid_token,
        "X-User-Role": "Admin"
    }
    payload = {
        "model": "gemma-3-27b",
        "messages": [
            {"role": "user", "content": "Explain Kafka fallback configurations."}
        ]
    }
    status_code, body = make_request("/v1/chat/completions", method="POST", headers=headers, data=payload)
    assert status_code == 200, f"Expected 200, got {status_code}"
    assert "choices" in body, f"Invalid response format: {body}"
    response_content = body["choices"][0]["message"]["content"]
    assert "dead-letter queue" in response_content.lower() or "dlq" in response_content.lower()
    print("✅ Test 6 Passed: Chat completions succeeded with Admin role and mock LiteLLM proxy.\n")

    # 7. Test completions RBAC denial: Guest role
    logger.info("Test 7: POST /v1/chat/completions with unauthorized role (Guest)")
    headers = {
        "X-Attestation-Token": valid_token,
        "X-User-Role": "Guest"
    }
    status_code, body = make_request("/v1/chat/completions", method="POST", headers=headers, data=payload)
    assert status_code == 403, f"Expected 403, got {status_code}"
    assert "does not have inference permission" in body.get("detail", ""), f"Unexpected error detail: {body}"
    print("✅ Test 7 Passed: Chat completions correctly blocked Guest role.\n")

    # 8. Test completions RBAC denial: Missing role
    logger.info("Test 8: POST /v1/chat/completions with missing role header")
    headers = {
        "X-Attestation-Token": valid_token
    }
    status_code, body = make_request("/v1/chat/completions", method="POST", headers=headers, data=payload)
    assert status_code == 401, f"Expected 401, got {status_code}"
    assert "Missing X-User-Role header" in body.get("detail", ""), f"Unexpected error detail: {body}"
    print("✅ Test 8 Passed: Chat completions correctly blocked missing role.\n")

    print("🎉 ALL TESTS PASSED SUCCESSFULLY! Enclave security rules and model routing verified.")

if __name__ == "__main__":
    # Point the gateway execution to our local mock LiteLLM server
    os.environ["LITELLM_PROXY_URL"] = "http://127.0.0.1:8002/v1/chat/completions"
    os.environ["LITELLM_API_KEY"] = "sk-sovereign-gateway-2026"

    # Start mock LiteLLM server in a separate thread
    litellm_thread = threading.Thread(
        target=lambda: uvicorn.run(mock_litellm, host="127.0.0.1", port=8002, log_level="warning"),
        daemon=True
    )
    litellm_thread.start()

    # Start main gateway server thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Wait for servers to bind
    time.sleep(2.0)
    
    try:
        run_all_tests()
    except AssertionError as ae:
        logger.error(f"❌ TEST SUITE FAILED: {ae}")
        exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error in test run: {e}")
        exit(1)
