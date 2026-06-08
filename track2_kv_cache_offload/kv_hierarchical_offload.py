# kv_hierarchical_offload.py - Hierarchical 3-Tier KV Cache Offloader Simulation
import os
import time
import shutil
import atexit
import logging
import torch
from typing import Dict, List, Tuple, Any, Optional

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("HierarchicalOffloader")

class KVCacheBlock:
    """Represents a Key-Value Cache block for a single active generation session."""
    def __init__(self, session_id: str, k_tensor: torch.Tensor, v_tensor: torch.Tensor, location: str = "GPU"):
        self.session_id = session_id
        self.k_tensor = k_tensor
        self.v_tensor = v_tensor
        self.location = location  # "GPU", "CPU", "NVMe"
        self.last_accessed = time.time()
        self.access_count = 1
        
        # Stored metadata for when the block is offloaded to NVMe and tensors are deleted from memory
        self._token_count = k_tensor.shape[2]
        self._size_bytes = (k_tensor.element_size() * k_tensor.nelement() +
                            v_tensor.element_size() * v_tensor.nelement())
        self.file_path: Optional[str] = None

    @property
    def token_count(self) -> int:
        if self.location == "NVMe":
            return self._token_count
        return self.k_tensor.shape[2]

    @property
    def size_bytes(self) -> int:
        if self.location == "NVMe":
            return self._size_bytes
        return (self.k_tensor.element_size() * self.k_tensor.nelement() +
                self.v_tensor.element_size() * self.v_tensor.nelement())

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024.0 * 1024.0)

    def touch(self):
        """Updates access metrics for LRU policy decisions."""
        self.last_accessed = time.time()
        self.access_count += 1

    def evict_to_cpu(self):
        """Moves Key and Value tensors to CPU Host RAM."""
        if self.location != "GPU":
            return
        
        start = time.perf_counter()
        self.k_tensor = self.k_tensor.cpu()
        self.v_tensor = self.v_tensor.cpu()
        # Clean CUDA cache if applicable
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
        self.location = "CPU"
        self.touch()
        return time.perf_counter() - start

    def evict_to_nvme(self, filepath: str):
        """Serializes Key and Value tensors and saves them to the NVMe filesystem."""
        if self.location != "CPU" and self.location != "GPU":
            return
            
        start = time.perf_counter()
        self.file_path = filepath
        self._token_count = self.token_count
        self._size_bytes = self.size_bytes
        
        # Save to disk as PyTorch binary
        torch.save({"k": self.k_tensor.cpu(), "v": self.v_tensor.cpu()}, filepath)
        
        # Free CPU/GPU memory reference
        self.k_tensor = None
        self.v_tensor = None
        self.location = "NVMe"
        self.touch()
        return time.perf_counter() - start

    def load_from_nvme(self, target_device: torch.device):
        """Deserializes Key and Value tensors from NVMe storage back to GPU/CPU memory."""
        if self.location != "NVMe" or not self.file_path:
            return
            
        start = time.perf_counter()
        # Load from disk to host memory first, then move to the target device
        checkpoint = torch.load(self.file_path, map_location='cpu')
        self.k_tensor = checkpoint["k"].to(target_device)
        self.v_tensor = checkpoint["v"].to(target_device)
        
        # Remove serialized file to keep storage clean
        if os.path.exists(self.file_path):
            os.remove(self.file_path)
            
        self.file_path = None
        self.location = "GPU" if target_device.type == "cuda" else "CPU"
        self.touch()
        return time.perf_counter() - start

    def load_to_gpu(self, gpu_device: torch.device):
        """Moves Key and Value tensors from CPU Host RAM back to GPU HBM."""
        if self.location != "CPU":
            return
            
        start = time.perf_counter()
        self.k_tensor = self.k_tensor.to(gpu_device)
        self.v_tensor = self.v_tensor.to(gpu_device)
        self.location = "GPU"
        self.touch()
        return time.perf_counter() - start


class TieredKVCache:
    """
    Manages allocation, retrieval, and eviction of KV Cache blocks
    across three tiers: Tier 1 (HBM3 GPU), Tier 2 (DDR5 Host RAM), and Tier 3 (NVMe Storage).
    Enforces a 90% utilization threshold at each level using an LRU eviction policy.
    """
    def __init__(self,
                 gpu_capacity_mb: float = 250.0,
                 cpu_capacity_mb: float = 100.0,
                 model_base_mb: float = 100.0,
                 gpu_threshold_pct: float = 90.0,
                 cpu_threshold_pct: float = 90.0,
                 pcie_bandwidth_gb_s: float = 16.0,  # GPU <-> CPU Bandwidth (PCIe Gen 4 x8)
                 nvme_bandwidth_gb_s: float = 6.0,   # CPU <-> NVMe Bandwidth (PCIe Gen 4 NVMe)
                 nvme_dir: str = "./nvme_cache"):
        
        self.gpu_capacity_mb = gpu_capacity_mb
        self.cpu_capacity_mb = cpu_capacity_mb
        self.model_base_mb = model_base_mb
        
        self.gpu_threshold_pct = gpu_threshold_pct
        self.cpu_threshold_pct = cpu_threshold_pct
        
        self.pcie_bandwidth_gb_s = pcie_bandwidth_gb_s
        self.nvme_bandwidth_gb_s = nvme_bandwidth_gb_s
        self.nvme_dir = os.path.abspath(nvme_dir)
        
        # Ensure clean directory for NVMe cache
        if os.path.exists(self.nvme_dir):
            shutil.rmtree(self.nvme_dir)
        os.makedirs(self.nvme_dir, exist_ok=True)
        
        # Track blocks
        self.blocks: Dict[str, KVCacheBlock] = {}
        
        # Execution Device Configuration
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Logs for latency tables
        self.latency_logs: List[Dict[str, Any]] = []
        
        logger.info("Initializing Tiered 3-Tier KV Cache Manager...")
        logger.info(f"Execution Target Device: {self.device}")
        logger.info(f"Tier 1 (GPU HBM3)  | Capacity: {self.gpu_capacity_mb}MB | Threshold: {self.gpu_threshold_pct}% (Max KV: {self.gpu_capacity_mb * (self.gpu_threshold_pct/100.0) - self.model_base_mb:.2f}MB)")
        logger.info(f"Tier 2 (DDR5 RAM)  | Capacity: {self.cpu_capacity_mb}MB | Threshold: {self.cpu_threshold_pct}% (Max KV: {self.cpu_capacity_mb * (self.cpu_threshold_pct/100.0):.2f}MB)")
        logger.info(f"Tier 3 (NVMe Storage) | Path: {self.nvme_dir} (Unlimited Capacity)")
        logger.info(f"PCIe Bandwidth: {self.pcie_bandwidth_gb_s} GB/s | NVMe Bandwidth: {self.nvme_bandwidth_gb_s} GB/s\n")

    @property
    def gpu_kv_usage_mb(self) -> float:
        return sum(b.size_mb for b in self.blocks.values() if b.location == "GPU")

    @property
    def gpu_total_usage_mb(self) -> float:
        return self.model_base_mb + self.gpu_kv_usage_mb

    @property
    def gpu_utilization_pct(self) -> float:
        return (self.gpu_total_usage_mb / self.gpu_capacity_mb) * 100.0

    @property
    def cpu_kv_usage_mb(self) -> float:
        return sum(b.size_mb for b in self.blocks.values() if b.location == "CPU")

    @property
    def cpu_utilization_pct(self) -> float:
        return (self.cpu_kv_usage_mb / self.cpu_capacity_mb) * 100.0

    @property
    def nvme_kv_usage_mb(self) -> float:
        return sum(b.size_mb for b in self.blocks.values() if b.location == "NVMe")

    def allocate(self, session_id: str, num_tokens: int, layers: int = 42, heads: int = 8, head_dim: int = 256):
        """Allocates memory for a new session in GPU HBM."""
        # Key shape: [layers, heads, tokens, head_dim]
        # Value shape: [layers, heads, tokens, head_dim]
        k = torch.randn(layers, heads, num_tokens, head_dim, dtype=torch.float16, device=self.device)
        v = torch.randn(layers, heads, num_tokens, head_dim, dtype=torch.float16, device=self.device)
        
        block = KVCacheBlock(session_id, k, v, location="GPU")
        self.blocks[session_id] = block
        
        logger.info(f"[ALLOCATE] Session '{session_id}': Created {num_tokens} tokens ({block.size_mb:.2f} MB) in GPU HBM3.")
        self._enforce_limits()

    def update(self, session_id: str, new_tokens: int, layers: int = 42, heads: int = 8, head_dim: int = 256):
        """Appends new tokens to an existing session's KV Cache, paging it back into GPU first if needed."""
        block = self.blocks.get(session_id)
        if not block:
            self.allocate(session_id, new_tokens, layers, heads, head_dim)
            return

        block.touch()
        
        # Page-in if it is currently offloaded
        if block.location != "GPU":
            logger.warning(f"[CACHE MISS] Session '{session_id}' resides in {block.location}. Paging in...")
            self._page_in(block)

        # Append new tensors along token dimension
        new_k = torch.randn(layers, heads, new_tokens, head_dim, dtype=torch.float16, device=self.device)
        new_v = torch.randn(layers, heads, new_tokens, head_dim, dtype=torch.float16, device=self.device)
        
        block.k_tensor = torch.cat([block.k_tensor, new_k], dim=2)
        block.v_tensor = torch.cat([block.v_tensor, new_v], dim=2)
        block.touch()
        
        logger.info(f"[UPDATE] Session '{session_id}': Appended {new_tokens} tokens. Total tokens: {block.token_count} ({block.size_mb:.2f} MB).")
        self._enforce_limits()

    def _page_in(self, block: KVCacheBlock):
        """Recalls cache block to GPU HBM3, measuring latencies and handling eviction cascade."""
        origin = block.location
        size_mb = block.size_mb
        
        if origin == "CPU":
            # PCIe DDR5 -> GPU HBM3
            actual_time = block.load_to_gpu(self.device)
            theoretical_time = size_mb / (self.pcie_bandwidth_gb_s * 1024.0)
            
            logger.info(f"[PAGE-IN] CPU -> GPU (PCIe): Paged in '{block.session_id}' ({size_mb:.2f} MB) in {actual_time:.6f}s (Theoretical: {theoretical_time:.6f}s)")
            self.latency_logs.append({
                "session_id": block.session_id,
                "event": "CPU -> GPU Page-In",
                "size_mb": size_mb,
                "theoretical_sec": theoretical_time,
                "actual_sec": actual_time,
                "hbm_saved_mb": -size_mb
            })
            
        elif origin == "NVMe":
            # NVMe -> CPU RAM -> GPU HBM3
            # We model the transfer path as loading directly to GPU HBM (since PyTorch handles the deserialization)
            actual_time = block.load_from_nvme(self.device)
            theoretical_time = size_mb / (self.nvme_bandwidth_gb_s * 1024.0) + size_mb / (self.pcie_bandwidth_gb_s * 1024.0)
            
            logger.info(f"[PAGE-IN] NVMe -> GPU: Recalled '{block.session_id}' ({size_mb:.2f} MB) in {actual_time:.6f}s (Theoretical: {theoretical_time:.6f}s)")
            self.latency_logs.append({
                "session_id": block.session_id,
                "event": "NVMe -> GPU Page-In",
                "size_mb": size_mb,
                "theoretical_sec": theoretical_time,
                "actual_sec": actual_time,
                "hbm_saved_mb": -size_mb
            })
            
        block.touch()
        # Paging in to GPU might push GPU memory over safety threshold
        self._enforce_limits()

    def _enforce_limits(self):
        """Enforces 90% utilization threshold hierarchically (GPU HBM -> Host RAM -> NVMe)."""
        # 1. GPU HBM Eviction Loop
        gpu_threshold = self.gpu_capacity_mb * (self.gpu_threshold_pct / 100.0)
        while self.gpu_total_usage_mb > gpu_threshold:
            gpu_blocks = [b for b in self.blocks.values() if b.location == "GPU"]
            if not gpu_blocks:
                break
            
            # Find least recently used (LRU) GPU block
            gpu_blocks.sort(key=lambda x: x.last_accessed)
            victim = gpu_blocks[0]
            
            self._evict_gpu_to_cpu(victim)
            
        # 2. CPU RAM Eviction Loop
        cpu_threshold = self.cpu_capacity_mb * (self.cpu_threshold_pct / 100.0)
        while self.cpu_kv_usage_mb > cpu_threshold:
            cpu_blocks = [b for b in self.blocks.values() if b.location == "CPU"]
            if not cpu_blocks:
                break
                
            # Find least recently used (LRU) CPU block
            cpu_blocks.sort(key=lambda x: x.last_accessed)
            victim = cpu_blocks[0]
            
            self._evict_cpu_to_nvme(victim)

    def _evict_gpu_to_cpu(self, block: KVCacheBlock):
        """Evicts cache block from GPU HBM3 to DDR5 RAM."""
        size_mb = block.size_mb
        actual_time = block.evict_to_cpu()
        theoretical_time = size_mb / (self.pcie_bandwidth_gb_s * 1024.0)
        
        logger.warning(f"[EVICT] GPU -> CPU: Evicted '{block.session_id}' ({size_mb:.2f} MB) to Host RAM due to GPU hitting 90% capacity.")
        self.latency_logs.append({
            "session_id": block.session_id,
            "event": "GPU -> CPU Eviction",
            "size_mb": size_mb,
            "theoretical_sec": theoretical_time,
            "actual_sec": actual_time,
            "hbm_saved_mb": size_mb
        })

    def _evict_cpu_to_nvme(self, block: KVCacheBlock):
        """Evicts cache block from DDR5 RAM to NVMe disk storage."""
        size_mb = block.size_mb
        filepath = os.path.join(self.nvme_dir, f"{block.session_id}_kv.pt")
        actual_time = block.evict_to_nvme(filepath)
        theoretical_time = size_mb / (self.nvme_bandwidth_gb_s * 1024.0)
        
        logger.warning(f"[EVICT] CPU -> NVMe: Serialized '{block.session_id}' ({size_mb:.2f} MB) to NVMe due to Host RAM hitting 90% threshold.")
        self.latency_logs.append({
            "session_id": block.session_id,
            "event": "CPU -> NVMe Eviction",
            "size_mb": size_mb,
            "theoretical_sec": theoretical_time,
            "actual_sec": actual_time,
            "hbm_saved_mb": 0.0  # Already saved from GPU, now we save CPU RAM
        })

    def clean_up(self):
        """Removes temporary files on disk."""
        if os.path.exists(self.nvme_dir):
            shutil.rmtree(self.nvme_dir)
            logger.info("[CLEANUP] Deleted temporary NVMe directory.")

    def print_tables(self):
        """Outputs clean, formatted summary tables displaying latencies and memory savings."""
        print("\n" + "="*95)
        print("                        HIERARCHICAL KV CACHE PERFORMANCE REPORT")
        print("="*95)
        
        # 1. PAGING / EVICTION LOG TABLE
        headers = ["Session ID", "Data Movement Event", "Size (MB)", "Theoretical Lat", "Actual Lat", "Saved GPU HBM"]
        rows = []
        total_hbm_saved = 0.0
        
        for entry in self.latency_logs:
            hbm_saved_str = f"+{entry['hbm_saved_mb']:.2f} MB" if entry['hbm_saved_mb'] > 0 else f"{entry['hbm_saved_mb']:.2f} MB"
            total_hbm_saved += entry['hbm_saved_mb']
            
            rows.append([
                entry['session_id'],
                entry['event'],
                f"{entry['size_mb']:.2f}",
                f"{entry['theoretical_sec']:.6f}s",
                f"{entry['actual_sec']:.6f}s",
                hbm_saved_str
            ])
            
        print("\n--- [Data Movement & Latency Event Logs] ---")
        self._render_table(headers, rows)
        
        # 2. CURRENT STORAGE STATE TABLE
        print("\n--- [Hierarchical Tier Memory Allocations] ---")
        status_headers = ["Memory Storage Tier", "Active Usage", "Limit Capacity", "Utilization %", "Current Cache Blocks"]
        
        gpu_blocks_str = ", ".join([k for k, v in self.blocks.items() if v.location == "GPU"])
        cpu_blocks_str = ", ".join([k for k, v in self.blocks.items() if v.location == "CPU"])
        nvme_blocks_str = ", ".join([k for k, v in self.blocks.items() if v.location == "NVMe"])
        
        status_rows = [
            ["Tier 1: HBM3 (GPU)", f"{self.gpu_total_usage_mb:.2f} MB", f"{self.gpu_capacity_mb:.2f} MB", f"{self.gpu_utilization_pct:.1f}%", f"[Model Weights], {gpu_blocks_str}"],
            ["Tier 2: DDR5 (Host RAM)", f"{self.cpu_kv_usage_mb:.2f} MB", f"{self.cpu_capacity_mb:.2f} MB", f"{self.cpu_utilization_pct:.1f}%", cpu_blocks_str],
            ["Tier 3: NVMe (Storage)", f"{self.nvme_kv_usage_mb:.2f} MB", "Unlimited", "N/A", nvme_blocks_str]
        ]
        self._render_table(status_headers, status_rows)

        # 3. EFFICIENCY METRICS SUMMARY
        total_actual_lat = sum(e['actual_sec'] for e in self.latency_logs)
        total_theo_lat = sum(e['theoretical_sec'] for e in self.latency_logs)
        current_saved_hbm = sum(b.size_mb for b in self.blocks.values() if b.location != "GPU")
        
        print("\n--- [System Efficiency & Metrics Summary] ---")
        summary_headers = ["Performance Metric", "Value"]
        summary_rows = [
            ["Total Cumulative Data Moved", f"{sum(e['size_mb'] for e in self.latency_logs):.2f} MB"],
            ["Cumulative Actual Latency Overhead", f"{total_actual_lat:.6f} seconds"],
            ["Cumulative Theoretical Latency Limit", f"{total_theo_lat:.6f} seconds"],
            ["Physical vs Theoretical Variance", f"{abs(total_actual_lat - total_theo_lat):.6f} seconds"],
            ["Current GPU HBM Bypassed (Offloaded)", f"{current_saved_hbm:.2f} MB"],
            ["Total Memory Relieved from HBM (Paged)", f"{sum(e['hbm_saved_mb'] for e in self.latency_logs if e['hbm_saved_mb'] > 0):.2f} MB"]
        ]
        self._render_table(summary_headers, summary_rows)
        print("="*95 + "\n")

    def _render_table(self, headers: List[str], rows: List[List[Any]]):
        """Helper to format a clean text-based table."""
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, val in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(val)))
                
        sep = "+" + "+".join(["-" * (w + 2) for w in col_widths]) + "+"
        print(sep)
        header_str = "|" + "|".join([f" {headers[i]:<{col_widths[i]}} " for i in range(len(headers))]) + "|"
        print(header_str)
        print(sep)
        for row in rows:
            row_str = "|" + "|".join([f" {str(row[i]):<{col_widths[i]}} " for i in range(len(row))]) + "|"
            print(row_str)
        print(sep)


def run_simulation():
    """Runs a simulated multi-agent multi-turn token generation task."""
    # Instantiating the manager
    # GPU HBM Limit = 250 MB. Model base takes 100 MB. Safety threshold = 90% (225 MB total, 125 MB KV limit)
    # CPU DDR5 Limit = 100 MB. Safety threshold = 90% (90 MB KV limit)
    cache_manager = TieredKVCache(
        gpu_capacity_mb=250.0,
        cpu_capacity_mb=100.0,
        model_base_mb=100.0,
        gpu_threshold_pct=90.0,
        cpu_threshold_pct=90.0,
        pcie_bandwidth_gb_s=16.0,
        nvme_bandwidth_gb_s=6.0,
        nvme_dir="./nvme_cache"
    )
    
    # Ensure cleanup at exits
    atexit.register(cache_manager.clean_up)
    
    # Session names
    agents = ["agent_alpha", "agent_beta", "agent_gamma", "agent_delta"]
    
    logger.info("="*80)
    logger.info("   STAGE 1: INITIAL COMPOSITION & ALLOCATION OF AGENTS")
    logger.info("="*80)
    
    # Initial prompts (large allocations to load GPU memory)
    # Token count size = tokens * 0.328125 MB
    cache_manager.allocate("agent_alpha", num_tokens=200)  # ~65.6 MB
    cache_manager.allocate("agent_beta", num_tokens=150)   # ~49.2 MB
    
    # Pushing GPU over 90% limit (225MB total. Current HBM total: 100 + 65.6 + 49.2 = 214.8MB)
    # Allocating gamma (100 tokens ~ 32.8MB) will exceed the HBM limit, triggering eviction of alpha to Host RAM
    cache_manager.allocate("agent_gamma", num_tokens=100)  # ~32.8 MB
    
    # Allocating delta (50 tokens ~ 16.4MB)
    cache_manager.allocate("agent_delta", num_tokens=50)    # ~16.4 MB
    
    logger.info("\n" + "="*80)
    logger.info("   STAGE 2: ACTIVE TOKEN GENERATION LOOP (MUTLI-TURN ROTATION)")
    logger.info("="*80)
    
    # Simulated generation turns (agents generate text blocks of 10-15 tokens)
    # This triggers cache misses, re-paging (GPU recall), and nested CPU -> NVMe serializations!
    
    # Turn 1: agent_alpha needs to append tokens (Miss! Resident on CPU, recall to GPU HBM, evict beta)
    logger.info("\n>>> Turn 1: agent_alpha generation turn (Cache Miss expected)")
    cache_manager.update("agent_alpha", new_tokens=10)
    
    # Turn 2: agent_beta needs to append tokens (Miss! Resident on CPU, recall to GPU HBM, evicts gamma and delta)
    logger.info("\n>>> Turn 2: agent_beta generation turn (Cache Miss expected)")
    cache_manager.update("agent_beta", new_tokens=10)
    
    # Turn 3: agent_gamma needs to append tokens (Miss! Resident on CPU, recalls gamma, evicts alpha to CPU)
    # CPU usage will increase, but remains below threshold
    logger.info("\n>>> Turn 3: agent_gamma generation turn (Cache Miss expected)")
    cache_manager.update("agent_gamma", new_tokens=10)
    
    # Turn 4: agent_delta needs to append tokens (Miss! Resident on CPU, recalls delta)
    logger.info("\n>>> Turn 4: agent_delta generation turn (Cache Miss expected)")
    cache_manager.update("agent_delta", new_tokens=10)
    
    # Turn 5: agent_alpha needs to append tokens (Miss! Resident on CPU, recalls alpha, evicts beta to CPU)
    logger.info("\n>>> Turn 5: agent_alpha generation turn (Cache Miss expected)")
    cache_manager.update("agent_alpha", new_tokens=10)
    
    # Turn 6: Trigger Tier 3 (NVMe) Eviction Cascade!
    # Recalling agent_beta (52.5 MB) to GPU. GPU has: alpha (72.2 MB), gamma (36.1 MB), delta (19.7 MB) = 128 MB KV.
    # GPU HBM limit is exceeded, forcing HBM LRU eviction: gamma (36.1 MB) to CPU.
    # Recalling agent_gamma to GPU again, forcing HBM LRU eviction: alpha (72.2 MB) to CPU.
    # Now CPU will hold alpha (72.2 MB) and delta (19.7 MB) = 91.9 MB, which exceeds the CPU safety limit (90 MB)!
    # This triggers the first CPU -> NVMe offload cascade, moving delta to NVMe!
    logger.info("\n>>> Turn 6: Triggering nested HBM -> DDR5 -> NVMe eviction cascade")
    cache_manager.update("agent_beta", new_tokens=10)
    cache_manager.update("agent_gamma", new_tokens=10)
    
    # Turn 7: agent_delta needs to append tokens (Deep Cache Miss! NVMe -> GPU recall)
    logger.info("\n>>> Turn 7: Recall agent_delta from Tier 3 (NVMe) storage")
    cache_manager.update("agent_delta", new_tokens=10)
    
    # Final state reporting
    cache_manager.print_tables()
    
if __name__ == "__main__":
    run_simulation()
