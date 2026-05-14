#!/usr/bin/env python3
"""Seed the Aurora MySQL demo database with sample data.

Designed to run inside the ECS container where RDS_CLUSTER_ENDPOINT and
RDS_SECRET_ARN env vars are set.

Usage (standalone):
    python scripts/seed_rds.py

Usage (via ECS run-task override):
    aws ecs run-task --cluster ... --task-definition ... \
        --overrides '{"containerOverrides":[{"name":"rca-backend-agent","command":["python","scripts/seed_rds.py"]}]}'
"""
import json
import logging
import os
import random
import sys
from datetime import datetime, timedelta

import boto3
import pymysql

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

SERVICES = ["aurora-db", "ecs-cluster", "lambda", "api-gateway", "s3-storage", "monitoring", "network"]
STATUSES = ["ok", "ok", "ok", "ok", "ok", "ok", "ok", "error", "timeout"]

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
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_arn)
    return json.loads(response["SecretString"])


def generate_rows(count: int = 1000) -> list[tuple]:
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
    conn = pymysql.connect(
        host=host, port=port, user=user, password=password,
        database=database, connect_timeout=10,
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
    secret_arn = os.environ.get("RDS_SECRET_ARN")
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-west-1"

    if not secret_arn:
        logger.error("RDS_SECRET_ARN env var not set.")
        sys.exit(1)

    creds = get_rds_credentials(secret_arn, region)
    host = os.environ.get("RDS_CLUSTER_ENDPOINT") or creds.get("host")
    port = int(creds.get("port", 3306))
    user = creds.get("username")
    password = creds.get("password")
    database = creds.get("dbname", "operations")

    if not all([host, user, password]):
        logger.error("Missing host, username, or password.")
        sys.exit(1)

    logger.info(f"Connecting to {host}:{port}/{database} as {user}")
    seed_database(host, port, user, password, database)
    logger.info("Seed complete.")


if __name__ == "__main__":
    main()
