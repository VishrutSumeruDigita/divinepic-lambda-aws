#!/bin/bash

# GPU Orchestration Deployment - Fast Processing
# Cost: ~$0.50-1.00 per GPU hour (g4dn.xlarge)
# Processing time: 5-10 seconds per image
# Lambda orchestrates GPU instances for batch processing

set -e

echo "⚡ DivinePic GPU Orchestrator - Fast Deployment"
echo "=============================================="

# Configuration
IAM_USER="divinepic-test-user"
FUNCTION_NAME="divinepic-gpu-orchestrator"
STATUS_FUNCTION="divinepic-gpu-status"
REGION="ap-south-1"
INSTANCE_TYPE="g4dn.xlarge"
KEY_NAME="divinepic-gpu-key"

echo "1️⃣ Creating GPU orchestration IAM policy..."

# Create comprehensive IAM policy for GPU orchestration
cat > gpu-orchestrator-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:RunInstances",
                "ec2:DescribeInstances",
                "ec2:TerminateInstances",
                "ec2:CreateTags",
                "ec2:DescribeImages",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeSubnets",
                "ec2:DescribeKeyPairs",
                "iam:PassRole",
                "s3:GetObject",
                "s3:PutObject",
                "s3:ListBucket",
                "ssm:PutParameter",
                "ssm:GetParameter",
                "ssm:DeleteParameter"
            ],
            "Resource": "*"
        }
    ]
}
EOF

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
GPU_POLICY_NAME="DivinepicGPUOrchestrator"
GPU_POLICY_ARN="arn:aws:iam::$ACCOUNT_ID:policy/$GPU_POLICY_NAME"

aws iam create-policy \
    --policy-name "$GPU_POLICY_NAME" \
    --policy-document file://gpu-orchestrator-policy.json \
    --description "GPU orchestration permissions for DivinePic" \
    2>/dev/null || echo "ℹ️  GPU policy already exists"

aws iam attach-user-policy \
    --user-name "$IAM_USER" \
    --policy-arn "$GPU_POLICY_ARN" \
    2>/dev/null || echo "ℹ️  GPU policy already attached"

echo "✅ GPU orchestration permissions configured"

echo "2️⃣ Creating SSH key pair for GPU instances..."

aws ec2 create-key-pair \
    --key-name "$KEY_NAME" \
    --query 'KeyMaterial' \
    --output text > "${KEY_NAME}.pem" 2>/dev/null || echo "ℹ️  Key pair already exists"

chmod 600 "${KEY_NAME}.pem" 2>/dev/null || true

echo "✅ SSH key pair ready"

echo "3️⃣ Creating security group for GPU instances..."

VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query 'Vpcs[0].VpcId' --output text)

SG_ID=$(aws ec2 create-security-group \
    --group-name "divinepic-gpu-sg" \
    --description "Security group for DivinePic GPU instances" \
    --vpc-id "$VPC_ID" \
    --query 'GroupId' \
    --output text 2>/dev/null || {
        aws ec2 describe-security-groups \
            --filters "Name=group-name,Values=divinepic-gpu-sg" \
            --query 'SecurityGroups[0].GroupId' \
            --output text
    })

# Allow SSH access (optional, for debugging)
aws ec2 authorize-security-group-ingress \
    --group-id "$SG_ID" \
    --protocol tcp \
    --port 22 \
    --cidr 0.0.0.0/0 \
    2>/dev/null || echo "ℹ️  SSH rule already exists"

echo "✅ Security group configured: $SG_ID"

echo "4️⃣ Creating IAM role for GPU instances..."

# Create instance role for GPU instances
cat > gpu-instance-trust-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "ec2.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF

cat > gpu-instance-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "ssm:PutParameter",
                "ssm:GetParameter"
            ],
            "Resource": "*"
        }
    ]
}
EOF

INSTANCE_ROLE_NAME="DivinepicGPUInstanceRole"

aws iam create-role \
    --role-name "$INSTANCE_ROLE_NAME" \
    --assume-role-policy-document file://gpu-instance-trust-policy.json \
    2>/dev/null || echo "ℹ️  Instance role already exists"

aws iam put-role-policy \
    --role-name "$INSTANCE_ROLE_NAME" \
    --policy-name "DivinepicGPUInstancePolicy" \
    --policy-document file://gpu-instance-policy.json \
    2>/dev/null || echo "ℹ️  Instance policy already attached"

aws iam create-instance-profile \
    --instance-profile-name "$INSTANCE_ROLE_NAME" \
    2>/dev/null || echo "ℹ️  Instance profile already exists"

aws iam add-role-to-instance-profile \
    --instance-profile-name "$INSTANCE_ROLE_NAME" \
    --role-name "$INSTANCE_ROLE_NAME" \
    2>/dev/null || echo "ℹ️  Role already in instance profile"

echo "✅ GPU instance IAM role configured"

echo "5️⃣ Deploying Lambda orchestrator function..."

# Create deployment package
zip -r gpu-orchestrator.zip lambda_orchestrator.py 2>/dev/null || echo "ℹ️  Creating new zip"

aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime python3.9 \
    --role "arn:aws:iam::$ACCOUNT_ID:role/lambda-execution-role" \
    --handler lambda_orchestrator.lambda_handler \
    --zip-file fileb://gpu-orchestrator.zip \
    --timeout 900 \
    --memory-size 256 \
    --environment Variables="{
        \"S3_BUCKET_NAME\":\"divinepic-test\",
        \"AWS_REGION\":\"$REGION\",
        \"INSTANCE_TYPE\":\"$INSTANCE_TYPE\",
        \"KEY_NAME\":\"$KEY_NAME\",
        \"SECURITY_GROUP_ID\":\"$SG_ID\",
        \"INSTANCE_PROFILE_ARN\":\"arn:aws:iam::$ACCOUNT_ID:instance-profile/$INSTANCE_ROLE_NAME\"
    }" \
    2>/dev/null || {
        echo "ℹ️  Orchestrator function exists, updating..."
        aws lambda update-function-code \
            --function-name "$FUNCTION_NAME" \
            --zip-file fileb://gpu-orchestrator.zip
    }

echo "6️⃣ Deploying status checker function..."

zip -r gpu-status.zip lambda_status_checker.py 2>/dev/null || echo "ℹ️  Creating status zip"

aws lambda create-function \
    --function-name "$STATUS_FUNCTION" \
    --runtime python3.9 \
    --role "arn:aws:iam::$ACCOUNT_ID:role/lambda-execution-role" \
    --handler lambda_status_checker.lambda_handler \
    --zip-file fileb://gpu-status.zip \
    --timeout 60 \
    --memory-size 128 \
    --environment Variables="{
        \"AWS_REGION\":\"$REGION\"
    }" \
    2>/dev/null || {
        echo "ℹ️  Status function exists, updating..."
        aws lambda update-function-code \
            --function-name "$STATUS_FUNCTION" \
            --zip-file fileb://gpu-status.zip
    }

echo "7️⃣ Creating public endpoints..."

ORCHESTRATOR_URL=$(aws lambda create-function-url-config \
    --function-name "$FUNCTION_NAME" \
    --cors '{
        "AllowCredentials": false,
        "AllowHeaders": ["*"],
        "AllowMethods": ["POST"],
        "AllowOrigins": ["*"],
        "MaxAge": 86400
    }' \
    --auth-type NONE \
    --query 'FunctionUrl' \
    --output text 2>/dev/null || {
        aws lambda get-function-url-config \
            --function-name "$FUNCTION_NAME" \
            --query 'FunctionUrl' \
            --output text
    })

STATUS_URL=$(aws lambda create-function-url-config \
    --function-name "$STATUS_FUNCTION" \
    --cors '{
        "AllowCredentials": false,
        "AllowHeaders": ["*"],
        "AllowMethods": ["GET"],
        "AllowOrigins": ["*"],
        "MaxAge": 86400
    }' \
    --auth-type NONE \
    --query 'FunctionUrl' \
    --output text 2>/dev/null || {
        aws lambda get-function-url-config \
            --function-name "$STATUS_FUNCTION" \
            --query 'FunctionUrl' \
            --output text
    })

echo "✅ GPU orchestrator deployment complete!"
echo ""
echo "⚡ COST ESTIMATE:"
echo "   GPU Instance: g4dn.xlarge = $0.526/hour"
echo "   Processing time: ~5-10 minutes per batch"
echo "   Cost per batch: ~$0.50-1.00"
echo "   Monthly cost (100 images): ~$15-25"
echo ""
echo "📍 Function Details:"
echo "   Orchestrator: $FUNCTION_NAME"
echo "   Status Checker: $STATUS_FUNCTION"
echo "   Orchestrator URL: $ORCHESTRATOR_URL"
echo "   Status URL: $STATUS_URL"
echo ""
echo "🧪 Submit job:"
echo "   curl -X POST '$ORCHESTRATOR_URL' \\"
echo "        -H 'Content-Type: multipart/form-data' \\"
echo "        -F 'files=@image1.jpg' \\"
echo "        -F 'files=@image2.jpg'"
echo ""
echo "📊 Check status:"
echo "   curl '$STATUS_URL?job_id=YOUR_JOB_ID'"

# Cleanup temporary files
rm -f gpu-orchestrator-policy.json gpu-instance-trust-policy.json gpu-instance-policy.json
rm -f gpu-orchestrator.zip gpu-status.zip 