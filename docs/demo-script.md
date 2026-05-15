# Demo Script — Alert to Action: AI Operations Center

**Event**: AWS Summit Milan 2026 (AI Village booth)  
**Duration**: ~3 minutes per loop  
**Presenter**: Controls via DevPanel (Ctrl+D or gear icon, bottom-right)

---

## Pre-Demo Checklist

1. Open the frontend in Chrome (full-screen, no dev tools visible)
2. Open DevPanel (Ctrl+D) — verify:
   - WebSocket: connected (green dot in header)
   - Phase: HEALTHY
   - Voice Mode: **Mode B** (Twilio) selected
   - Phone number: your mobile number (with country code, e.g. +39...)
3. Verify all 7 services show green/healthy in the metrics panel
4. Have your phone ready (ringer ON, screen unlocked)
5. Passphrase reminder: **"REDACTED_PASSPHRASE"**

---

## The 3-Minute Loop

### Step 1 — Break (0:00)

Click **"Break DB"** in the DevPanel (AWS Operations section).

What happens:
- Security group rule removed instantly (port 3306 blocked)
- UI immediately shows INCIDENT_DETECTED
- Master agent activates

### Step 2 — Diagnosis (0:05 – 0:40)

Watch the agent log panel. The AI agents will:
- Check network connectivity (detects missing SG rule)
- Check database health (status: available but unreachable)
- Pull error logs
- Produce Root Cause Analysis

Narrate to audience: *"The AI has detected that the firewall rule for port 3306 was removed from the security group. It's now escalating to the on-call DBA."*

### Step 3 — Phone Call (0:40 – 1:30)

Your phone will ring. Answer it.

The AI voice agent will:
1. Identify itself as the AI Operations Center
2. Explain the issue (security group misconfiguration)
3. Ask for your authentication passphrase

Say: **"REDACTED_PASSPHRASE"**

The agent will confirm authentication and ask for authorization to restore the firewall rule.

Say: **"Yes, restore the firewall"** (or "fix it", "go ahead", "authorized")

### Step 4 — Recovery (1:30 – 2:00)

After you authorize:
- Security group rule is re-added instantly
- Phase advances: RECOVERING → RESOLVED → HEALTHY
- Metrics resume within ~10 seconds
- All services return to green

Narrate: *"The AI restored the firewall configuration in under a second. All systems are back to healthy."*

### Step 5 — Ready for Next Loop (2:00+)

System is back to HEALTHY. You can run another loop immediately.

---

## Recovery — If Something Goes Wrong

| Problem | Fix |
|---------|-----|
| Call didn't come through | Click **Reset**, wait 10s, check phone number, retry |
| Agent stuck in DIAGNOSING | Click **Reset**, wait 10s, retry |
| Metrics not updating | Check WebSocket connection (reconnects automatically) |
| Voice auth failed | Say passphrase again clearly: "REDACTED_PASSPHRASE" |
| Phase stuck after call | Click **Reset** — it restores SG rule and returns to HEALTHY |

**Nuclear option**: Click **Reset** — this always brings you back to a clean state (restores SG rule, cancels in-flight calls, resets all phases).

---

## Tips

- Keep DevPanel open but minimized during the demo (gear icon toggles it)
- Have a backup phone ready in case primary doesn't ring
- Between loops: no action needed — system is ready immediately after HEALTHY
- If audience asks about the phone call: it's a real Twilio call to a real phone using Amazon Nova Sonic for voice synthesis
- The security group change is real AWS infrastructure — show `aws ec2 describe-security-groups` in a terminal if asked
- Auto Advance is OFF by default — you control when to break the system
