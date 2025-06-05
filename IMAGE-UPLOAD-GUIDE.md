# DivinePic Lambda - Image Upload Guide

## Two Deployment Options

### 💰 CPU Lambda (Cheap Option)
- **Cost**: ~$0.005-0.01 per image
- **Processing Time**: 30-60 seconds per image
- **Best For**: Low volume, budget-conscious processing

### ⚡ GPU Orchestrator (Fast Option)
- **Cost**: ~$0.50-1.00 per batch (5-10 images)
- **Processing Time**: 5-10 seconds per image
- **Best For**: High volume, fast processing needs

## How to Upload Images

### Method 1: Single Image Upload (CPU Lambda)

```bash
# Replace YOUR_CPU_LAMBDA_URL with your actual CPU function URL
curl -X POST 'YOUR_CPU_LAMBDA_URL' \
  -H 'Content-Type: multipart/form-data' \
  -F 'files=@/path/to/your/image.jpg'
```

**Example Response:**
```json
{
  "message": "Images processed successfully",
  "results": [
    {
      "image_name": "https://divinepic-test.s3.ap-south-1.amazonaws.com/image.jpg",
      "faces_detected": 2,
      "face_embeddings": [
        {
          "face_id": "face_1_abc123",
          "bounding_box": [100, 150, 200, 250],
          "embedding_indexed": true
        }
      ]
    }
  ],
  "processing_time": "45.3 seconds",
  "cost_estimate": "$0.008"
}
```

### Method 2: Multiple Images Upload (CPU Lambda)

```bash
curl -X POST 'YOUR_CPU_LAMBDA_URL' \
  -H 'Content-Type: multipart/form-data' \
  -F 'files=@image1.jpg' \
  -F 'files=@image2.jpg' \
  -F 'files=@image3.jpg'
```

### Method 3: Batch Processing (GPU Orchestrator)

**Step 1: Submit Job**
```bash
curl -X POST 'YOUR_GPU_ORCHESTRATOR_URL' \
  -H 'Content-Type: multipart/form-data' \
  -F 'files=@image1.jpg' \
  -F 'files=@image2.jpg' \
  -F 'files=@image3.jpg' \
  -F 'files=@image4.jpg' \
  -F 'files=@image5.jpg'
```

**Response:**
```json
{
  "job_id": "job_abc123def456",
  "status": "submitted",
  "images_count": 5,
  "estimated_processing_time": "5-10 minutes",
  "estimated_cost": "$0.75"
}
```

**Step 2: Check Status**
```bash
curl 'YOUR_GPU_STATUS_URL?job_id=job_abc123def456'
```

**Status Response:**
```json
{
  "job_id": "job_abc123def456",
  "status": "processing", // submitted, processing, completed, failed
  "progress": "3/5 images processed",
  "estimated_completion": "2024-01-15T10:35:00Z",
  "results_available": false
}
```

**Final Results:**
```json
{
  "job_id": "job_abc123def456",
  "status": "completed",
  "results": [
    {
      "image_name": "https://divinepic-test.s3.ap-south-1.amazonaws.com/image1.jpg",
      "faces_detected": 3,
      "processing_time": "2.1 seconds"
    }
  ],
  "total_processing_time": "8.5 minutes",
  "total_cost": "$0.73"
}
```

## Programming Examples

### Python Example (CPU Lambda)

```python
import requests

def upload_images_cpu(lambda_url, image_paths):
    files = []
    for path in image_paths:
        files.append(('files', (path, open(path, 'rb'), 'image/jpeg')))
    
    response = requests.post(lambda_url, files=files)
    
    # Close file handles
    for _, (_, file_obj, _) in files:
        file_obj.close()
    
    return response.json()

# Usage
cpu_url = "https://your-cpu-lambda-url/"
images = ["photo1.jpg", "photo2.jpg"]
result = upload_images_cpu(cpu_url, images)
print(result)
```

### Python Example (GPU Orchestrator)

```python
import requests
import time

def submit_gpu_job(orchestrator_url, image_paths):
    files = []
    for path in image_paths:
        files.append(('files', (path, open(path, 'rb'), 'image/jpeg')))
    
    response = requests.post(orchestrator_url, files=files)
    
    # Close file handles
    for _, (_, file_obj, _) in files:
        file_obj.close()
    
    return response.json()

def check_job_status(status_url, job_id):
    response = requests.get(f"{status_url}?job_id={job_id}")
    return response.json()

def wait_for_completion(status_url, job_id, max_wait=600):
    start_time = time.time()
    while time.time() - start_time < max_wait:
        status = check_job_status(status_url, job_id)
        
        if status['status'] == 'completed':
            return status
        elif status['status'] == 'failed':
            raise Exception(f"Job failed: {status}")
        
        print(f"Status: {status['status']} - {status.get('progress', 'Processing...')}")
        time.sleep(10)  # Check every 10 seconds
    
    raise TimeoutError("Job did not complete within the expected time")

# Usage
orchestrator_url = "https://your-gpu-orchestrator-url/"
status_url = "https://your-gpu-status-url/"
images = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]

# Submit job
job = submit_gpu_job(orchestrator_url, images)
print(f"Job submitted: {job['job_id']}")

# Wait for completion
result = wait_for_completion(status_url, job['job_id'])
print("Job completed:", result)
```

### JavaScript/Node.js Example

```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

async function uploadImagesCPU(lambdaUrl, imagePaths) {
    const form = new FormData();
    
    imagePaths.forEach(path => {
        form.append('files', fs.createReadStream(path));
    });
    
    const response = await axios.post(lambdaUrl, form, {
        headers: form.getHeaders()
    });
    
    return response.data;
}

// Usage
const cpuUrl = 'https://your-cpu-lambda-url/';
const images = ['photo1.jpg', 'photo2.jpg'];

uploadImagesCPU(cpuUrl, images)
    .then(result => console.log(result))
    .catch(error => console.error('Error:', error));
```

## Cost Comparison

| Method | Processing Time | Cost per Image | Best For |
|--------|-----------------|----------------|----------|
| CPU Lambda | 30-60 seconds | $0.005-0.01 | 1-10 images, budget-conscious |
| GPU Orchestrator | 5-10 seconds | $0.10-0.20 | 10+ images, time-sensitive |

## File Format Support

- **Supported**: JPG, JPEG, PNG, WEBP
- **Max File Size**: 10MB per image
- **Max Batch Size**: 
  - CPU Lambda: 5 images
  - GPU Orchestrator: 50 images

## Error Handling

Common error responses:

```json
{
  "error": "File too large",
  "message": "Image size exceeds 10MB limit",
  "max_size": "10MB"
}
```

```json
{
  "error": "Unsupported format",
  "message": "Only JPG, PNG, WEBP formats are supported",
  "supported_formats": ["jpg", "jpeg", "png", "webp"]
}
```

```json
{
  "error": "No faces detected",
  "message": "No faces found in the uploaded images",
  "suggestion": "Ensure images contain clear, visible faces"
}
```

## Monitoring & Debugging

- **CPU Lambda Logs**: Check AWS CloudWatch logs for function `divinepic-cpu-detection`
- **GPU Orchestrator Logs**: Check CloudWatch logs for `divinepic-gpu-orchestrator`
- **Cost Monitoring**: Use AWS Cost Explorer to track spending
- **Performance**: Monitor function duration and memory usage in CloudWatch 