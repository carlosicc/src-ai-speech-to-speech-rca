---
description: Code review the current branch against main
---

1. Run `git diff main...HEAD --stat` to see all changed files.
2. For each changed file, read the diff and check:
   - Naming conventions match CLAUDE.md
   - No hardcoded values (regions, account IDs, secrets)
   - Type hints on all functions
   - Logging present (logger.info/error)
   - Error handling with specific exceptions
   - Shared code uses Lambda layer (not duplicated)
3. Summarize findings as a numbered list.
