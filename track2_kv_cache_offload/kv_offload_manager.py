# kv_offload_manager.py - Dynamic GPU-to-CPU KV Cache Paging Agent
import time
import asyncio
import logging
from typing import Dict, List, Tuple, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("kv_offload_manager")

class KVCacheBlock:
    """Represents the KV cache structure for a single active generation session."""
    def __init__(self, session_id: str, initial_tokens: int):
        self.session_id = session_id
        self.token_count = initial_tokens
        
        # Gemma 3 FP16 model dimensions: 42 layers, 8 Key-Value heads, 256 head dimension
        # Size per token = 2 (Key + Value) * 42 layers * 8 heads * 256 dim * 2 bytes (FP16)
        #                 = 344,064 bytes = 0.328125 MB per token
        self.bytes_per_token = 2 * 42 * 8 * 256 * 2
        self.size_mb = (self.bytes_per_token * initial_tokens) / (1024 * 1024)
        
        self.location = "GPU"  # GPU or CPU (Host RAM)
        self.last_accessed = time.time()
        self.access_count = 1

    def update_tokens(self, additional_tokens: int):
        """Simulates growth of the KV cache as new tokens are generated."""
        self.token_count += additional_tokens
        self.size_mb = (self.bytes_per_token * self.token_count) / (1024 * 1024)
        self.last_accessed = time.time()
        self.access_count += 1

    def touch(self):
        """Updates last accessed timestamp and frequency counts for LRU/LFU decisions."""
        self.last_accessed = time.time()
        self.access_count += 1


class KVOffloadManager:
    """
    Manages allocation, retrieval, and paging of KV Cache Blocks between GPU HBM and CPU RAM.
    Triggers dynamic offloading (paging out) when GPU HBM utilization exceeds the threshold.
    """
    def __init__(
        self,
        gpu_hbm_limit_mb: float = 16384.0,      # 16 GB simulated GPU partition (MIG slice)
        base_model_size_mb: float = 8192.0,      # 8 GB base model footprint (Gemma 3 7B FP16)
        hbm_safety_threshold_pct: float = 90.0,  # Page out when HBM exceeds 90%
        pcie_bandwidth_gb_s: float = 16.0       # PCIe Gen 4 x8 speed (16 GB/s)
    ):
        self.gpu_hbm_limit_mb = gpu_hbm_limit_mb
        self.base_model_size_mb = base_model_size_mb
        self.safety_threshold_pct = hbm_safety_threshold_pct
        self.pcie_bandwidth_gb_s = pcie_bandwidth_gb_s
        
        self.hbm_safety_limit_mb = (hbm_safety_threshold_pct / 100.0) * gpu_hbm_limit_mb
        self.blocks: Dict[str, KVCacheBlock] = {}
        self.lock = asyncio.Lock()
        
        logger.info(
            f"Initialized KV Cache Offload Manager. HBM Limit: {gpu_hbm_limit_mb}MB, "
            f"Safety Limit: {self.hbm_safety_limit_mb}MB ({hbm_safety_threshold_pct}%), "
            f"PCIe Bandwidth: {pcie_bandwidth_gb_s}GB/s"
        )

    @property
    def gpu_kv_usage_mb(self) -> float:
        """Returns total KV Cache size currently stored in GPU HBM."""
        return sum(block.size_mb for block in self.blocks.values() if block.location == "GPU")

    @property
    def gpu_total_usage_mb(self) -> float:
        """Returns total GPU HBM memory allocated (Base Model + Active KV Cache)."""
        return self.base_model_size_mb + self.gpu_kv_usage_mb

    @property
    def gpu_utilization_pct(self) -> float:
        """Returns the percentage of GPU HBM memory currently utilized."""
        return (self.gpu_total_usage_mb / self.gpu_hbm_limit_mb) * 100.0

    @property
    def cpu_ram_usage_mb(self) -> float:
        """Returns total memory of paged out KV caches stored in Host CPU RAM."""
        return sum(block.size_mb for block in self.blocks.values() if block.location == "CPU")

    async def allocate_or_update(self, session_id: str, initial_or_new_tokens: int) -> Dict[str, Any]:
        """
        Allocates a new cache block or updates an existing one, triggering paging if HBM usage
        goes above the safety threshold.
        """
        async with self.lock:
            paged_out_sessions = []
            pcie_latency = 0.0
            
            if session_id not in self.blocks:
                # Fresh allocation
                logger.info(f"Allocating new KV cache for session {session_id} with {initial_or_new_tokens} tokens.")
                block = KVCacheBlock(session_id, initial_or_new_tokens)
                self.blocks[session_id] = block
            else:
                # Existing block growth
                block = self.blocks[session_id]
                block.update_tokens(initial_or_new_tokens)
                logger.info(f"Growing KV cache for session {session_id} to {block.token_count} tokens ({block.size_mb:.2f} MB).")
                
                # If block was offloaded to CPU, we must page it in first
                if block.location == "CPU":
                    logger.info(f"Session {session_id} cache requested but is on host RAM. Triggering page in...")
                    in_latency, in_pages = await self._page_in_block(block)
                    pcie_latency += in_latency
                    paged_out_sessions.extend(in_pages)

            # Ensure we are within safety thresholds after allocation or update
            out_latency, out_pages = await self._enforce_hbm_safety()
            pcie_latency += out_latency
            paged_out_sessions.extend(out_pages)
            
            block.touch()
            return {
                "session_id": session_id,
                "current_location": block.location,
                "token_count": block.token_count,
                "size_mb": block.size_mb,
                "gpu_utilization_pct": (self.gpu_total_usage_mb / self.gpu_hbm_limit_mb) * 100,
                "paged_out_sessions": paged_out_sessions,
                "pcie_transfer_latency_sec": pcie_latency
            }

    async def get_active_block(self, session_id: str) -> Tuple[KVCacheBlock, float, List[str]]:
        """
        Retrieves a session's KV block, automatically paging it in from CPU if it was offloaded.
        """
        async with self.lock:
            if session_id not in self.blocks:
                raise KeyError(f"Session {session_id} has no allocated KV Cache.")
            
            block = self.blocks[session_id]
            block.touch()
            
            pcie_latency = 0.0
            paged_out_sessions = []
            
            if block.location == "CPU":
                logger.info(f"Cache miss! Session {session_id} is on Host CPU RAM. Paging in...")
                pcie_latency, paged_out_sessions = await self._page_in_block(block)
                
            return block, pcie_latency, paged_out_sessions

    async def release(self, session_id: str) -> bool:
        """Releases the KV cache allocation and frees HBM/RAM."""
        async with self.lock:
            if session_id in self.blocks:
                block = self.blocks[session_id]
                logger.info(f"Releasing KV cache for session {session_id} ({block.size_mb:.2f} MB freed from {block.location}).")
                del self.blocks[session_id]
                return True
            return False

    async def _page_in_block(self, block: KVCacheBlock) -> Tuple[float, List[str]]:
        """Pages in a specific block from Host CPU RAM to GPU HBM (internal locked function)."""
        paged_out_sessions = []
        pcie_latency = 0.0
        
        # Enforce safety limits before pulling the block back to GPU
        # Check if the block's size fits within the HBM space when combined with existing blocks
        required_free_space = block.size_mb
        
        # Evict other blocks until we have room for the paged-in block
        evicted_latency, evicted_pages = await self._free_gpu_hbm(required_free_space)
        pcie_latency += evicted_latency
        paged_out_sessions.extend(evicted_pages)

        # Simulate PCIe transport from Host CPU RAM to GPU HBM
        # Bandwidth check: size_mb / (bandwidth_gb_s * 1024)
        transfer_time = block.size_mb / (self.pcie_bandwidth_gb_s * 1024.0)
        logger.info(f"Paging in {block.session_id} ({block.size_mb:.2f} MB). Estimated PCIe transfer time: {transfer_time:.4f}s")
        await asyncio.sleep(transfer_time)
        
        block.location = "GPU"
        block.touch()
        pcie_latency += transfer_time
        
        return pcie_latency, paged_out_sessions

    async def _enforce_hbm_safety(self) -> Tuple[float, List[str]]:
        """Ensures total GPU usage does not exceed safety limits (internal helper)."""
        if self.gpu_total_usage_mb <= self.hbm_safety_limit_mb:
            return 0.0, []
        
        overage_mb = self.gpu_total_usage_mb - self.hbm_safety_limit_mb
        logger.warning(f"GPU HBM safety limit exceeded by {overage_mb:.2f} MB. Triggering reactive offload...")
        return await self._free_gpu_hbm(overage_mb)

    async def _free_gpu_hbm(self, target_mb: float) -> Tuple[float, List[str]]:
        """Evicts cold blocks from GPU HBM to Host CPU RAM using LRU policy (internal helper)."""
        evicted_sessions = []
        pcie_latency = 0.0
        
        while target_mb > 0:
            # Gather all active blocks on GPU, excluding model weights
            gpu_blocks = [b for b in self.blocks.values() if b.location == "GPU"]
            if not gpu_blocks:
                break
                
            # Find the least recently used (LRU) block based on last_accessed timestamp
            gpu_blocks.sort(key=lambda x: x.last_accessed)
            lru_block = gpu_blocks[0]
            
            # Simulate PCIe transfer out
            transfer_time = lru_block.size_mb / (self.pcie_bandwidth_gb_s * 1024.0)
            logger.info(
                f"Evicting session {lru_block.session_id} ({lru_block.size_mb:.2f} MB) "
                f"from GPU to CPU. PCIe Transfer: {transfer_time:.4f}s"
            )
            await asyncio.sleep(transfer_time)
            
            lru_block.location = "CPU"
            lru_block.touch()
            
            pcie_latency += transfer_time
            target_mb -= lru_block.size_mb
            evicted_sessions.append(lru_block.session_id)
            
            # Check if we have cleared enough HBM space
            if self.gpu_total_usage_mb <= self.hbm_safety_limit_mb:
                break
                
        return pcie_latency, evicted_sessions

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic memory statistics of the manager."""
        return {
            "gpu_hbm_limit_mb": self.gpu_hbm_limit_mb,
            "gpu_base_model_size_mb": self.base_model_size_mb,
            "gpu_kv_usage_mb": self.gpu_kv_usage_mb,
            "gpu_total_usage_mb": self.gpu_total_usage_mb,
            "gpu_utilization_pct": self.gpu_utilization_pct,
            "cpu_ram_usage_mb": self.cpu_ram_usage_mb,
            "active_sessions": {
                sid: {
                    "location": block.location,
                    "token_count": block.token_count,
                    "size_mb": block.size_mb,
                    "last_accessed": block.last_accessed,
                    "access_count": block.access_count
                } for sid, block in self.blocks.items()
            }
        }
