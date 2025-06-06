#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 Setting up EC2 instance permissions for Lambda ECR deployment...${NC}"

# Configuration
EC2_ROLE_NAME="DivinePicEC2Role"
LAMBDA_ROLE_NAME="DivinePicLambdaExecutionRole"
REPO_NAME="divinepic-face-detection"
REGION="ap-south-1"

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)

if [ -z "$ACCOUNT_ID" ]; then
    echo -e "${RED}❌ Failed to get AWS account ID. Please check if EC2 instance has IAM role attached.${NC}"
    echo -e "${YELLOW}💡 If running on EC2, make sure the instance has an IAM role with basic permissions.${NC}"
    exit 1
fi

echo -e "${BLUE}Account ID: $ACCOUNT_ID${NC}"

# Check if we're running on EC2
if curl -s --max-time 3 http://169.254.169.254/latest/meta-data/instance-id > /dev/null 2>&1; then
    INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
    echo -e "${BLUE}Running on EC2 instance: $INSTANCE_ID${NC}"
else
    echo -e "${YELLOW}⚠️  Not running on EC2 instance or metadata service unavailable${NC}"
fi

echo -e "${YELLOW}📝 Step 1: Creating EC2 IAM role with necessary permissions...${NC}"

# Create EC2 role if it doesn't exist
if aws iam get-role --role-name "$EC2_ROLE_NAME" >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  EC2 role '$EC2_ROLE_NAME' already exists. Updating policies...${NC}"
else
    aws iam create-role \
        --role-name "$EC2_ROLE_NAME" \
        --assume-role-policy-document file://ec2-trust-policy.json \
        --description "EC2 role for DivinePic Lambda deployment with ECR access" >/dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ EC2 role created successfully${NC}"
    else
        echo -e "${YELLOW}⚠️  EC2 role creation failed, it might already exist${NC}"
    fi
fi

# Attach policy to EC2 role
aws iam put-role-policy \
    --role-name "$EC2_ROLE_NAME" \
    --policy-name "DivinePicEC2DeploymentPolicy" \
    --policy-document file://ec2-iam-policy.json >/dev/null 2>&1

# Create instance profile if it doesn't exist
aws iam create-instance-profile --instance-profile-name "$EC2_ROLE_NAME" >/dev/null 2>&1
aws iam add-role-to-instance-profile --instance-profile-name "$EC2_ROLE_NAME" --role-name "$EC2_ROLE_NAME" >/dev/null 2>&1

echo -e "${GREEN}✅ EC2 role and permissions configured${NC}"

echo -e "${YELLOW}📝 Step 2: Creating Lambda execution role...${NC}"

# Create Lambda execution role
if aws iam get-role --role-name "$LAMBDA_ROLE_NAME" >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Lambda role '$LAMBDA_ROLE_NAME' already exists. Updating policies...${NC}"
else
    aws iam create-role \
        --role-name "$LAMBDA_ROLE_NAME" \
        --assume-role-policy-document file://lambda-trust-policy.json \
        --description "Execution role for DivinePic Lambda function with ECR access" >/dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Lambda execution role created successfully${NC}"
    else
        echo -e "${YELLOW}⚠️  Lambda role creation failed, it might already exist${NC}"
    fi
fi

# Attach policies to Lambda role
aws iam attach-role-policy \
    --role-name "$LAMBDA_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" >/dev/null 2>&1

aws iam put-role-policy \
    --role-name "$LAMBDA_ROLE_NAME" \
    --policy-name "DivinePicLambdaCustomPolicy" \
    --policy-document file://lambda-execution-role-policy.json >/dev/null 2>&1

echo -e "${GREEN}✅ Lambda execution role configured${NC}"

echo -e "${YELLOW}📝 Step 3: Creating ECR repository...${NC}"

# Create ECR repository if it doesn't exist
if aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo -e "${BLUE}ℹ️  ECR repository '$REPO_NAME' already exists${NC}"
else
    aws ecr create-repository \
        --repository-name "$REPO_NAME" \
        --region "$REGION" \
        --image-scanning-configuration scanOnPush=true >/dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ ECR repository created successfully${NC}"
    else
        echo -e "${RED}❌ Failed to create ECR repository${NC}"
        exit 1
    fi
fi

# Set ECR repository policy
aws ecr set-repository-policy \
    --repository-name "$REPO_NAME" \
    --policy-text file://ecr-repository-policy.json \
    --region "$REGION" >/dev/null 2>&1

echo -e "${GREEN}✅ ECR repository policy configured${NC}"

echo -e "${YELLOW}📝 Step 4: Installing Docker if not present...${NC}"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Installing Docker...${NC}"
    sudo apt-get update -qq
    sudo apt-get install -y docker.io
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker $USER
    echo -e "${GREEN}✅ Docker installed successfully${NC}"
    echo -e "${YELLOW}⚠️  Please logout and login again to use Docker without sudo${NC}"
else
    echo -e "${BLUE}ℹ️  Docker already installed${NC}"
fi

echo -e "${YELLOW}⏳ Waiting for role propagation (15 seconds)...${NC}"
sleep 15

# Display final information
LAMBDA_ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$LAMBDA_ROLE_NAME"
ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO_NAME"

echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo -e "${BLUE}📋 Configuration Details:${NC}"
echo -e "${BLUE}   • Lambda Role ARN: $LAMBDA_ROLE_ARN${NC}"
echo -e "${BLUE}   • ECR Repository: $ECR_URI${NC}"
echo -e "${BLUE}   • AWS Region: $REGION${NC}"
echo -e "${BLUE}   • AWS Account: $ACCOUNT_ID${NC}"

echo ""
echo -e "${YELLOW}🚀 Next Steps:${NC}"
echo -e "${BLUE}   1. Run: ./build-and-deploy-container.sh${NC}"
echo -e "${BLUE}   2. Or build manually with the ECR URI above${NC}"

echo ""
echo -e "${YELLOW}💡 If this is a new EC2 instance, you may need to:${NC}"
echo -e "${BLUE}   • Attach the IAM role '$EC2_ROLE_NAME' to this EC2 instance${NC}"
echo -e "${BLUE}   • Or ensure your EC2 instance has the necessary permissions${NC}" 