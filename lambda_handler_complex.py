import json
import os
import uuid
import time
import logging
import base64
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Any
import boto3
import cv2
import numpy as np
import torch
from insightface.app import FaceAnalysis
from elasticsearch import Elasticsearch

# ─── Setup logging ──────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── Environment variables ──────────────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "divinepic-test")
ES_HOST = os.environ.get("ES_HOST", "http://13.202.43.6:9200")
INDEX_NAME = "face_embeddings"

# ─── Global variables (for model caching between invocations) ──────────────────
face_app = None
s3_client = None
es_client = None

def initialize_clients():
    """Initialize AWS and Elasticsearch clients."""
    global s3_client, es_client
    
    if s3_client is None:
        s3_client = boto3.client("s3", region_name=AWS_REGION)
        logger.info("✅ S3 client initialized")
    
    if es_client is None:
        es_client = Elasticsearch([ES_HOST], verify_certs=False)
        try:
            info = es_client.info()
            version = info.get("version", {}).get("number", "<unknown>")
            logger.info(f"✅ Connected to Elasticsearch - version {version}")
        except Exception as e:
            logger.error(f"⚠️ Could not connect to Elasticsearch: {e}")

def get_face_model():
    """Get or initialize the face detection model (cached for warm starts)."""
    global face_app
    
    if face_app is None:
        logger.info("🤖 Loading face detection model...")
        try:
            DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Using device: {DEVICE}")

            face_app = FaceAnalysis(
                name="antelopev2", 
                providers=["CPUExecutionProvider"] if DEVICE == "cpu" else ["CUDAExecutionProvider"]
            )
            face_app.prepare(ctx_id=0 if DEVICE == "cuda" else -1, det_thresh=0.35, det_size=(640, 640))
            logger.info("✅ Face model loaded successfully")
        except Exception as e:
            logger.error(f"❌ Error loading face model: {e}")
            raise
    
    return face_app

def extract_date_from_filename(filename: str) -> str:
    """Extract date from filename and return formatted date string."""
    try:
        parts = filename.split("_")
        if len(parts) < 2:
            # If no timestamp in filename, use current time
            ts_ms = int(time.time() * 1000)
        else:
            ts_ms = int(parts[1])
        dt = time.strftime("%d_%b_%Y", time.gmtime(ts_ms / 1000.0))
        return dt.upper()
    except (ValueError, IndexError):
        # Fallback to current date if parsing fails
        dt = time.strftime("%d_%b_%Y", time.gmtime())
        return dt.upper()

def upload_image_to_s3(image_data: bytes, filename: str) -> str:
    """Upload image to S3 and return public URL."""
    try:
        date_str = extract_date_from_filename(filename)
        unique_id = uuid.uuid4().hex[:6]
        new_name = f"{date_str}_{unique_id}_{filename}"
        s3_key = new_name

        s3_client.put_object(
            Bucket=S3_BUCKET, 
            Key=s3_key, 
            Body=image_data, 
            ContentType=f"image/{Path(filename).suffix.lstrip('.')}"
        )

        public_url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
        logger.info(f"✅ Uploaded to S3: {public_url}")
        return public_url
    except Exception as e:
        logger.error(f"⚠️ Failed to upload '{filename}' to S3: {e}")
        raise

def process_single_image(image_data: bytes, filename: str) -> Dict[str, Any]:
    """Process a single image and return results."""
    try:
        # Upload to S3
        s3_url = upload_image_to_s3(image_data, filename)
        
        # Convert bytes to OpenCV image
        nparr = np.frombuffer(image_data, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img_bgr is None:
            return {
                "filename": filename,
                "s3_url": s3_url,
                "faces_detected": 0,
                "error": "Could not decode image"
            }
        
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        
        # Get face model and detect faces
        face_model = get_face_model()
        faces = face_model.get(img_rgb)
        num_faces = len(faces)
        
        logger.info(f"Detected {num_faces} faces in '{filename}'")
        
        indexed_faces = []
        
        # Index each face to Elasticsearch
        for idx, face in enumerate(faces):
            emb_vec = face.normed_embedding
            box_coords = face.bbox.tolist()
            
            face_id = f"{Path(filename).stem}_face_{idx+1}_{uuid.uuid4().hex[:8]}"
            
            doc = {
                "image_name": s3_url,
                "embeds": emb_vec.tolist(),
                "box": box_coords
            }
            
            try:
                es_client.index(index=INDEX_NAME, id=face_id, document=doc)
                indexed_faces.append({
                    "face_id": face_id,
                    "bbox": box_coords
                })
                logger.info(f"✅ Indexed face {idx+1} from '{filename}'")
            except Exception as e:
                logger.error(f"❌ Failed to index face {idx+1}: {e}")
        
        return {
            "filename": filename,
            "s3_url": s3_url,
            "faces_detected": num_faces,
            "faces_indexed": len(indexed_faces),
            "faces": indexed_faces
        }
        
    except Exception as e:
        logger.error(f"⚠️ Error processing '{filename}': {e}")
        return {
            "filename": filename,
            "error": str(e),
            "faces_detected": 0
        }

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for processing image uploads.
    
    Handles both Function URL events and direct invocations.
    """
    try:
        # Initialize clients
        initialize_clients()
        
        logger.info("⏳ Starting Lambda image processing...")
        logger.info(f"Event keys: {list(event.keys())}")
        
        # Handle Function URL events
        if "requestContext" in event and "http" in event["requestContext"]:
            # This is a Function URL event
            logger.info("📡 Processing Function URL request")
            
            if event.get("httpMethod") == "GET" or event["requestContext"]["http"]["method"] == "GET":
                return {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "message": "DivinePic Face Detection API",
                        "status": "Active",
                        "usage": "POST with JSON body containing 'images' array"
                    })
                }
            
            # Parse request body
            try:
                if event.get("isBase64Encoded", False):
                    body = base64.b64decode(event["body"]).decode('utf-8')
                else:
                    body = event.get("body", "{}")
                
                request_data = json.loads(body)
                
                if "images" not in request_data:
                    return {
                        "statusCode": 400,
                        "headers": {"Content-Type": "application/json"},
                        "body": json.dumps({
                            "error": "Missing 'images' array in request body"
                        })
                    }
                
                images = request_data["images"]
                
            except Exception as e:
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "error": f"Invalid JSON in request body: {str(e)}"
                    })
                }
        
        # Handle direct Lambda invocation
        elif "images" in event:
            logger.info("🎯 Processing direct invocation")
            images = event["images"]
            
        else:
            error_msg = "Invalid event format. Expected Function URL event or direct invocation with 'images' array."
            logger.error(error_msg)
            
            # Return appropriate error format
            if "requestContext" in event:
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"error": error_msg})
                }
            else:
                return {"error": error_msg}
        
        # Process images
        results = []
        for img_data in images:
            filename = img_data["filename"]
            try:
                image_bytes = base64.b64decode(img_data["data"])
                result = process_single_image(image_bytes, filename)
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing {filename}: {e}")
                results.append({
                    "filename": filename,
                    "error": f"Failed to decode image: {str(e)}",
                    "faces_detected": 0
                })
        
        # Calculate summary statistics
        total_images = len(results)
        total_faces = sum(r.get("faces_detected", 0) for r in results)
        total_indexed = sum(r.get("faces_indexed", 0) for r in results)
        errors = [r for r in results if "error" in r]
        
        response = {
            "message": "Images processed successfully",
            "summary": {
                "total_images": total_images,
                "total_faces_detected": total_faces,
                "total_faces_indexed": total_indexed,
                "errors": len(errors)
            },
            "results": results
        }
        
        logger.info(f"✅ Processed {total_images} images, detected {total_faces} faces, indexed {total_indexed}")
        
        # Return appropriate format based on event type
        if "requestContext" in event:
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(response)
            }
        else:
            return response
            
    except Exception as e:
        logger.error(f"❌ Lambda handler error: {e}")
        error_response = {
            "error": str(e),
            "message": "Failed to process images"
        }
        
        if "requestContext" in event:
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(error_response)
            }
        else:
            return error_response 