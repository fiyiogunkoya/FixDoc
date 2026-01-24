"""Analyze command for fixdoc CLI."""

from pathlib import Path

import click

from ..analyzer import TerraformAnalyzer


@click.command()
@click.argument("plan_file", type=click.Path(exists=True))
def analyze(plan_file: str):
    """
    Analyze a terraform plan for issues.

    Usage:
        terraform plan -out=plan.tfplan
        terraform show -json plan.tfplan > plan.json
        fixdoc analyze plan.json
    """
    analyzer = TerraformAnalyzer()
    plan_path = Path(plan_file)

    try:
        output = analyzer.analyze_and_format(plan_path)
        click.echo(output)
    except Exception as e:
        click.echo(f"Error analyzing plan: {e}", err=True)
        raise SystemExit(1)
