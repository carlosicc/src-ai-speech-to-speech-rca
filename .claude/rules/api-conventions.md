# API Design Rules

- REST endpoints: /api/{version}/{resource}
- Response format: { "data": {...} } for success, { "error": { "code": "...", "message": "..." } } for errors
- CORS headers on ALL responses (including error gateway responses)
- Status codes: 200 (OK), 201 (Created), 400 (Bad Request), 403 (Forbidden), 404 (Not Found), 500 (Internal Error)
- Pagination: ?limit=N&next_token=TOKEN
- WebSocket messages: { "type": "...", "payload": {...}, "timestamp": "ISO8601" }
