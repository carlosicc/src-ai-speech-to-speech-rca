# Code Style Rules

## Python
- Type hints required on all function signatures.
- Import order: stdlib → third-party → local (with blank lines between groups).
- Use `logger.info()` / `logger.error()` — never `print()`.
- Catch specific exceptions (ClientError, ValueError) — never bare `except:`.
- Use f-strings for string formatting.
- Max line length: 120 characters.

## TypeScript
- Strict mode enabled. No `any` types unless explicitly justified.
- Functional components with hooks — no class components.
- Use named exports, not default exports.
