#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 Creating Lambda execution role manually...${NC}"

ROLE_NAME="DivinePicLambdaExecutionRole"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo -e "${BLUE}Account ID: $ACCOUNT_ID${NC}"
echo -e "${BLUE}Creating role: $ROLE_NAME${NC}"

# Try to create the Lambda execution role
echo -e "${YELLOW}📝 Step 1: Creating Lambda execution role...${NC}"

aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document file://lambda-trust-policy.json \
    --description "Execution role for DivinePic Lambda function with ECR access"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Lambda execution role created successfully${NC}"
else
    echo -e "${RED}❌ Failed to create Lambda execution role${NC}"
    echo -e "${YELLOW}💡 This might be due to insufficient IAM permissions for user 'divinepic-test-user'${NC}"
    echo -e "${BLUE}Please ask your AWS administrator to:${NC}"
    echo -e "${BLUE}   1. Create the role 'DivinePicLambdaExecutionRole'${NC}"
    echo -e "${BLUE}   2. Use the trust policy in 'lambda-trust-policy.json'${NC}"
    echo -e "${BLUE}   3. Use the permissions in 'lambda-execution-role-policy.json'${NC}"
    echo -e "${BLUE}   4. Attach AWSLambdaBasicExecutionRole managed policy${NC}"
    exit 1
fi

# Step 2: Attach basic Lambda execution policy
echo -e "${YELLOW}📝 Step 2: Attaching basic Lambda execution policy...${NC}"
aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Basic execution policy attached${NC}"
else
    echo -e "${RED}❌ Failed to attach basic execution policy${NC}"
fi

# Step 3: Attach custom policy
echo -e "${YELLOW}📝 Step 3: Attaching custom policy for ECR and S3...${NC}"
aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "DivinePicLambdaCustomPolicy" \
    --policy-document file://lambda-execution-role-policy.json

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Custom policy attached${NC}"
else
    echo -e "${RED}❌ Failed to attach custom policy${NC}"
fi

# Wait for propagation
echo -e "${YELLOW}⏳ Waiting for role propagation (10 seconds)...${NC}"
sleep 10

# Verify role exists
aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"
    echo -e "${GREEN}✅ Role created and verified!${NC}"
    echo -e "${BLUE}Role ARN: $ROLE_ARN${NC}"
    echo ""
    echo -e "${YELLOW}🚀 Now you can run: ./build-and-deploy-container.sh${NC}"
else
    echo -e "${RED}❌ Role verification failed${NC}"
    exit 1
fi 