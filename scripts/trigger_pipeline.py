"""
trigger_pipeline.py
SageMaker ML Pipeline tetikleyici — production grade.

Geliştirmeler (orijinale göre):
- --triggered-by: kim başlattı bilgisi
- Duplicate execution guard: aynı commit için çift çalışmayı önler
- Execution URL: direkt SageMaker console linki log'a yazılır
- SSM yerine SageMaker Tags: lineage native SageMaker'da tutulur
- Structured JSON logging
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

    # FIX: Duplicate execution guard — aynı commit SHA için zaten çalışan var mı?
    if _is_already_running(sm_client, pipeline_name, commit_sha):
        logger.warning(
            f"Pipeline execution for commit {commit_sha} already running. Skipping."
        )
        return None

    pipeline_params = [
        {"Name": "CommitSha",            "Value": commit_sha},
        {"Name": "ExecutionDate",        "Value": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
        # FIX: utcnow() deprecated Python 3.12+ — timezone-aware kullan
        {"Name": "ModelApprovalStatus",  "Value": "PendingManualApproval"},
        {"Name": "TriggeredBy",          "Value": triggered_by},
        # FIX: Kim tetikledi bilgisi pipeline içinden de erişilebilir
    ]

    logger.info(f"Triggering pipeline: {pipeline_name} commit={commit_sha[:8]} by={triggered_by}")

    response = sm_client.start_pipeline_execution(
        PipelineName=pipeline_name,
        PipelineExecutionDisplayName=f"gh-{commit_sha[:8]}-{triggered_by}",
        PipelineParameters=pipeline_params,
        PipelineExecutionDescription=f"GitHub Actions | commit={commit_sha} | by={triggered_by}",
    )

    execution_arn = response["PipelineExecutionArn"]

    # FIX: Execution URL'i log'a yaz — konsolda direkt tıkla
    execution_id = execution_arn.split("/")[-1]
    console_url = (
        f"https://{region}.console.aws.amazon.com/sagemaker/home"
        f"?region={region}#/pipeline-executions/{execution_id}"
    )
    logger.info(f"Pipeline execution started: {execution_arn}")
    logger.info(f"Console URL: {console_url}")

    # FIX: Lineage'ı SSM yerine SageMaker Tags ile tut
    #      SSM'e yazmak ayrı IAM permission gerektiriyor, tags daha temiz
    _tag_execution(sm_client, execution_arn, commit_sha, triggered_by)

    # FIX: SSM'e de yaz (isteğe bağlı, eski sistemlerle uyumluluk için)
    _record_to_ssm(region, pipeline_name, execution_arn, commit_sha, triggered_by)

    return execution_arn


def _is_already_running(sm_client, pipeline_name: str, commit_sha: str) -> bool:
    """Aynı commit için zaten çalışan execution var mı?"""
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
        pass  # pipeline henüz yoksa sorun değil
    return False


def _tag_execution(sm_client, execution_arn: str, commit_sha: str, triggered_by: str):
    """Execution'a tag ekle — native SageMaker lineage."""
    try:
        sm_client.add_tags(
            ResourceArn=execution_arn,
            Tags=[
                {"Key": "CommitSha",    "Value": commit_sha},
                {"Key": "TriggeredBy",  "Value": triggered_by},
                {"Key": "TriggeredAt",  "Value": datetime.now(timezone.utc).isoformat()},
                {"Key": "Source",       "Value": "github-actions"},
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
    """SSM Parameter Store'a lineage kaydı yaz."""
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