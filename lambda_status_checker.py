import json
import os
import boto3
import logging
from typing import Dict, Any, List

# ─── Setup logging ──────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── Environment variables ──────────────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "divinepic-test")

# ─── Global clients ─────────────────────────────────────────────────────────────
ssm_client = None
s3_client = None
ec2_client = None

def initialize_clients():
    """Initialize AWS clients."""
    global ssm_client, s3_client, ec2_client
    
    if ssm_client is None:
        ssm_client = boto3.client("ssm", region_name=AWS_REGION)
        logger.info("✅ SSM client initialized")
    
    if s3_client is None:
        s3_client = boto3.client("s3", region_name=AWS_REGION)
        logger.info("✅ S3 client initialized")
    
    if ec2_client is None:
        ec2_client = boto3.client("ec2", region_name=AWS_REGION)
        logger.info("✅ EC2 client initialized")

def get_job_status(job_id: str) -> Dict[str, Any]:
    """Get the current status of a processing job."""
    try:
        # Get job status from SSM Parameter Store
        status_param = f"/divinepic/jobs/{job_id}/status"
        instance_param = f"/divinepic/jobs/{job_id}/instance_id"
        
        status = "unknown"
        instance_id = None
        
        try:
            status_response = ssm_client.get_parameter(Name=status_param)
            status = status_response['Parameter']['Value']
        except ssm_client.exceptions.ParameterNotFound:
            logger.warning(f"Status parameter not found for job {job_id}")
        
        try:
            instance_response = ssm_client.get_parameter(Name=instance_param)
            instance_id = instance_response['Parameter']['Value']
        except ssm_client.exceptions.ParameterNotFound:
            logger.warning(f"Instance parameter not found for job {job_id}")
        
        job_info = {
            "job_id": job_id,
            "status": status,
            "instance_id": instance_id
        }
        
        # If we have an instance ID, get instance details
        if instance_id:
            try:
                instances_response = ec2_client.describe_instances(InstanceIds=[instance_id])
                if instances_response['Reservations']:
                    instance = instances_response['Reservations'][0]['Instances'][0]
                    job_info["instance_state"] = instance['State']['Name']
                    job_info["instance_type"] = instance['InstanceType']
                    
                    if 'PublicIpAddress' in instance:
                        job_info["instance_ip"] = instance['PublicIpAddress']
            except Exception as e:
                logger.error(f"Failed to get instance details: {e}")
                job_info["instance_state"] = "unknown"
        
        # If job is completed, try to get results
        if status == "completed":
            results_key = f"jobs/{job_id}/results.json"
            try:
                results_response = s3_client.get_object(Bucket=S3_BUCKET, Key=results_key)
                results_data = json.loads(results_response['Body'].read().decode('utf-8'))
                job_info["results"] = results_data
                job_info["results_url"] = f"s3://{S3_BUCKET}/{results_key}"
            except Exception as e:
                logger.error(f"Failed to get results for job {job_id}: {e}")
                job_info["results_error"] = str(e)
        
        return job_info
        
    except Exception as e:
        logger.error(f"Failed to get job status for {job_id}: {e}")
        return {
            "job_id": job_id,
            "status": "error",
            "error": str(e)
        }

def list_recent_jobs(limit: int = 10) -> List[Dict[str, Any]]:
    """List recent processing jobs."""
    try:
        # Get all job status parameters
        paginator = ssm_client.get_paginator('describe_parameters')
        page_iterator = paginator.paginate(
            ParameterFilters=[
                {
                    'Key': 'Name',
                    'Option': 'BeginsWith',
                    'Values': ['/divinepic/jobs/']
                }
            ]
        )
        
        job_ids = set()
        for page in page_iterator:
            for param in page['Parameters']:
                # Extract job ID from parameter name
                param_name = param['Name']
                if '/status' in param_name:
                    job_id = param_name.split('/')[3]  # /divinepic/jobs/{job_id}/status
                    job_ids.add(job_id)
        
        # Sort job IDs by timestamp (newest first) and limit
        sorted_job_ids = sorted(job_ids, reverse=True)[:limit]
        
        # Get status for each job
        jobs = []
        for job_id in sorted_job_ids:
            job_info = get_job_status(job_id)
            jobs.append(job_info)
        
        return jobs
        
    except Exception as e:
        logger.error(f"Failed to list recent jobs: {e}")
        return []

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for checking job status and retrieving results.
    
    Expected event formats:
    1. Check specific job: {"job_id": "job_123456_abcd1234"}
    2. List recent jobs: {"action": "list", "limit": 10}
    """
    try:
        initialize_clients()
        
        # Check if this is a list request
        if event.get("action") == "list":
            limit = event.get("limit", 10)
            jobs = list_recent_jobs(limit)
            
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({
                    "action": "list",
                    "jobs": jobs,
                    "count": len(jobs)
                })
            }
        
        # Check specific job
        job_id = event.get("job_id")
        if not job_id:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "Missing 'job_id' in request"
                })
            }
        
        job_info = get_job_status(job_id)
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(job_info)
        }
        
    except Exception as e:
        logger.error(f"❌ Status check failed: {e}")
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "message": "Failed to check job status"
            })
        } 