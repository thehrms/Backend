import rule_engine
import re

def normalize_rule(expr: str) -> str | None:
    """
    Normalize rule expressions into valid rule-engine syntax.
    Handles:
    - ANY clauses (flattens them)
    - 'matches' regex -> weekday checks
    - General whitespace cleanup
    """

    if not expr:
        return None

    raw_expr = expr.strip()

    # 1. Remove "rule:" prefix if present
    expr = re.sub(r"^rule:\s*", "", raw_expr, flags=re.IGNORECASE)

    # 2. Flatten ANY clauses
    # Example: "leave_balances ANY (leave_type == 'Paid Leave' and remaining_days > 0)"
    expr = re.sub(r"\w+\s+ANY\s*\((.*?)\)", r"\1", expr)

    # 3. Convert regex 'matches' for Friday/Monday into weekday checks
    # Example: start_date matches '^.*(Friday|Monday).*$' -> start_date.weekday() in (0,4)
    expr = re.sub(
        r"(\w+)\s+matches\s+'[^']*(Friday\|Monday)[^']*'",
        lambda m: f"({m.group(1)}.weekday() in (0,4))",
        expr,
        flags=re.IGNORECASE
    )

    # 4. Cleanup null/None usage
    expr = expr.replace("null", "None")

    # 5. Extra cleanup: multiple spaces
    expr = re.sub(r"\s+", " ", expr).strip()

    # ✅ Validate with rule-engine
    try:
        rule_engine.Rule(expr)  # compile test
        print(f"✅ Normalized rule: {expr}")
        return expr
    except Exception as e:
        print(f"❌ Invalid rule after normalization: {expr} | Error: {e}")
        return None




def validate_rule(expr: str) -> bool:
    """Check if a rule can be parsed by rule-engine."""
    try:
        rule_engine.Rule(expr)
        return True
    except Exception as e:
        print(f"❌ Invalid rule skipped: {expr} | Error: {e}")
        return False
