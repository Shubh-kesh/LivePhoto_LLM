# ADR-009 — Kubernetes/GKE Production Target

- **Status:** Accepted (production direction)
- **Date:** M0

## Context
Production deployment targets GCP with a Kubernetes cluster, autoscaling (HPA), regional
deployment, and independent scaling of inference from the API. No manifests are created in M0.

## Decision
Production runs on **GCP / GKE (Kubernetes)** with:

- Regional cluster; multiple API and frontend replicas; **HPA** required.
- PodDisruptionBudgets; readiness/liveness probes; resource requests/limits.
- Secrets management (secret manager / k8s secrets per policy); network policies; TLS + ingress;
  artifact registry; centralized logging; Prometheus + OpenTelemetry.
- Inference workers independently scalable from the API (HPA signals beyond CPU where appropriate:
  request rate, inference queue depth, inference latency, custom metrics).
- Infrastructure-as-code (Terraform) is the preferred future option (M18); not created in M0.

## Alternatives considered
- **Single VM / VMSS** — rejected: weaker autoscaling, harder to keep inference independent.
- **Other clouds** — not in scope; GCP is the baseline per the product brief.

## Consequences
- Deployment complexity is deferred to M16/M17/M18; M0 documents the direction and non-functional
  requirements only.
- Availability/RPO/RTO specifics remain open stakeholder questions pending bank infrastructure
  input.

## Future review triggers
- Re-open if the bank mandates a different cloud/ingress/WAF standard (questions #6/#7) or if
  regional/residency requirements change.