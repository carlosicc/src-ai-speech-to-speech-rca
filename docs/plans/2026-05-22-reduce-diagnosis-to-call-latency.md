# Plan: Reduce Time from Incident Detection to Phone Call

**Goal**: Reduce the ~44 seconds between "Incident detected" and "Placing call", for a snappy booth demo.

---

## Problem

From the demo logs, the timeline from incident detection to call placement:

```
09:42:40  Incident detected. Activating response protocol.
09:42:43  Diagnosis agent activated. Pulling logs and running health checks...
09:42:43  Master Agent activated — following SoP...
09:42:47  Master Agent → activating Diagnosis Agent...
09:43:09  RCA Complete (26 seconds for diagnosis!)
09:43:14  Master Agent → escalating to on-call DBA via voice...
09:43:18  DBA confirmed. Executing recovery procedure...
09:43:24  Placing call to +44XXXXXXXXXX
```

**Total: 44 seconds** from detection to call. For a booth demo where people walk by, this is too long.

### Breakdown

| Phase | Duration | What's happening |
|-------|----------|-----------------|
| Incident → Diagnosis start | 3s | Phase transitions, master agent startup |
| Diagnosis agent running | 22s | Claude Sonnet runs 4 tools + generates full RCA report |
| Diagnosis → Escalation decision | 5s | Master agent processes RCA, decides to escalate |
| Escalation → Call placed | 10s | Escalation logic, Twilio call setup |

The **22-second diagnosis** is the main bottleneck.

---

## Requirements

- People at a booth have ~30 seconds of attention before they walk away
- The phone should ring, ideally, within 10-15 seconds of pressing "Break DB"
- The diagnosis/RCA can still appear on the UI for visual impact, but shouldn't block the call
- The demo must still look like a real multi-agent system (not just a scripted animation)

---

## Possible Approaches

1. **Parallelize diagnosis and call** — Start the voice call immediately while diagnosis runs in the background. The voice agent greets the DBA and authenticates while diagnosis finishes. Brief the voice agent with RCA results when they arrive (via tool or context injection).

2. **Use a faster model for diagnosis** — Switch from Claude Sonnet to Claude Haiku. Still runs all real tools (pull_logs, check_health, etc.) but generates the RCA summary faster.

3. **Reduce diagnosis scope** — Run fewer tools or skip the full RCA text generation. Just run the essential tools (check_health, pull_logs) and pass raw results to the master agent without asking Claude to write a full report.

4. **Shorten the master agent pipeline** — Remove intermediate steps between diagnosis and call placement. The master agent currently takes ~5s between RCA complete and deciding to escalate. Streamline the SoP so escalation is immediate once diagnosis confirms a critical issue.

---

## Decision: Approach 1 — Parallelize Diagnosis and Call

**Implemented.** The demo now runs diagnosis and the Twilio voice call in parallel. The Twilio+Nova Sonic setup takes ~7 seconds, which is enough time for the diagnosis tools to complete. By the time the DBA picks up and the agent starts speaking, all tool results are available.

**Expected new timeline:**
```
09:42:40  Incident detected
09:42:42  Diagnosis + Call start in parallel
09:42:42  Diagnosis agent running (background)
09:42:42  Twilio call placed
09:42:49  DBA picks up, agent starts speaking (~7s Twilio setup)
09:42:50  RCA complete (diagnosis finished in background)
```

**Total: ~9 seconds** from detection to agent speaking (vs. 44s before).

---

## Additional Observations from the Log

1. **`{ "interrupted" : true }` appearing as transcript** — KEEP AS-IS. This is a positive demo feature — it shows the audience the barge-in mechanism in Nova Sonic visually on the UI.

2. **Agent keeps talking after fix** — After `apply_network_fix` succeeds and the system resolves, the voice agent continues explaining. It should detect the phase change and wrap up quickly.

3. **Multiple turns after resolution** — The agent goes through 4+ additional turns after the fix is applied. The system prompt should instruct it to say goodbye promptly once the fix is confirmed.
