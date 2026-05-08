"""Pre-deployment validation checks."""

import subprocess
import sys


def check_no_secrets_in_source() -> bool:
    """Ensure no secrets are hardcoded in source."""
    patterns = ["AKIA", "sk-", "password=", "secret=", "token="]
    for pattern in patterns:
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py", pattern, "src_infra/"],
            capture_output=True, text=True,
        )
        if result.stdout.strip():
            print(f"FAIL: Found potential secret pattern '{pattern}':")
            print(result.stdout)
            return False
    print("PASS: No secrets found in source code")
    return True


def run_tests() -> bool:
    """Run pytest suite."""
    result = subprocess.run(
        [".venv/bin/pytest", "-v", "tests/"],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print("FAIL: Tests did not pass")
        print(result.stderr)
        return False
    print("PASS: All tests passed")
    return True


def run_cdk_diff() -> bool:
    """Run cdk diff to preview changes."""
    result = subprocess.run(
        ["cdk", "diff", "--all"],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0 and "There were differences" not in result.stderr:
        print("WARN: CDK diff reported issues")
        print(result.stderr)
    return True


if __name__ == "__main__":
    checks = [
        check_no_secrets_in_source(),
        run_tests(),
        run_cdk_diff(),
    ]
    if not all(checks):
        print("\nSome checks failed. Review above output.")
        sys.exit(1)
    print("\nAll pre-deployment checks passed.")
