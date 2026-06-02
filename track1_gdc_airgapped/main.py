import time
import asyncio
import logging
import os
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Header, HTTPException, Depends, status
from pydantic import BaseModel, Field
import httpx
from auth_verifier import verify_attestation_token, AttestationValidationError

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("main")

app = FastAPI(
    title="GDC Air-Gapped Gemma 3 Inference Gateway",
    description="Sovereign edge inference API for Gemma 3 models in GDC enclaves.",
    version="1.0.0"
)

# Models
class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the sender, e.g., 'user', 'system'")
    content: str = Field(..., description="Text content of the message")

class ChatCompletionRequest(BaseModel):
    model: str = Field("gemma-3-27b", description="Model name to target")
    messages: List[ChatMessage] = Field(..., description="Conversation history")
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(512, ge=1)

class ChatCompletionResponseChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionResponseChoice]

# Simple RBAC configuration
ALLOWED_ROLES = {"Admin", "DataAnalyst"}

def get_rbac_clearance(x_user_role: Optional[str] = Header(None)) -> str:
    """Dependency verifying strict role-based access control without external IAM dependency."""
    if not x_user_role:
        logger.warning("Access Denied: Missing X-User-Role header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Missing X-User-Role header."
        )
    if x_user_role not in ALLOWED_ROLES:
        logger.warning(f"Access Denied: Role '{x_user_role}' is unauthorized.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access Denied: Role '{x_user_role}' does not have inference permission."
        )
    return x_user_role

def get_hardware_attestation(x_attestation_token: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Dependency verifying GDC Confidential Space attestation before allowing any workload compute."""
    if not x_attestation_token:
        logger.warning("Access Denied: Missing X-Attestation-Token header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Missing X-Attestation-Token header."
        )
    try:
        claims = verify_attestation_token(x_attestation_token)
        return claims
    except AttestationValidationError as ave:
        logger.critical(f"SECURITY ALERT: Enclave attestation failed: {ave}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Security Violation: Enclave hardware attestation failed: {str(ave)}"
        )

# LiteLLM Proxy configuration targeting the Proxmox Sovereign Gateway over Tailscale
# Default values can be overridden via environment variables at runtime
DEFAULT_LITELLM_PROXY_URL = "http://100.116.70.21:4000/v1/chat/completions"
DEFAULT_LITELLM_API_KEY = "sk-sovereign-gateway-2026"

async def run_litellm_inference(request_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Routes the chat completion request to the LiteLLM proxy running on Proxmox.
    Communication occurs securely over the Tailscale overlay network.
    """
    proxy_url = os.getenv("LITELLM_PROXY_URL", DEFAULT_LITELLM_PROXY_URL)
    api_key = os.getenv("LITELLM_API_KEY", DEFAULT_LITELLM_API_KEY)
    
    logger.info(f"Routing request to LiteLLM proxy at {proxy_url}...")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                proxy_url,
                json=request_payload,
                headers=headers
            )
            response.raise_for_status()
            logger.info("Successfully received response from LiteLLM proxy.")
            return response.json()
    except httpx.HTTPStatusError as hse:
        logger.error(f"LiteLLM Proxy returned error status: {hse.response.status_code} - {hse.response.text}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LiteLLM proxy error: {hse.response.text}"
        )
    except Exception as e:
        logger.error(f"Failed to communicate with LiteLLM proxy: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LiteLLM proxy unavailable: {str(e)}"
        )

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    role: str = Depends(get_rbac_clearance),
    attestation: Dict[str, Any] = Depends(get_hardware_attestation)
):
    """OpenAI-compatible Chat Completion endpoint secured by GDC hardware attestation, local RBAC, and routed to LiteLLM."""
    logger.info(f"Inference request authorized for role: '{role}' in GDC enclave.")
    
    # Map the incoming request directly to LiteLLM payload
    # LiteLLM accepts standard OpenAI schema parameters
    payload = {
        "model": request.model,
        "messages": [msg.dict() for msg in request.messages],
        "temperature": request.temperature,
        "max_tokens": request.max_tokens
    }
    
    # Run inference via Proxmox LiteLLM gateway
    response_data = await run_litellm_inference(payload)
    return response_data

@app.get("/health")
def health(attestation: Dict[str, Any] = Depends(get_hardware_attestation)):
    """Health check endpoint proving the enclave hardware state is verified."""
    return {
        "status": "HEALTHY",
        "enclave_state": "VERIFIED_HARDWARE",
        "hwmodel": attestation.get("hwmodel"),
        "secboot": attestation.get("secboot")
    }
