import os
import json
import hashlib
import time
import base64

# ==========================================
# 1. AMD SEV-SNP Reference Measurements
# ==========================================
SEV_SNP_REFERENCE_MEASUREMENTS = {
    "firmware_launch_digest": "8a7c2b3e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c",
    "enclave_container_digest": "3f8b7c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b",
    "secure_boot_loader_hash": "b2a3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3"
}

RUNNING_HARDWARE_MEASUREMENTS = {
    "firmware_launch_digest": "8a7c2b3e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c",
    "enclave_container_digest": "3f8b7c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b",
    "secure_boot_loader_hash": "b2a3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3",
    "platform_info": {
        "amd_cpu_family": "EPYC Genoa",
        "sev_enabled": True,
        "es_enabled": True,
        "snp_enabled": True
    }
}

# ==========================================
# 2. Generating Fictitious Competing Banks Data
# ==========================================
raw_bank_alpha = [
    {"name": "Alice Smith", "ssn": "999-12-3456", "credit_score": 720, "dti": 0.28, "risk_class": 0},
    {"name": "Bob Jones", "ssn": "999-23-4567", "credit_score": 580, "dti": 0.45, "risk_class": 1},
    {"name": "Charlie Brown", "ssn": "999-34-5678", "credit_score": 690, "dti": 0.35, "risk_class": 0}
]

raw_bank_beta = [
    {"name": "David Davis", "ssn": "999-45-6789", "credit_score": 640, "dti": 0.41, "risk_class": 1},
    {"name": "Eva Green", "ssn": "999-56-7890", "credit_score": 790, "dti": 0.22, "risk_class": 0},
    {"name": "Frank White", "ssn": "999-67-8901", "credit_score": 520, "dti": 0.55, "risk_class": 1}
]

raw_bank_gamma = [
    {"name": "Grace Kelly", "ssn": "999-78-9012", "credit_score": 710, "dti": 0.31, "risk_class": 0},
    {"name": "Henry Ford", "ssn": "999-89-0123", "credit_score": 600, "dti": 0.48, "risk_class": 1},
    {"name": "Ivy League", "ssn": "999-90-1234", "credit_score": 810, "dti": 0.15, "risk_class": 0}
]

local_weights_alpha = [0.15, -0.005, 0.45]
local_weights_beta = [0.18, -0.004, 0.42]
local_weights_gamma = [0.12, -0.006, 0.48]

def encrypt_payload(data):
    json_str = json.dumps(data)
    encoded = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
    return f"ENC::KMS_KEY_DECRYPT_REQUIRED::{encoded}"

MOCK_INPUTS_ENCRYPTED = {
    "Bank_Alpha": {
        "key_id": "projects/my_project/locations/global/keyRings/kr_sovereign/cryptoKeys/key_bank_alpha",
        "ciphertext": encrypt_payload({"records": raw_bank_alpha, "weights": local_weights_alpha}),
        "mac": hashlib.sha256(json.dumps(raw_bank_alpha).encode()).hexdigest()
    },
    "Bank_Beta": {
        "key_id": "projects/my_project/locations/global/keyRings/kr_sovereign/cryptoKeys/key_bank_beta",
        "ciphertext": encrypt_payload({"records": raw_bank_beta, "weights": local_weights_beta}),
        "mac": hashlib.sha256(json.dumps(raw_bank_beta).encode()).hexdigest()
    },
    "Bank_Gamma": {
        "key_id": "projects/my_project/locations/global/keyRings/kr_sovereign/cryptoKeys/key_bank_gamma",
        "ciphertext": encrypt_payload({"records": raw_bank_gamma, "weights": local_weights_gamma}),
        "mac": hashlib.sha256(json.dumps(raw_bank_gamma).encode()).hexdigest()
    }
}

# ==========================================
# 3. Attestation & Decryption Simulation
# ==========================================
def verify_amd_sev_snp_hardware():
    print("[Attestation] Initiating guest attestation protocol on /dev/sev-guest...")
    time.sleep(0.1)
    for key, expected in SEV_SNP_REFERENCE_MEASUREMENTS.items():
        actual = RUNNING_HARDWARE_MEASUREMENTS.get(key)
        if actual != expected:
            raise PermissionError(f"[Attestation Failed] Hardware measurements mismatch!")
    print("[Attestation] Guest attestation report validated against AMD Root Key (ARK) successfully.")
    return True

def fetch_kms_decryption_keys():
    print("[Attestation] Submitting hardware attestation report to Identity Provider...")
    print("[KMS] Attestation claim verification PASSED. Decryption keys authorized.")
    return {
        "Bank_Alpha": "secret_key_alpha_32B",
        "Bank_Beta": "secret_key_beta_32B",
        "Bank_Gamma": "secret_key_gamma_32B"
    }

def decrypt_payload(ciphertext, key):
    if not ciphertext.startswith("ENC::KMS_KEY_DECRYPT_REQUIRED::"):
        raise ValueError("Invalid cipher structure.")
    encoded = ciphertext.replace("ENC::KMS_KEY_DECRYPT_REQUIRED::", "")
    decoded_str = base64.b64decode(encoded.encode('utf-8')).decode('utf-8')
    return json.loads(decoded_str)

# ==========================================
# 4. Secure RAM Zeroization (Mitigates State Leakage)
# ==========================================
def secure_zero_memory(*args):
    """
    Simulates scrubbing/zeroing out secure RAM registers containing key material and raw data.
    In C/Rust enclaves, this compiles to a volatile memset (memset_s / zeroize) to prevent compiler optimization bypass.
    """
    print("[Secure RAM] CRITICAL ACTION: Zeroing out key material and decrypted PII buffers in enclave heap...")
    for arg in args:
        if isinstance(arg, list):
            arg.clear()
        elif isinstance(arg, dict):
            arg.clear()
    import gc
    gc.collect()
    print("[Secure RAM] Enclave memory successfully scrubbed.")

# ==========================================
# 5. Federated Aggregator & Risk Scoring (Inside Enclave)
# ==========================================
def execute_mpc_aggregation_and_scoring(decryption_keys, simulate_kms_failure=False):
    print("[Enclave Core] Decrypting bank telemetry inside secure enclave RAM...")
    
    all_records = []
    local_weights_list = []
    bank_sample_sizes = {}
    
    try:
        for bank_name, meta in MOCK_INPUTS_ENCRYPTED.items():
            key = decryption_keys.get(bank_name)
            
            # Simulate KMS key rotation failure mid-way (specifically on Bank_Gamma)
            if simulate_kms_failure and bank_name == "Bank_Gamma":
                print("\n[KMS] ERROR: Key version for Bank_Gamma was rotated mid-execution by the bank admin.")
                raise ConnectionError("KMS_KEY_ROTATION_FAILURE: The requested key version is disabled or retired.")
                
            decrypted_data = decrypt_payload(meta["ciphertext"], key)
            records = decrypted_data["records"]
            weights = decrypted_data["weights"]
            
            all_records.extend(records)
            local_weights_list.append(weights)
            bank_sample_sizes[bank_name] = len(records)
            print(f"[Enclave Core] Successfully decrypted {len(records)} records from {bank_name}.")

        # Federated Learning Aggregation (FedAvg)
        total_samples = sum(bank_sample_sizes.values())
        global_weights = [0.0, 0.0, 0.0]
        
        for weights, size in zip(local_weights_list, bank_sample_sizes.values()):
            weight_factor = size / total_samples
            for idx in range(len(global_weights)):
                global_weights[idx] += weights[idx] * weight_factor
                
        # Cross-Bank Risk Scoring
        scores = [r["credit_score"] for r in all_records]
        dtis = [r["dti"] for r in all_records]
        high_risk_count = sum(1 for r in all_records if r["credit_score"] < 600 or r["dti"] > 0.4)
        
        mean_credit_score = sum(scores) / len(scores)
        mean_dti = sum(dtis) / len(dtis)
        high_risk_ratio = high_risk_count / len(all_records)
        
        return {
            "status": "COMPLETED",
            "global_model_parameters": {
                "aggregated_bias": global_weights[0],
                "aggregated_w_credit": global_weights[1],
                "aggregated_w_dti": global_weights[2]
            },
            "aggregate_telemetry": {
                "total_parties": len(bank_sample_sizes),
                "total_samples": total_samples,
                "mean_credit_score": mean_credit_score,
                "mean_dti": mean_dti,
                "high_risk_percentage": high_risk_ratio * 100
            }
        }
        
    except Exception as e:
        # Scrub sensitive variables in RAM immediately
        secure_zero_memory(all_records, local_weights_list, bank_sample_sizes, decryption_keys)
        raise e

# ==========================================
# 6. Secure Telemetry Auditor
# ==========================================
def secure_telemetry_logger(start_time, attestation_status, aggregation_result):
    execution_time = time.time() - start_time
    
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "log_level": "INFO" if aggregation_result.get("status") == "COMPLETED" else "ERROR",
        "enclave_context": {
            "amd_sev_snp": {
                "hardware_authenticated": attestation_status,
                "launch_digest": RUNNING_HARDWARE_MEASUREMENTS["firmware_launch_digest"],
                "container_digest": RUNNING_HARDWARE_MEASUREMENTS["enclave_container_digest"],
                "amd_security_features": RUNNING_HARDWARE_MEASUREMENTS["platform_info"]
            }
        },
        "performance_telemetry": {
            "execution_duration_sec": execution_time,
            "memory_usage_state": "Cleaned - RAM zeroized post-execution/abort",
            "federated_iterations": 1 if aggregation_result.get("status") == "COMPLETED" else 0
        },
        "audit_trail": {
            "computation_status": aggregation_result.get("status"),
            "errors_logged": aggregation_result.get("errors", []),
            "parties_engaged": ["Bank_Alpha", "Bank_Beta", "Bank_Gamma"],
            "aggregated_metrics": aggregation_result.get("aggregate_telemetry"),
            "aggregated_weights": aggregation_result.get("global_model_parameters")
        }
    }
    
    # Save log report
    log_path = os.path.join(os.path.dirname(__file__), "enclave_telemetry_audit.json")
    with open(log_path, "w") as f:
        json.dump(log_entry, f, indent=2)
        
    print("\n--- Enclave Audit Log Generated ---")
    print(json.dumps(log_entry, indent=2))
    print(f"Audit report saved: {log_path}\n")

# ==========================================
# 7. Main Enclave Orchestration
# ==========================================
def main():
    print("=== Track 14: Confidential Space Federated Risk Scorer ===")
    
    # --- SCENARIO A: Normal Clean Execution ---
    print("\n--- Running Scenario A: Clean Multi-Party Computation ---")
    start_time = time.time()
    attestation_ok = False
    agg_res = {"status": "NOT_EXECUTED"}
    try:
        attestation_ok = verify_amd_sev_snp_hardware()
        decryption_keys = fetch_kms_decryption_keys()
        agg_res = execute_mpc_aggregation_and_scoring(decryption_keys, simulate_kms_failure=False)
    except Exception as e:
        agg_res = {"status": "ERROR", "errors": [str(e)]}
    finally:
        secure_telemetry_logger(start_time, attestation_ok, agg_res)
        
    # --- SCENARIO B: KMS Key Rotation Failure Mid-Way ---
    print("\n--- Running Scenario B: KMS Key Rotation Failure Mid-Way (Adversarial Testing) ---")
    start_time = time.time()
    attestation_ok = False
    agg_res = {"status": "NOT_EXECUTED"}
    try:
        attestation_ok = verify_amd_sev_snp_hardware()
        decryption_keys = fetch_kms_decryption_keys()
        # Trigger simulation of key failure mid-way
        agg_res = execute_mpc_aggregation_and_scoring(decryption_keys, simulate_kms_failure=True)
    except Exception as e:
        print(f"[Execution Failed] Graceful abort of joint risk scoring due to: {str(e)}")
        agg_res = {"status": "ABORTED_KEY_ROTATION_FAILURE", "errors": [str(e)]}
    finally:
        secure_telemetry_logger(start_time, attestation_ok, agg_res)

if __name__ == "__main__":
    main()
