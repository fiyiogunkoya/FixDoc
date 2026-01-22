"""CLI assembly for fixdoc."""

import click

from .commands import capture, search, show, analyze, list_fixes, stats, delete, edit


def create_cli() -> click.Group:

    @click.group()
    @click.version_option(version="0.1.0", prog_name="fixdoc")
    def cli():
        pass

    # group commands
    cli.add_command(capture)
    cli.add_command(search)
    cli.add_command(show)
    cli.add_command(analyze)
    cli.add_command(list_fixes)
    cli.add_command(stats)
    cli.add_command(delete)
    cli.add_command(edit)

    return cli
