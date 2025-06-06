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

# Create a script to cache InsightFace models
RUN echo 'import os' > /tmp/cache_models.py && \
    echo 'os.makedirs("/tmp/insightface_models", exist_ok=True)' >> /tmp/cache_models.py && \
    echo 'from insightface.app import FaceAnalysis' >> /tmp/cache_models.py && \
    echo 'try:' >> /tmp/cache_models.py && \
    echo '    app = FaceAnalysis(name="antelopev2", providers=["CPUExecutionProvider"])' >> /tmp/cache_models.py && \
    echo '    app.prepare(ctx_id=-1, det_thresh=0.5, det_size=(640, 640))' >> /tmp/cache_models.py && \
    echo '    print("✅ InsightFace models cached successfully")' >> /tmp/cache_models.py && \
    echo 'except Exception as e:' >> /tmp/cache_models.py && \
    echo '    print(f"⚠️ Model caching failed: {e}")' >> /tmp/cache_models.py

# Run the script to cache models
RUN python /tmp/cache_models.py && rm /tmp/cache_models.py

# Set the CMD to your handler (this can be overridden in Lambda console)
CMD ["lambda_handler.lambda_handler"]
