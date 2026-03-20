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
    lines.append("")
    lines.append(f"  K8s Change Impact: {result.change_name}")
    lines.append(f"  {result.from_version} -> {result.to_version}")
    lines.append(f"  Risk Score: {result.score}/100 ({result.severity.upper()})")
    lines.append("")
    lines.append(f"  {result.recommendation}")
    lines.append("")

    # Score explanation (verbose only)
    if verbose and result.score_explanation:
        lines.append("  Why this scored {:.0f}:".format(result.score))
        for exp in result.score_explanation:
            delta = exp.get("delta", 0)
            sign = "+" if delta >= 0 else ""
            lines.append(f"    {sign}{delta:.0f}  {exp.get('label', '')}")
        lines.append("")

    # Affected Resources (exposure-first — only when cluster data present)
    if result.cluster_exposure:
        high_med = [e for e in result.cluster_exposure if e.get("confidence", "high") != "low"]
        low_items = [e for e in result.cluster_exposure if e.get("confidence", "high") == "low"]
        shown_items = high_med if not verbose else result.cluster_exposure

        if shown_items:
            lines.append("  Affected Resources")
            lines.append("  " + "-" * 50)
            shown = shown_items if verbose else shown_items[:10]
            for item in shown:
                wl = item.get("workload", item.get("ingress", {}))
                kind = wl.get("kind", "Ingress")
                name = wl.get("name", "unknown")
                ns = wl.get("namespace", "default")
                conf = item.get("confidence", "high")
                conf_tag = " [low]" if conf == "low" else ""
                match_count = item.get("match_count", 1)

                count_label = f"  {match_count} issues" if match_count > 1 else ""
                lines.append(f"  {kind}/{name} (ns: {ns}){conf_tag}{count_label}")

                if match_count > 1 and item.get("all_matches"):
                    for m in item["all_matches"]:
                        impact_text = m.get("impact", "") or m.get("reason", "")
                        if impact_text:
                            lines.append(f"    - {impact_text}")
                else:
                    if item.get("impact"):
                        lines.append(f"    Why: {item.get('reason', '')}")
                        lines.append(f"    Impact: {item['impact']}")
                    elif item.get("reason"):
                        lines.append(f"    Why: {item['reason']}")
                lines.append("")
            if not verbose and len(shown_items) > 10:
                lines.append(f"  ... and {len(shown_items) - 10} more (use -v to see all)")
                lines.append("")
        if low_items and not verbose:
            lines.append(f"  {len(low_items)} low-confidence matches hidden (use -v to see all)")
            lines.append("")
    elif result.has_cluster_data:
        lines.append("  Affected Resources: None detected")
        lines.append("")

    # Rollout Risk
    if result.rollout_risk:
        rr = result.rollout_risk
        lines.append("  Rollout Risk")
        lines.append("  " + "-" * 50)
        if rr.get("type") == "routing":
            lines.append(f"  Ingress resources to migrate: {rr.get('ingress_count', 0)}")
            lines.append(f"  Affected namespaces: {rr.get('affected_namespaces', 0)}")
            if rr.get("has_tls"):
                lines.append("  TLS configuration present: yes — verify cert handling")
            lines.append(f"  Backends behind ingress: ~{rr.get('total_pod_estimate', 0)} pods")
        else:
            lines.append(f"  Nodes: {rr.get('total_node_count', 0)}")
            lines.append(f"  Affected node pools: {rr.get('affected_node_pool_count', 0)}")
            lines.append(f"  Estimated pod restarts: {rr.get('total_pod_estimate', 0)}")
            if rr.get("daemonset_count"):
                lines.append(f"  DaemonSets (restart on every node): {rr['daemonset_count']}")
            if rr.get("statefulset_count"):
                lines.append(f"  StatefulSets (ordered restart): {rr['statefulset_count']}")
        lines.append("")

    # Action Items (merged pre + post checks)
    if result.pre_checks or result.post_checks:
        if verbose:
            # Verbose: show separate sections with all checks
            if result.pre_checks:
                lines.append("  Pre-Migration Checklist")
                lines.append("  " + "-" * 50)
                for i, check in enumerate(result.pre_checks, 1):
                    lines.append(f"  {i}. {check}")
                lines.append("")
            if result.post_checks:
                lines.append("  Post-Migration Checklist")
                lines.append("  " + "-" * 50)
                for i, check in enumerate(result.post_checks, 1):
                    lines.append(f"  {i}. {check}")
                lines.append("")
        else:
            # Default: merged top items
            merged = list(result.pre_checks[:3]) + list(result.post_checks[:2])
            if merged:
                lines.append("  Action Items")
                lines.append("  " + "-" * 50)
                for i, check in enumerate(merged, 1):
                    lines.append(f"  {i}. {check}")
                lines.append("")

    # Platform Context (condensed when cluster data present)
    if result.platform_risks:
        count = len(result.platform_risks)
        if result.has_cluster_data and not verbose:
            # Condensed: one line per risk
            lines.append(f"  Platform Context ({count} known breaking changes)")
            lines.append("  " + "-" * 50)
            for risk in result.platform_risks:
                sev = risk.get("severity", "medium").upper()
                lines.append(f"  {sev:4s}  {risk.get('title', '')}")
            lines.append("")
        else:
            # Full descriptions (no cluster data or verbose)
            lines.append("  Platform Context")
            lines.append("  " + "-" * 50)
            for risk in result.platform_risks:
                sev = risk.get("severity", "medium").upper()
                lines.append(f"  [{sev}] {risk.get('title', '')}")
                lines.append(f"    {risk.get('description', '')}")
                if risk.get("consequence"):
                    lines.append(f"    What happens: {risk['consequence']}")
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

    # Affected Resources (moved up, replaces Cluster Exposure)
    if result.cluster_exposure:
        visible = [e for e in result.cluster_exposure if e.get("confidence", "high") != "low"]
        low_count = len(result.cluster_exposure) - len(visible)

        if visible:
            lines.append("### Affected Resources")
            lines.append("")
            shown = visible[:5]
            lines.append("| Workload | Namespace | Issues | Impact |")
            lines.append("|----------|-----------|--------|--------|")
            for item in shown:
                wl = item.get("workload", item.get("ingress", {}))
                kind = wl.get("kind", "Ingress")
                name = wl.get("name", "unknown")
                ns = wl.get("namespace", "default")
                match_count = item.get("match_count", 1)
                impact = item.get("impact", "") or item.get("reason", "")
                impact = impact[:60]
                lines.append(f"| {kind}/{name} | {ns} | {match_count} | {impact} |")
            if len(visible) > 5:
                lines.append("")
                lines.append(f"<details><summary>+{len(visible) - 5} more workloads</summary>")
                lines.append("")
                for item in visible[5:]:
                    wl = item.get("workload", item.get("ingress", {}))
                    lines.append(f"- {wl.get('kind', 'Ingress')}/{wl.get('name', '?')} ({wl.get('namespace', 'default')})")
                lines.append("")
                lines.append("</details>")
            if low_count:
                lines.append("")
                lines.append(f"*{low_count} low-confidence matches omitted.*")
            lines.append("")

    # Rollout Risk
    if result.rollout_risk:
        rr = result.rollout_risk
        lines.append("### Rollout Risk")
        lines.append("")
        if rr.get("type") == "routing":
            lines.append(f"- **Ingress resources to migrate:** {rr.get('ingress_count', 0)}")
            lines.append(f"- **Affected namespaces:** {rr.get('affected_namespaces', 0)}")
            if rr.get("has_tls"):
                lines.append("- **TLS configuration present:** yes — verify cert handling")
            lines.append(f"- **Backends behind ingress:** ~{rr.get('total_pod_estimate', 0)} pods")
        else:
            lines.append(f"- **Nodes:** {rr.get('total_node_count', 0)}")
            lines.append(f"- **Affected node pools:** {rr.get('affected_node_pool_count', 0)}")
            lines.append(f"- **Estimated pod restarts:** {rr.get('total_pod_estimate', 0)}")
            if rr.get("daemonset_count"):
                lines.append(f"- **DaemonSets (restart on every node):** {rr['daemonset_count']}")
            if rr.get("statefulset_count"):
                lines.append(f"- **StatefulSets (ordered restart):** {rr['statefulset_count']}")
        lines.append("")

    # Action Items (merged pre + post)
    if result.pre_checks or result.post_checks:
        merged = list(result.pre_checks[:3]) + list(result.post_checks[:2])
        if merged:
            lines.append("### Action Items")
            lines.append("")
            for check in merged:
                lines.append(f"- [ ] {check}")
            lines.append("")

    # Platform Context (collapsed details when cluster data present)
    if result.platform_risks:
        if result.has_cluster_data:
            count = len(result.platform_risks)
            lines.append(f"<details><summary><strong>Platform Context</strong> ({count} known breaking changes)</summary>")
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
            lines.append("</details>")
            lines.append("")
        else:
            lines.append("### Platform Context")
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

    # Score Breakdown
    if result.score_explanation:
        lines.append("### Score Breakdown")
        lines.append("")
        for exp in result.score_explanation[:3]:
            delta = exp.get("delta", 0)
            sign = "+" if delta >= 0 else ""
            lines.append(f"- {sign}{delta:.0f} {exp.get('label', '')}")
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
