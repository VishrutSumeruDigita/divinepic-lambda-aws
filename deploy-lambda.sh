#!/bin/bash

# ─── Lambda Deployment Script ───────────────────────────────────────────────────
echo "🚀 DivinePic Lambda Deployment Script"
echo "====================================="

# Check if required tools are installed
command -v npm >/dev/null 2>&1 || { echo "❌ npm is required but not installed. Aborting." >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required but not installed. Aborting." >&2; exit 1; }

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating template..."
    cat > .env << EOL
AWS_REGION=ap-south-1
S3_BUCKET_NAME=divinepic-test
ES_HOST=http://13.202.43.6:9200
EOL
    echo "📝 Please edit .env file with your actual values before deploying!"
    exit 1
fi

# Load environment variables
export $(cat .env | xargs)

echo "📋 Configuration:"
echo "   AWS Region: $AWS_REGION"
echo "   S3 Bucket: $S3_BUCKET_NAME"
echo "   ES Host: $ES_HOST"
echo ""

# Check if serverless is installed
if ! command -v serverless &> /dev/null; then
    echo "📦 Installing Serverless Framework..."
    npm install -g serverless
fi

# Install serverless plugins
if [ ! -d node_modules ]; then
    echo "📦 Installing Serverless plugins..."
    npm init -y
    npm install serverless-python-requirements
fi

# Validate S3 bucket exists
echo "🔍 Checking S3 bucket access..."
aws s3 ls s3://$S3_BUCKET_NAME/ >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "⚠️  Cannot access S3 bucket '$S3_BUCKET_NAME'. Creating it..."
    aws s3 mb s3://$S3_BUCKET_NAME --region $AWS_REGION
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create S3 bucket. Please check AWS credentials and permissions."
        exit 1
    fi
fi

# Create Elasticsearch index if it doesn't exist
echo "🔍 Checking Elasticsearch connection..."
curl -s "$ES_HOST/_cluster/health" >/dev/null
if [ $? -eq 0 ]; then
    echo "✅ Elasticsearch is accessible"
    
    # Create index if it doesn't exist
    curl -s -X PUT "$ES_HOST/face_embeddings" -H 'Content-Type: application/json' -d'
    {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "properties": {
                "image_name": {"type": "keyword"},
                "embeds": {"type": "dense_vector", "dims": 512, "index": true, "similarity": "cosine"},
                "box": {"type": "dense_vector", "dims": 4}
            }
        }
    }' >/dev/null 2>&1
else
    echo "⚠️  Cannot connect to Elasticsearch at $ES_HOST"
    echo "   The Lambda function will still deploy but face indexing may fail"
fi

echo ""
echo "🚀 Deploying Lambda function..."
echo "   This may take several minutes due to ML dependencies..."

# Deploy using serverless
serverless deploy --verbose

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Deployment successful!"
    echo ""
    echo "📝 Usage Instructions:"
    echo "====================="
    echo ""
    echo "1. Direct Lambda Invocation:"
    echo "   aws lambda invoke --function-name divinepic-lambda-dev-processImagesDirect \\"
    echo "   --payload '{\"images\":[{\"filename\":\"test.jpg\",\"data\":\"<base64_image_data>\"}]}' \\"
    echo "   response.json"
    echo ""
    echo "2. API Gateway Endpoint:"
    echo "   POST to the generated API Gateway URL"
    echo "   (Check the deployment output above for the exact URL)"
    echo ""
    echo "⚠️  Important Notes:"
    echo "   - Lambda cold starts may take 30-60 seconds due to ML model loading"
    echo "   - Maximum execution time is 15 minutes"
    echo "   - Consider using container images for better performance"
    echo "   - Monitor CloudWatch logs for debugging"
else
    echo "❌ Deployment failed. Check the error messages above."
    exit 1
fi 