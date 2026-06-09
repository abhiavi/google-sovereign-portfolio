import yaml
import re

class VPCPermeterPolicyEngine:
    def __init__(self, policy_file_path):
        with open(policy_file_path, 'r') as f:
            self.policy_data = yaml.safe_load(f)
        
        self.perimeter = self.policy_data.get('service_perimeter', {})
        self.name = self.perimeter.get('name')
        self.resources = set(self.perimeter.get('resources', []))
        self.restricted_services = set(self.perimeter.get('restricted_services', []))
        self.allowed_access_levels = set(self.perimeter.get('access_levels', []))
        self.ingress_rules = self.perimeter.get('ingress_policies', [])
        self.egress_rules = self.perimeter.get('egress_policies', [])

    def evaluate(self, request):
        """
        Evaluates a request context against the service perimeter definition.
        
        Request context dict structure:
        {
            'identity': str,        # e.g., 'serviceAccount:ai-agent-router@...'
            'source_ip': str,       # e.g., '192.168.1.5' or '8.8.8.8'
            'access_levels': list,  # e.g., ['accessPolicies/.../al_secure_operator_network']
            'service': str,         # e.g., 'storage.googleapis.com'
            'method': str,          # e.g., 'google.cloud.storage.v1.Objects.Get'
            'source_project': str,  # e.g., 'projects/my_project' (caller context)
            'target_project': str   # e.g., 'projects/external_shared_analytics' (resource context)
        }
        """
        service = request.get('service')
        target_project = request.get('target_project')
        source_project = request.get('source_project')
        identity = request.get('identity')
        request_access_levels = set(request.get('access_levels', []))
        method = request.get('method')
        
        # 1. If the targeted service is not restricted by this perimeter, it's outside VPC-SC scope
        if service not in self.restricted_services:
            return {
                'decision': 'ALLOW',
                'reason': f"Service '{service}' is not protected by the perimeter."
            }

        # Determine direction:
        # Ingress: Caller is OUTSIDE, resource is INSIDE
        # Egress: Caller is INSIDE, resource is OUTSIDE
        # Intra-Perimeter: Caller is INSIDE, resource is INSIDE

        caller_inside = source_project in self.resources
        target_inside = target_project in self.resources

        # Scenario A: Intra-perimeter access
        if caller_inside and target_inside:
            # Inside to inside is always allowed by default in a service perimeter
            return {
                'decision': 'ALLOW',
                'reason': "Intra-perimeter call (both source and target are inside the boundary)."
            }

        # Scenario B: Ingress Attempt (Outside calling Inside)
        if not caller_inside and target_inside:
            # Verify Ingress Rules
            for rule in self.ingress_rules:
                ingress_from = rule.get('ingress_from', {})
                ingress_to = rule.get('ingress_to', {})
                
                # Check Identities
                allowed_identities = ingress_from.get('identities', [])
                if '*' not in allowed_identities and identity not in allowed_identities:
                    continue
                
                # Check Sources (Access Levels)
                source_allowed = False
                for src in ingress_from.get('sources', []):
                    al = src.get('access_level')
                    if al and al in request_access_levels:
                        source_allowed = True
                        break
                if not source_allowed:
                    continue
                    
                # Check Operations (Services & Methods)
                for op in ingress_to.get('operations', []):
                    if op.get('service_name') == service:
                        method_selectors = [m.get('method') for m in op.get('method_selectors', [])]
                        if '*' in method_selectors or method in method_selectors:
                            # Check target resource
                            if target_project in ingress_to.get('resources', []):
                                return {
                                    'decision': 'ALLOW',
                                    'reason': "Authorized Ingress policy match."
                                }
            
            return {
                'decision': 'DENIED',
                'code': 'VPC_SC_INGRESS_VIOLATION',
                'reason': f"Ingress denied: No matching ingress rule allows identity '{identity}' "
                          f"accessing '{service}/{method}' from source access levels."
            }

        # Scenario C: Egress Attempt (Inside calling Outside)
        if caller_inside and not target_inside:
            # Verify Egress Rules
            for rule in self.egress_rules:
                egress_from = rule.get('egress_from', {})
                egress_to = rule.get('egress_to', {})
                
                # Check Identities
                allowed_identities = egress_from.get('identities', [])
                if '*' not in allowed_identities and identity not in allowed_identities:
                    continue
                    
                # Check Operations
                for op in egress_to.get('operations', []):
                    if op.get('service_name') == service:
                        method_selectors = [m.get('method') for m in op.get('method_selectors', [])]
                        if '*' in method_selectors or method in method_selectors:
                            # Check target resource
                            if target_project in egress_to.get('resources', []):
                                return {
                                    'decision': 'ALLOW',
                                    'reason': "Authorized Egress policy match."
                                }
            
            return {
                'decision': 'DENIED',
                'code': 'VPC_SC_EGRESS_VIOLATION',
                'reason': f"Egress denied: Exfiltration blocked. Accessing external resource "
                          f"'{target_project}' via service '{service}/{method}' is not permitted by egress policies."
            }

        # Scenario D: Outside calling Outside (not related to this perimeter resource protection)
        return {
            'decision': 'ALLOW',
            'reason': "Both source and target are outside this perimeter's scope."
        }
