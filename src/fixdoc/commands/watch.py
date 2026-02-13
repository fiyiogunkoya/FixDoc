"""Watch command — wraps a command and captures errors on failure."""

import subprocess
import sys
import threading
from typing import Optional

import click

from ..storage import FixRepository
from .capture_handlers import handle_piped_input


@click.command()
@click.argument("command", nargs=-1, required=True)
@click.option("--tags", "-t", default=None, help="Tags to apply to captured fix.")
@click.option(
    "--no-prompt",
    is_flag=True,
    default=False,
    help="Skip confirmation and go straight to capture on failure.",
)
@click.pass_context
def watch(ctx, command, tags, no_prompt):
    """Run a command and capture errors on failure.

    Wraps any command, streams output normally, and on failure
    offers to capture the error through the fixdoc pipeline.

    Usage: fixdoc watch -- terraform apply
    """
    if not command:
        raise click.UsageError("No command provided. Usage: fixdoc watch -- <command>")

    base_path = ctx.obj["base_path"]
    config = ctx.obj["config"]
    repo = FixRepository(base_path)

    captured_output = []

    def _reader(pipe):
        """Read from pipe, display to terminal, and buffer output."""
        try:
            for line in iter(pipe.readline, b""):
                decoded = line.decode("utf-8", errors="replace")
                sys.stdout.write(decoded)
                sys.stdout.flush()
                captured_output.append(decoded)
        except ValueError:
            pass
        finally:
            pipe.close()

    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError:
        click.echo(f"Command not found: {command[0]}", err=True)
        sys.exit(127)

    reader_thread = threading.Thread(target=_reader, args=(proc.stdout,))
    reader_thread.daemon = True
    reader_thread.start()

    proc.wait()
    reader_thread.join(timeout=5)

    exit_code = proc.returncode

    if exit_code != 0:
        output_text = "".join(captured_output).strip()

        if output_text:
            if not no_prompt:
                click.echo()
                should_capture = click.confirm(
                    f"Command failed (exit code {exit_code}). Capture this error?",
                    default=True,
                )
                if not should_capture:
                    sys.exit(exit_code)

            fix = handle_piped_input(
                output_text, tags=tags, repo=repo, config=config
            )
            if fix:
                repo.save(fix)
                click.echo(f"\nFix saved: {fix.id[:8]}")

    sys.exit(exit_code)
