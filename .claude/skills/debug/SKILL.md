---
name: debugging
description: Systematic debugging workflow for this project
triggers:
  - "debug"
  - "not working"
  - "error"
  - "failing"
---

## Debugging Steps
1. **Reproduce**: Get the exact error message or unexpected behavior.
2. **Locate**: Find the relevant code path (check ECS logs, Lambda logs, frontend console).
3. **Isolate**: Determine if it's infra (CDK), runtime (agent code), or config (SSM/Secrets/DynamoDB).
4. **Diagnose**: Read the code, check environment variables, verify DynamoDB entries.
5. **Fix**: Make the minimal change.
6. **Verify**: Run tests or manual check to confirm fix.

## Common Issues
- Agent not responding → Check BEDROCK_MODEL_ID env var, verify IAM permissions for bedrock:InvokeModel
- WebSocket disconnects → Check ECS health check path, verify ALB target group settings
- Voice call fails → Check Twilio credentials in Secrets Manager, verify phone number format (+E.164)
- Prompt not loading → Verify DynamoDB has PROMPT#{agent_type}/LATEST entry
