#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/src_frontend/app"
ENV_NAME="${1:-dev01}"
STACK_NAME="RcaFrontendStack-${ENV_NAME}"

echo "==> Deploying frontend (env: $ENV_NAME)"

# 1. Build frontend (copies diagrams into dist/diagrams/ via Vite plugin)
echo "==> Building frontend..."
cd "$FRONTEND_DIR"
npm run build
cd "$PROJECT_ROOT"

# 2. Get S3 bucket and CloudFront distribution ID from CDK outputs
echo "==> Fetching stack outputs..."
BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue' \
    --output text)

DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`DistributionId`].OutputValue' \
    --output text)

if [ -z "$BUCKET_NAME" ] || [ -z "$DISTRIBUTION_ID" ]; then
    echo "ERROR: Could not fetch BucketName or DistributionId from stack $STACK_NAME"
    exit 1
fi

echo "    Bucket: $BUCKET_NAME"
echo "    Distribution: $DISTRIBUTION_ID"

# 3. Sync built frontend to S3
echo "==> Uploading to S3..."
aws s3 sync "$FRONTEND_DIR/dist/" "s3://$BUCKET_NAME/" --delete

# 4. Invalidate CloudFront cache
echo "==> Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
    --distribution-id "$DISTRIBUTION_ID" \
    --paths "/*" \
    --query 'Invalidation.Id' \
    --output text

echo "==> Done! Frontend deployed."
