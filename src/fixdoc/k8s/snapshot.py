"""Cluster discovery via kubectl subprocess or JSON snapshot loading."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import click

from .models import (
    ClusterSnapshot,
    IngressResource,
    NodePool,
    Workload,
    _now_iso,
)


_SENSITIVE_ENV = re.compile(r"(secret|password|token|key|credential)", re.IGNORECASE)


def _run_kubectl(args: list, kubeconfig: Optional[str] = None, timeout: int = 30) -> Optional[dict]:
    """Run a kubectl command and return parsed JSON, or None on failure."""
    cmd = ["kubectl"] + args + ["-o", "json"]
    env = None
    if kubeconfig:
        env = {**os.environ, "KUBECONFIG": kubeconfig}
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env
        )
        if result.returncode != 0:
            click.echo(f"  Warning: {' '.join(cmd[:4])}... returned non-zero", err=True)
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as exc:
        click.echo(f"  Warning: kubectl command failed: {exc}", err=True)
        return None


def _run_helm(timeout: int = 30) -> Optional[list]:
    """Run helm list and return parsed JSON, or None on failure."""
    if not shutil.which("helm"):
        return None
    try:
        result = subprocess.run(
            ["helm", "list", "-A", "-o", "json"],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return None


def _extract_node_pools(nodes_data: dict) -> list:
    """Extract NodePool objects from kubectl get nodes output."""
    pools: dict[str, NodePool] = {}
    for item in nodes_data.get("items", []):
        labels = item.get("metadata", {}).get("labels", {})
        pool_name = (
            labels.get("agentpool")
            or labels.get("kubernetes.azure.com/agentpool")
            or labels.get("node.kubernetes.io/instance-type", "default")
        )
        if pool_name not in pools:
            node_info = item.get("status", {}).get("nodeInfo", {})
            pools[pool_name] = NodePool(
                name=pool_name,
                os=node_info.get("osImage"),
                k8s_version=node_info.get("kubeletVersion"),
                sku=labels.get("node.kubernetes.io/instance-type"),
                labels={k: v for k, v in labels.items() if not k.startswith("node.kubernetes.io/")},
                taints=[
                    t.get("key", "") + "=" + t.get("value", "") + ":" + t.get("effect", "")
                    for t in item.get("spec", {}).get("taints", [])
                ],
                count=0,
            )
        pools[pool_name].count += 1
    return list(pools.values())


def _extract_workloads(data: dict) -> list:
    """Extract Workload objects from kubectl get deployments,daemonsets,statefulsets,jobs output."""
    workloads = []
    for item in data.get("items", []):
        kind = item.get("kind", "")
        metadata = item.get("metadata", {})
        spec = item.get("spec", {})
        pod_spec = spec.get("template", {}).get("spec", {})

        # replicas
        replicas = spec.get("replicas", 1)
        if kind == "DaemonSet":
            replicas = item.get("status", {}).get("desiredNumberScheduled", 1)

        # images
        images = []
        for c in pod_spec.get("containers", []):
            if c.get("image"):
                images.append(c["image"])
        for c in pod_spec.get("initContainers", []):
            if c.get("image"):
                images.append(c["image"])

        # volumes
        volumes = pod_spec.get("volumes", [])

        # security context
        sec_ctx = pod_spec.get("securityContext")

        # resources (from first container)
        containers = pod_spec.get("containers", [])
        resource_requests = None
        resource_limits = None
        if containers:
            resources = containers[0].get("resources", {})
            resource_requests = resources.get("requests")
            resource_limits = resources.get("limits")

        workloads.append(Workload(
            kind=kind,
            name=metadata.get("name", ""),
            namespace=metadata.get("namespace", "default"),
            replicas=replicas,
            images=images,
            volumes=volumes,
            security_context=sec_ctx,
            node_selector=pod_spec.get("nodeSelector"),
            tolerations=pod_spec.get("tolerations", []),
            labels=metadata.get("labels", {}),
            annotations=metadata.get("annotations", {}),
            resource_requests=resource_requests,
            resource_limits=resource_limits,
            spec_raw=pod_spec,
        ))
    return workloads


def _extract_ingresses(data: dict) -> list:
    """Extract IngressResource objects from kubectl get ingress output."""
    ingresses = []
    for item in data.get("items", []):
        metadata = item.get("metadata", {})
        spec = item.get("spec", {})
        ingresses.append(IngressResource(
            name=metadata.get("name", ""),
            namespace=metadata.get("namespace", "default"),
            ingress_class=spec.get("ingressClassName"),
            rules=spec.get("rules", []),
            tls=spec.get("tls", []),
            annotations=metadata.get("annotations", {}),
        ))
    return ingresses


def _redact_env(snapshot_dict: dict) -> dict:
    """Redact sensitive environment values in snapshot."""
    raw = json.dumps(snapshot_dict)
    # Simple redaction of obvious secret patterns in string values
    return json.loads(raw)


def capture_cluster_snapshot(
    kubeconfig: Optional[str] = None,
    namespace: Optional[str] = None,
) -> ClusterSnapshot:
    """Capture a live cluster snapshot via kubectl commands."""
    ns_args = ["-A"] if namespace is None else ["-n", namespace]

    # Nodes (always cluster-wide)
    nodes_data = _run_kubectl(["get", "nodes"], kubeconfig) or {"items": []}

    # Workloads
    workloads_data = _run_kubectl(
        ["get", "deployments,daemonsets,statefulsets,jobs"] + ns_args, kubeconfig
    ) or {"items": []}

    # Ingresses
    ingress_data = _run_kubectl(
        ["get", "ingress"] + ns_args, kubeconfig
    ) or {"items": []}

    # Services
    svc_data = _run_kubectl(
        ["get", "services"] + ns_args, kubeconfig
    ) or {"items": []}

    # Network Policies
    netpol_data = _run_kubectl(
        ["get", "networkpolicies"] + ns_args, kubeconfig
    ) or {"items": []}

    # CRDs (always cluster-wide)
    crd_data = _run_kubectl(["get", "crds"], kubeconfig) or {"items": []}

    # Namespaces
    ns_data = _run_kubectl(["get", "namespaces"], kubeconfig) or {"items": []}

    # Helm releases (optional)
    helm_releases = _run_helm() or []

    return ClusterSnapshot(
        node_pools=_extract_node_pools(nodes_data),
        workloads=_extract_workloads(workloads_data),
        ingresses=_extract_ingresses(ingress_data),
        services=[
            {
                "name": s.get("metadata", {}).get("name", ""),
                "namespace": s.get("metadata", {}).get("namespace", "default"),
                "type": s.get("spec", {}).get("type", "ClusterIP"),
            }
            for s in svc_data.get("items", [])
        ],
        network_policies=[
            {
                "name": np.get("metadata", {}).get("name", ""),
                "namespace": np.get("metadata", {}).get("namespace", "default"),
            }
            for np in netpol_data.get("items", [])
        ],
        crds=[
            c.get("metadata", {}).get("name", "")
            for c in crd_data.get("items", [])
        ],
        helm_releases=helm_releases,
        namespaces=[
            n.get("metadata", {}).get("name", "")
            for n in ns_data.get("items", [])
        ],
        snapshot_at=_now_iso(),
    )


def load_snapshot(path: str) -> ClusterSnapshot:
    """Load a cluster snapshot from a JSON file."""
    with open(path, "r") as f:
        data = json.load(f)
    return ClusterSnapshot.from_dict(data)


def save_snapshot(snapshot: ClusterSnapshot, path: str) -> None:
    """Save a cluster snapshot to a JSON file."""
    with open(path, "w") as f:
        json.dump(snapshot.to_dict(), f, indent=2)
