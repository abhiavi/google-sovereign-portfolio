# generate_architecture.py - Architecture Diagram Generator for GKE Kueue Gang Scheduling
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("diagram_gen")

def build_architecture_svg(filename: str):
    """Generates a high-quality vector SVG architecture diagram comparing Standard vs Kueue scheduling."""
    svg_content = """<svg width="1200" height="750" viewBox="0 0 1200 750" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <!-- Background Gradient -->
    <linearGradient id="bg-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#070a13" />
      <stop offset="100%" stop-color="#0f172a" />
    </linearGradient>
    
    <!-- Component Gradients -->
    <linearGradient id="kueue-grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#6366f1" />
      <stop offset="100%" stop-color="#3b82f6" />
    </linearGradient>
    <linearGradient id="deadlock-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ef4444" />
      <stop offset="100%" stop-color="#b91c1c" />
    </linearGradient>
    <linearGradient id="success-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#10b981" />
      <stop offset="100%" stop-color="#047857" />
    </linearGradient>
    <linearGradient id="job-a-grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#a855f7" />
      <stop offset="100%" stop-color="#7c3aed" />
    </linearGradient>
    <linearGradient id="job-b-grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#14b8a6" />
      <stop offset="100%" stop-color="#0d9488" />
    </linearGradient>
    
    <!-- Shadow Filter -->
    <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="8" stdDeviation="6" flood-color="#000" flood-opacity="0.5" />
    </filter>
    <filter id="glow-red" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="4" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
    <filter id="glow-green" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="4" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>

    <!-- Marker definition for arrows -->
    <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
    </marker>
    <marker id="arrow-blue" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#3b82f6" />
    </marker>
  </defs>

  <!-- Background -->
  <rect width="100%" height="100%" fill="url(#bg-grad)" />
  
  <!-- Subtle Grid -->
  <path d="M 0,50 L 1200,50 M 0,100 L 1200,100 M 0,150 L 1200,150 M 0,200 L 1200,200 M 0,250 L 1200,250 M 0,300 L 1200,300 M 0,350 L 1200,350 M 0,400 L 1200,400 M 0,450 L 1200,450 M 0,500 L 1200,500 M 0,550 L 1200,550 M 0,600 L 1200,600 M 0,650 L 1200,650 M 0,700 L 1200,700" fill="none" stroke="#1e293b" stroke-width="0.5" opacity="0.3" />
  <path d="M 100,0 L 100,750 M 200,0 L 200,750 M 300,0 L 300,750 M 400,0 L 400,750 M 500,0 L 500,750 M 600,0 L 600,750 M 700,0 L 700,750 M 800,0 L 800,750 M 900,0 L 900,750 M 1000,0 L 1000,750 M 1100,0 L 1100,750" fill="none" stroke="#1e293b" stroke-width="0.5" opacity="0.3" />

  <!-- HEADER -->
  <text x="50" y="55" font-family="'Inter', system-ui, sans-serif" font-size="28" font-weight="800" fill="#f8fafc" letter-spacing="-0.5">GKE Kueue Gang Scheduling Architecture</text>
  <text x="50" y="85" font-family="'Inter', system-ui, sans-serif" font-size="14" font-weight="500" fill="#94a3b8">How Kueue prevents resource deadlocks in distributed LLM workloads compared to standard Kubernetes</text>

  <!-- SECTION 1: WORKLOAD INTAKE (LEFT) -->
  <g transform="translate(50, 150)">
    <!-- Section Border Box -->
    <rect width="250" height="520" rx="12" fill="#0f172a" stroke="#1e293b" stroke-width="1.5" />
    <text x="20" y="35" font-family="'Inter', system-ui, sans-serif" font-size="15" font-weight="700" fill="#f1f5f9">1. Job Submission</text>
    
    <!-- Job A Card -->
    <g transform="translate(20, 60)" filter="url(#shadow)">
      <rect width="210" height="90" rx="8" fill="url(#job-a-grad)" />
      <text x="15" y="30" font-family="'Inter', system-ui, sans-serif" font-size="14" font-weight="700" fill="#ffffff">Job A: Llama-3-70B</text>
      <text x="15" y="52" font-family="'Inter', system-ui, sans-serif" font-size="11" fill="#f3e8ff">• 4 Pods requested</text>
      <text x="15" y="70" font-family="'Inter', system-ui, sans-serif" font-size="11" fill="#f3e8ff">• 8 GPUs/Pod (32 GPUs total)</text>
    </g>

    <!-- Job B Card -->
    <g transform="translate(20, 170)" filter="url(#shadow)">
      <rect width="210" height="90" rx="8" fill="url(#job-b-grad)" />
      <text x="15" y="30" font-family="'Inter', system-ui, sans-serif" font-size="14" font-weight="700" fill="#ffffff">Job B: DeepRL Swarm</text>
      <text x="15" y="52" font-family="'Inter', system-ui, sans-serif" font-size="11" fill="#ccfbf1">• 4 Pods requested</text>
      <text x="15" y="70" font-family="'Inter', system-ui, sans-serif" font-size="11" fill="#ccfbf1">• 8 GPUs/Pod (32 GPUs total)</text>
    </g>

    <!-- Interception Webhook -->
    <g transform="translate(20, 290)">
      <rect width="210" height="100" rx="8" fill="#1e293b" stroke="#3b82f6" stroke-width="1.5" />
      <text x="15" y="30" font-family="'Inter', system-ui, sans-serif" font-size="12" font-weight="700" fill="#3b82f6">Kueue Mutating Webhook</text>
      <text x="15" y="55" font-family="'Inter', system-ui, sans-serif" font-size="11" fill="#94a3b8">Intercepts Job creation and</text>
      <text x="15" y="72" font-family="'Inter', system-ui, sans-serif" font-size="11" fill="#94a3b8">forces spec.suspend: true</text>
    </g>

    <!-- Suspended Queue State -->
    <g transform="translate(20, 410)">
      <rect width="210" height="85" rx="8" fill="#020617" stroke="#334155" stroke-width="1.5" />
      <text x="15" y="30" font-family="'Inter', system-ui, sans-serif" font-size="12" font-weight="700" fill="#f1f5f9">Kueue Local Queue</text>
      <text x="15" y="52" font-family="'Inter', system-ui, sans-serif" font-size="11" fill="#e2e8f0">• Job A (Suspended)</text>
      <text x="15" y="70" font-family="'Inter', system-ui, sans-serif" font-size="11" fill="#e2e8f0">• Job B (Suspended)</text>
    </g>
  </g>

  <!-- Flow Arrows from Jobs to Webhook and Queue -->
  <path d="M 280,240 L 320,240 L 320,490 L 280,490" fill="none" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)" />
  <path d="M 155,300 L 155,270" fill="none" stroke="#3b82f6" stroke-width="2" stroke-dasharray="4,4" />
  <path d="M 155,410 L 155,390" fill="none" stroke="#3b82f6" stroke-width="2" />

  <!-- SECTION 2: ADMISSION DECISION (MIDDLE) -->
  <g transform="translate(360, 150)">
    <!-- Section Border Box -->
    <rect width="260" height="520" rx="12" fill="#0f172a" stroke="#1e293b" stroke-width="1.5" />
    <text x="20" y="35" font-family="'Inter', system-ui, sans-serif" font-size="15" font-weight="700" fill="#f1f5f9">2. Kueue Admission Controller</text>

    <!-- Capacity Check Box -->
    <g transform="translate(20, 60)">
      <rect width="220" height="110" rx="8" fill="#1e293b" stroke="#334155" stroke-width="1" />
      <text x="15" y="25" font-family="'Inter', system-ui, sans-serif" font-size="12" font-weight="700" fill="#cbd5e1">Quota Verification</text>
      <text x="15" y="48" font-family="'Inter', system-ui, sans-serif" font-size="11" fill="#94a3b8">Verifies ClusterQueue quota:</text>
      <text x="15" y="66" font-family="'Inter', system-ui, sans-serif" font-size="11" fill="#94a3b8">nominalQuota: 32 GPUs</text>
      <rect x="15" y="80" width="190" height="18" rx="4" fill="#020617" />
      <text x="22" y="93" font-family="'Inter', system-ui, sans-serif" font-size="10" font-weight="700" fill="#f1f5f9">Total GPUs in Cluster: 32</text>
    </g>

    <!-- Admission Decision Tree -->
    <g transform="translate(20, 190)">
      <polygon points="110,10 210,60 110,110 10,60" fill="url(#kueue-grad)" opacity="0.9" />
      <text x="110" y="55" font-family="'Inter', system-ui, sans-serif" font-size="11" font-weight="800" fill="#ffffff" text-anchor="middle">Can satisfy</text>
      <text x="110" y="70" font-family="'Inter', system-ui, sans-serif" font-size="11" font-weight="800" fill="#ffffff" text-anchor="middle">ENTIRE GANG?</text>
    </g>

    <!-- Standard K8s path -->
    <g transform="translate(20, 320)">
      <rect width="220" height="70" rx="8" fill="#020617" stroke="#f87171" stroke-width="1" />
      <text x="15" y="25" font-family="'Inter', system-ui, sans-serif" font-size="11" font-weight="700" fill="#f87171">Standard K8s Path (Bypassed)</text>
      <text x="15" y="45" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8">Allocates greedily pod-by-pod</text>
      <text x="15" y="57" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8">causing deadlock.</text>
    </g>

    <!-- Kueue Gang path -->
    <g transform="translate(20, 405)">
      <rect width="220" height="90" rx="8" fill="#020617" stroke="#34d399" stroke-width="1" />
      <text x="15" y="25" font-family="'Inter', system-ui, sans-serif" font-size="11" font-weight="700" fill="#34d399">Kueue Gang Path (Active)</text>
      <text x="15" y="45" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8">Allows only all-or-nothing.</text>
      <text x="15" y="57" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8">Admits Job A (32 GPUs).</text>
      <text x="15" y="69" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8">Suspends Job B in queue.</text>
    </g>
  </g>

  <!-- Connectors from intake to admission -->
  <path d="M 300,560 L 330,560 L 330,250 L 360,250" fill="none" stroke="#3b82f6" stroke-width="2" marker-end="url(#arrow-blue)" />
  <path d="M 470,170 L 470,190" fill="none" stroke="#64748b" stroke-width="1.5" />
  
  <!-- Decisions flow -->
  <path d="M 470,300 L 470,320" fill="none" stroke="#f87171" stroke-width="2" marker-end="url(#arrow)" />
  <path d="M 570,250 L 590,250 L 590,405" fill="none" stroke="#34d399" stroke-width="2" marker-end="url(#arrow)" />

  <!-- SECTION 3: CLUSTER STATE SCHEDULING (RIGHT) -->
  
  <!-- SCENARIO A: STANDARD SCHEDULER (DEADLOCK) - TOP RIGHT -->
  <g transform="translate(670, 150)">
    <rect width="480" height="245" rx="12" fill="#0f172a" stroke="#ef4444" stroke-width="1.5" />
    <text x="20" y="30" font-family="'Inter', system-ui, sans-serif" font-size="14" font-weight="700" fill="#f87171">Standard Scheduler: INTERLEAVED DEADLOCK</text>
    
    <!-- 4 Nodes -->
    <g transform="translate(20, 50)">
      <!-- Node 1 -->
      <g transform="translate(0, 0)">
        <rect width="100" height="110" rx="6" fill="#1e293b" stroke="#334155" />
        <text x="50" y="20" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8" text-anchor="middle">Node 1</text>
        <rect x="10" y="30" width="80" height="40" rx="4" fill="url(#job-a-grad)" />
        <text x="50" y="47" font-family="'Inter', system-ui, sans-serif" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">Pod A1</text>
        <text x="50" y="60" font-family="'Inter', system-ui, sans-serif" font-size="8" fill="#e2e8f0" text-anchor="middle">8 GPUs (100% Run)</text>
        <text x="50" y="90" font-family="'Inter', system-ui, sans-serif" font-size="9" fill="#94a3b8" text-anchor="middle">Rendezvous...</text>
      </g>
      
      <!-- Node 2 -->
      <g transform="translate(110, 0)">
        <rect width="100" height="110" rx="6" fill="#1e293b" stroke="#334155" />
        <text x="50" y="20" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8" text-anchor="middle">Node 2</text>
        <rect x="10" y="30" width="80" height="40" rx="4" fill="url(#job-b-grad)" />
        <text x="50" y="47" font-family="'Inter', system-ui, sans-serif" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">Pod B1</text>
        <text x="50" y="60" font-family="'Inter', system-ui, sans-serif" font-size="8" fill="#e2e8f0" text-anchor="middle">8 GPUs (100% Run)</text>
        <text x="50" y="90" font-family="'Inter', system-ui, sans-serif" font-size="9" fill="#94a3b8" text-anchor="middle">Rendezvous...</text>
      </g>

      <!-- Node 3 -->
      <g transform="translate(220, 0)">
        <rect width="100" height="110" rx="6" fill="#1e293b" stroke="#334155" />
        <text x="50" y="20" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8" text-anchor="middle">Node 3</text>
        <rect x="10" y="30" width="80" height="40" rx="4" fill="url(#job-a-grad)" />
        <text x="50" y="47" font-family="'Inter', system-ui, sans-serif" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">Pod A2</text>
        <text x="50" y="60" font-family="'Inter', system-ui, sans-serif" font-size="8" fill="#e2e8f0" text-anchor="middle">8 GPUs (100% Run)</text>
        <text x="50" y="90" font-family="'Inter', system-ui, sans-serif" font-size="9" fill="#94a3b8" text-anchor="middle">Rendezvous...</text>
      </g>

      <!-- Node 4 -->
      <g transform="translate(330, 0)">
        <rect width="100" height="110" rx="6" fill="#1e293b" stroke="#334155" />
        <text x="50" y="20" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8" text-anchor="middle">Node 4</text>
        <rect x="10" y="30" width="80" height="40" rx="4" fill="url(#job-b-grad)" />
        <text x="50" y="47" font-family="'Inter', system-ui, sans-serif" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">Pod B2</text>
        <text x="50" y="60" font-family="'Inter', system-ui, sans-serif" font-size="8" fill="#e2e8f0" text-anchor="middle">8 GPUs (100% Run)</text>
        <text x="50" y="90" font-family="'Inter', system-ui, sans-serif" font-size="9" fill="#94a3b8" text-anchor="middle">Rendezvous...</text>
      </g>
    </g>

    <!-- Deadlock Connection Overlay -->
    <path d="M 70,120 L 180,120 M 290,120 L 400,120" stroke="#ef4444" stroke-width="2.5" stroke-dasharray="3,3" />
    <circle cx="125" cy="120" r="12" fill="#ef4444" filter="url(#glow-red)" />
    <text x="125" y="123" font-family="'Inter', system-ui, sans-serif" font-size="10" font-weight="900" fill="#ffffff" text-anchor="middle">X</text>
    <circle cx="345" cy="120" r="12" fill="#ef4444" filter="url(#glow-red)" />
    <text x="345" y="123" font-family="'Inter', system-ui, sans-serif" font-size="10" font-weight="900" fill="#ffffff" text-anchor="middle">X</text>

    <!-- Cost Penalty Warning -->
    <rect x="20" y="180" width="440" height="45" rx="6" fill="#7f1d1d" opacity="0.6" />
    <text x="35" y="207" font-family="'Inter', system-ui, sans-serif" font-size="12" font-weight="700" fill="#fca5a5">DEADLOCK ACTIVE: 32 GPUs Idle &amp; Spinning at $117.44/hr cost</text>
  </g>

  <!-- SCENARIO B: KUEUE GANG SCHEDULER (SUCCESS) - BOTTOM RIGHT -->
  <g transform="translate(670, 425)">
    <rect width="480" height="245" rx="12" fill="#0f172a" stroke="#34d399" stroke-width="1.5" />
    <text x="20" y="30" font-family="'Inter', system-ui, sans-serif" font-size="14" font-weight="700" fill="#34d399">GKE Kueue Scheduler: GANG SUCCESS (ALL-OR-NOTHING)</text>

    <!-- 4 Nodes -->
    <g transform="translate(20, 50)">
      <!-- Node 1 -->
      <g transform="translate(0, 0)">
        <rect width="100" height="110" rx="6" fill="#1e293b" stroke="#334155" />
        <text x="50" y="20" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8" text-anchor="middle">Node 1</text>
        <rect x="10" y="30" width="80" height="40" rx="4" fill="url(#job-a-grad)" />
        <text x="50" y="47" font-family="'Inter', system-ui, sans-serif" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">Pod A1</text>
        <text x="50" y="60" font-family="'Inter', system-ui, sans-serif" font-size="8" fill="#e2e8f0" text-anchor="middle">8 GPUs (Active)</text>
        <text x="50" y="92" font-family="'Inter', system-ui, sans-serif" font-size="9" font-weight="700" fill="#34d399" text-anchor="middle">ACTIVE</text>
      </g>
      
      <!-- Node 2 -->
      <g transform="translate(110, 0)">
        <rect width="100" height="110" rx="6" fill="#1e293b" stroke="#334155" />
        <text x="50" y="20" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8" text-anchor="middle">Node 2</text>
        <rect x="10" y="30" width="80" height="40" rx="4" fill="url(#job-a-grad)" />
        <text x="50" y="47" font-family="'Inter', system-ui, sans-serif" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">Pod A2</text>
        <text x="50" y="60" font-family="'Inter', system-ui, sans-serif" font-size="8" fill="#e2e8f0" text-anchor="middle">8 GPUs (Active)</text>
        <text x="50" y="92" font-family="'Inter', system-ui, sans-serif" font-size="9" font-weight="700" fill="#34d399" text-anchor="middle">ACTIVE</text>
      </g>

      <!-- Node 3 -->
      <g transform="translate(220, 0)">
        <rect width="100" height="110" rx="6" fill="#1e293b" stroke="#334155" />
        <text x="50" y="20" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8" text-anchor="middle">Node 3</text>
        <rect x="10" y="30" width="80" height="40" rx="4" fill="url(#job-a-grad)" />
        <text x="50" y="47" font-family="'Inter', system-ui, sans-serif" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">Pod A3</text>
        <text x="50" y="60" font-family="'Inter', system-ui, sans-serif" font-size="8" fill="#e2e8f0" text-anchor="middle">8 GPUs (Active)</text>
        <text x="50" y="92" font-family="'Inter', system-ui, sans-serif" font-size="9" font-weight="700" fill="#34d399" text-anchor="middle">ACTIVE</text>
      </g>

      <!-- Node 4 -->
      <g transform="translate(330, 0)">
        <rect width="100" height="110" rx="6" fill="#1e293b" stroke="#334155" />
        <text x="50" y="20" font-family="'Inter', system-ui, sans-serif" font-size="10" fill="#94a3b8" text-anchor="middle">Node 4</text>
        <rect x="10" y="30" width="80" height="40" rx="4" fill="url(#job-a-grad)" />
        <text x="50" y="47" font-family="'Inter', system-ui, sans-serif" font-size="10" font-weight="700" fill="#ffffff" text-anchor="middle">Pod A4</text>
        <text x="50" y="60" font-family="'Inter', system-ui, sans-serif" font-size="8" fill="#e2e8f0" text-anchor="middle">8 GPUs (Active)</text>
        <text x="50" y="92" font-family="'Inter', system-ui, sans-serif" font-size="9" font-weight="700" fill="#34d399" text-anchor="middle">ACTIVE</text>
      </g>
    </g>

    <!-- Successful Rendezvous Link Overlay -->
    <path d="M 70,120 L 400,120" stroke="#10b981" stroke-width="2" />
    <circle cx="235" cy="120" r="10" fill="#10b981" filter="url(#glow-green)" />
    <path d="M 231,120 L 234,123 L 239,117" fill="none" stroke="#ffffff" stroke-width="2" />

    <!-- Cost Savings Confirmation -->
    <rect x="20" y="180" width="440" height="45" rx="6" fill="#064e3b" opacity="0.6" />
    <text x="35" y="207" font-family="'Inter', system-ui, sans-serif" font-size="12" font-weight="700" fill="#a7f3d0">JOB A RUNNING PRODUCTIVELY: $0.00 Wasted Deadlock Cost</text>
  </g>

  <!-- Connectors from admission to cluster states -->
  <path d="M 620,355 L 645,355 L 645,280 L 670,280" fill="none" stroke="#f87171" stroke-width="1.5" marker-end="url(#arrow)" />
  <path d="M 620,490 L 645,490 L 645,550 L 670,550" fill="none" stroke="#34d399" stroke-width="1.5" marker-end="url(#arrow)" />
</svg>
"""
    with open(filename, "w") as f:
        f.write(svg_content)
    logger.info(f"Architecture SVG written to '{filename}'.")

if __name__ == "__main__":
    target_dir = os.path.dirname(os.path.abspath(__file__))
    svg_path = os.path.join(target_dir, "architecture_diagram.svg")
    build_architecture_svg(svg_path)
    print("\n🎉 Architecture SVG generated successfully at:", svg_path)
