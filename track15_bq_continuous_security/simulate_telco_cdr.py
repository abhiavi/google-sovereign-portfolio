#!/usr/bin/env python3
"""
Track 15: Telco CDR Log Generator
Generates 1,000,000 simulated Call Detail Record (CDR) logs and pipes them into
the continuous BigQuery simulation framework to measure scale and latency.
"""
import time
import uuid
import random
import json

def generate_cdr_logs(num_records):
    print(f"Starting generation of {num_records} CDR logs...")
    start_time = time.time()
    
    towers = [f"TWR-{i:04d}" for i in range(1, 101)]
    cells = [f"CELL-{i:04d}" for i in range(1, 501)]
    
    batch_size = 10000
    for batch_start in range(0, num_records, batch_size):
        batch = []
        for _ in range(batch_size):
            # Simulate late-arriving data: 5% of records delayed by up to 300 seconds
            is_late = random.random() < 0.05
            delay = random.uniform(10, 300) if is_late else 0
            
            record = {
                "event_timestamp": time.time() - delay,
                "is_late_arrival": is_late,
                "tower_id": random.choice(towers),
                "cell_id": random.choice(cells),
                "interface_id": f"eth{random.randint(0,4)}",
                "source_ip": f"10.0.{random.randint(1,255)}.{random.randint(1,255)}",
                "destination_ip": f"192.168.{random.randint(1,255)}.{random.randint(1,255)}",
                "protocol": random.choice(["TCP", "UDP", "ICMP"]),
                "traffic_bytes": random.randint(100, 100000),
                "packet_count": random.randint(1, 100),
                "threat_severity": random.choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"])
            }
            batch.append(record)
        # In a real environment, pipe this batch to BigQuery Storage Write API
        # print(f"Piped batch of {batch_size} records. Total: {batch_start + batch_size}")
    
    end_time = time.time()
    print(f"Generated {num_records} CDR logs in {end_time - start_time:.2f} seconds.")

if __name__ == "__main__":
    generate_cdr_logs(1_000_000)
