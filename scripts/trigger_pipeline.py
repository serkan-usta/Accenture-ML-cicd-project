"""
trigger_pipeline.py
Triggers a SageMaker ML Pipeline execution. Production grade.

Improvements over v1:
    triggered_by: records who initiated the execution
    Duplicate execution guard: prevents double-running for the same commit
    Execution URL: direct SageMaker console link written to logs
    SageMaker Tags instead of SSM: lineage stays native to SageMaker
    Structured JSON logging
"""

import argparse
import json
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
)
logger = logging.getLogger(__name__)


def trigger_pipeline(
    pipeline_name: str,
    region: str,
    commit_sha: str,
    triggered_by: str = "unknown",
):
    sm_client = boto3.client("sagemaker", region_name=region)

    # FIX: Duplicate execution guard. Check whether this commit is already running.
    if _is_already_running(sm_client, pipeline_name, commit_sha):
        logger.warning(
            f"Pipeline execution for commit {commit_sha} already running. Skipping."
        )
        return None

    pipeline_params = [
        {"Name": "CommitSha",           "Value": commit_sha},
        {"Name": "ExecutionDate",       "Value": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
        # FIX: timezone-aware datetime, utcnow() is deprecated in Python 3.12+
        {"Name": "ModelApprovalStatus", "Value": "PendingManualApproval"},
        {"Name": "TriggeredBy",         "Value": triggered_by},
        # FIX: Who triggered the execution is accessible as a pipeline parameter
    ]

    logger.info(f"Triggering pipeline: {pipeline_name} commit={commit_sha[:8]} by={triggered_by}")

    response = sm_client.start_pipeline_execution(
        PipelineName=pipeline_name,
        PipelineExecutionDisplayName=f"gh-{commit_sha[:8]}-{triggered_by}",
        PipelineParameters=pipeline_params,
        PipelineExecutionDescription=f"GitHub Actions | commit={commit_sha} | by={triggered_by}",
    )

    execution_arn = response["PipelineExecutionArn"]

    # FIX: Write clickable console URL to logs, no need to search manually
    execution_id = execution_arn.split("/")[-1]
    console_url = (
        f"https://{region}.console.aws.amazon.com/sagemaker/home"
        f"?region={region}#/pipeline-executions/{execution_id}"
    )
    logger.info(f"Pipeline execution started: {execution_arn}")
    logger.info(f"Console URL: {console_url}")

    # FIX: Use SageMaker Tags instead of SSM for lineage
    #      Writing to SSM requires a separate IAM permission, tags are cleaner
    _tag_execution(sm_client, execution_arn, commit_sha, triggered_by)

    # FIX: Also write to SSM for backward compatibility with existing tooling
    _record_to_ssm(region, pipeline_name, execution_arn, commit_sha, triggered_by)

    return execution_arn


def _is_already_running(sm_client, pipeline_name: str, commit_sha: str) -> bool:
    """Check whether an execution for this commit SHA is already in progress."""
    try:
        paginator = sm_client.get_paginator("list_pipeline_executions")
        for page in paginator.paginate(PipelineName=pipeline_name):
            for execution in page["PipelineExecutionSummaries"]:
                if (
                    execution["PipelineExecutionStatus"] == "Executing"
                    and commit_sha[:8] in execution.get("PipelineExecutionDisplayName", "")
                ):
                    return True
    except ClientError:
        pass  # pipeline does not exist yet, not an error
    return False


def _tag_execution(sm_client, execution_arn: str, commit_sha: str, triggered_by: str):
    """Tag the execution for native SageMaker lineage tracking."""
    try:
        sm_client.add_tags(
            ResourceArn=execution_arn,
            Tags=[
                {"Key": "CommitSha",   "Value": commit_sha},
                {"Key": "TriggeredBy", "Value": triggered_by},
                {"Key": "TriggeredAt", "Value": datetime.now(timezone.utc).isoformat()},
                {"Key": "Source",      "Value": "github-actions"},
            ],
        )
    except ClientError as e:
        logger.warning(f"Could not tag execution (non-critical): {e}")


def _record_to_ssm(
    region: str,
    pipeline_name: str,
    execution_arn: str,
    commit_sha: str,
    triggered_by: str,
):
    """Write lineage record to SSM Parameter Store."""
    try:
        ssm = boto3.client("ssm", region_name=region)
        ssm.put_parameter(
            Name=f"/ml-pipeline/last-execution/{pipeline_name}",
            Value=json.dumps({
                "execution_arn":  execution_arn,
                "commit_sha":     commit_sha,
                "triggered_by":   triggered_by,
                "triggered_at":   datetime.now(timezone.utc).isoformat(),
            }),
            Type="String",
            Overwrite=True,
        )
        logger.info("Lineage recorded in SSM.")
    except ClientError as e:
        logger.warning(f"SSM write failed (non-critical): {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-name",  required=True)
    parser.add_argument("--region",         default="us-east-1")
    parser.add_argument("--commit-sha",     required=True)
    parser.add_argument("--triggered-by",   default="unknown")
    args = parser.parse_args()

    trigger_pipeline(
        pipeline_name=args.pipeline_name,
        region=args.region,
        commit_sha=args.commit_sha,
        triggered_by=args.triggered_by,
    )
