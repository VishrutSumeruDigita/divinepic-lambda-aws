#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 Setting up Lambda ECR permissions...${NC}"

# Configuration
ROLE_NAME="DivinePicLambdaExecutionRole"
REPO_NAME="divinepic-face-detection"
REGION="ap-south-1"

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

if [ -z "$ACCOUNT_ID" ]; then
    echo -e "${RED}❌ Failed to get AWS account ID. Please check your AWS credentials.${NC}"
    exit 1
fi

echo -e "${BLUE}Account ID: $ACCOUNT_ID${NC}"

# Step 1: Create Lambda execution role
echo -e "${YELLOW}📝 Creating Lambda execution role...${NC}"

# Check if role already exists
if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Role '$ROLE_NAME' already exists. Updating policies...${NC}"
else
    # Create the role
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document file://lambda-trust-policy.json \
        --description "Execution role for DivinePic Lambda function with ECR access"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Lambda execution role created successfully${NC}"
    else
        echo -e "${RED}❌ Failed to create Lambda execution role${NC}"
        exit 1
    fi
fi

# Step 2: Attach managed policy for basic Lambda execution
echo -e "${YELLOW}📝 Attaching basic Lambda execution policy...${NC}"
aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

# Step 3: Create and attach custom policy for ECR and S3 access
echo -e "${YELLOW}📝 Creating custom policy for ECR and S3 access...${NC}"

POLICY_NAME="DivinePicLambdaCustomPolicy"
POLICY_ARN="arn:aws:iam::$ACCOUNT_ID:policy/$POLICY_NAME"

# Delete existing policy if it exists
aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" >/dev/null 2>&1

# Create inline policy
aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "$POLICY_NAME" \
    --policy-document file://lambda-execution-role-policy.json

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Custom policy attached successfully${NC}"
else
    echo -e "${RED}❌ Failed to attach custom policy${NC}"
    exit 1
fi

# Step 4: Set ECR repository policy
echo -e "${YELLOW}📝 Setting ECR repository policy...${NC}"

# Check if ECR repository exists
if aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo -e "${BLUE}ℹ️  ECR repository '$REPO_NAME' exists${NC}"
    
    # Set repository policy
    aws ecr set-repository-policy \
        --repository-name "$REPO_NAME" \
        --policy-text file://ecr-repository-policy.json \
        --region "$REGION"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ ECR repository policy set successfully${NC}"
    else
        echo -e "${RED}❌ Failed to set ECR repository policy${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ ECR repository '$REPO_NAME' does not exist. Please create it first.${NC}"
    exit 1
fi

# Step 5: Wait for role propagation
echo -e "${YELLOW}⏳ Waiting for IAM role propagation (30 seconds)...${NC}"
sleep 30

# Step 6: Display role ARN
ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"
echo -e "${GREEN}✅ Setup complete!${NC}"
echo -e "${BLUE}📋 Lambda execution role ARN: $ROLE_ARN${NC}"
echo -e "${BLUE}📋 ECR repository URI: $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO_NAME${NC}"

echo -e "${YELLOW}🚀 You can now deploy your Lambda function with the following role:${NC}"
echo -e "${BLUE}   --role $ROLE_ARN${NC}"

echo -e "${YELLOW}📄 Next steps:${NC}"
echo -e "${BLUE}   1. Build and push your Docker image to ECR${NC}"
echo -e "${BLUE}   2. Create Lambda function using the ECR image${NC}"
echo -e "${BLUE}   3. Use the role ARN printed above in your Lambda creation command${NC}" 