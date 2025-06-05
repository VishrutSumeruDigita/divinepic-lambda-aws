#!/bin/bash

# ─── Container Lambda Deployment Script ─────────────────────────────────────────
echo "🐳 DivinePic Container Lambda Deployment Script"
echo "==============================================="

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | xargs)
else
    echo "⚠️  .env file not found. Using defaults..."
fi

# Configuration
AWS_REGION=${AWS_REGION:-"ap-south-1"}
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPOSITORY="divinepic-lambda"
LAMBDA_FUNCTION_NAME="divinepic-face-detection"
IMAGE_TAG="latest"

echo "📋 Configuration:"
echo "   AWS Region: $AWS_REGION"
echo "   AWS Account: $AWS_ACCOUNT_ID"
echo "   ECR Repository: $ECR_REPOSITORY"
echo "   Lambda Function: $LAMBDA_FUNCTION_NAME"
echo ""

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if AWS CLI is configured
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo "❌ AWS CLI is not configured. Please run 'aws configure' first."
    exit 1
fi

# Create ECR repository if it doesn't exist
echo "📦 Creating ECR repository..."
aws ecr describe-repositories --repository-names $ECR_REPOSITORY --region $AWS_REGION >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "   Creating new repository: $ECR_REPOSITORY"
    aws ecr create-repository --repository-name $ECR_REPOSITORY --region $AWS_REGION
    
    # Set lifecycle policy to keep only recent images
    aws ecr put-lifecycle-policy --repository-name $ECR_REPOSITORY --region $AWS_REGION --lifecycle-policy-text '{
        "rules": [
            {
                "rulePriority": 1,
                "description": "Keep only 5 recent images",
                "selection": {
                    "tagStatus": "any",
                    "countType": "imageCountMoreThan",
                    "countNumber": 5
                },
                "action": {
                    "type": "expire"
                }
            }
        ]
    }'
else
    echo "   Repository already exists: $ECR_REPOSITORY"
fi

# Get ECR login token
echo "🔐 Logging into ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Build the Docker image
echo "🔨 Building Docker image..."
IMAGE_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG"

docker build -t $ECR_REPOSITORY:$IMAGE_TAG .

if [ $? -ne 0 ]; then
    echo "❌ Docker build failed"
    exit 1
fi

# Tag the image for ECR
docker tag $ECR_REPOSITORY:$IMAGE_TAG $IMAGE_URI

# Push the image to ECR
echo "📤 Pushing image to ECR..."
docker push $IMAGE_URI

if [ $? -ne 0 ]; then
    echo "❌ Docker push failed"
    exit 1
fi

echo "✅ Image pushed successfully: $IMAGE_URI"

# Create or update Lambda function
echo "⚡ Creating/updating Lambda function..."

# Check if function exists
aws lambda get-function --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION >/dev/null 2>&1
FUNCTION_EXISTS=$?

if [ $FUNCTION_EXISTS -eq 0 ]; then
    echo "   Updating existing function..."
    aws lambda update-function-code \
        --function-name $LAMBDA_FUNCTION_NAME \
        --image-uri $IMAGE_URI \
        --region $AWS_REGION
    
    # Update function configuration
    aws lambda update-function-configuration \
        --function-name $LAMBDA_FUNCTION_NAME \
        --timeout 900 \
        --memory-size 3008 \
        --environment "Variables={AWS_REGION=$AWS_REGION,S3_BUCKET_NAME=${S3_BUCKET_NAME:-divinepic-test},ES_HOST=${ES_HOST:-http://13.202.43.6:9200}}" \
        --region $AWS_REGION
        
else
    echo "   Creating new function..."
    
    # Create execution role if it doesn't exist
    ROLE_NAME="DivinePicLambdaRole"
    ROLE_ARN=$(aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text 2>/dev/null)
    
    if [ $? -ne 0 ]; then
        echo "   Creating IAM role..."
        
        # Create trust policy
        cat > trust-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "lambda.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF

        aws iam create-role \
            --role-name $ROLE_NAME \
            --assume-role-policy-document file://trust-policy.json
        
        # Attach policies
        aws iam attach-role-policy \
            --role-name $ROLE_NAME \
            --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
        
        aws iam attach-role-policy \
            --role-name $ROLE_NAME \
            --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
        
        # Create custom policy for Elasticsearch
        cat > lambda-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "es:ESHttpPost",
                "es:ESHttpPut"
            ],
            "Resource": "*"
        }
    ]
}
EOF

        aws iam create-policy \
            --policy-name DivinePicLambdaPolicy \
            --policy-document file://lambda-policy.json 2>/dev/null || true
        
        aws iam attach-role-policy \
            --role-name $ROLE_NAME \
            --policy-arn arn:aws:iam::$AWS_ACCOUNT_ID:policy/DivinePicLambdaPolicy
        
        # Wait for role to be ready
        echo "   Waiting for role to be ready..."
        sleep 10
        
        ROLE_ARN="arn:aws:iam::$AWS_ACCOUNT_ID:role/$ROLE_NAME"
        
        # Clean up temp files
        rm -f trust-policy.json lambda-policy.json
    fi
    
    # Create the Lambda function
    aws lambda create-function \
        --function-name $LAMBDA_FUNCTION_NAME \
        --code ImageUri=$IMAGE_URI \
        --role $ROLE_ARN \
        --package-type Image \
        --timeout 900 \
        --memory-size 3008 \
        --environment "Variables={AWS_REGION=$AWS_REGION,S3_BUCKET_NAME=${S3_BUCKET_NAME:-divinepic-test},ES_HOST=${ES_HOST:-http://13.202.43.6:9200}}" \
        --region $AWS_REGION
fi

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Lambda function deployed successfully!"
    echo ""
    echo "📝 Function Details:"
    echo "   Function Name: $LAMBDA_FUNCTION_NAME"
    echo "   Image URI: $IMAGE_URI"
    echo "   Region: $AWS_REGION"
    echo ""
    echo "🧪 Test the function:"
    echo "   aws lambda invoke --function-name $LAMBDA_FUNCTION_NAME \\"
    echo "   --payload '{\"images\":[{\"filename\":\"test.jpg\",\"data\":\"<base64_data>\"}]}' \\"
    echo "   --region $AWS_REGION response.json"
    echo ""
    echo "💡 Next steps:"
    echo "   1. Test the function using the AWS CLI or console"
    echo "   2. Create an API Gateway if you need HTTP endpoints"
    echo "   3. Set up monitoring and alerts"
    echo ""
    echo "💰 Estimated costs:"
    echo "   • Container image storage: ~$0.10/month"
    echo "   • Lambda execution: ~$0.20 per 1000 invocations"
    echo "   • Lambda compute: ~$0.0001667 per GB-second"
else
    echo "❌ Lambda function deployment failed"
    exit 1
fi 