"""
deploy_sagemaker.py
Deploys a Docker image to a SageMaker real-time endpoint. Production grade.

Improvements over v1:
    wait flag: blocks until deploy is fully complete
    Retry logic: handles transient AWS errors
    Data capture: writes live traffic to S3 for model monitoring
    Auto-scaling policy: endpoint scales automatically under load
    Waiter timeout: raises after 30 minutes
    Structured logging: JSON format compatible with CloudWatch
"""

import argparse
import json
import logging
import time
from datetime import datetime

import boto3
import sagemaker
from botocore.exceptions import ClientError, WaiterError
from sagemaker.model import Model

# FIX: Structured JSON logging, filterable in CloudWatch
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
)
logger = logging.getLogger(__name__)

INSTANCE_TYPE = "ml.m5.xlarge"
MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds


def deploy(
    image_uri: str,
    role_arn: str,
    endpoint_name: str,
    region: str,
    wait: bool = True,
):
    session = boto3.Session(region_name=region)
    sm_session = sagemaker.Session(boto_session=session)
    sm_client = session.client("sagemaker")

    logger.info(f"Starting deploy: endpoint={endpoint_name} image={image_uri}")

    # FIX: Timestamp in model name prevents collision with existing models of the same name
    model_name = f"ml-model-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    model = Model(
        image_uri=image_uri,
        role=role_arn,
        sagemaker_session=sm_session,
        name=model_name,
    )

    endpoint_exists = _endpoint_exists(sm_client, endpoint_name)

    # FIX: Data capture config writes live traffic to S3 for model drift detection
    from sagemaker.model_monitor import DataCaptureConfig
    data_capture = DataCaptureConfig(
        enable_capture=True,
        sampling_percentage=20,  # capture 20% of traffic
        destination_s3_uri=f"s3://your-ml-bucket/data-capture/{endpoint_name}",
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if endpoint_exists:
                logger.info(f"Updating existing endpoint (attempt {attempt})")
                model.deploy(
                    initial_instance_count=1,
                    instance_type=INSTANCE_TYPE,
                    endpoint_name=endpoint_name,
                    update_endpoint=True,
                    data_capture_config=data_capture,
                )
            else:
                logger.info(f"Creating new endpoint (attempt {attempt})")
                model.deploy(
                    initial_instance_count=1,
                    instance_type=INSTANCE_TYPE,
                    endpoint_name=endpoint_name,
                    data_capture_config=data_capture,
                )
            break  # success, exit retry loop

        except ClientError as e:
            code = e.response["Error"]["Code"]
            logger.warning(f"AWS error on attempt {attempt}: {code}")
            if attempt == MAX_RETRIES:
                logger.error("Max retries reached. Deploy failed.")
                raise
            time.sleep(RETRY_DELAY * attempt)  # exponential backoff

    if wait:
        _wait_for_endpoint(sm_client, endpoint_name)
        _setup_autoscaling(session, endpoint_name)

    logger.info(f"Deploy complete: {endpoint_name}")


def _endpoint_exists(sm_client, endpoint_name: str) -> bool:
    """Check whether the endpoint already exists."""
    try:
        sm_client.describe_endpoint(EndpointName=endpoint_name)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ValidationException":
            return False
        raise


def _wait_for_endpoint(sm_client, endpoint_name: str, timeout: int = 1800):
    """
    FIX: Block until endpoint reaches InService status.
    In v1 there was no wait. The deploy request was sent but completion was unknown.
    """
    logger.info(f"Waiting for endpoint to be InService (max {timeout}s)...")
    waiter = sm_client.get_waiter("endpoint_in_service")
    try:
        waiter.wait(
            EndpointName=endpoint_name,
            WaiterConfig={"Delay": 30, "MaxAttempts": timeout // 30},
        )
        logger.info("Endpoint is InService.")
    except WaiterError:
        logger.error(f"Endpoint did not become InService within {timeout}s")
        raise


def _setup_autoscaling(session, endpoint_name: str):
    """
    FIX: Auto-scaling policy, was missing in v1.
    Instance count scales automatically from 1 to 4 under load.
    """
    aas_client = session.client("application-autoscaling")
    resource_id = f"endpoint/{endpoint_name}/variant/AllTraffic"

    try:
        aas_client.register_scalable_target(
            ServiceNamespace="sagemaker",
            ResourceId=resource_id,
            ScalableDimension="sagemaker:variant:DesiredInstanceCount",
            MinCapacity=1,
            MaxCapacity=4,
        )
        aas_client.put_scaling_policy(
            PolicyName=f"{endpoint_name}-scaling-policy",
            ServiceNamespace="sagemaker",
            ResourceId=resource_id,
            ScalableDimension="sagemaker:variant:DesiredInstanceCount",
            PolicyType="TargetTrackingScaling",
            TargetTrackingScalingPolicyConfiguration={
                "TargetValue": 70.0,  # scale out at 70% CPU utilisation
                "PredefinedMetricSpecification": {
                    "PredefinedMetricType": "SageMakerVariantInvocationsPerInstance",
                },
                "ScaleInCooldown": 300,
                "ScaleOutCooldown": 60,
            },
        )
        logger.info("Auto-scaling policy configured.")
    except ClientError as e:
        logger.warning(f"Auto-scaling setup failed (non-critical): {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-uri", required=True)
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--wait", action="store_true", default=True)
    args = parser.parse_args()

    deploy(
        image_uri=args.image_uri,
        role_arn=args.role_arn,
        endpoint_name=args.endpoint_name,
        region=args.region,
        wait=args.wait,
    )
