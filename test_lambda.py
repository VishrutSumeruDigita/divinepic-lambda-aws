#!/usr/bin/env python3
"""
Test script for the DivinePic Lambda function.
Can be used to test both locally and deployed Lambda functions.
"""

import json
import base64
import boto3
import requests
from pathlib import Path

def encode_image_to_base64(image_path: str) -> str:
    """Convert an image file to base64 string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def test_local_lambda():
    """Test the Lambda function locally."""
    print("🧪 Testing Lambda function locally...")
    
    # Import the lambda handler
    try:
        from lambda_handler import lambda_handler
    except ImportError:
        print("❌ Could not import lambda_handler. Make sure you're in the right directory.")
        return
    
    # Prepare test data (you need to have a test image)
    test_image_path = "test_image.jpg"  # Replace with actual test image
    
    if not Path(test_image_path).exists():
        print(f"❌ Test image '{test_image_path}' not found.")
        print("   Please add a test image file or update the path.")
        return
    
    # Encode image to base64
    image_data = encode_image_to_base64(test_image_path)
    
    # Create test event
    event = {
        "images": [
            {
                "filename": "test_image.jpg",
                "data": image_data
            }
        ]
    }
    
    # Mock context object
    class MockContext:
        def __init__(self):
            self.function_name = "test-function"
            self.memory_limit_in_mb = 3008
            self.invoked_function_arn = "arn:aws:lambda:region:account:function:test"
            self.aws_request_id = "test-request-id"
    
    context = MockContext()
    
    try:
        # Call the lambda handler
        result = lambda_handler(event, context)
        print("✅ Local test successful!")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"❌ Local test failed: {e}")

def test_deployed_lambda(function_name: str, region: str = "ap-south-1"):
    """Test the deployed Lambda function."""
    print(f"🧪 Testing deployed Lambda function: {function_name}")
    
    # Initialize boto3 client
    lambda_client = boto3.client('lambda', region_name=region)
    
    # Prepare test data
    test_image_path = "test_image.jpg"  # Replace with actual test image
    
    if not Path(test_image_path).exists():
        print(f"❌ Test image '{test_image_path}' not found.")
        print("   Please add a test image file or update the path.")
        return
    
    # Encode image to base64
    image_data = encode_image_to_base64(test_image_path)
    
    # Create test payload
    payload = {
        "images": [
            {
                "filename": "test_image.jpg",
                "data": image_data
            }
        ]
    }
    
    try:
        # Invoke the Lambda function
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        # Parse response
        response_payload = json.loads(response['Payload'].read().decode('utf-8'))
        
        print("✅ Deployed Lambda test successful!")
        print(json.dumps(response_payload, indent=2))
        
        # Check for errors
        if 'error' in response_payload:
            print(f"⚠️  Lambda returned an error: {response_payload['error']}")
        
    except Exception as e:
        print(f"❌ Deployed Lambda test failed: {e}")

def test_api_gateway(api_url: str):
    """Test the API Gateway endpoint."""
    print(f"🧪 Testing API Gateway endpoint: {api_url}")
    
    # Note: This is a simplified example
    # In practice, you'd need to handle multipart form data properly
    print("⚠️  API Gateway testing with multipart forms is complex.")
    print("   Consider using tools like Postman or curl for testing the HTTP endpoint.")
    print("   Or use the direct Lambda invocation method instead.")

def create_test_image():
    """Create a simple test image if none exists."""
    try:
        import cv2
        import numpy as np
        
        # Create a simple test image with a colored rectangle
        img = np.zeros((300, 300, 3), dtype=np.uint8)
        img[50:150, 50:150] = [0, 255, 0]  # Green rectangle
        img[150:250, 150:250] = [255, 0, 0]  # Blue rectangle
        
        cv2.imwrite("test_image.jpg", img)
        print("✅ Created test_image.jpg")
        
    except ImportError:
        print("❌ OpenCV not available. Please manually add a test image named 'test_image.jpg'")

if __name__ == "__main__":
    import sys
    
    print("🚀 DivinePic Lambda Test Suite")
    print("=============================")
    
    # Check if test image exists, create one if not
    if not Path("test_image.jpg").exists():
        print("📸 No test image found. Creating one...")
        create_test_image()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python test_lambda.py local                    # Test locally")
        print("  python test_lambda.py deployed <function_name> # Test deployed function")
        print("  python test_lambda.py api <api_gateway_url>    # Test API Gateway")
        sys.exit(1)
    
    test_type = sys.argv[1].lower()
    
    if test_type == "local":
        test_local_lambda()
    elif test_type == "deployed":
        if len(sys.argv) < 3:
            print("❌ Please provide the Lambda function name")
            print("   Example: python test_lambda.py deployed divinepic-lambda-dev-processImagesDirect")
            sys.exit(1)
        function_name = sys.argv[2]
        test_deployed_lambda(function_name)
    elif test_type == "api":
        if len(sys.argv) < 3:
            print("❌ Please provide the API Gateway URL")
            sys.exit(1)
        api_url = sys.argv[2]
        test_api_gateway(api_url)
    else:
        print("❌ Invalid test type. Use 'local', 'deployed', or 'api'")
        sys.exit(1) 