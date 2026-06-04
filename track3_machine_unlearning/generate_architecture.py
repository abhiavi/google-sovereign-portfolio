# generate_architecture.py - Generate GDC SISA Machine Unlearning Architecture Diagram
from diagrams import Diagram, Cluster, Edge
from diagrams.gcp.compute import GCE, GKE
from diagrams.gcp.database import Datastore
from diagrams.gcp.security import Iam, KeyManagementService
from diagrams.gcp.network import VPC

# Set dark theme attributes
graph_attr = {
    "bgcolor": "#0d1117",
    "fontsize": "16",
    "fontcolor": "#ffffff",
    "pad": "0.5",
    "nodesep": "0.5",
    "ranksep": "0.8",
}

node_attr = {
    "fontcolor": "#ffffff",
    "fontsize": "12",
}

with Diagram(
    "GDC SISA Machine Unlearning Architecture",
    show=False,
    filename="sisa_architecture",
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr
):
    # Entry point
    deletion_request = KeyManagementService("User Deletion Request\n(DPDP Sec 12)")

    with Cluster("Google Distributed Cloud (GDC) Air-Gapped Rack", graph_attr={"bgcolor": "#161b22", "fontcolor": "#ffffff", "fontsize": "14"}):
        sisa_gate = GKE("SISA Gateway")
        shard_mapper = Iam("Shard Mapper")
        
        # Aggregate ensemble
        inference_ensemble = GKE("Inference Ensemble\n(Aggregation / Voting)")

        # Create Sharded Training loops
        with Cluster("SISA Sharded Training (Isolated Compute Pools)", graph_attr={"bgcolor": "#21262d", "fontcolor": "#ffffff", "fontsize": "14"}):
            # Shard 1
            shard_1 = Datastore("Shard 1\n(Untouched)")
            model_1 = GCE("Model 1\n(Static weights)")
            shard_1 >> Edge(color="#8b949e", style="dashed") >> model_1
            
            # Shard 2
            shard_2 = Datastore("Shard 2\n(Untouched)")
            model_2 = GCE("Model 2\n(Static weights)")
            shard_2 >> Edge(color="#8b949e", style="dashed") >> model_2
            
            # Shard K (Affected)
            shard_k = Datastore("Shard K\n(Affected)")
            model_k = GCE("Model K\n(Retrained)")
            shard_k >> Edge(color="#ff3333", style="bold", label="Opt-Out Erasure") >> model_k
            
            # Shard 10
            shard_10 = Datastore("Shard 10\n(Untouched)")
            model_10 = GCE("Model 10\n(Static weights)")
            shard_10 >> Edge(color="#8b949e", style="dashed") >> model_10

    # Flow connections
    deletion_request >> Edge(color="#ff3333", style="bold", label="Trigger Erasure") >> sisa_gate
    sisa_gate >> shard_mapper
    
    # Mapper connects to shards
    shard_mapper >> Edge(color="#8b949e", style="dotted") >> shard_1
    shard_mapper >> Edge(color="#8b949e", style="dotted") >> shard_2
    shard_mapper >> Edge(color="#ff3333", style="bold", label="Retrain Shard K") >> shard_k
    shard_mapper >> Edge(color="#8b949e", style="dotted") >> shard_10
    
    # Models feed ensemble
    model_1 >> Edge(color="#8b949e", style="dashed") >> inference_ensemble
    model_2 >> Edge(color="#8b949e", style="dashed") >> inference_ensemble
    model_k >> Edge(color="#00ff00", style="bold", label="Update Weights") >> inference_ensemble
    model_10 >> Edge(color="#8b949e", style="dashed") >> inference_ensemble

    # External Client queries the system
    client = GCE("Inference Client")
    inference_ensemble >> Edge(color="#58a6ff", label="Aggregated Predictions") >> client
