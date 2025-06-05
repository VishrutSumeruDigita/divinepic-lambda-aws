#!/bin/bash

# CPU-Only Lambda Deployment - Cheap and Simple
# Cost: ~$0.0001 per 100ms execution + storage
# Processing time: 30-60 seconds per image
# Memory: 1024MB (sufficient for CPU processing)

set -e

echo "💰 DivinePic CPU Lambda - Cheap Deployment"
echo "=========================================="

# Configuration
IAM_USER="divinepic-test-user"
POLICY_NAME="DivinepicECRAccess" 
FUNCTION_NAME="divinepic-cpu-detection"
REGION="ap-south-1"
REPOSITORY_NAME="divinepic-cpu-lambda"

echo "1️⃣ Adding ECR permissions..."

# Create and attach ECR policy
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
POLICY_ARN="arn:aws:iam::$ACCOUNT_ID:policy/$POLICY_NAME"

aws iam create-policy \
    --policy-name "$POLICY_NAME" \
    --policy-document file://ecr-permissions-policy.json \
    --description "ECR permissions for DivinePic Lambda" \
    2>/dev/null || echo "ℹ️  Policy already exists"

aws iam attach-user-policy \
    --user-name "$IAM_USER" \
    --policy-arn "$POLICY_ARN" \
    2>/dev/null || echo "ℹ️  Policy already attached"

echo "✅ ECR permissions configured"

echo "2️⃣ Creating ECR repository..."

aws ecr create-repository \
    --repository-name "$REPOSITORY_NAME" \
    --region "$REGION" \
    2>/dev/null || echo "ℹ️  Repository already exists"

echo "✅ ECR repository ready"

echo "3️⃣ Building CPU-optimized Docker image..."

# Build lightweight CPU image
docker build -f Dockerfile.cpu -t "$REPOSITORY_NAME" .

if [ $? -ne 0 ]; then
    echo "❌ Docker build failed"
    exit 1
fi

echo "✅ CPU Docker image built"

echo "4️⃣ Pushing to ECR..."

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPOSITORY_NAME:latest"
docker tag "$REPOSITORY_NAME:latest" "$ECR_URI"
docker push "$ECR_URI"

echo "✅ Image pushed to ECR"

echo "5️⃣ Creating CPU Lambda function..."

# Create CPU-optimized Lambda (lower memory = lower cost)
aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --package-type Image \
    --code ImageUri="$ECR_URI" \
    --role "arn:aws:iam::$ACCOUNT_ID:role/lambda-execution-role" \
    --timeout 300 \
    --memory-size 1024 \
    --environment Variables='{
        "S3_BUCKET_NAME":"divinepic-test",
        "AWS_REGION":"ap-south-1",
        "ES_HOST":"http://13.202.43.6:9200",
        "PROCESSING_MODE":"cpu"
    }' \
    2>/dev/null || {
        echo "ℹ️  Function exists, updating..."
        aws lambda update-function-code \
            --function-name "$FUNCTION_NAME" \
            --image-uri "$ECR_URI"
    }

echo "6️⃣ Creating public endpoint..."

FUNCTION_URL=$(aws lambda create-function-url-config \
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

echo "✅ CPU Lambda deployment complete!"
echo ""
echo "💰 COST ESTIMATE:"
echo "   Memory: 1024MB = $0.0000166667 per 100ms"
echo "   Processing time: ~30-60 sec per image"
echo "   Cost per image: ~$0.005-0.01"
echo "   Monthly cost (100 images): ~$0.50-1.00"
echo ""
echo "📍 Function Details:"
echo "   Name: $FUNCTION_NAME"
echo "   URL:  $FUNCTION_URL"
echo "   Mode: CPU-only processing"
echo ""
echo "🧪 Test with:"
echo "   curl -X POST '$FUNCTION_URL' \\"
echo "        -H 'Content-Type: multipart/form-data' \\"
echo "        -F 'files=@your-image.jpg'" 