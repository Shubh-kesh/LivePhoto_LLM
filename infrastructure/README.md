# Infrastructure

Deployment/infrastructure planning area for later milestones. **No production manifests exist in
M1** (`ROADMAP.md` M16–M21).

| Directory | Purpose | Milestone |
|---|---|---|
| `docker/` | Production container images | M16 |
| `kubernetes/` | GKE manifests: deployments, HPA, PDB, ingress, TLS, network policies | M17 |
| `terraform/` | Infrastructure-as-code (GCP) | M18 |
| `monitoring/` | Prometheus/Grafana/OTel deployment and alerting | M14/M15 |

Each subdirectory contains a short README. Local development runs the frontend/backend directly —
no containers required.