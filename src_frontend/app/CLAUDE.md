# Frontend Development Standards — RCA Agent Demo

## Tech Stack
- React 18 + TypeScript (strict mode)
- Vite for dev/build
- AWS Cloudscape Design System (components, tokens, global styles)
- TanStack Query for server state
- WebSocket for real-time updates

## Rules
- Use Cloudscape components — never build custom versions of existing Cloudscape components.
- Functional components with hooks only — no class components.
- Named exports — no default exports.
- No `any` types unless explicitly justified with a comment.
- Mock-first development: `VITE_USE_MOCKS=true` by default.
- WebSocket messages follow: `{ type: string, payload: object, timestamp: string }`

## Directory Structure
- `src/app/` — Entry point, router, providers
- `src/types/` — Domain types, WebSocket message types
- `src/lib/` — API client, WebSocket client, query hooks
- `src/components/` — Reusable UI components
- `src/routes/` — Page components (mapped to routes)
- `src/styles/` — Design tokens, global CSS

## Key Patterns

### WebSocket Hook
```typescript
export function useIncidentStream() {
  const [state, setState] = useState<IncidentState>(initialState);
  // Connect to /ws, parse messages, update state
  return state;
}
```

### Mock-first API
```typescript
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS !== "false";

export function useSystemStatus() {
  return useQuery({
    queryKey: ["system-status"],
    queryFn: () => USE_MOCKS ? mockSystemStatus() : apiClient("/api/v1/status"),
  });
}
```
