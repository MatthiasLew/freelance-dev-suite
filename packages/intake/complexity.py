def classify_complexity(
    languages_count: int, frameworks_count: int, loc: int, total_files: int, workspace_count: int
) -> str:
    """
    Classify the complexity of a project based on deterministic factors.
    Returns complexity level: LOW, MEDIUM, HIGH, or VERY_HIGH.
    """
    # Monorepo generally bumps complexity.
    if workspace_count > 1:
        if total_files >= 500 or loc >= 30000 or languages_count > 3:
            return "VERY_HIGH"
        if total_files >= 200 or loc >= 10000 or languages_count > 2:
            return "HIGH"
        return "MEDIUM"

    if total_files < 50 and loc < 2000 and languages_count <= 1 and frameworks_count <= 1:
        return "LOW"
    elif total_files < 200 and loc < 10000 and languages_count <= 2:
        return "MEDIUM"
    elif total_files < 500 and loc < 30000 and languages_count <= 3:
        return "HIGH"
    else:
        return "VERY_HIGH"


def estimate_work_hours(complexity: str, task_description: str = "") -> tuple[float, float]:
    """
    Estimate minimum and maximum work hours based on project complexity.
    Returns tuple of (min_hours, max_hours).
    """
    ranges = {
        "LOW": (1.0, 3.0),
        "MEDIUM": (3.0, 8.0),
        "HIGH": (8.0, 20.0),
        "VERY_HIGH": (20.0, 50.0),
    }
    minimum, maximum = ranges.get(complexity, ranges["MEDIUM"])
    description = task_description.lower()
    broad_scope_terms = {"migration", "rewrite", "refactor", "authentication", "integration"}
    small_scope_terms = {"typo", "small fix", "minor fix", "one-line", "jedna linia"}
    if any(term in description for term in broad_scope_terms):
        minimum *= 1.25
        maximum *= 1.5
    elif any(term in description for term in small_scope_terms):
        minimum *= 0.5
        maximum *= 0.75
    return round(minimum, 1), round(maximum, 1)
