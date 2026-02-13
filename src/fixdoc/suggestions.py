"""Similar fix suggestions for fixdoc.
This module finds fixes similar to a new error before creating duplicates.
"""

from typing import Optional
import click

from .config import SuggestionWeights
from .models import Fix
from .storage import FixRepository


def find_similar_fixes(
    repo: FixRepository,
    error_text: str,
    tags: Optional[str] = None,
    limit: int = 5,
    weights: Optional[SuggestionWeights] = None,
) -> list[Fix]:
    """
    Find fixes similar to the given error text and tags.
    """
    all_fixes = repo.list_all()
    if not all_fixes:
        return []

    if weights is None:
        weights = SuggestionWeights()

    scored_fixes: list[tuple[Fix, int]] = []

    # Extract keywords from error text
    error_keywords = _extract_keywords(error_text)
    error_lower = error_text.lower()

    # Parse input tags
    input_tags = set()
    if tags:
        input_tags = {t.strip().lower() for t in tags.split(",") if t.strip()}

    for fix in all_fixes:
        score = 0

        # Tag matching (highest weight)
        if fix.tags:
            fix_tags = {t.strip().lower() for t in fix.tags.split(",") if t.strip()}
            tag_overlap = input_tags & fix_tags
            score += len(tag_overlap) * weights.tag_weight

        # Error excerpt matching
        if fix.error_excerpt:
            excerpt_lower = fix.error_excerpt.lower()
            # Check for common error codes
            for code in _extract_error_codes(error_lower):
                if code in excerpt_lower:
                    score += weights.error_code_weight

        # Keyword matching in issue
        issue_keywords = _extract_keywords(fix.issue)
        keyword_overlap = error_keywords & issue_keywords
        score += len(keyword_overlap) * weights.issue_keyword_weight

        # Keyword matching in resolution
        resolution_keywords = _extract_keywords(fix.resolution)
        resolution_overlap = error_keywords & resolution_keywords
        score += len(resolution_overlap) * weights.resolution_keyword_weight

        # Resource type matching (from error text)
        resource_types = _extract_resource_types(error_lower)
        for rt in resource_types:
            if fix.tags and rt in fix.tags.lower():
                score += weights.resource_type_weight

        if score > 0:
            scored_fixes.append((fix, score))

    # Sort by score descending
    scored_fixes.sort(key=lambda x: x[1], reverse=True)

    return [fix for fix, score in scored_fixes[:limit]]


def prompt_similar_fixes(
    repo: FixRepository,
    error_text: str,
    tags: Optional[str] = None,
    limit: int = 5,
) -> Optional[Fix]:
    """
    Find similar fixes and prompt user to select one or create new.
    """
    similar = find_similar_fixes(repo, error_text, tags, limit=limit)
    
    if not similar:
        return None
    
    click.echo("\n Found similar fixes:\n")
    
    for i, fix in enumerate(similar, 1):
        tags_str = f" [{fix.tags}]" if fix.tags else ""
        issue_preview = fix.issue[:60] + "..." if len(fix.issue) > 60 else fix.issue
        click.echo(f"  [{i}] {fix.id[:8]}{tags_str}")
        click.echo(f"      {issue_preview}")
        resolution_preview = fix.resolution[:60] + "..." if len(fix.resolution) > 60 else fix.resolution
        click.echo(f"      → {resolution_preview}")
        click.echo()
    
    click.echo(f"  [n] Create new fix\n")
    
    choice = click.prompt(
        "Use existing fix?",
        default="n",
        show_default=True,
    )
    
    if choice.lower() == "n":
        return None
    
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(similar):
            return similar[idx]
    except ValueError:
        pass
    
    click.echo("Invalid choice, creating new fix.")
    return None


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text."""
    if not text:
        return set()
    
    # Common stop words to ignore
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "must", "shall",
        "can", "need", "dare", "ought", "used", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "during", "before", "after", "above", "below", "between",
        "under", "again", "further", "then", "once", "here", "there",
        "when", "where", "why", "how", "all", "each", "few", "more",
        "most", "other", "some", "such", "no", "nor", "not", "only",
        "own", "same", "so", "than", "too", "very", "just", "and",
        "but", "if", "or", "because", "until", "while", "this", "that",
        "these", "those", "it", "its", "error", "failed", "failure",
    }
    
    # Extract words, lowercase, filter
    words = set()
    for word in text.lower().split():
        # Clean punctuation
        word = "".join(c for c in word if c.isalnum() or c == "_")
        if word and len(word) > 2 and word not in stop_words:
            words.add(word)
    
    return words


def _extract_error_codes(text: str) -> set[str]:
    """Extract common error codes from text."""
    codes = set()
    
    # Common patterns
    import re
    
    # Azure style: Code: "AuthorizationFailed"
    azure_codes = re.findall(r'code[:\s]*["\']?(\w+)["\']?', text, re.IGNORECASE)
    codes.update(c.lower() for c in azure_codes)
    
    # HTTP status codes
    http_codes = re.findall(r'\b(4\d{2}|5\d{2})\b', text)
    codes.update(http_codes)
    
    # Common error names
    error_patterns = [
        "accessdenied", "authorizationfailed", "forbidden", "unauthorized",
        "notfound", "timeout", "connectionrefused", "permissiondenied",
        "invalidrequest", "quotaexceeded", "throttled", "conflict",
    ]
    for pattern in error_patterns:
        if pattern in text:
            codes.add(pattern)
    
    return codes


def _extract_resource_types(text: str) -> set[str]:
    """Extract cloud resource types from text."""
    types = set()
    
    # Azure resource types
    import re
    azure_types = re.findall(r'(azurerm_\w+)', text, re.IGNORECASE)
    types.update(t.lower() for t in azure_types)
    
    # AWS resource types
    aws_types = re.findall(r'(aws_\w+)', text, re.IGNORECASE)
    types.update(t.lower() for t in aws_types)
    
    # GCP resource types
    gcp_types = re.findall(r'(google_\w+)', text, re.IGNORECASE)
    types.update(t.lower() for t in gcp_types)
    
    return types