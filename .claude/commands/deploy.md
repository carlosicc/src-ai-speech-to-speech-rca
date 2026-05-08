---
description: Deploy infrastructure to specified environment
---

1. Run `cdk diff --all` to show pending changes.
2. Ask user to confirm deployment.
3. Run `cdk deploy --all --require-approval never`.
4. Run post-deployment scripts:
   - `python src_config/scripts/deploy_ssm_parameters.py --env $ARGUMENTS`
   - `python src_config/scripts/deploy_secrets.py --env $ARGUMENTS`
5. Report deployment status.
