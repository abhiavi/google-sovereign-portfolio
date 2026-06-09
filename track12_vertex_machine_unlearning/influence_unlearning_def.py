import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader
import copy
import numpy as np
import time
import os
import json

# Set random seed for reproducibility
torch.manual_seed(42)
np.random.seed(42)

# ==========================================
# 1. Define Model and Synthetic Dataset
# ==========================================
class SimpleMLP(nn.Module):
    def __init__(self, input_dim=16, hidden_dim=32, output_dim=1):
        super(SimpleMLP, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.Tanh(), # Smooth, twice-differentiable activation function
            nn.Linear(hidden_dim, output_dim)
        )
        
    def forward(self, x):
        return self.net(x)

def generate_synthetic_data(num_samples=100000, input_dim=16):
    """
    Generates synthetic user embeddings and binary labels.
    """
    X = torch.randn(num_samples, input_dim)
    true_weights = torch.randn(input_dim, 1)
    # Generate labels with a linear boundary and noise
    y = (torch.matmul(X, true_weights) + 0.1 * torch.randn(num_samples, 1) > 0.0).float()
    return X, y

# ==========================================
# 2. Hessian-Vector Product (HVP) & LiSSA
# ==========================================
def compute_hvp(model, loss_fn, inputs, targets, vector):
    params = [p for p in model.parameters() if p.requires_grad]
    outputs = model(inputs)
    loss = loss_fn(outputs, targets)
    grads = torch.autograd.grad(loss, params, create_graph=True)
    grad_v = sum((g * v).sum() for g, v in zip(grads, vector))
    hvp = torch.autograd.grad(grad_v, params)
    return hvp

def compute_hvp_lissa(model, loss_fn, remain_dataset, target_grad, scale=10.0, damping=0.01, num_iters=50):
    h_estimate = [tg.clone() for tg in target_grad]
    loader = DataLoader(remain_dataset, batch_size=64, shuffle=True)
    loader_iter = iter(loader)
    
    for i in range(num_iters):
        try:
            x_batch, y_batch = next(loader_iter)
        except StopIteration:
            loader_iter = iter(loader)
            x_batch, y_batch = next(loader_iter)
            
        hvp = compute_hvp(model, loss_fn, x_batch, y_batch, h_estimate)
        
        with torch.no_grad():
            for j in range(len(h_estimate)):
                h_estimate[j] = (
                    target_grad[j] 
                    + h_estimate[j] 
                    - (hvp[j] + damping * h_estimate[j]) / scale
                )
                
    with torch.no_grad():
        for j in range(len(h_estimate)):
            h_estimate[j] = h_estimate[j] / scale
            
    return h_estimate

# ==========================================
# 3. DP-Compliant Influence Unlearning
# ==========================================
def run_dp_influence_unlearning(model, loss_fn, remain_dataset, forget_dataset, 
                               epsilon=1.0, delta=1e-5, scale=20.0, damping=0.01, 
                               num_iters=50, clip_norm=0.05):
    unlearned_model = copy.deepcopy(model)
    unlearned_model.eval()
    
    forget_loader = DataLoader(forget_dataset, batch_size=len(forget_dataset), shuffle=False)
    x_forget, y_forget = next(iter(forget_loader))
    
    outputs_forget = unlearned_model(x_forget)
    loss_forget = loss_fn(outputs_forget, y_forget)
    
    params = [p for p in unlearned_model.parameters() if p.requires_grad]
    target_grad = torch.autograd.grad(loss_forget, params)
    
    inverse_hvp = compute_hvp_lissa(
        unlearned_model, loss_fn, remain_dataset, target_grad, 
        scale=scale, damping=damping, num_iters=num_iters
    )
    
    learning_rate = 1.0
    scaled_hvp = [inv_h * learning_rate for inv_h in inverse_hvp]
    
    # Flatten the update vector for global L2 clipping
    flat_hvp = torch.cat([h.flatten() for h in scaled_hvp])
    actual_norm = torch.norm(flat_hvp).item()
    
    # Apply clipping
    if actual_norm > clip_norm:
        flat_hvp = flat_hvp * (clip_norm / actual_norm)
        clipped = True
    else:
        clipped = False
        
    # Calibrate Gaussian noise
    sigma = (clip_norm * np.sqrt(2 * np.log(1.25 / delta))) / epsilon
    noise = torch.randn_like(flat_hvp) * sigma
    dp_hvp = flat_hvp + noise
    
    # Apply the DP parameter update
    current_idx = 0
    with torch.no_grad():
        for p in unlearned_model.parameters():
            if p.requires_grad:
                numel = p.numel()
                param_update = dp_hvp[current_idx : current_idx + numel].view_as(p)
                p.data.add_(param_update)
                current_idx += numel
                
    return unlearned_model, actual_norm, sigma, clipped

# ==========================================
# 4. Standard Training & Evaluation Helpers
# ==========================================
def train_model(model, loss_fn, train_dataset, epochs=5, lr=0.05, batch_size=1024):
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9)
    loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    
    for epoch in range(epochs):
        model.train()
        for x_batch, y_batch in loader:
            optimizer.zero_grad()
            outputs = model(x_batch)
            loss = loss_fn(outputs, y_batch)
            loss.backward()
            optimizer.step()
    model.eval()
    return model

def evaluate_model(model, loss_fn, dataset):
    loader = DataLoader(dataset, batch_size=2048, shuffle=False)
    total_loss = 0.0
    correct = 0
    total = 0
    model.eval()
    with torch.no_grad():
        for x, y in loader:
            outputs = model(x)
            loss = loss_fn(outputs, y)
            total_loss += loss.item() * len(x)
            preds = (torch.sigmoid(outputs) > 0.5).float()
            correct += (preds == y).sum().item()
            total += len(x)
    return total_loss / total, (correct / total) * 100

# ==========================================
# 5. Threshold-Based Rejection Mechanism (Safety Guard)
# ==========================================
def verify_and_apply_unlearning(model, loss_fn, remain_dataset, forget_dataset, validation_dataset,
                                safety_threshold=95.0, epsilon=1.0, delta=1e-5, scale=50.0, 
                                damping=0.05, num_iters=100, clip_norm=0.05):
    """
    Performs unlearning on a trial basis, evaluates model performance on validation set,
    and commits or rejects the update based on safety accuracy threshold.
    """
    print(f"\n[Safety Guard] Initiating trial unlearning run for cohort of {len(forget_dataset)} samples...")
    
    # 1. Compute trial unlearned model
    trial_model, raw_norm, sigma, clipped = run_dp_influence_unlearning(
        model, loss_fn, remain_dataset, forget_dataset,
        epsilon=epsilon, delta=delta, scale=scale, damping=damping,
        num_iters=num_iters, clip_norm=clip_norm
    )
    
    # 2. Evaluate performance on baseline validation set
    val_loss, val_acc = evaluate_model(trial_model, loss_fn, validation_dataset)
    print(f"[Safety Guard] Trial validation accuracy: {val_acc:.2f}% (Safety Limit: {safety_threshold:.2f}%)")
    
    # 3. Decision check
    if val_acc >= safety_threshold:
        print("[Safety Guard] SUCCESS: Trial model accuracy exceeds safety limit. Unlearning APPROVED and committed.")
        return trial_model, True, val_acc, raw_norm, sigma
    else:
        print(f"[Safety Guard] ALERT: Trial model accuracy ({val_acc:.2f}%) fell below safety threshold ({safety_threshold:.2f}%).")
        print("[Safety Guard] CRITICAL: Potential Adversarial Unlearning Attack detected. Weight update REJECTED/ROLLED BACK.")
        return model, False, val_acc, raw_norm, sigma

# ==========================================
# 6. Main Execution Simulation
# ==========================================
def main():
    print("=== Track 12: Adversarial Unlearning Simulator & Safety Lockdown ===")
    
    # 1. Generate large synthetic dataset (100,000 user embeddings)
    X, y = generate_synthetic_data(num_samples=100000, input_dim=16)
    X_test, y_test = generate_synthetic_data(num_samples=10000, input_dim=16)
    
    # Split validation set for the safety guard (1,000 samples)
    X_val, y_val = X[-1000:], y[-1000:]
    X_train_pool, y_train_pool = X[:-1000], y[:-1000]
    
    train_pool_ds = TensorDataset(X_train_pool, y_train_pool)
    val_ds = TensorDataset(X_val, y_val)
    test_ds = TensorDataset(X_test, y_test)
    
    loss_fn = nn.BCEWithLogitsLoss()
    
    # Train base model
    print("Training base model on ALL training embeddings...")
    base_model = SimpleMLP(input_dim=16)
    base_model = train_model(base_model, loss_fn, train_pool_ds, epochs=5, lr=0.05, batch_size=1024)
    
    base_loss, base_acc = evaluate_model(base_model, loss_fn, val_ds)
    print(f"Base model initialized. Validation Accuracy: {base_acc:.2f}%")
    
    # Define safety settings
    safety_limit = 92.0 # Unlearning must preserve at least 92% baseline accuracy
    
    # --- SCENARIO A: Benign Cohort Unlearning Request (500 users) ---
    print("\n--- SCENARIO A: Benign Deletion Request (500 users) ---")
    benign_size = 500
    X_benign_forget, y_benign_forget = X_train_pool[:benign_size], y_train_pool[:benign_size]
    X_benign_remain, y_benign_remain = X_train_pool[benign_size:], y_train_pool[benign_size:]
    
    benign_forget_ds = TensorDataset(X_benign_forget, y_benign_forget)
    benign_remain_ds = TensorDataset(X_benign_remain, y_benign_remain)
    
    model_after_benign, benign_ok, benign_val_acc, _, _ = verify_and_apply_unlearning(
        base_model, loss_fn, benign_remain_ds, benign_forget_ds, val_ds,
        safety_threshold=safety_limit, epsilon=1.0, delta=1e-5
    )
    
    # --- SCENARIO B: Adversarial Poisoning Unlearning Request (5,000 users) ---
    print("\n--- SCENARIO B: Adversarial Poisoning Attack (5,000 users) ---")
    # A malicious user requests deletion of 5,000 key data records to degrade baseline model intelligence
    adv_size = 5000
    X_adv_forget, y_adv_forget = X_train_pool[:adv_size], y_train_pool[:adv_size]
    X_adv_remain, y_adv_remain = X_train_pool[adv_size:], y_train_pool[adv_size:]
    
    adv_forget_ds = TensorDataset(X_adv_forget, y_adv_forget)
    adv_remain_ds = TensorDataset(X_adv_remain, y_adv_remain)
    
    model_after_adv, adv_ok, adv_val_acc, adv_raw_norm, adv_sigma = verify_and_apply_unlearning(
        base_model, loss_fn, adv_remain_ds, adv_forget_ds, val_ds,
        safety_threshold=safety_limit, epsilon=1.0, delta=1e-5
    )
    
    # Verify final models
    final_benign_loss, final_benign_acc = evaluate_model(model_after_benign, loss_fn, val_ds)
    final_adv_loss, final_adv_acc = evaluate_model(model_after_adv, loss_fn, val_ds)
    
    # Save test results JSON
    log_output_path = os.path.join(os.path.dirname(__file__), "adversarial_unlearning_report.json")
    report = {
        "baseline": {
            "validation_accuracy": base_acc,
            "safety_threshold": safety_limit
        },
        "benign_scenario": {
            "requested_deletions": benign_size,
            "validation_accuracy_after_trial": benign_val_acc,
            "status": "APPROVED" if benign_ok else "REJECTED",
            "final_model_accuracy": final_benign_acc
        },
        "adversarial_scenario": {
            "requested_deletions": adv_size,
            "validation_accuracy_after_trial": adv_val_acc,
            "status": "APPROVED" if adv_ok else "REJECTED",
            "final_model_accuracy": final_adv_acc,
            "telemetry": {
                "raw_update_norm": adv_raw_norm,
                "noise_scale_sigma": adv_sigma
            }
        }
    }
    
    with open(log_output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nAdversarial testing results saved to: {log_output_path}")

if __name__ == "__main__":
    main()
