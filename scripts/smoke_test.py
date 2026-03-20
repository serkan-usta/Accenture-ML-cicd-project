"""
smoke_test.py
Verifies the endpoint is genuinely live after deploy.
This file did not exist in v1, it was a critical gap in the pipeline.
"""

import argparse
import json
import logging
import sys

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Minimal test payload the endpoint is expected to accept
TEST_PAYLOAD = json.dumps({"inputs": [[1.0, 2.0, 3.0, 4.0]]})
CONTENT_TYPE = "application/json"


def smoke_test(endpoint_name: str, region: str) -> bool:
    runtime = boto3.client("sagemaker-runtime", region_name=region)

    logger.info(f"Smoke testing endpoint: {endpoint_name}")
    try:
        response = runtime.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType=CONTENT_TYPE,
            Body=TEST_PAYLOAD,
        )
        status = response["ResponseMetadata"]["HTTPStatusCode"]
        body = response["Body"].read().decode("utf-8")

        if status == 200:
            logger.info(f"Smoke test passed. Response: {body[:200]}")
            return True
        else:
            logger.error(f"Smoke test failed. HTTP {status}: {body}")
            return False

    except ClientError as e:
        logger.error(f"Smoke test failed with error: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    success = smoke_test(args.endpoint_name, args.region)
    sys.exit(0 if success else 1)
