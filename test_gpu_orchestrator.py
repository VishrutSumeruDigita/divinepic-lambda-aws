#!/usr/bin/env python3
"""
Test script for the DivinePic GPU Orchestrator.
Tests both local simulation and deployed functions.
"""

import json
import base64
import time
import requests
import boto3
from pathlib import Path
from typing import Dict, Any

class GPUOrchestratorTester:
    def __init__(self, base_url: str = None, region: str = "ap-south-1"):
        self.base_url = base_url
        self.region = region
        self.lambda_client = boto3.client('lambda', region_name=region)
    
    def encode_image_to_base64(self, image_path: str) -> str:
        """Convert an image file to base64 string."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def test_local_orchestrator(self):
        """Test the orchestrator function locally."""
        print("🧪 Testing GPU Orchestrator locally...")
        
        try:
            from lambda_orchestrator import lambda_handler
        except ImportError:
            print("❌ Could not import lambda_orchestrator. Make sure you're in the right directory.")
            return None
        
        # Prepare test data
        test_image_path = "test_image.jpg"
        
        if not Path(test_image_path).exists():
            self.create_test_image()
        
        # Encode image to base64
        image_data = self.encode_image_to_base64(test_image_path)
        
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
                self.function_name = "test-orchestrator"
                self.memory_limit_in_mb = 512
                self.invoked_function_arn = "arn:aws:lambda:region:account:function:test"
                self.aws_request_id = "test-request-id"
        
        context = MockContext()
        
        try:
            result = lambda_handler(event, context)
            print("✅ Local orchestrator test successful!")
            print(json.dumps(result, indent=2))
            
            # Extract job_id for status checking
            body = json.loads(result.get('body', '{}'))
            job_id = body.get('job_id')
            return job_id
            
        except Exception as e:
            print(f"❌ Local orchestrator test failed: {e}")
            return None
    
    def test_deployed_orchestrator(self, function_name: str = None):
        """Test the deployed orchestrator function."""
        if not function_name:
            function_name = "divinepic-gpu-orchestrator-dev-orchestrator"
        
        print(f"🧪 Testing deployed orchestrator: {function_name}")
        
        # Prepare test data
        test_image_path = "test_image.jpg"
        
        if not Path(test_image_path).exists():
            self.create_test_image()
        
        # Encode image to base64
        image_data = self.encode_image_to_base64(test_image_path)
        
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
            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            response_payload = json.loads(response['Payload'].read().decode('utf-8'))
            
            print("✅ Deployed orchestrator test successful!")
            print(json.dumps(response_payload, indent=2))
            
            # Extract job_id
            body = json.loads(response_payload.get('body', '{}'))
            job_id = body.get('job_id')
            return job_id
            
        except Exception as e:
            print(f"❌ Deployed orchestrator test failed: {e}")
            return None
    
    def test_api_gateway(self, test_images: list = None):
        """Test via API Gateway endpoints."""
        if not self.base_url:
            print("❌ No API Gateway URL provided")
            return None
        
        print(f"🧪 Testing API Gateway: {self.base_url}")
        
        # Prepare test data
        if not test_images:
            test_image_path = "test_image.jpg"
            if not Path(test_image_path).exists():
                self.create_test_image()
            
            image_data = self.encode_image_to_base64(test_image_path)
            test_images = [
                {
                    "filename": "test_image.jpg",
                    "data": image_data
                }
            ]
        
        payload = {"images": test_images}
        
        try:
            response = requests.post(
                f"{self.base_url}/process-images",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print("✅ API Gateway test successful!")
                print(json.dumps(result, indent=2))
                return result.get('job_id')
            else:
                print(f"❌ API Gateway test failed: {response.status_code}")
                print(response.text)
                return None
                
        except Exception as e:
            print(f"❌ API Gateway test failed: {e}")
            return None
    
    def check_job_status(self, job_id: str, method: str = "api"):
        """Check the status of a processing job."""
        print(f"🔍 Checking status for job: {job_id}")
        
        if method == "api" and self.base_url:
            try:
                response = requests.get(f"{self.base_url}/job-status/{job_id}")
                if response.status_code == 200:
                    result = response.json()
                    print(f"✅ Job status retrieved via API")
                    print(json.dumps(result, indent=2))
                    return result
                else:
                    print(f"❌ Failed to get job status: {response.status_code}")
                    return None
            except Exception as e:
                print(f"❌ API status check failed: {e}")
                return None
        
        elif method == "lambda":
            try:
                function_name = "divinepic-gpu-orchestrator-dev-statusChecker"
                payload = {"job_id": job_id}
                
                response = self.lambda_client.invoke(
                    FunctionName=function_name,
                    InvocationType='RequestResponse',
                    Payload=json.dumps(payload)
                )
                
                response_payload = json.loads(response['Payload'].read().decode('utf-8'))
                body = json.loads(response_payload.get('body', '{}'))
                
                print(f"✅ Job status retrieved via Lambda")
                print(json.dumps(body, indent=2))
                return body
                
            except Exception as e:
                print(f"❌ Lambda status check failed: {e}")
                return None
    
    def monitor_job(self, job_id: str, max_wait_time: int = 1800):  # 30 minutes max
        """Monitor a job until completion or timeout."""
        print(f"👀 Monitoring job {job_id}...")
        
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            status_info = self.check_job_status(job_id)
            
            if status_info:
                status = status_info.get('status', 'unknown')
                print(f"⏱️  Job {job_id} status: {status}")
                
                if status == 'completed':
                    print(f"✅ Job {job_id} completed successfully!")
                    if 'results' in status_info:
                        self.display_results(status_info['results'])
                    return status_info
                
                elif status == 'error':
                    print(f"❌ Job {job_id} failed!")
                    return status_info
            
            # Wait before next check
            time.sleep(30)  # Check every 30 seconds
        
        print(f"⏰ Timeout waiting for job {job_id}")
        return None
    
    def display_results(self, results: list):
        """Display processing results in a readable format."""
        print("\n📊 Processing Results:")
        print("=" * 50)
        
        total_images = len(results)
        total_faces = sum(r.get('faces_detected', 0) for r in results)
        total_indexed = sum(r.get('faces_indexed', 0) for r in results)
        errors = [r for r in results if 'error' in r]
        
        print(f"Images processed: {total_images}")
        print(f"Faces detected: {total_faces}")
        print(f"Faces indexed: {total_indexed}")
        print(f"Errors: {len(errors)}")
        print()
        
        for idx, result in enumerate(results, 1):
            print(f"{idx}. {result.get('s3_key', 'Unknown')}")
            if 'error' in result:
                print(f"   ❌ Error: {result['error']}")
            else:
                faces = result.get('faces_detected', 0)
                indexed = result.get('faces_indexed', 0)
                print(f"   👥 Faces: {faces} detected, {indexed} indexed")
                if result.get('public_url'):
                    print(f"   🔗 URL: {result['public_url']}")
            print()
    
    def list_all_jobs(self):
        """List all recent jobs."""
        print("📋 Listing all recent jobs...")
        
        if self.base_url:
            try:
                response = requests.get(f"{self.base_url}/jobs")
                if response.status_code == 200:
                    result = response.json()
                    jobs = result.get('jobs', [])
                    
                    if jobs:
                        print(f"Found {len(jobs)} recent jobs:")
                        for job in jobs:
                            status = job.get('status', 'unknown')
                            job_id = job.get('job_id', 'unknown')
                            print(f"  • {job_id}: {status}")
                    else:
                        print("No recent jobs found")
                    
                    return jobs
                else:
                    print(f"❌ Failed to list jobs: {response.status_code}")
                    return []
            except Exception as e:
                print(f"❌ Failed to list jobs: {e}")
                return []
    
    def create_test_image(self):
        """Create a simple test image if none exists."""
        try:
            import cv2
            import numpy as np
            
            # Create a simple test image
            img = np.zeros((300, 300, 3), dtype=np.uint8)
            img[50:150, 50:150] = [0, 255, 0]  # Green rectangle
            img[150:250, 150:250] = [255, 0, 0]  # Blue rectangle
            
            cv2.imwrite("test_image.jpg", img)
            print("✅ Created test_image.jpg")
            
        except ImportError:
            print("❌ OpenCV not available. Please manually add a test image named 'test_image.jpg'")

def main():
    import sys
    
    print("🚀 DivinePic GPU Orchestrator Test Suite")
    print("========================================")
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python test_gpu_orchestrator.py local")
        print("  python test_gpu_orchestrator.py deployed [function_name]")
        print("  python test_gpu_orchestrator.py api <api_gateway_url>")
        print("  python test_gpu_orchestrator.py status <job_id> [api_url]")
        print("  python test_gpu_orchestrator.py monitor <job_id> [api_url]")
        print("  python test_gpu_orchestrator.py list [api_url]")
        sys.exit(1)
    
    test_type = sys.argv[1].lower()
    
    if test_type == "local":
        tester = GPUOrchestratorTester()
        job_id = tester.test_local_orchestrator()
        if job_id:
            print(f"\n🆔 Job ID: {job_id}")
    
    elif test_type == "deployed":
        function_name = sys.argv[2] if len(sys.argv) > 2 else None
        tester = GPUOrchestratorTester()
        job_id = tester.test_deployed_orchestrator(function_name)
        if job_id:
            print(f"\n🆔 Job ID: {job_id}")
            print("💡 You can monitor this job with:")
            print(f"   python test_gpu_orchestrator.py monitor {job_id}")
    
    elif test_type == "api":
        if len(sys.argv) < 3:
            print("❌ Please provide the API Gateway URL")
            sys.exit(1)
        
        api_url = sys.argv[2]
        tester = GPUOrchestratorTester(base_url=api_url)
        job_id = tester.test_api_gateway()
        if job_id:
            print(f"\n🆔 Job ID: {job_id}")
            print("💡 You can monitor this job with:")
            print(f"   python test_gpu_orchestrator.py monitor {job_id} {api_url}")
    
    elif test_type == "status":
        if len(sys.argv) < 3:
            print("❌ Please provide the job ID")
            sys.exit(1)
        
        job_id = sys.argv[2]
        api_url = sys.argv[3] if len(sys.argv) > 3 else None
        tester = GPUOrchestratorTester(base_url=api_url)
        tester.check_job_status(job_id, method="api" if api_url else "lambda")
    
    elif test_type == "monitor":
        if len(sys.argv) < 3:
            print("❌ Please provide the job ID")
            sys.exit(1)
        
        job_id = sys.argv[2]
        api_url = sys.argv[3] if len(sys.argv) > 3 else None
        tester = GPUOrchestratorTester(base_url=api_url)
        tester.monitor_job(job_id)
    
    elif test_type == "list":
        api_url = sys.argv[2] if len(sys.argv) > 2 else None
        tester = GPUOrchestratorTester(base_url=api_url)
        tester.list_all_jobs()
    
    else:
        print("❌ Invalid test type")
        sys.exit(1)

if __name__ == "__main__":
    main() 