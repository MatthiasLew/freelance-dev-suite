def assess_risk(
    has_tests: bool,
    has_lint: bool,
    has_typecheck: bool,
    has_docker: bool,
    has_ci: bool,
    total_files: int,
    dependency_count: int,
    config_warnings: list[str],
    tests_failed: int = 0,
    validation_status: str = "unknown",
) -> tuple[str, list[str]]:
    """
    Assess the risk of a project based on deterministic factors.
    Returns a tuple of (risk_level, list of risk_factors).
    """
    risk_factors: list[str] = []
    score = 0.0

    if not has_tests:
        risk_factors.append("No tests detected")
        score += 2
    if not has_lint:
        risk_factors.append("No linter detected")
        score += 1
    if not has_typecheck:
        risk_factors.append("No type checker detected")
        score += 1
    if not has_tests and not has_lint and not has_typecheck:
        risk_factors.append("No automated quality gate detected")
        score += 1
    if not has_ci:
        risk_factors.append("No CI/CD configuration detected")
        score += 0.5

    if tests_failed:
        risk_factors.append(f"Failing tests/checks: {tests_failed}")
        score += min(4.0, 1.0 + tests_failed * 0.5)
    if validation_status == "failed":
        risk_factors.append("Technical validation failed")
        score += 2

    if total_files > 2000:
        risk_factors.append("Very large project (>2000 files)")
        score += 3
    elif total_files > 500:
        risk_factors.append("Large project (>500 files)")
        score += 2

    if dependency_count > 30:
        risk_factors.append("Many dependencies (>30)")
        score += 2

    if config_warnings:
        risk_factors.append(f"Config warnings present: {len(config_warnings)}")
        score += min(2.0, len(config_warnings) * 0.5)

    if score <= 2:
        risk_level = "LOW"
    elif score <= 5:
        risk_level = "MEDIUM"
    elif score <= 8:
        risk_level = "HIGH"
    else:
        risk_level = "VERY_HIGH"

    return risk_level, risk_factors
