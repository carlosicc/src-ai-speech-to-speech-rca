#!/usr/bin/env python3
"""Seed the Aurora MySQL demo database with sample data.

Usage:
    python src_config/scripts/seed_rds.py --env dev01

Requires:
    - AWS credentials with secretsmanager:GetSecretValue
    - Network access to the RDS cluster (run from ECS task or VPN)
"""
import argparse
import json
import logging
import random
import sys
from datetime import datetime, timedelta

import boto3
import pymysql

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

SERVICES = ["aurora-db", "ecs-cluster", "lambda", "api-gateway", "s3-storage", "monitoring", "network"]
STATUSES = ["ok", "ok", "ok", "ok", "ok", "ok", "ok", "error", "timeout"]  # weighted toward ok

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS demo_transactions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    service VARCHAR(64) NOT NULL,
    status ENUM('ok','error','timeout') DEFAULT 'ok',
    latency_ms INT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def get_rds_credentials(secret_arn: str, region: str) -> dict:
    """Retrieve RDS credentials from Secrets Manager."""
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_arn)
    return json.loads(response["SecretString"])


def generate_rows(count: int = 1000) -> list[tuple]:
    """Generate sample transaction rows spanning the last 24 hours."""
    now = datetime.utcnow()
    rows = []
    for _ in range(count):
        ts = now - timedelta(seconds=random.randint(0, 86400))
        service = random.choice(SERVICES)
        status = random.choice(STATUSES)
        latency_ms = random.randint(5, 50) if status == "ok" else random.randint(500, 5000)
        rows.append((ts, service, status, latency_ms))
    return rows


def seed_database(host: str, port: int, user: str, password: str, database: str) -> None:
    """Connect to RDS and seed the demo_transactions table."""
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(CREATE_TABLE_SQL)
            logger.info("Table demo_transactions ensured.")

            cursor.execute("SELECT COUNT(*) FROM demo_transactions")
            existing = cursor.fetchone()[0]
            if existing >= 1000:
                logger.info(f"Table already has {existing} rows, skipping seed.")
                return

            # Clear and re-seed
            cursor.execute("TRUNCATE TABLE demo_transactions")
            rows = generate_rows(1000)
            cursor.executemany(
                "INSERT INTO demo_transactions (ts, service, status, latency_ms) VALUES (%s, %s, %s, %s)",
                rows,
            )
            conn.commit()
            logger.info(f"Inserted {len(rows)} rows into demo_transactions.")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed RDS Aurora MySQL with demo data")
    parser.add_argument("--env", default="dev01", help="Environment name (default: dev01)")
    parser.add_argument("--region", default="eu-west-1", help="AWS region")
    parser.add_argument("--secret-arn", help="Override: Secrets Manager ARN for RDS credentials")
    parser.add_argument("--host", help="Override: RDS cluster endpoint")
    args = parser.parse_args()

    project_name = "rca"

    # Resolve secret ARN from CDK outputs if not provided
    if args.secret_arn:
        secret_arn = args.secret_arn
    else:
        cf = boto3.client("cloudformation", region_name=args.region)
        stack_name = f"RcaBackendStack-{args.env}"
        try:
            resp = cf.describe_stacks(StackName=stack_name)
            outputs = {o["OutputKey"]: o["OutputValue"] for o in resp["Stacks"][0].get("Outputs", [])}
            secret_arn = outputs.get("RdsSecretArn")
            if not secret_arn:
                logger.error(f"RdsSecretArn not found in {stack_name} outputs.")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to read stack outputs: {e}")
            sys.exit(1)

    # Get credentials
    creds = get_rds_credentials(secret_arn, args.region)
    host = args.host or creds.get("host")
    port = int(creds.get("port", 3306))
    user = creds.get("username")
    password = creds.get("password")
    database = creds.get("dbname", "operations")

    if not all([host, user, password]):
        logger.error("Missing host, username, or password in secret.")
        sys.exit(1)

    logger.info(f"Connecting to {host}:{port}/{database} as {user}")
    seed_database(host, port, user, password, database)
    logger.info("Seed complete.")


if __name__ == "__main__":
    main()
