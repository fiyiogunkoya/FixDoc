"""Watch command — wraps a command and captures errors on failure."""

import subprocess
import sys
import threading
from typing import Optional

import click

from ..parsers import detect_and_parse, detect_error_source, ErrorSource
from ..parsers.base import ParsedError
from ..pending import PendingEntry, PendingStore, pending_entry_from_parsed_error
from ..storage import FixRepository
from .capture_handlers import (
    capture_single_error,
    capture_single_k8s_error,
    get_similar_fixes_for_error,
    handle_piped_input,
)


def _display_summary_table(errors: list) -> None:
    """Print a numbered summary table of parsed errors."""
    click.echo(f"\nFound {len(errors)} error(s)\n")

    # Header
    click.echo(f" {'#':>2}  {'Resource':<40}  {'Code/Type'}")
    for i, err in enumerate(errors, 1):
        resource = err.resource_address or err.resource_name or "unknown"
        if len(resource) > 40:
            resource = resource[:37] + "..."
        code = err.error_code or err.error_type or ""
        click.echo(f" {i:>2}  {resource:<40}  {code}")
    click.echo()


def _prompt_multi_error_action() -> str:
    """Prompt user for what to do with multiple errors.

    Returns one of: 'all', a number string, 'skip', 'defer_all'.
    """
    click.echo("What do you want to do?")
    click.echo("[Enter] Capture all one-by-one")
    click.echo("1) Capture a single error")
    click.echo("2) Skip capture")
    click.echo("3) Save all to pending and exit")
    choice = click.prompt("Choice", default="", show_default=False).strip()

    if choice == "":
        return "all"
    elif choice == "1":
        return "single"
    elif choice == "2":
        return "skip"
    elif choice == "3":
        return "defer_all"
    else:
        return "all"


def _display_error_card(err: ParsedError, index: int, total: int,
                        similar_fixes: list) -> None:
    """Display a compact error card for per-error iteration."""
    resource = err.resource_address or err.resource_name or "unknown"
    code = f"  ({err.error_code})" if err.error_code else ""
    click.echo(f"\nError {index}/{total}: {resource}{code}")
    click.echo(f"  Error: {err.short_error()}")

    if similar_fixes:
        click.echo("\n  Possible matches:")
        for fix in similar_fixes[:3]:
            issue_preview = fix.issue[:60] + "..." if len(fix.issue) > 60 else fix.issue
            click.echo(f"    - {fix.id[:8]} ({issue_preview})")


def _prompt_per_error_action(has_matches: bool) -> str:
    """Prompt for per-error action.

    Returns one of: 'capture', 'match', 'skip', 'defer'.
    """
    click.echo("\nAction?")
    click.echo("[Enter] Capture new fix")
    if has_matches:
        click.echo("m) Use existing match")
    click.echo("s) Skip")
    click.echo("d) Defer (save to pending)")
    choice = click.prompt("Choice", default="", show_default=False).strip().lower()

    if choice == "":
        return "capture"
    elif choice == "m" and has_matches:
        return "match"
    elif choice == "s":
        return "skip"
    elif choice == "d":
        return "defer"
    else:
        return "capture"


def _prompt_single_error_action(exit_code: int) -> str:
    """Prompt user for what to do with a single error on failure.

    Returns one of: 'capture', 'defer', 'skip'.
    """
    click.echo()
    click.echo(f"Command failed (exit code {exit_code}).")
    click.echo("[Enter] Capture this error")
    click.echo("d) Defer (save to pending)")
    click.echo("s) Skip")
    choice = click.prompt("Choice", default="", show_default=False).strip().lower()

    if choice == "d":
        return "defer"
    elif choice == "s":
        return "skip"
    else:
        return "capture"


def _capture_error_for_watch(err: ParsedError, tags: Optional[str],
                             repo: FixRepository, config) -> Optional:
    """Route a single error through the appropriate capture function."""
    from ..parsers import ErrorSource
    if err.error_type in ("terraform",):
        return capture_single_error(err, err.raw_output, tags, repo, config)
    elif err.error_type in ("kubectl", "helm", "kubernetes"):
        return capture_single_k8s_error(err, err.raw_output, tags, repo, config)
    else:
        return capture_single_error(err, err.raw_output, tags, repo, config)


def _handle_multi_error_flow(errors: list, tags: Optional[str],
                             repo: FixRepository, config,
                             command_str: Optional[str] = None) -> list:
    """Handle the multi-error interactive flow. Returns list of saved fixes."""
    saved_fixes = []
    store = None  # Lazily created when needed for defer

    _display_summary_table(errors)
    action = _prompt_multi_error_action()

    if action == "skip":
        return []

    if action == "defer_all":
        store = PendingStore()
        for err in errors:
            entry = pending_entry_from_parsed_error(err, command=command_str)
            store.save(entry)
        click.echo(f"\nSaved {len(errors)} error(s) to pending.")
        return []

    if action == "single":
        num = click.prompt("Which error number?", type=int)
        if 1 <= num <= len(errors):
            errors = [errors[num - 1]]
        else:
            click.echo("Invalid number, capturing all.")

    # Iterate through errors one by one
    for i, err in enumerate(errors, 1):
        similar = get_similar_fixes_for_error(err, tags, repo, config)
        _display_error_card(err, i, len(errors), similar)

        per_action = _prompt_per_error_action(has_matches=bool(similar))

        if per_action == "capture":
            fix = _capture_error_for_watch(err, tags, repo, config)
            if fix:
                repo.save(fix)
                saved_fixes.append(fix)
                click.echo(f"Fix saved: {fix.id[:8]}")

        elif per_action == "match":
            if similar:
                click.echo(f"\n Using existing fix: {similar[0].id[:8]}")
                click.echo(f"  Resolution: {similar[0].resolution[:80]}")

        elif per_action == "defer":
            if store is None:
                store = PendingStore()
            entry = pending_entry_from_parsed_error(err, command=command_str)
            store.save(entry)
            click.echo(f"Saved to pending: {err.error_id[:8]}")

        # skip → do nothing, move to next

    return saved_fixes


def _handle_single_error_flow(errors: list, output_text: str,
                              tags: Optional[str], repo: FixRepository,
                              config, no_prompt: bool) -> None:
    """Handle the single-error path (1 error or --no-prompt)."""
    if no_prompt:
        # Auto-capture all errors
        for err in errors:
            fix = _capture_error_for_watch(err, tags, repo, config)
            if fix:
                repo.save(fix)
                click.echo(f"\nFix saved: {fix.id[:8]}")
    else:
        # Single error — use existing single-capture flow
        fix = _capture_error_for_watch(errors[0], tags, repo, config)
        if fix:
            repo.save(fix)
            click.echo(f"\nFix saved: {fix.id[:8]}")


@click.command()
@click.argument("command", nargs=-1, required=True)
@click.option("--tags", "-t", default=None, help="Tags to apply to captured fix.")
@click.option(
    "--no-prompt",
    is_flag=True,
    default=False,
    help="Skip confirmation and auto-capture all errors on failure.",
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
    command_str = " ".join(command)

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
            # Parse all errors
            errors = detect_and_parse(output_text)

            if not errors:
                # No structured errors found — fall back to generic capture
                if not no_prompt:
                    action = _prompt_single_error_action(exit_code)
                    if action == "skip":
                        sys.exit(exit_code)
                    elif action == "defer":
                        # For generic errors, create a minimal PendingEntry
                        store = PendingStore()
                        from ..parsers.base import compute_error_id
                        entry = PendingEntry(
                            error_id=compute_error_id(
                                error_message=output_text
                            ),
                            error_type="generic",
                            short_message=output_text[:120],
                            error_excerpt=output_text[:2000],
                            tags=tags or "",
                            command=command_str,
                        )
                        store.save(entry)
                        click.echo(f"Saved to pending: {entry.error_id[:8]}")
                        sys.exit(exit_code)

                fix = handle_piped_input(
                    output_text, tags=tags, repo=repo, config=config
                )
                if fix:
                    repo.save(fix)
                    click.echo(f"\nFix saved: {fix.id[:8]}")

            elif len(errors) == 1 and not no_prompt:
                # Single error — prompt with capture/defer/skip
                action = _prompt_single_error_action(exit_code)
                if action == "skip":
                    sys.exit(exit_code)
                elif action == "defer":
                    store = PendingStore()
                    entry = pending_entry_from_parsed_error(
                        errors[0], command=command_str
                    )
                    store.save(entry)
                    click.echo(f"Saved to pending: {errors[0].error_id[:8]}")
                else:
                    _handle_single_error_flow(
                        errors, output_text, tags, repo, config, no_prompt=False
                    )

            elif no_prompt:
                # --no-prompt: auto-capture all
                _handle_single_error_flow(
                    errors, output_text, tags, repo, config, no_prompt=True
                )

            else:
                # Multiple errors — interactive multi-error flow
                click.echo()
                _handle_multi_error_flow(
                    errors, tags, repo, config, command_str=command_str
                )

    sys.exit(exit_code)
