# Use AWS Lambda Python 3.9 base image
FROM public.ecr.aws/lambda/python:3.9

# Install system dependencies
RUN yum update -y && \
    yum install -y \
    gcc \
    gcc-c++ \
    make \
    cmake \
    wget \
    unzip \
    git \
    && yum clean all

# Install Python dependencies
COPY requirements-container.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r requirements-container.txt

# Copy function code
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}/
COPY lambda_orchestrator.py ${LAMBDA_TASK_ROOT}/
COPY lambda_status_checker.py ${LAMBDA_TASK_ROOT}/

# Download and cache the InsightFace models to reduce cold start time
RUN python -c "\
import os; \
os.makedirs('/tmp/insightface_models', exist_ok=True); \
from insightface.app import FaceAnalysis; \
try: \
    app = FaceAnalysis(name='antelopev2', providers=['CPUExecutionProvider']); \
    app.prepare(ctx_id=-1, det_thresh=0.5, det_size=(640, 640)); \
    print('✅ InsightFace models cached successfully'); \
except Exception as e: \
    print(f'⚠️ Model caching failed: {e}'); \
"

# Set the CMD to your handler (this can be overridden in Lambda console)
CMD ["lambda_handler.lambda_handler"]
