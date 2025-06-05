# DivinePic Lambda Function Guide

This guide explains how to convert your FastAPI application to an AWS Lambda function for serverless face detection and embedding processing.

## 🏗️ Architecture Overview

### Original FastAPI vs Lambda

| Aspect | FastAPI | Lambda |
|--------|---------|---------|
| **Hosting** | Always running server | Serverless, pay-per-use |
| **Scaling** | Manual/container scaling | Automatic scaling |
| **Background Tasks** | FastAPI BackgroundTasks | Not supported directly |
| **Model Loading** | Once at startup | Per cold start (cached) |
| **File Upload** | Direct multipart upload | Base64 encoded or S3 events |
| **Cost** | Fixed server costs | Pay only for execution time |

### Lambda Benefits
- ✅ **Cost Effective**: Pay only when processing images
- ✅ **Auto Scaling**: Handles traffic spikes automatically
- ✅ **No Server Management**: AWS manages infrastructure
- ✅ **Built-in Monitoring**: CloudWatch logs and metrics

### Lambda Limitations
- ❌ **Cold Starts**: First invocation takes 30-60 seconds
- ❌ **15 Min Timeout**: Maximum execution time
- ❌ **Memory Limit**: Max 10GB RAM (we use 3GB)
- ❌ **Package Size**: 250MB deployment package limit

## 📁 Files Overview

```
├── app.py                  # Original FastAPI application
├── lambda_handler.py       # Lambda function handler
├── requirements-lambda.txt # Minimal dependencies for Lambda
├── serverless.yml         # Serverless Framework config
├── deploy-lambda.sh       # Deployment script
├── test_lambda.py         # Testing utilities
└── README-Lambda.md       # This guide
```

## 🔧 Key Changes for Lambda

### 1. **Model Loading Strategy**
```python
# Original: Model loaded once at startup
face_app = FaceAnalysis(...)

# Lambda: Lazy loading with caching
face_app = None
def get_face_model():
    global face_app
    if face_app is None:
        face_app = FaceAnalysis(...)
    return face_app
```

### 2. **File Handling**
```python
# Original: Temporary files on disk
with open(image_path, "wb") as buffer:
    buffer.write(await uploaded_file.read())

# Lambda: In-memory processing
nparr = np.frombuffer(image_data, np.uint8)
img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
```

### 3. **Background Tasks**
```python
# Original: FastAPI background tasks
background_tasks.add_task(process_images, image_paths)

# Lambda: Synchronous processing or SQS/Step Functions
results = []
for image in images:
    result = process_single_image(image)
    results.append(result)
```

## 🚀 Deployment Options

### Option 1: Serverless Framework (Recommended)

1. **Install Prerequisites**:
```bash
npm install -g serverless
npm install serverless-python-requirements
```

2. **Configure Environment**:
```bash
cp .env.example .env
# Edit .env with your AWS credentials and settings
```

3. **Deploy**:
```bash
chmod +x deploy-lambda.sh
./deploy-lambda.sh
```

### Option 2: AWS SAM

1. **Install SAM CLI**:
```bash
pip install aws-sam-cli
```

2. **Create SAM template** (sam-template.yaml):
```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  ImageProcessingFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: .
      Handler: lambda_handler.lambda_handler
      Runtime: python3.9
      MemorySize: 3008
      Timeout: 900
      Environment:
        Variables:
          S3_BUCKET_NAME: !Ref S3Bucket
```

3. **Deploy**:
```bash
sam build
sam deploy --guided
```

### Option 3: Container Images (For Large Dependencies)

1. **Create Dockerfile**:
```dockerfile
FROM public.ecr.aws/lambda/python:3.9

# Copy requirements and install dependencies
COPY requirements-lambda.txt ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements-lambda.txt

# Copy function code
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}

CMD ["lambda_handler.lambda_handler"]
```

2. **Build and Deploy**:
```bash
docker build -t divinepic-lambda .
aws ecr create-repository --repository-name divinepic-lambda
# Tag and push to ECR, then create Lambda function
```

## 🧪 Testing

### Local Testing
```bash
python test_lambda.py local
```

### Testing Deployed Function
```bash
python test_lambda.py deployed divinepic-lambda-dev-processImagesDirect
```

### API Gateway Testing
```bash
curl -X POST https://your-api-gateway-url/upload-images \
  -H "Content-Type: multipart/form-data" \
  -F "files=@test_image.jpg"
```

## 📊 Performance Considerations

### Memory Configuration
- **1GB**: Basic processing, small images
- **2GB**: Medium workload, multiple images
- **3GB**: Recommended for ML models (current setting)
- **10GB**: Maximum, for very large images or batch processing

### Timeout Settings
- **30s**: Quick face detection
- **300s**: Multiple images processing
- **900s**: Maximum (15 minutes) for large batches

### Cold Start Optimization
1. **Provisioned Concurrency**: Keep instances warm
```yaml
ProvisionedConcurrencyConfig:
  ProvisionedConcurrencyEnabled: true
  ProvisionedConcurrency: 2
```

2. **Container Images**: Faster than ZIP packages for large dependencies

3. **Model Caching**: Store models in `/tmp` or use EFS

## 💰 Cost Estimation

### Lambda Pricing (ap-south-1 region)
- **Requests**: $0.0000002 per request
- **Compute**: $0.0000166667 per GB-second

### Example Costs
| Scenario | Memory | Duration | Monthly Requests | Cost/Month |
|----------|--------|----------|------------------|------------|
| Light usage | 1GB | 10s | 1,000 | $0.17 |
| Medium usage | 3GB | 30s | 10,000 | $15.00 |
| Heavy usage | 3GB | 60s | 100,000 | $300.00 |

### Cost Optimization Tips
1. **Right-size memory**: Don't over-provision
2. **Optimize dependencies**: Use minimal packages
3. **Batch processing**: Process multiple images per invocation
4. **Monitor usage**: Use CloudWatch to track costs

## 🔍 Monitoring and Debugging

### CloudWatch Logs
```bash
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/divinepic
aws logs tail /aws/lambda/divinepic-lambda-dev-processImages --follow
```

### Key Metrics to Monitor
- **Duration**: Function execution time
- **Memory Usage**: Peak memory consumption
- **Error Rate**: Failed invocations
- **Cold Start**: First invocation latency

### Common Issues and Solutions

#### 1. **Cold Start Timeout**
```
Task timed out after 30.00 seconds
```
**Solution**: Increase timeout to 900s, use provisioned concurrency

#### 2. **Memory Errors**
```
Runtime exited with error: signal: killed
```
**Solution**: Increase memory allocation

#### 3. **Package Too Large**
```
Unzipped size must be smaller than 262144000 bytes
```
**Solution**: Use container images or Lambda layers

#### 4. **Model Loading Errors**
```
InsightFace model not found
```
**Solution**: Ensure antelopev2 models are included in deployment

## 🔄 Migration Strategy

### Phase 1: Parallel Deployment
1. Keep FastAPI running
2. Deploy Lambda for testing
3. Compare results and performance

### Phase 2: Gradual Migration
1. Route 10% of traffic to Lambda
2. Monitor performance and costs
3. Gradually increase Lambda usage

### Phase 3: Full Migration
1. Route all traffic to Lambda
2. Decommission FastAPI server
3. Implement cost monitoring

## 🚨 Production Considerations

### Security
- Use IAM roles with minimal permissions
- Enable VPC if accessing private resources
- Encrypt environment variables

### Reliability
- Implement retry logic for failed uploads
- Use DLQ (Dead Letter Queue) for failed invocations
- Monitor and alert on error rates

### Scalability
- Set reserved concurrency limits
- Use SQS for async processing if needed
- Consider Step Functions for complex workflows

## 📚 Additional Resources

- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/)
- [Serverless Framework Documentation](https://www.serverless.com/framework/docs/)
- [Lambda Performance Optimization](https://docs.aws.amazon.com/lambda/latest/operatorguide/performance-optimization.html)
- [Lambda Container Images](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html) 