#!/usr/bin/env python3
"""WP-108: Threat cluster validation.

Validates cluster coherence between threat intelligence data and the WP-107
framework clusters. Runs three queries and produces a plain-text report.

Usage:
  python scripts/validate_threat_clusters.py [--limit 15]

Flags:
  --limit N   Top-N threats by report coverage (default: 15)
"""
import argparse
import sys
from typing import Any

from neo4j.exceptions import AuthError, ServiceUnavailable

from memory_service.config import Settings, get_driver


# ── Graph queries ─────────────────────────────────────────────────────────


def _query_top_threats(session, limit: int) -> list[dict[str, Any]]:
    """Query 1: Top threats by report coverage.

    Returns threat_id, threat_text, report_count, severities, trends.
    """
    result = session.run(
        'MATCH (tr:ThreatReport)-[r:IDENTIFIES]->(t:Threat) '
        'WITH t, count(tr) AS report_count, '
        '     collect(DISTINCT r.severity) AS severities, '
        '     collect(DISTINCT r.trend) AS trends '
        'ORDER BY report_count DESC LIMIT $limit '
        'RETURN t.id AS threat_id, t.text AS threat_text, '
        '       report_count, severities, trends',
        limit=limit,
    )
    return [dict(r) for r in result]


def _query_attack_technique_coverage(session) -> list[dict[str, Any]]:
    """Query 2: ATT&CK technique coverage per threat.

    Returns threat_id, techniques (list), mitigating_controls (count),
    sample_clusters (first 3).
    """
    result = session.run(
        'MATCH (t:Threat)-[:MAPPED_TO_TECHNIQUE]->(tech:Framework) '
        'OPTIONAL MATCH (ctrl:Control)-[:MITIGATES]->(tech) '
        'RETURN t.id AS threat_id, '
        '       collect(DISTINCT tech.id) AS techniques, '
        '       count(DISTINCT ctrl) AS mitigating_controls, '
        '       collect(DISTINCT ctrl.embedding_cluster_id) AS sample_clusters'
    )
    return [dict(r) for r in result]


def _query_unmitigated_techniques(session) -> list[dict[str, Any]]:
    """Query 3: Unmitigated technique gaps.

    Returns threat_id and list of unmitigated technique IDs.
    """
    result = session.run(
        'MATCH (t:Threat)-[:MAPPED_TO_TECHNIQUE]->(tech:Framework) '
        'WHERE NOT (tech)<-[:MITIGATES]-(:Control) '
        'RETURN t.id AS threat_id, '
        '       collect(tech.id) AS unmitigated_techniques'
    )
    return [dict(r) for r in result]


def _count_nodes(session, label: str) -> int:
    """Count nodes with a given label."""
    result = session.run(f'MATCH (n:{label}) RETURN count(n) AS cnt')
    rec = result.single()
    return rec['cnt'] if rec else 0


def _count_edges(session, rel_type: str) -> int:
    """Count edges with a given type."""
    result = session.run(f'MATCH ()-[r:{rel_type}]->() RETURN count(r) AS cnt')
    rec = result.single()
    return rec['cnt'] if rec else 0


def _count_threats_with_controls(session) -> tuple[int, int]:
    """Count threats with at least one mitigating control, and without.

    Returns (with_controls, without_controls).
    """
    result = session.run(
        'MATCH (t:Threat)-[:MAPPED_TO_TECHNIQUE]->(tech:Framework) '
        'OPTIONAL MATCH (ctrl:Control)-[:MITIGATES]->(tech) '
        'WITH t, count(DISTINCT ctrl) AS ctrl_count '
        'RETURN sum(CASE WHEN ctrl_count > 0 THEN 1 ELSE 0 END) AS with_controls, '
        '       sum(CASE WHEN ctrl_count = 0 THEN 1 ELSE 0 END) AS without_controls'
    )
    rec = result.single()
    if rec:
        return (rec.get('with_controls', 0) or 0, rec.get('without_controls', 0) or 0)
    return (0, 0)


# ── Report generation ─────────────────────────────────────────────────────


def _truncate_text(text: str | None, max_len: int = 80) -> str:
    """Truncate text to max_len characters, adding ellipsis if needed."""
    if not text:
        return '(no text)'
    if len(text) > max_len:
        return text[:max_len - 3] + '...'
    return text


def _format_list(items: list | None, max_items: int = 5) -> str:
    """Format a list as a compact string, truncating if needed."""
    if not items:
        return '(none)'
    items = [str(x) for x in items]
    if len(items) > max_items:
        return ', '.join(items[:max_items]) + f', +{len(items) - max_items} more'
    return ', '.join(items)


def _generate_report(
    top_threats: list[dict[str, Any]],
    technique_coverage: list[dict[str, Any]],
    unmitigated_gaps: list[dict[str, Any]],
    summary: dict[str, int],
) -> str:
    """Generate plain-text validation report."""
    lines = ['', '=== WP-108 Threat Cluster Validation Report ===', '']

    # ── Top threats by report coverage ────────────────────────────────────
    lines.append('--- Top Threats by Report Coverage ---')
    if top_threats:
        for row in top_threats:
            threat_id = row.get('threat_id', '(unknown)')
            threat_text = _truncate_text(row.get('threat_text'))
            report_count = row.get('report_count', 0)
            severities = _format_list(row.get('severities'))
            trends = _format_list(row.get('trends'))
            lines.append(
                f'{threat_id} | {report_count:3} reports | '
                f'severities={severities} | trends={trends}'
            )
            lines.append(f'  Text: {threat_text}')
    else:
        lines.append('  (no threats found)')
    lines.append('')

    # ── ATT&CK technique coverage ─────────────────────────────────────────
    lines.append('--- ATT&CK Technique Coverage ---')
    if technique_coverage:
        for row in technique_coverage:
            threat_id = row.get('threat_id', '(unknown)')
            technique_count = len(row.get('techniques', []))
            mitigating_controls = row.get('mitigating_controls', 0)
            sample_clusters = (row.get('sample_clusters') or [])[:3]
            clusters_str = _format_list(sample_clusters, max_items=3)
            lines.append(
                f'{threat_id} | {technique_count} techniques | '
                f'{mitigating_controls} mitigating controls | '
                f'sample_clusters={clusters_str}'
            )
    else:
        lines.append('  (no threat-technique mappings found)')
    lines.append('')

    # ── Unmitigated technique gaps ────────────────────────────────────────
    lines.append('--- Unmitigated Technique Gaps ---')
    if unmitigated_gaps:
        for row in unmitigated_gaps:
            threat_id = row.get('threat_id', '(unknown)')
            unmitigated_techs = row.get('unmitigated_techniques', [])
            tech_str = _format_list(unmitigated_techs, max_items=10)
            lines.append(f'{threat_id} | {len(unmitigated_techs)} unmitigated | {tech_str}')
    else:
        lines.append('  (no unmitigated techniques found)')
    lines.append('')

    # ── Summary ───────────────────────────────────────────────────────────
    lines.append('--- Summary ---')
    for key in sorted(summary.keys()):
        lines.append(f'{key}: {summary[key]}')
    lines.append('')

    return '\n'.join(lines)


# ── main ──────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='WP-108: Threat cluster validation')
    parser.add_argument(
        '--limit', type=int, default=15,
        help='Top-N threats by report coverage (default: 15)',
    )
    args = parser.parse_args(argv)

    if args.limit < 1:
        parser.error('--limit must be >= 1')

    settings = Settings()
    driver = get_driver(settings)

    try:
        print('Validating threat clusters...', flush=True)

        with driver.session() as s:
            print('  Running Query 1: Top threats by report coverage...', flush=True)
            top_threats = _query_top_threats(s, limit=args.limit)
            print(f'    {len(top_threats)} threats found.')

            print('  Running Query 2: ATT&CK technique coverage...', flush=True)
            technique_coverage = _query_attack_technique_coverage(s)
            print(f'    {len(technique_coverage)} threat-technique mappings found.')

            print('  Running Query 3: Unmitigated technique gaps...', flush=True)
            unmitigated_gaps = _query_unmitigated_techniques(s)
            print(f'    {len(unmitigated_gaps)} threats with unmitigated techniques found.')

            print('  Computing summary counts...', flush=True)
            threat_report_count = _count_nodes(s, 'ThreatReport')
            threat_count = _count_nodes(s, 'Threat')
            identifies_count = _count_edges(s, 'IDENTIFIES')
            mapped_to_technique_count = _count_edges(s, 'MAPPED_TO_TECHNIQUE')
            with_controls, without_controls = _count_threats_with_controls(s)

        summary = {
            'Total ThreatReport nodes': threat_report_count,
            'Total Threat nodes': threat_count,
            'Total IDENTIFIES edges': identifies_count,
            'Total MAPPED_TO_TECHNIQUE edges': mapped_to_technique_count,
            'Threats with at least one mitigating control': with_controls,
            'Threats with zero mitigating controls': without_controls,
        }

        report = _generate_report(top_threats, technique_coverage, unmitigated_gaps, summary)
        print(report)

    except (ServiceUnavailable, AuthError) as exc:
        print(
            f'ERROR: Cannot connect to Memgraph at '
            f'bolt://{settings.memgraph_host}:{settings.memgraph_port} — {exc}',
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        driver.close()


if __name__ == '__main__':
    main()
