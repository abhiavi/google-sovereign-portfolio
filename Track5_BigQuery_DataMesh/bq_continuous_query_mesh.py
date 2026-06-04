# bq_continuous_query_mesh.py - BigQuery Continuous Query Data Mesh Simulator
import csv
import time
import random
import uuid
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("bq_mesh_simulator")

class TelcoTelemetryStream:
    """Generates simulated high-velocity Telco network telemetry events."""
    
    @staticmethod
    def generate_events(count: int, traffic_level: str) -> List[Dict[str, Any]]:
        """Generates CDR and network quality events."""
        events = []
        base_time = time.time()
        
        # Adjust signal strength distribution based on traffic scenarios
        # Higher traffic load can correlate with slightly degraded network signals due to congestion
        signal_min = -115 if traffic_level in ["High", "Peak"] else -105
        
        tower_ids = [f"TWR-{random.randint(100, 199)}" for _ in range(20)]
        
        for i in range(count):
            # Distribute event times across a simulated window (e.g. 5 minutes in seconds)
            # For micro-batch, this simulates events accumulating over the 300s window.
            event_offset = random.uniform(0, 300)
            event_time = base_time - event_offset
            
            signal_strength = random.randint(signal_min, -50)
            
            event = {
                "event_id": str(uuid.uuid4()),
                "cell_tower_id": random.choice(tower_ids),
                "caller_msisdn": f"+1555{random.randint(1000000, 9999999)}",
                "receiver_msisdn": f"+1555{random.randint(1000000, 9999999)}",
                "duration_sec": random.randint(0, 3600) if random.random() > 0.1 else 0,
                "network_type": random.choice(["5G", "4G", "LTE"]),
                "signal_strength_dbm": signal_strength,
                "event_timestamp": event_time,
                "packet_loss_pct": round(random.uniform(0.0, 5.0) if signal_strength > -95 else random.uniform(5.0, 25.0), 2)
            }
            events.append(event)
            
        return events


class DataMeshArchitectures:
    """Benchmarks traditional Micro-batch ETL and real-time BigQuery Continuous Queries."""
    
    def __init__(self):
        # FinOps Constants (Google Cloud Pricing as of 2026)
        # BigQuery Batch query scan: $6.25 per TB ($0.00000625 per GB)
        self.bq_scan_cost_per_gb = 6.25 / 1024.0
        # Compute engine VM to orchestrate ETL: e.g. e2-standard-4 ($0.134/hour)
        self.orchestration_hourly_rate = 0.134
        
        # BQ Continuous Query Pricing:
        # Standard reservation slots configured for continuous query: e.g. $0.04 per slot-hour
        self.bq_continuous_slot_rate = 0.04
        # Pub/Sub pricing: $40 per TB ingested/delivered ($0.00004 per GB)
        self.pubsub_cost_per_gb = 40.0 / 1024.0
        
        # Average size of raw JSON/telemetry event = 0.5 KB (0.0005 MB)
        self.event_size_gb = 0.5 / (1024.0 * 1024.0)

    def simulate_micro_batch(self, events: List[Dict[str, Any]], batch_interval_sec: float = 300.0) -> Dict[str, Any]:
        """
        Simulates traditional Micro-batch ETL architecture.
        Data accumulates over 5 minutes (300s). An orchestration job runs, scans the BigQuery table,
        filters anomalies (signal_strength < -100 dBm), and writes outputs.
        """
        start_compute_time = time.perf_counter()
        
        # Filter anomalies representing typical ETL transformation
        anomalies = [e for e in events if e["signal_strength_dbm"] < -100]
        
        # Simulate processing delay: query compile, scheduling, scanning, sorting, writing
        # A 5-minute batch query takes around 4.5 to 8 seconds depending on data volume
        query_overhead = random.uniform(4.5, 8.0)
        time.sleep(0.05)  # Quick yield to simulate execution lag
        
        end_compute_time = time.perf_counter()
        execution_lag = end_compute_time - start_compute_time + query_overhead
        
        # Latency calculations:
        # For each event, latency = (time batch runs + execution lag) - event creation timestamp
        run_timestamp = time.time()
        latencies = []
        for e in anomalies:
            event_latency = (run_timestamp + execution_lag) - e["event_timestamp"]
            # Ensure no negative latency
            latencies.append(max(event_latency, execution_lag))
            
        avg_latency = sum(latencies) / len(latencies) if latencies else batch_interval_sec / 2.0
        
        # Cost evaluations:
        # 1. BQ Scan cost: batch query scans a full table partition (e.g. 50 GB partition size minimum)
        scanned_data_gb = max(50.0, len(events) * self.event_size_gb * 100.0) # simulating scanning history
        bq_query_cost = scanned_data_gb * self.bq_scan_cost_per_gb
        
        # 2. Scheduler VM cost (assumes VM runs continuously to manage scheduling, or serverless invocation overhead)
        orchestration_cost = (batch_interval_sec / 3600.0) * self.orchestration_hourly_rate
        
        total_cost = bq_query_cost + orchestration_cost
        
        # Compute overhead in core-seconds
        # Orchestrator uses ~1 CPU core, BQ query scales across multiple query slots (e.g. 20 slots for query_overhead seconds)
        compute_slots = 20
        compute_overhead_cores = (1 * execution_lag) + (compute_slots * query_overhead)
        
        return {
            "architecture": "Micro-batch ETL",
            "event_count": len(events),
            "anomaly_count": len(anomalies),
            "latency_seconds": round(avg_latency, 3),
            "compute_overhead_cores": round(compute_overhead_cores, 2),
            "simulated_cost_usd": round(total_cost, 6)
        }

    def simulate_continuous_query(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Simulates stateful BigQuery Continuous Query to Pub/Sub.
        Events stream directly to BigQuery and are instantly evaluated by the continuous query engine.
        Results are forwarded to a Pub/Sub topic in sub-second latency.
        """
        start_compute_time = time.perf_counter()
        
        anomalies = [e for e in events if e["signal_strength_dbm"] < -100]
        
        # Continuous query engine processes records with sub-second stream processing latency
        # Average pipeline latency is typically 150ms to 450ms
        stream_latency_offset = random.uniform(0.12, 0.45)
        
        end_compute_time = time.perf_counter()
        processing_lag = end_compute_time - start_compute_time + stream_latency_offset
        
        # Since continuous query streams and evaluates immediately upon ingestion,
        # there is no batch wait time.
        avg_latency = processing_lag
        
        # Cost evaluations:
        # 1. BQ Continuous Query runs on a reservation (e.g. 2 slots allocated per continuous query)
        # Cost for a 5-minute (300s) continuous execution window:
        slots_allocated = 2
        bq_continuous_cost = (300.0 / 3600.0) * slots_allocated * self.bq_continuous_slot_rate
        
        # 2. Pub/Sub delivery cost:
        # Data size of anomaly output (events * anomaly ratio * size)
        anomaly_data_gb = len(anomalies) * self.event_size_gb
        pubsub_cost = anomaly_data_gb * self.pubsub_cost_per_gb
        
        total_cost = bq_continuous_cost + pubsub_cost
        
        # Compute overhead: continuous query reserves slots (e.g. 2 cores active over the 300s window)
        compute_overhead_cores = slots_allocated * 300.0
        
        return {
            "architecture": "Continuous Query (Pub/Sub)",
            "event_count": len(events),
            "anomaly_count": len(anomalies),
            "latency_seconds": round(avg_latency, 3),
            "compute_overhead_cores": round(compute_overhead_cores, 2),
            "simulated_cost_usd": round(total_cost, 6)
        }


def save_telemetry_to_csv(metrics: List[Dict[str, Any]], filename: str):
    """Saves benchmark results to a CSV file."""
    fields = ["timestamp", "traffic_level", "architecture", "event_count", "anomaly_count", "latency_seconds", "compute_overhead_cores", "simulated_cost_usd"]
    
    file_exists = os.path.exists(filename)
    
    with open(filename, mode="a" if file_exists else "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
            
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for metric in metrics:
            row = metric.copy()
            row["timestamp"] = current_time
            writer.writerow(row)
            
    logger.info(f"Telemetry metrics appended to '{filename}'.")


if __name__ == "__main__":
    logger.info("Initializing BigQuery Continuous Query Mesh Simulation...")
    
    # We will simulate different network traffic levels
    traffic_scenarios = [
        {"level": "Off-Peak", "events": 3000},     # 10 events/sec over 5 mins
        {"level": "Low", "events": 15000},         # 50 events/sec
        {"level": "Medium", "events": 60000},      # 200 events/sec
        {"level": "High", "events": 180000},       # 600 events/sec
        {"level": "Peak", "events": 300000}        # 1000 events/sec
    ]
    
    benchmark = DataMeshArchitectures()
    telemetry_records = []
    
    print("\n" + "="*80)
    print(f"{'BIGQUERY CONTINUOUS QUERY VS MICRO-BATCH ETL BENCHMARK':^80}")
    print("="*80)
    print(f"{'Traffic':<10} | {'Architecture':<28} | {'Events':<8} | {'Anomalies':<9} | {'Latency':<8} | {'Cost ($)':<8}")
    print("-"*80)
    
    for scenario in traffic_scenarios:
        level = scenario["level"]
        event_count = scenario["events"]
        
        # Generate mock telemetry logs
        events = TelcoTelemetryStream.generate_events(event_count, level)
        
        # Run Micro-batch simulation
        micro_batch_res = benchmark.simulate_micro_batch(events)
        micro_batch_res["traffic_level"] = level
        telemetry_records.append(micro_batch_res)
        
        # Run Continuous query simulation
        continuous_res = benchmark.simulate_continuous_query(events)
        continuous_res["traffic_level"] = level
        telemetry_records.append(continuous_res)
        
        # Print format
        print(f"{level:<10} | {micro_batch_res['architecture']:<28} | {event_count:<8} | {micro_batch_res['anomaly_count']:<9} | {micro_batch_res['latency_seconds']:>6}s | ${micro_batch_res['simulated_cost_usd']:.4f}")
        print(f"{level:<10} | {continuous_res['architecture']:<28} | {event_count:<8} | {continuous_res['anomaly_count']:<9} | {continuous_res['latency_seconds']:>6}s | ${continuous_res['simulated_cost_usd']:.4f}")
        print("-"*80)
        
    # Save the output CSV
    output_path = "/home/abhishek/ObsidianVault/08_Google_Content_Engine/Track5_BigQuery_DataMesh/streaming_telemetry.csv"
    save_telemetry_to_csv(telemetry_records, output_path)
    
    # Print high-level statistics summary
    print("\n" + "="*80)
    print(f"{'SIMULATION COMPLETED SUCCESSFULLY':^80}")
    print("="*80)
    
    # Calculate averages
    mb_latencies = [r["latency_seconds"] for r in telemetry_records if r["architecture"] == "Micro-batch ETL"]
    cq_latencies = [r["latency_seconds"] for r in telemetry_records if r["architecture"] == "Continuous Query (Pub/Sub)"]
    
    mb_avg = sum(mb_latencies) / len(mb_latencies)
    cq_avg = sum(cq_latencies) / len(cq_latencies)
    latency_reduction = ((mb_avg - cq_avg) / mb_avg) * 100.0
    
    print(f"Average Micro-batch ETL Latency:  {mb_avg:.2f} seconds")
    print(f"Average Continuous Query Latency: {cq_avg:.4f} seconds")
    print(f"🎉 Real-time Latency Reduction:   {latency_reduction:.4f}%")
    print(f"Telemetry report written to:      {output_path}")
    print("="*80 + "\n")
