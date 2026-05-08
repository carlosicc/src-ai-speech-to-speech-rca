# Testing Rules

## Backend (Python)
- Framework: pytest
- CDK stacks: use `aws_cdk.assertions.Template.from_stack()`
- Lambda functions: test with mock events and mocked boto3 clients
- Run with: `.venv/bin/pytest -v`

## Frontend (TypeScript)
- Framework: Vitest + React Testing Library
- Mock react-router hooks (useParams, useNavigate) in route tests
- Use `vi.useFakeTimers()` with `fireEvent` (not `userEvent`) for timer tests
