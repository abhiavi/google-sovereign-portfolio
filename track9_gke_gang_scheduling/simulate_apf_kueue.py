#!/usr/bin/env python3
"""
simulate_apf_kueue.py - Discrete-Event Simulation of GKE Control Plane & etcd
This script simulates etcd write-queue saturation under a 10,000-job traffic burst.
It compares:
  1. Standard Greedy Scheduling (No APF + Greedy) -> Triggers etcd crashes & deadlocks.
  2. Kueue Gang Scheduling with APF -> Bounded etcd latency & smooth throughput.
"""

import heapq
import random
import sys
import math
from typing import List, Dict, Any, Tuple

# Set random seed for reproducibility
random.seed(42)

class SimulationEvent:
    def __init__(self, time: float, event_type: str, payload: Any):
        self.time = time
        self.event_type = event_type
        self.payload = payload

    def __lt__(self, other):
        return self.time < other.time

class Job:
    def __init__(self, job_id: int, size: int, submit_time: float, execution_time: float = 15.0):
        self.job_id = job_id
        self.size = size  # Number of pods/agents required (e.g., 4 or 8)
        self.submit_time = submit_time
        self.execution_time = execution_time
        self.allocated_gpus = 0
        self.start_time = -1.0
        self.completion_time = -1.0
        self.status = "PENDING"  # PENDING, RUNNING, COMPLETED, DEADLOCKED

class Cluster:
    def __init__(self, total_gpus: int = 128):
        self.total_gpus = total_gpus
        self.allocated_gpus = 0

    def has_capacity(self, gpus: int) -> bool:
        return (self.total_gpus - self.allocated_gpus) >= gpus

    def allocate(self, gpus: int):
        self.allocated_gpus += gpus

    def release(self, gpus: int):
        self.allocated_gpus = max(0, self.allocated_gpus - gpus)

class APFQueue:
    """Simulates API Priority and Fairness queueing."""
    def __init__(self, nominal_concurrency: int, queue_limit: int):
        self.nominal_concurrency = nominal_concurrency
        self.queue_limit = queue_limit
        self.active_requests = 0
        self.queue: List[Tuple[float, Any]] = []  # List of (arrival_time, request_payload)

    def try_enqueue(self, time: float, payload: Any) -> bool:
        if len(self.queue) >= self.queue_limit:
            return False  # HTTP 429 Too Many Requests (dropped)
        self.queue.append((time, payload))
        return True

    def process_next(self) -> Any:
        if self.queue:
            return self.queue.pop(0)[1]
        return None

class GKESimulator:
    def __init__(self, mode: str, num_jobs: int = 10000):
        self.mode = mode  # "GREEDY_NO_APF" or "KUEUE_WITH_APF"
        self.num_jobs = num_jobs
        self.current_time = 0.0
        self.events: List[SimulationEvent] = []
        
        # Cluster state
        self.cluster = Cluster(total_gpus=128)
        self.jobs: Dict[int, Job] = {}
        
        # etcd transaction state
        self.etcd_queue_len = 0
        self.etcd_max_concurrency = 20  # etcd handles 20 concurrent write transactions
        self.etcd_active_writes = 0
        self.etcd_write_latency = 0.002  # base 2ms
        self.etcd_crashes = 0
        self.etcd_last_crash_time = -100.0
        self.etcd_transaction_queue: List[Tuple[str, float]] = []  # queue of (write_type, arrival_time)
        
        # APF state (active in KUEUE_WITH_APF)
        self.apf_scheduling = APFQueue(nominal_concurrency=40, queue_limit=150)
        self.apf_system_concurrency = 150
        self.apf_system_active = 0
        
        # Metrics tracking
        self.history_time: List[float] = []
        self.history_etcd_latency: List[float] = []
        self.history_etcd_queue: List[float] = []
        self.history_gpu_utilization: List[float] = []
        self.dropped_requests = 0
        self.total_api_requests = 0

    def schedule_event(self, time: float, event_type: str, payload: Any):
        heapq.heappush(self.events, SimulationEvent(time, event_type, payload))

    def run(self) -> Dict[str, Any]:
        # Generate 10k jobs submitted in a sharp burst (first 10 seconds)
        for i in range(self.num_jobs):
            size = random.choice([4, 8])
            submit_time = random.uniform(0.0, 10.0)
            self.jobs[i] = Job(job_id=i, size=size, submit_time=submit_time)
            self.schedule_event(submit_time, "JOB_SUBMIT", i)

        # Schedule periodic system heartbeats (every 0.1s to capture control plane health)
        for t in range(0, 3000):
            self.schedule_event(t * 0.1, "SYSTEM_HEARTBEAT", None)

        # Schedule metrics logging
        for t in range(0, 60):
            self.schedule_event(t * 5.0, "LOG_METRICS", None)

        step_count = 0
        while self.events and self.current_time < 300.0:
            event = heapq.heappop(self.events)
            self.current_time = event.time
            self.process_event(event)
            step_count += 1
            
            if step_count > 500000:
                break

        # Calculate final metrics
        completed_jobs = [j for j in self.jobs.values() if j.status == "COMPLETED"]
        deadlocked_jobs = [j for j in self.jobs.values() if j.status == "DEADLOCKED"]
        pending_jobs = [j for j in self.jobs.values() if j.status == "PENDING"]
        running_jobs = [j for j in self.jobs.values() if j.status == "RUNNING"]
        
        turnarounds = [(j.completion_time - j.submit_time) for j in completed_jobs]
        avg_turnaround = sum(turnarounds) / len(turnarounds) if turnarounds else 0.0
        p50_turnaround = sorted(turnarounds)[len(turnarounds)//2] if turnarounds else 0.0
        p95_turnaround = sorted(turnarounds)[int(len(turnarounds)*0.95)] if turnarounds else 0.0

        return {
            "mode": self.mode,
            "total_jobs": self.num_jobs,
            "completed": len(completed_jobs),
            "deadlocked": len(deadlocked_jobs) + len(running_jobs),
            "pending": len(pending_jobs),
            "avg_turnaround": avg_turnaround,
            "p50_turnaround": p50_turnaround,
            "p95_turnaround": p95_turnaround,
            "etcd_crashes": self.etcd_crashes,
            "dropped_requests": self.dropped_requests,
            "max_etcd_latency": max(self.history_etcd_latency) if self.history_etcd_latency else 0.002,
            "avg_etcd_latency": sum(self.history_etcd_latency)/len(self.history_etcd_latency) if self.history_etcd_latency else 0.002
        }

    def process_event(self, event: SimulationEvent):
        # Master recovery takes 15 seconds. Reject events during reboot.
        is_crashed = (self.etcd_last_crash_time > 0 and (self.current_time - self.etcd_last_crash_time) < 15.0)
        
        if is_crashed:
            if event.event_type not in ["LOG_METRICS", "WRITE_COMPLETE"]:
                if event.event_type in ["JOB_SUBMIT", "SYSTEM_HEARTBEAT"]:
                    self.dropped_requests += 1
                return

        if event.event_type == "JOB_SUBMIT":
            job_id = event.payload
            self.total_api_requests += 1
            if self.mode == "GREEDY_NO_APF":
                self.process_greedy_schedule(job_id)
            else:
                self.process_kueue_submit(job_id)

        elif event.event_type == "SYSTEM_HEARTBEAT":
            self.process_heartbeat()

        elif event.event_type == "WRITE_COMPLETE":
            self.process_write_complete(event.payload)

        elif event.event_type == "JOB_COMPLETE":
            job_id = event.payload
            job = self.jobs[job_id]
            job.status = "COMPLETED"
            job.completion_time = self.current_time
            self.cluster.release(job.allocated_gpus)
            if self.mode == "KUEUE_WITH_APF":
                self.schedule_pending_kueue_jobs()

        elif event.event_type == "LOG_METRICS":
            self.history_time.append(self.current_time)
            self.history_etcd_latency.append(self.etcd_write_latency)
            self.history_etcd_queue.append(self.etcd_queue_len)
            self.history_gpu_utilization.append((self.cluster.allocated_gpus / self.cluster.total_gpus) * 100.0)
            self.schedule_event(self.current_time + 5.0, "LOG_METRICS", None)

    def process_greedy_schedule(self, job_id: int):
        job = self.jobs[job_id]
        
        # Immediate pod creation requests generated (one per pod needed)
        for _ in range(job.size):
            self.request_etcd_write("pod_creation")

        # Greedy allocation logic
        available = self.cluster.total_gpus - self.cluster.allocated_gpus
        if available > 0:
            allocated = min(job.size, available)
            self.cluster.allocate(allocated)
            job.allocated_gpus = allocated
            
            if allocated == job.size:
                job.status = "RUNNING"
                job.start_time = self.current_time
                self.schedule_event(self.current_time + job.execution_time, "JOB_COMPLETE", job_id)
            else:
                job.status = "DEADLOCKED"  # Resource hold-and-wait deadlock
        else:
            job.status = "PENDING"

    def process_kueue_submit(self, job_id: int):
        job = self.jobs[job_id]
        
        # Request goes through APF queue
        success = self.apf_scheduling.try_enqueue(self.current_time, job_id)
        if not success:
            self.dropped_requests += 1
            return

        # Drain queue if scheduling capacity is available
        if self.apf_scheduling.active_requests < self.apf_scheduling.nominal_concurrency:
            self.drain_apf_queue()

    def drain_apf_queue(self):
        next_job_id = self.apf_scheduling.process_next()
        if next_job_id is not None:
            self.apf_scheduling.active_requests += 1
            # Request workload write to etcd
            self.request_etcd_write("kueue_workload_create")
            self.apf_scheduling.active_requests -= 1
            
            # Admitted to Kueue queue
            self.schedule_pending_kueue_jobs()

    def schedule_pending_kueue_jobs(self):
        for job in self.jobs.values():
            if job.status == "PENDING":
                if self.cluster.has_capacity(job.size):
                    self.cluster.allocate(job.size)
                    job.allocated_gpus = job.size
                    job.status = "RUNNING"
                    job.start_time = self.current_time
                    self.schedule_event(self.current_time + job.execution_time, "JOB_COMPLETE", job.job_id)
                    # Trigger a single write to unsuspend the job's pods (co-scheduling)
                    self.request_etcd_write("kueue_job_unsuspend")

    def process_heartbeat(self):
        if self.mode == "GREEDY_NO_APF":
            # Heartbeats share the same saturated etcd queue under greedy spikes
            self.request_etcd_write("node_heartbeat")
        else:
            # APF isolates system heartbeats into a separate flow, guaranteeing prompt execution
            if self.apf_system_active < self.apf_system_concurrency:
                self.apf_system_active += 1
                self.request_etcd_write("node_heartbeat_secured")
                self.apf_system_active -= 1
            else:
                self.dropped_requests += 1

    def request_etcd_write(self, write_type: str):
        if self.etcd_active_writes < self.etcd_max_concurrency:
            self.start_etcd_transaction(write_type)
        else:
            self.etcd_transaction_queue.append((write_type, self.current_time))
            self.etcd_queue_len = len(self.etcd_transaction_queue)

    def start_etcd_transaction(self, write_type: str):
        self.etcd_active_writes += 1
        
        # Calculate latency based on current etcd queue length
        # In GREEDY_NO_APF, queue length can reach 1000s, pushing write latency to seconds
        q_len = len(self.etcd_transaction_queue)
        alpha = 0.0001
        latency = 0.005 * (1.0 + alpha * (q_len ** 1.85))
        
        # Cap latency at 15.0 seconds
        latency = min(15.0, latency)
        self.etcd_write_latency = latency
        
        # If write latency exceeds 5.0 seconds, heartbeats/leases fail and etcd crashes
        if latency > 5.0:
            if (self.current_time - self.etcd_last_crash_time) > 20.0:
                self.etcd_crashes += 1
                self.etcd_last_crash_time = self.current_time
                self.etcd_transaction_queue.clear()
                self.etcd_queue_len = 0
                self.etcd_active_writes = 0
                self.etcd_write_latency = 0.002
                return

        self.schedule_event(self.current_time + latency, "WRITE_COMPLETE", write_type)

    def process_write_complete(self, write_type: str):
        self.etcd_active_writes = max(0, self.etcd_active_writes - 1)
        
        # If there are queued transactions, process the next one
        if self.etcd_transaction_queue:
            next_write, arrival_time = self.etcd_transaction_queue.pop(0)
            self.etcd_queue_len = len(self.etcd_transaction_queue)
            
            # Check if request timed out in queue (HTTP 504 Gateway Timeout)
            if (self.current_time - arrival_time) > 10.0:
                self.dropped_requests += 1
            else:
                self.start_etcd_transaction(next_write)


if __name__ == "__main__":
    print("==================================================================")
    print("    GKE API PRIORITY & FAIRNESS / KUEUE SCHEDULER SIMULATION     ")
    print("==================================================================")
    
    print("\n[SIMULATION] Executing Mode 1: Standard Greedy Scheduling (No APF)...")
    sim1 = GKESimulator(mode="GREEDY_NO_APF", num_jobs=10000)
    results1 = sim1.run()
    
    print("[SIMULATION] Executing Mode 2: Kueue Gang-Scheduling + APF...")
    sim2 = GKESimulator(mode="KUEUE_WITH_APF", num_jobs=10000)
    results2 = sim2.run()
    
    print("\n" + "="*80)
    print(f" {'Telemetry Performance Metrics Comparison':^78} ")
    print("="*80)
    print(f"| {'Metric / Parameter':<32} | {'Default K8s (Greedy)':<20} | {'Kueue + APF (Sovereign)':<20} |")
    print("-"*80)
    print(f"| {'Total Jobs Admitted':<32} | {results1['completed'] + results1['deadlocked']:<20d} | {results2['completed']:<20d} |")
    print(f"| {'Jobs Completed Successfully':<32} | {results1['completed']:<20d} | {results2['completed']:<20d} |")
    print(f"| {'Jobs Deadlocked / Hung':<32} | {results1['deadlocked']:<20d} | {results2['deadlocked']:<20d} |")
    print(f"| {'Control Plane (etcd) Crashes':<32} | {results1['etcd_crashes']:<20d} | {results2['etcd_crashes']:<20d} |")
    print(f"| {'Avg etcd Write Latency':<32} | {results1['avg_etcd_latency']*1000.0:<17.2f} ms | {results2['avg_etcd_latency']*1000.0:<17.2f} ms |")
    print(f"| {'Max etcd Write Latency':<32} | {results1['max_etcd_latency']*1000.0:<17.2f} ms | {results2['max_etcd_latency']*1000.0:<17.2f} ms |")
    print(f"| {'Dropped requests (HTTP 429/503)':<32} | {results1['dropped_requests']:<20d} | {results2['dropped_requests']:<20d} |")
    print(f"| {'Median Turnaround (p50)':<32} | {results1['p50_turnaround']:<17.2f} s  | {results2['p50_turnaround']:<17.2f} s  |")
    print(f"| {'Tail Turnaround (p95)':<32} | {results1['p95_turnaround']:<17.2f} s  | {results2['p95_turnaround']:<17.2f} s  |")
    print("="*80)
    
    # Write metrics to a local file
    metrics_path = "simulation_results.txt"
    with open(metrics_path, "w") as f:
        f.write("=== Telemetry Performance Metrics Comparison ===\n")
        f.write(f"Default K8s (Greedy) Completed: {results1['completed']}\n")
        f.write(f"Default K8s (Greedy) Deadlocked/Hung: {results1['deadlocked']}\n")
        f.write(f"Default K8s (Greedy) etcd Crashes: {results1['etcd_crashes']}\n")
        f.write(f"Default K8s (Greedy) Avg etcd Latency: {results1['avg_etcd_latency']*1000.0:.2f} ms\n")
        f.write(f"Default K8s (Greedy) Max etcd Latency: {results1['max_etcd_latency']*1000.0:.2f} ms\n")
        f.write(f"Kueue + APF Completed: {results2['completed']}\n")
        f.write(f"Kueue + APF Deadlocked/Hung: {results2['deadlocked']}\n")
        f.write(f"Kueue + APF etcd Crashes: {results2['etcd_crashes']}\n")
        f.write(f"Kueue + APF Avg etcd Latency: {results2['avg_etcd_latency']*1000.0:.2f} ms\n")
        f.write(f"Kueue + APF Max etcd Latency: {results2['max_etcd_latency']*1000.0:.2f} ms\n")
    print(f"\n[INFO] Simulation results written to {metrics_path}")
