# 🚀 EC2 Deployment Guide for DivinePic Lambda

This guide walks you through deploying the DivinePic face detection Lambda function using a container image built on an EC2 instance.

## 📋 Prerequisites

1. **EC2 Instance** with Ubuntu/Amazon Linux
2. **IAM Role** attached to EC2 instance (will be created by setup script)
3. **AWS CLI** installed and configured
4. **Docker** (will be installed by setup script)

## 🔧 Step 1: Initial Setup

First, run the setup script to configure all necessary permissions:

```bash
chmod +x setup-ec2-permissions.sh
./setup-ec2-permissions.sh
```

This script will:
- ✅ Create EC2 IAM role with deployment permissions
- ✅ Create Lambda execution role with ECR access
- ✅ Create ECR repository
- ✅ Install Docker if needed
- ✅ Configure all necessary policies

**Important:** If Docker was installed for the first time, you may need to logout and login again, or run:
```bash
sudo systemctl restart docker
sudo usermod -aG docker $USER
newgrp docker
```

## 🏗️ Step 2: Build and Deploy

Run the deployment script:

```bash
chmod +x build-and-deploy-container.sh
./build-and-deploy-container.sh
```

This will:
- 🔨 Build the Docker container with face detection model
- 📤 Push to ECR repository  
- ⚡ Create/update Lambda function
- 🔗 Configure function URL for HTTP access

## 📊 Expected Output

```
🔧 Setting up EC2 instance permissions for Lambda ECR deployment...
Account ID: 123456789012
Running on EC2 instance: i-1234567890abcdef0
✅ EC2 role and permissions configured
✅ Lambda execution role configured  
✅ ECR repository created successfully
✅ Setup complete!

📋 Configuration Details:
   • Lambda Role ARN: arn:aws:iam::123456789012:role/DivinePicLambdaExecutionRole
   • ECR Repository: 123456789012.dkr.ecr.ap-south-1.amazonaws.com/divinepic-face-detection
   • AWS Region: ap-south-1
   • AWS Account: 123456789012
```

## 🧪 Step 3: Test the Function

### Option 1: AWS CLI Test
```bash
aws lambda invoke \
  --function-name divinepic-face-detection \
  --payload '{"images":[{"filename":"test.jpg","data":"<base64_encoded_image>"}]}' \
  --region ap-south-1 \
  response.json

cat response.json
```

### Option 2: HTTP Endpoint Test
If function URL is created, you can send HTTP requests:
```bash
curl -X POST "https://your-function-url.lambda-url.ap-south-1.on.aws/" \
  -H "Content-Type: application/json" \
  -d '{"images":[{"filename":"test.jpg","data":"<base64_data>"}]}'
```

## 🔐 IAM Permissions Created

### EC2 Role (`DivinePicEC2Role`)
- ECR: Full access for pushing images
- Lambda: Full access for function management  
- IAM: Role creation and policy management
- S3: Access to divinepic-test bucket
- Logging: CloudWatch logs access

### Lambda Execution Role (`DivinePicLambdaExecutionRole`)
- ECR: Image pulling permissions
- S3: Access to divinepic-test bucket
- Logs: CloudWatch logging
- Basic Lambda execution permissions

## 📁 Files Created

- `ec2-iam-policy.json` - EC2 instance permissions
- `ec2-trust-policy.json` - EC2 role trust relationship
- `lambda-execution-role-policy.json` - Lambda runtime permissions
- `lambda-trust-policy.json` - Lambda role trust relationship
- `ecr-repository-policy.json` - ECR access policy
- `setup-ec2-permissions.sh` - Automated setup script

## 🚨 Troubleshooting

### Permission Errors
```
An error occurred (AccessDeniedException) when calling the CreateFunction operation
```

**Solution:** Ensure the EC2 instance has the `DivinePicEC2Role` attached:
1. Go to EC2 Console → Instances
2. Select your instance → Actions → Security → Modify IAM role
3. Attach `DivinePicEC2Role`

### Docker Permission Errors
```
permission denied while trying to connect to the Docker daemon socket
```

**Solution:**
```bash
sudo usermod -aG docker $USER
newgrp docker
# Or logout and login again
```

### ECR Login Issues
```
no basic auth credentials
```

**Solution:** Re-run the ECR login:
```bash
aws ecr get-login-password --region ap-south-1 | \
docker login --username AWS --password-stdin \
123456789012.dkr.ecr.ap-south-1.amazonaws.com
```

## 💰 Cost Estimation

### Container Storage (ECR)
- ~$0.10/month for storing the container image

### Lambda Execution
- **Memory:** 3008 MB (maximum)
- **Timeout:** 15 minutes maximum
- **Cost per invocation:** ~$0.25-0.50 depending on execution time
- **Free tier:** 1M requests and 400,000 GB-seconds per month

### Example Monthly Costs
- **100 requests/month:** ~$0.10-0.20
- **1,000 requests/month:** ~$1.00-2.50  
- **10,000 requests/month:** ~$25-50

## 🔍 Monitoring

### CloudWatch Logs
- Function logs: `/aws/lambda/divinepic-face-detection`
- Error tracking and performance monitoring

### CloudWatch Metrics
- Invocation count
- Duration
- Error rate
- Throttles

## 🚀 Next Steps

1. **API Gateway:** Add REST API endpoints
2. **Authentication:** Add API keys or IAM auth
3. **Monitoring:** Set up CloudWatch alarms
4. **CI/CD:** Automate deployments with GitHub Actions
5. **Scaling:** Configure reserved concurrency if needed

## 📚 Additional Resources

- [AWS Lambda Container Images](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html)
- [ECR User Guide](https://docs.aws.amazon.com/AmazonECR/latest/userguide/)
- [Lambda Pricing](https://aws.amazon.com/lambda/pricing/) 