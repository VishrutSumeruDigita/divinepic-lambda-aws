import json
import os
import uuid
import time
import logging
import base64
import boto3
from typing import List, Dict, Any

# ─── Setup logging ──────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── Environment variables ──────────────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "divinepic-test")
EC2_AMI_ID = os.environ.get("EC2_AMI_ID", "ami-0c94855ba95b798c7")  # Ubuntu 20.04 LTS
EC2_KEY_PAIR = os.environ.get("EC2_KEY_PAIR", "divinepic-key")
EC2_SECURITY_GROUP = os.environ.get("EC2_SECURITY_GROUP", "divinepic-sg")
EC2_SUBNET_ID = os.environ.get("EC2_SUBNET_ID", "")  # Optional: specify subnet

# ─── Global clients ─────────────────────────────────────────────────────────────
ec2_client = None
s3_client = None
ssm_client = None

def initialize_clients():
    """Initialize AWS clients."""
    global ec2_client, s3_client, ssm_client
    
    if ec2_client is None:
        ec2_client = boto3.client("ec2", region_name=AWS_REGION)
        logger.info("✅ EC2 client initialized")
    
    if s3_client is None:
        s3_client = boto3.client("s3", region_name=AWS_REGION)
        logger.info("✅ S3 client initialized")
    
    if ssm_client is None:
        ssm_client = boto3.client("ssm", region_name=AWS_REGION)
        logger.info("✅ SSM client initialized")

def upload_images_to_s3(images: List[Dict], job_id: str) -> List[str]:
    """Upload images to S3 and return their keys."""
    s3_keys = []
    
    for idx, img_data in enumerate(images):
        filename = img_data["filename"]
        image_bytes = base64.b64decode(img_data["data"])
        
        # Create S3 key for the image
        s3_key = f"jobs/{job_id}/input/{idx:03d}_{filename}"
        
        try:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=s3_key,
                Body=image_bytes,
                ContentType=f"image/{filename.split('.')[-1]}"
            )
            s3_keys.append(s3_key)
            logger.info(f"✅ Uploaded {filename} to s3://{S3_BUCKET}/{s3_key}")
        except Exception as e:
            logger.error(f"❌ Failed to upload {filename}: {e}")
            raise
    
    return s3_keys

def create_user_data_script(job_id: str, s3_bucket: str, s3_keys: List[str]) -> str:
    """Create user data script for EC2 instance."""
    s3_keys_json = json.dumps(s3_keys)
    
    user_data = f"""#!/bin/bash
set -e

# Update system
apt-get update -y

# Install required packages
apt-get install -y python3-pip awscli docker.io nvidia-docker2

# Start Docker
systemctl start docker
systemctl enable docker

# Install NVIDIA drivers and CUDA (for g4dn instances)
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/x86_64/cuda-ubuntu2004.pin
mv cuda-ubuntu2004.pin /etc/apt/preferences.d/cuda-repository-pin-600
wget https://developer.download.nvidia.com/compute/cuda/12.2.0/local_installers/cuda-repo-ubuntu2004-12-2-local_12.2.0-535.54.03-1_amd64.deb
dpkg -i cuda-repo-ubuntu2004-12-2-local_12.2.0-535.54.03-1_amd64.deb
cp /var/cuda-repo-ubuntu2004-12-2-local/cuda-*-keyring.gpg /usr/share/keyrings/
apt-get update -y
apt-get install -y cuda-toolkit-12-2

# Set environment variables
export PATH=/usr/local/cuda-12.2/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.2/lib64:$LD_LIBRARY_PATH

# Install Python dependencies
pip3 install boto3 opencv-python torch torchvision insightface elasticsearch onnxruntime-gpu

# Create processing script
cat > /home/ubuntu/process_images.py << 'PYTHON_SCRIPT'
import os
import json
import uuid
import logging
import boto3
import cv2
import numpy as np
import torch
from pathlib import Path
from insightface.app import FaceAnalysis
from elasticsearch import Elasticsearch

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
S3_BUCKET = "{s3_bucket}"
JOB_ID = "{job_id}"
S3_KEYS = {s3_keys_json}
ES_HOST = os.environ.get("ES_HOST", "http://13.202.43.6:9200")
INDEX_NAME = "face_embeddings"

def setup_face_model():
    """Initialize face detection model with GPU."""
    logger.info("🤖 Loading face detection model on GPU...")
    
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Using device: {{DEVICE}}")
    
    face_app = FaceAnalysis(
        name="antelopev2",
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
    )
    face_app.prepare(ctx_id=0, det_thresh=0.35, det_size=(640, 640))
    
    logger.info("✅ Face model loaded successfully")
    return face_app

def process_job():
    """Main processing function."""
    s3_client = boto3.client("s3")
    es_client = Elasticsearch([ES_HOST], verify_certs=False)
    
    # Initialize face model
    face_app = setup_face_model()
    
    results = []
    
    for s3_key in S3_KEYS:
        try:
            logger.info(f"Processing {{s3_key}}...")
            
            # Download image from S3
            response = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
            image_data = response['Body'].read()
            
            # Decode image
            nparr = np.frombuffer(image_data, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            
            # Detect faces
            faces = face_app.get(img_rgb)
            num_faces = len(faces)
            
            logger.info(f"Detected {{num_faces}} faces in {{s3_key}}")
            
            # Create public URL for the image
            public_url = f"https://{{S3_BUCKET}}.s3.amazonaws.com/{{s3_key}}"
            
            indexed_faces = []
            
            # Index each face
            for idx, face in enumerate(faces):
                emb_vec = face.normed_embedding
                box_coords = face.bbox.tolist()
                
                face_id = f"{{Path(s3_key).stem}}_face_{{idx+1}}_{{uuid.uuid4().hex[:8]}}"
                
                doc = {{
                    "image_name": public_url,
                    "embeds": emb_vec.tolist(),
                    "box": box_coords
                }}
                
                try:
                    es_client.index(index=INDEX_NAME, id=face_id, document=doc)
                    indexed_faces.append({{
                        "face_id": face_id,
                        "bbox": box_coords
                    }})
                    logger.info(f"✅ Indexed face {{idx+1}} from {{s3_key}}")
                except Exception as e:
                    logger.error(f"❌ Failed to index face {{idx+1}}: {{e}}")
            
            result = {{
                "s3_key": s3_key,
                "public_url": public_url,
                "faces_detected": num_faces,
                "faces_indexed": len(indexed_faces),
                "faces": indexed_faces
            }}
            
            results.append(result)
            
        except Exception as e:
            logger.error(f"❌ Error processing {{s3_key}}: {{e}}")
            results.append({{
                "s3_key": s3_key,
                "error": str(e),
                "faces_detected": 0
            }})
    
    # Upload results to S3
    results_key = f"jobs/{{JOB_ID}}/results.json"
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=results_key,
        Body=json.dumps(results, indent=2),
        ContentType="application/json"
    )
    
    logger.info(f"✅ Job {{JOB_ID}} completed. Results uploaded to {{results_key}}")
    
    # Signal completion
    ssm_client = boto3.client("ssm")
    try:
        ssm_client.put_parameter(
            Name=f"/divinepic/jobs/{{JOB_ID}}/status",
            Value="completed",
            Type="String",
            Overwrite=True
        )
    except Exception as e:
        logger.error(f"Failed to update job status: {{e}}")

if __name__ == "__main__":
    process_job()
PYTHON_SCRIPT

# Make script executable
chmod +x /home/ubuntu/process_images.py

# Set environment variables for the script
echo "ES_HOST=http://13.202.43.6:9200" >> /etc/environment

# Run the processing script
cd /home/ubuntu
python3 process_images.py

# Signal completion and shutdown
aws ssm put-parameter --name "/divinepic/jobs/{job_id}/status" --value "completed" --type "String" --overwrite --region {AWS_REGION}

# Auto-shutdown after completion (optional)
shutdown -h +5
"""

    return user_data

def launch_gpu_instance(job_id: str, s3_keys: List[str]) -> str:
    """Launch g4dn.xlarge instance for image processing."""
    user_data = create_user_data_script(job_id, S3_BUCKET, s3_keys)
    
    launch_params = {
        'ImageId': EC2_AMI_ID,
        'InstanceType': 'g4dn.xlarge',
        'KeyName': EC2_KEY_PAIR,
        'SecurityGroupIds': [EC2_SECURITY_GROUP],
        'UserData': user_data,
        'MinCount': 1,
        'MaxCount': 1,
        'TagSpecifications': [
            {
                'ResourceType': 'instance',
                'Tags': [
                    {'Key': 'Name', 'Value': f'divinepic-processing-{job_id}'},
                    {'Key': 'Job', 'Value': job_id},
                    {'Key': 'Purpose', 'Value': 'face-detection'},
                    {'Key': 'AutoShutdown', 'Value': 'true'}
                ]
            }
        ],
        'IamInstanceProfile': {
            'Name': 'DivinePicEC2Role'  # You'll need to create this role
        }
    }
    
    # Add subnet if specified
    if EC2_SUBNET_ID:
        launch_params['SubnetId'] = EC2_SUBNET_ID
    
    try:
        response = ec2_client.run_instances(**launch_params)
        instance_id = response['Instances'][0]['InstanceId']
        
        logger.info(f"✅ Launched g4dn.xlarge instance: {instance_id}")
        
        # Create job status parameter
        ssm_client.put_parameter(
            Name=f"/divinepic/jobs/{job_id}/status",
            Value="processing",
            Type="String",
            Overwrite=True
        )
        
        ssm_client.put_parameter(
            Name=f"/divinepic/jobs/{job_id}/instance_id",
            Value=instance_id,
            Type="String",
            Overwrite=True
        )
        
        return instance_id
        
    except Exception as e:
        logger.error(f"❌ Failed to launch instance: {e}")
        raise

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler that orchestrates image processing using GPU instances.
    
    Expected event format:
    {
        "images": [
            {
                "filename": "image1.jpg", 
                "data": "base64_encoded_image_data"
            }
        ]
    }
    """
    try:
        initialize_clients()
        
        logger.info("⏳ Starting GPU-accelerated image processing orchestration...")
        
        # Validate input
        if "images" not in event:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "Missing 'images' in request body"
                })
            }
        
        images = event["images"]
        if not images:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "No images provided"
                })
            }
        
        # Generate unique job ID
        job_id = f"job_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        logger.info(f"🆔 Created job: {job_id} with {len(images)} images")
        
        # Upload images to S3
        s3_keys = upload_images_to_s3(images, job_id)
        
        # Launch GPU instance
        instance_id = launch_gpu_instance(job_id, s3_keys)
        
        response = {
            "message": "Image processing job started successfully",
            "job_id": job_id,
            "instance_id": instance_id,
            "images_count": len(images),
            "status": "processing",
            "estimated_completion": "5-10 minutes",
            "results_check_url": f"s3://{S3_BUCKET}/jobs/{job_id}/results.json"
        }
        
        logger.info(f"✅ Job {job_id} orchestration completed")
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(response)
        }
        
    except Exception as e:
        logger.error(f"❌ Orchestration failed: {e}")
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "message": "Failed to start image processing job"
            })
        } 