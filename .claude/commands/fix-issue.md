---
description: Diagnose and fix an issue using goal-driven execution
---

1. Reproduce the issue: write a test or command that demonstrates the failure.
2. Verify reproduction: run the test — confirm it fails.
3. Identify root cause: read relevant code, trace the logic.
4. Implement fix: minimal change that addresses root cause.
5. Verify fix: run the reproduction test — confirm it passes.
6. Regression check: run full test suite — confirm nothing else broke.
7. Report what changed and why.
