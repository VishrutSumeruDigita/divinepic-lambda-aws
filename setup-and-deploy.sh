#!/bin/bash

# Comprehensive setup and deployment script for DivinePic Lambda
set -e

echo "🚀 DivinePic Lambda Container Deployment"
echo "========================================"

# Configuration
IAM_USER="divinepic-test-user"
POLICY_NAME="DivinepicECRAccess" 
FUNCTION_NAME="divinepic-face-detection"
REGION="ap-south-1"
REPOSITORY_NAME="divinepic-lambda"

echo "1️⃣ Adding ECR permissions to IAM user..."

# Create and attach ECR policy
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
POLICY_ARN="arn:aws:iam::$ACCOUNT_ID:policy/$POLICY_NAME"

# Try to create policy (ignore if already exists)
aws iam create-policy \
    --policy-name "$POLICY_NAME" \
    --policy-document file://ecr-permissions-policy.json \
    --description "ECR permissions for DivinePic Lambda" \
    2>/dev/null || echo "ℹ️  Policy already exists"

# Attach policy to user
aws iam attach-user-policy \
    --user-name "$IAM_USER" \
    --policy-arn "$POLICY_ARN" \
    2>/dev/null || echo "ℹ️  Policy already attached"

echo "✅ ECR permissions configured"

echo "2️⃣ Creating ECR repository..."

# Create ECR repository
aws ecr create-repository \
    --repository-name "$REPOSITORY_NAME" \
    --region "$REGION" \
    2>/dev/null || echo "ℹ️  Repository already exists"

# Set lifecycle policy to keep only 3 images
aws ecr put-lifecycle-policy \
    --repository-name "$REPOSITORY_NAME" \
    --region "$REGION" \
    --lifecycle-policy-text '{
        "rules": [{
            "rulePriority": 1,
            "selection": {
                "tagStatus": "untagged",
                "countType": "imageCountMoreThan",
                "countNumber": 3
            },
            "action": { "type": "expire" }
        }]
    }' 2>/dev/null || echo "ℹ️  Lifecycle policy already exists"

echo "✅ ECR repository configured"

echo "3️⃣ Building Docker image..."

# Build the Docker image
docker build -t "$REPOSITORY_NAME" .

if [ $? -ne 0 ]; then
    echo "❌ Docker build failed"
    exit 1
fi

echo "✅ Docker image built successfully"

echo "4️⃣ Pushing to ECR..."

# Login to ECR
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# Tag and push image
ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPOSITORY_NAME:latest"
docker tag "$REPOSITORY_NAME:latest" "$ECR_URI"
docker push "$ECR_URI"

echo "✅ Image pushed to ECR"

echo "5️⃣ Creating Lambda function..."

# Create Lambda function
aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --package-type Image \
    --code ImageUri="$ECR_URI" \
    --role "arn:aws:iam::$ACCOUNT_ID:role/lambda-execution-role" \
    --timeout 900 \
    --memory-size 3008 \
    --environment Variables='{
        "S3_BUCKET_NAME":"divinepic-test",
        "AWS_REGION":"ap-south-1",
        "ES_HOST":"http://13.202.43.6:9200"
    }' \
    2>/dev/null || {
        echo "ℹ️  Function exists, updating code..."
        aws lambda update-function-code \
            --function-name "$FUNCTION_NAME" \
            --image-uri "$ECR_URI"
    }

echo "✅ Lambda function deployed"

echo "6️⃣ Creating Function URL for easy access..."

# Create function URL (public endpoint)
FUNCTION_URL=$(aws lambda create-function-url-config \
    --function-name "$FUNCTION_NAME" \
    --cors '{
        "AllowCredentials": false,
        "AllowHeaders": ["*"],
        "AllowMethods": ["POST", "GET"],
        "AllowOrigins": ["*"],
        "ExposeHeaders": ["*"],
        "MaxAge": 86400
    }' \
    --auth-type NONE \
    --query 'FunctionUrl' \
    --output text 2>/dev/null || {
        # Get existing URL if already created
        aws lambda get-function-url-config \
            --function-name "$FUNCTION_NAME" \
            --query 'FunctionUrl' \
            --output text
    })

echo "✅ Lambda deployment complete!"
echo ""
echo "📍 Function Details:"
echo "   Name: $FUNCTION_NAME"
echo "   URL:  $FUNCTION_URL"
echo "   Region: $REGION"
echo ""
echo "🧪 Test the function:"
echo "   curl -X POST '$FUNCTION_URL' -H 'Content-Type: application/json' -d '{\"test\": true}'"
echo ""
echo "📸 Upload images (see usage instructions below)" 