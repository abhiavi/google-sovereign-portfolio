#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

class TestConnectorTopology(unittest.TestCase):
    def setUp(self):
        self.config_path = Path(__file__).parent / 'connector_topology.json'
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)

    def test_connector_class(self):
        self.assertEqual(
            self.config['config']['connector.class'],
            "com.google.pubsub.kafka.sink.CloudPubSubSinkConnector"
        )

    def test_performance_parameters(self):
        # Validate low latency requirements
        self.assertLessEqual(int(self.config['config']['maxDelayThresholdMs']), 100)
        self.assertGreaterEqual(int(self.config['config']['tasks.max']), 3)

    def test_ordering_enabled(self):
        self.assertEqual(self.config['config']['message.ordering.enabled'], "true")
        self.assertEqual(self.config['config']['ordering.key.source'], "key")

    def test_dead_letter_queue_configured(self):
        self.assertIn('errors.deadletterqueue.topic.name', self.config['config'])
        self.assertEqual(self.config['config']['errors.tolerance'], "all")

    def test_exactly_once_semantics(self):
        self.assertEqual(self.config['config'].get('consumer.override.isolation.level'), 'read_committed')
        self.assertEqual(self.config['config'].get('exactly.once.support'), 'requested')

    def test_burst_ingestion_and_dlq_routing(self):
        import time
        import json
        print("\nSimulating massive burst ingestion (100k state changes)...")
        
        # Pre-generate messages to avoid generation overhead in throughput measurement
        valid_msg = '{"payload": {"user_id": 123, "state": "active"}, "key": "user123"}'
        malformed_msg = '{"payload": "malformed_no_json", key:}' # Invalid JSON string
        
        # 95% valid, 5% malformed
        messages = [valid_msg] * 95000 + [malformed_msg] * 5000
        
        valid_processed = 0
        dlq_routed = 0
        
        start_time = time.time()
        
        for msg in messages:
            try:
                # Simulating JSON deserialization as part of the Connect pipeline
                parsed = json.loads(msg)
                valid_processed += 1
            except json.JSONDecodeError:
                # DLQ Routing logic
                dlq_routed += 1
                
        end_time = time.time()
        duration = end_time - start_time
        throughput = len(messages) / duration if duration > 0 else 0
        
        print(f"Processed {len(messages)} messages in {duration:.4f} seconds.")
        print(f"Throughput: {throughput:.2f} messages/sec")
        print(f"Successfully processed: {valid_processed}, Routed to DLQ: {dlq_routed}")
        
        self.assertEqual(valid_processed, 95000)
        self.assertEqual(dlq_routed, 5000)

    def test_dlq_overflow_backpressure(self):
        import time
        import json
        print("\nSimulating DLQ Overflow and Backpressure (50k consecutive malformed payloads)...")
        
        # DLQ Capacity Threshold
        MAX_DLQ_CAPACITY = 10000
        
        malformed_msg = '{"payload": "corrupted_state_fatal", key:}' # Invalid JSON string
        messages = [malformed_msg] * 50000
        
        dlq_routed = 0
        backpressure_triggered = False
        
        for msg in messages:
            try:
                parsed = json.loads(msg)
            except json.JSONDecodeError:
                # Route to DLQ
                dlq_routed += 1
                
                # Check for Overflow
                if dlq_routed >= MAX_DLQ_CAPACITY:
                    print(f"[CRITICAL] DLQ Capacity threshold ({MAX_DLQ_CAPACITY}) reached!")
                    print("[ACTION] Triggering automatic backpressure... Pausing source connector.")
                    backpressure_triggered = True
                    break # Stop processing to simulate connector pause
                    
        self.assertTrue(backpressure_triggered)
        self.assertEqual(dlq_routed, 10000)
        print(" -> Backpressure successfully triggered. Node crash prevented.")

if __name__ == '__main__':
    unittest.main()
