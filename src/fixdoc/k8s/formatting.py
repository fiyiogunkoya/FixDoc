"""Output formatters for Kubernetes change impact results."""

import json
from typing import Optional

from .models import K8sImpactResult


_SEVERITY_COLORS = {
    "critical": "red",
    "high": "yellow",
    "medium": "blue",
    "low": "green",
}

_SEVERITY_EMOJI = {
    "critical": ":red_circle:",
    "high": ":warning:",
    "medium": ":large_blue_circle:",
    "low": ":white_check_mark:",
}


# ---------------------------------------------------------------------------
# Human format
# ---------------------------------------------------------------------------


def format_human(result: K8sImpactResult, verbose: bool = False) -> str:
    """Format result for terminal display."""
    lines = []

    # Header
    color = _SEVERITY_COLORS.get(result.severity, "white")
    lines.append("")
    lines.append(f"  K8s Change Impact: {result.change_name}")
    lines.append(f"  {result.from_version} -> {result.to_version}")
    lines.append(f"  Risk Score: {result.score}/100 ({result.severity.upper()})")
    lines.append("")
    lines.append(f"  {result.recommendation}")
    lines.append("")

    # Score explanation
    if result.score_explanation:
        lines.append("  Why this scored {:.0f}:".format(result.score))
        for exp in result.score_explanation:
            delta = exp.get("delta", 0)
            sign = "+" if delta >= 0 else ""
            lines.append(f"    {sign}{delta:.0f}  {exp.get('label', '')}")
        lines.append("")

    # Platform Risks
    if result.platform_risks:
        lines.append("  Platform Risks")
        lines.append("  " + "-" * 50)
        for risk in result.platform_risks:
            sev = risk.get("severity", "medium").upper()
            lines.append(f"  [{sev}] {risk.get('title', '')}")
            lines.append(f"    {risk.get('description', '')}")
            if risk.get("consequence"):
                lines.append(f"    What happens: {risk['consequence']}")
            lines.append("")

    # Cluster Exposure
    if result.cluster_exposure:
        lines.append("  Cluster Exposure")
        lines.append("  " + "-" * 50)
        shown = result.cluster_exposure if verbose else result.cluster_exposure[:10]
        for item in shown:
            wl = item.get("workload", item.get("ingress", {}))
            kind = wl.get("kind", "Ingress")
            name = wl.get("name", "unknown")
            ns = wl.get("namespace", "default")
            lines.append(f"  {kind}/{name} (ns: {ns})")
            if item.get("reason"):
                lines.append(f"    Why: {item['reason']}")
            if item.get("impact"):
                lines.append(f"    Impact: {item['impact']}")
            lines.append("")
        if not verbose and len(result.cluster_exposure) > 10:
            lines.append(f"  ... and {len(result.cluster_exposure) - 10} more (use -v to see all)")
            lines.append("")
    elif result.has_cluster_data:
        lines.append("  Cluster Exposure: None detected")
        lines.append("")

    # Rollout Risk
    if result.rollout_risk:
        rr = result.rollout_risk
        lines.append("  Rollout Risk")
        lines.append("  " + "-" * 50)
        lines.append(f"  Nodes: {rr.get('total_node_count', 0)}")
        lines.append(f"  Affected node pools: {rr.get('affected_node_pool_count', 0)}")
        lines.append(f"  Estimated pod restarts: {rr.get('total_pod_estimate', 0)}")
        if rr.get("daemonset_count"):
            lines.append(f"  DaemonSets (restart on every node): {rr['daemonset_count']}")
        if rr.get("statefulset_count"):
            lines.append(f"  StatefulSets (ordered restart): {rr['statefulset_count']}")
        lines.append("")

    # Pre-Migration Checklist
    if result.pre_checks:
        lines.append("  Pre-Migration Checklist")
        lines.append("  " + "-" * 50)
        for i, check in enumerate(result.pre_checks, 1):
            lines.append(f"  {i}. {check}")
        lines.append("")

    # Post-Migration Checklist
    if result.post_checks:
        lines.append("  Post-Migration Checklist")
        lines.append("  " + "-" * 50)
        for i, check in enumerate(result.post_checks, 1):
            lines.append(f"  {i}. {check}")
        lines.append("")

    # Relevant Team Knowledge
    if result.relevant_fixes:
        lines.append("  Relevant Team Knowledge")
        lines.append("  " + "-" * 50)
        for fix in result.relevant_fixes:
            issue = fix.get("issue", "")
            preview = issue[:80] + "..." if len(issue) > 80 else issue
            lines.append(f"  FIX-{fix.get('id', '?')}: {preview}")
            res = fix.get("resolution", "")
            res_preview = res[:80] + "..." if len(res) > 80 else res
            lines.append(f"    Resolution: {res_preview}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON format
# ---------------------------------------------------------------------------


def format_json(result: K8sImpactResult) -> str:
    """Format result as JSON."""
    return json.dumps(result.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# Markdown format
# ---------------------------------------------------------------------------


def format_markdown(result: K8sImpactResult) -> str:
    """Format result as GitHub-flavored markdown."""
    lines = []
    emoji = _SEVERITY_EMOJI.get(result.severity, "")

    lines.append(f"## {emoji} K8s Change Impact: {result.change_name}")
    lines.append("")
    lines.append(f"**{result.from_version}** -> **{result.to_version}**")
    lines.append(f"**Risk Score:** {result.score}/100 ({result.severity.upper()})")
    lines.append("")
    lines.append(f"> {result.recommendation}")
    lines.append("")

    # Score explanation
    if result.score_explanation:
        lines.append("### Score Breakdown")
        lines.append("")
        for exp in result.score_explanation[:3]:
            delta = exp.get("delta", 0)
            sign = "+" if delta >= 0 else ""
            lines.append(f"- {sign}{delta:.0f} {exp.get('label', '')}")
        lines.append("")

    # Platform Risks
    if result.platform_risks:
        lines.append("### Platform Risks")
        lines.append("")
        for risk in result.platform_risks:
            sev = risk.get("severity", "medium").upper()
            sev_emoji = _SEVERITY_EMOJI.get(risk.get("severity", "medium"), "")
            lines.append(f"#### {sev_emoji} {risk.get('title', '')} ({sev})")
            lines.append("")
            lines.append(risk.get("description", ""))
            if risk.get("consequence"):
                lines.append("")
                lines.append(f"**What happens:** {risk['consequence']}")
            lines.append("")

    # Cluster Exposure
    if result.cluster_exposure:
        lines.append("### Cluster Exposure")
        lines.append("")
        shown = result.cluster_exposure[:5]
        lines.append("| Workload | Namespace | Why | Impact |")
        lines.append("|----------|-----------|-----|--------|")
        for item in shown:
            wl = item.get("workload", item.get("ingress", {}))
            kind = wl.get("kind", "Ingress")
            name = wl.get("name", "unknown")
            ns = wl.get("namespace", "default")
            reason = item.get("reason", "")[:60]
            impact = item.get("impact", "")[:60]
            lines.append(f"| {kind}/{name} | {ns} | {reason} | {impact} |")
        if len(result.cluster_exposure) > 5:
            lines.append("")
            lines.append(f"<details><summary>+{len(result.cluster_exposure) - 5} more workloads</summary>")
            lines.append("")
            for item in result.cluster_exposure[5:]:
                wl = item.get("workload", item.get("ingress", {}))
                lines.append(f"- {wl.get('kind', 'Ingress')}/{wl.get('name', '?')} ({wl.get('namespace', 'default')})")
            lines.append("")
            lines.append("</details>")
        lines.append("")

    # Pre-Migration Checklist
    if result.pre_checks:
        lines.append("### Pre-Migration Checklist")
        lines.append("")
        for check in result.pre_checks[:5]:
            lines.append(f"- [ ] {check}")
        lines.append("")

    # Relevant Team Knowledge
    if result.relevant_fixes:
        lines.append("### Relevant Team Knowledge")
        lines.append("")
        for fix in result.relevant_fixes[:3]:
            issue = fix.get("issue", "")
            preview = issue[:80] + "..." if len(issue) > 80 else issue
            lines.append(f"- **FIX-{fix.get('id', '?')}**: {preview}")
        lines.append("")

    return "\n".join(lines)
