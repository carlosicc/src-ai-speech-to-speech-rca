# Plan: Code Showcase Pages for Booth Visitors

**Date**: 2026-05-26  
**Status**: COMPLETE  
**Goal**: Create standalone HTML page(s) with representative code snippets that tell the story of how the demo works — for technical attendees (SDEs) at the booth.  
**Style**: White/light theme matching existing architecture pages (AWS orange accents, card-based)  
**Navigation**: Independent button in the demo UI (not attached to existing diagram buttons)  
**Content**: Simplified, representative snippets — NOT real code. Shows imports, patterns, and flow.

---

## Design Decisions

- **Tab structure**: Sequential story (Setup → Orchestration → Tools → Voice)
- **Presentation**: Light theme with colored syntax highlighting, card-based code blocks
- **Placement**: New standalone button in `DiagramViewer.tsx`, visually separated from existing buttons (blue/purple, bottom-right)
- **File location**: `docs/architecture/codeShowcaseLight.html` (same serving mechanism as other pages)
- **Screen**: Optimized for 36-42" booth display at ~1-2m viewing distance

---

## Tab Content

### Tab 1: "Setup & Imports"
Libraries, `os.environ` model configuration, DynamoDB prompt loading.

### Tab 2: "Master Orchestrates"
Agent creation with tools list, `activate_diagnosis()` as agent-as-tool pattern, one-line invocation.

### Tab 3: "Agent Uses Tools"
`@tool` decorator, real boto3 calls (EC2, CloudWatch), autonomous tool chaining.

### Tab 4: "Voice via Nova Sonic"
Bidirectional stream, Twilio call placement, mulaw↔PCM audio bridge, mid-call tool use.

---

## Phases

### Phase 1: HTML Page ✅ DONE
- [x] Created `docs/architecture/codeShowcaseLight.html` (white/light theme — selected)
- [x] Also created `docs/architecture/codeShowcase.html` (dark IDE theme — kept as alternative)
- [x] CSS-only syntax highlighting, card-based code blocks
- [x] Tab navigation (4 tabs) with auto-advance toggle
- [x] Representative snippets for all 4 tabs

### Phase 2: UI Integration ✅ DONE
- [x] Added `code` type to DiagramViewer with `codeShowcaseLight.html`
- [x] New blue/purple button at bottom-right (independent from green architecture buttons)
- [x] Vite plugin automatically picks up new HTML file
- [x] Tested in dev server via Chrome DevTools

### Phase 3: Polish & Deploy ✅ DONE
- [x] Bumped font sizes for 36-42" screen readability (code: 0.92rem, headers: 1.4rem, annotations: 0.85rem)
- [x] Added fade-in animation on tab switch
- [x] Navigation arrows (← 1/4 →) for presentation mode
- [x] Keyboard arrow keys (left/right) for navigation
- [x] Auto-advance OFF by default
- [x] `os.environ` for model IDs (not hardcoded)
- [x] Built and deployed to CloudFront (invalidation: I1F7K8WYT6VT7S765YY4JVTJSB)

---

## Files Changed

| File | Change |
|------|--------|
| `docs/architecture/codeShowcaseLight.html` | New — light theme code showcase (primary) |
| `docs/architecture/codeShowcase.html` | New — dark theme code showcase (alternative) |
| `src_frontend/app/src/components/DiagramViewer.tsx` | Added `code` diagram type + button |
| `src_frontend/app/src/styles/theme.css` | Added `.diagram-code-btn` styling |
| `docs/plans/2026-05-26-code-showcase-pages.md` | This plan |
