#!/usr/bin/env python3
"""
Batch-process all images in a local folder and index face embeddings to Elasticsearch:
1. Extract the millisecond timestamp from each filename and rename.
2. Upload images to S3.
3. Run face detection + embeddings using InsightFace with antelopev2.
4. Index embeddings into Elasticsearch with face bounding box info.
5. Log all events with timestamp and message.
"""

import os
import uuid
import time
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import boto3
import torch
import cv2
import numpy as np
from tqdm import tqdm
from elasticsearch import Elasticsearch
from insightface.app import FaceAnalysis

import traceback

# ─── Setup logging to console and log file ───────────────────────────────────────
log_file_path = "logs.txt"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file_path)
    ]
)
logger = logging.getLogger(__name__)

# ─── Load AWS credentials & config from .env ────────────────────────────────────
load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
S3_BUCKET = os.getenv("S3_BUCKET_NAME", "divinepic-test")

# ─── Local folder containing images to process ─────────────────────────────────
INPUT_DIR = "/home/amarjeet/Desktop/2/divinepic_gallery_emb_setup/Gallery"

# ─── Elasticsearch cluster endpoints ─────────────────────────────────────────
ES_HOSTS = [
    "http://13.202.43.6:9200",   # Remote ES host
    "http://localhost:9200"      # Local ES host
]

INDEX_NAME = "face_embeddings"

# ─── Validate that INPUT_DIR exists ────────────────────────────────────────────
if not os.path.isdir(INPUT_DIR):
    logger.error(f"Input directory '{INPUT_DIR}' does not exist or is not a folder.")
    raise ValueError(f"Input directory '{INPUT_DIR}' does not exist or is not a folder.")

if not S3_BUCKET:
    logger.error("S3 bucket name not provided. Set S3_BUCKET_NAME in .env or edit the script.")
    raise ValueError("S3 bucket name not provided.")

# ─── Initialize AWS S3 client ──────────────────────────────────────────────────
s3_client = boto3.client("s3", region_name=AWS_REGION)

# ─── Elasticsearch setup ────────────────────────────────────────────────────────
es_clients = []
for host in ES_HOSTS:
    client = Elasticsearch([host], verify_certs=False)
    try:
        info = client.info()
        version = info.get("version", {}).get("number", "<unknown>")
        logger.info(f"✅ Connected to Elasticsearch at {host} — version {version}")
    except Exception as e:
        logger.error(f"⚠️ Could not connect to Elasticsearch at {host}: {e}")
    es_clients.append((client, host))

def create_index_on_both():
    """Ensure the Elasticsearch index exists and create it if necessary."""
    mapping_body = {
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "properties": {
                "image_name": {"type": "keyword"},
                "embeds": {"type": "dense_vector", "dims": 512, "index": True, "similarity": "cosine"},
                "box": {"type": "dense_vector", "dims": 4}
            }
        }
    }

    for client, host in es_clients:
        try:
            if client.indices.exists(index=INDEX_NAME):
                logger.info(f"ℹ️ Index '{INDEX_NAME}' already exists on {host}")
            else:
                logger.info(f"🚀 Creating index '{INDEX_NAME}' on {host}")
                client.indices.create(index=INDEX_NAME, body=mapping_body)
                logger.info(f"✅ Index '{INDEX_NAME}' created successfully on {host}")
        except Exception as e:
            logger.error(f"❌ Failed to create index on {host}: {e}")

def setup_face_model():
    """Initialize antelopev2 face detection and recognition model."""
    logger.info("🤖 Loading antelopev2 face model...")

    try:
        # Define DEVICE (use CUDA if available, else CPU)
        DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {DEVICE}")

        # Set the environment variable for model path explicitly
        os.environ['INSIGHTFACE_MODEL_PATH'] = '/root/.insightface/models/antelopev2'


        # Manually load the model files in the model path
        model_files = [
            'genderage.onnx', 
            '2d106det.onnx', 
            '1k3d68.onnx', 
            'glintr100.onnx', 
            'scrfd_10g_bnkps.onnx'
        ]

        # Manually set the paths for models to ensure they are loaded
        model_paths = [os.path.join(os.environ['INSIGHTFACE_MODEL_PATH'], f) for f in model_files]
        for path in model_paths:
            if not os.path.exists(path):
                logger.error(f"❌ Model file {path} not found.")
                raise FileNotFoundError(f"Model file {path} not found.")

        # Initialize detector with antelopev2 model
        detector = FaceAnalysis(name='antelopev2', providers=["CPUExecutionProvider"] if DEVICE == "cpu" else ["CUDAExecutionProvider"])
        detector.prepare(ctx_id=-1, det_thresh=0.35, det_size=(640, 640))

        logger.info("✅ antelopev2 model loaded successfully")
        return detector

    except Exception as e:
        logger.error(f"❌ Error loading face model: {str(e)}")
        logger.error(f"Stacktrace: {traceback.format_exc()}")
        return None

# ─── Extract date from filename ────────────────────────────────────────────────
def extract_date_from_filename(filename: str) -> str:
    """Extract date from filename and return formatted date string (DD_MON_YYYY)."""
    parts = filename.split("_")
    if len(parts) < 2:
        logger.error(f"Unexpected format: {filename}")
        raise ValueError(f"Unexpected format: {filename}")
    try:
        ts_ms = int(parts[1])
    except ValueError:
        logger.error(f"'{parts[1]}' is not a valid millisecond timestamp in {filename}")
        raise ValueError(f"'{parts[1]}' is not a valid millisecond timestamp in {filename}")

    dt = datetime.utcfromtimestamp(ts_ms / 1000.0)
    return dt.strftime("%d_%b_%Y").upper()

def upload_image_flat(local_path: str) -> str:
    """Upload image to S3 and return public URL."""
    orig_name = Path(local_path).name
    date_str = extract_date_from_filename(orig_name)
    unique_id = uuid.uuid4().hex[:6]
    new_name = f"{date_str}_{unique_id}_{orig_name}"
    s3_key = new_name

    with open(local_path, "rb") as f:
        raw = f.read()

    try:
        s3_client.put_object(
            Bucket=S3_BUCKET, Key=s3_key, Body=raw, ContentType=f"image/{Path(orig_name).suffix.lstrip('.')}"
        )
    except Exception as e:
        logger.error(f"⚠️ Failed to upload '{local_path}' to S3: {e}")
        raise

    public_url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
    return public_url

def process_and_index_image(image_path: str, face_app):
    """Process image, upload to S3, run face detection, and index to Elasticsearch."""
    try:
        # Upload image to S3
        s3_url = upload_image_flat(image_path)
    except Exception as e:
        logger.error(f"⚠️ Failed to upload image '{image_path}' to S3: {e}")
        return

    # Read image and run face detection
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        logger.warning(f"⚠️ Could not read image '{image_path}' (skipping).")
        return
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    faces = face_app.get(img_rgb)
    num_faces = len(faces)
    
    # Log the number of faces detected for each image
    logger.info(f"Detected {num_faces} faces in '{Path(image_path).name}'.")

    if not faces:
        logger.info(f"ℹ️  No faces detected in '{Path(image_path).name}'. Uploaded → {s3_url}")
        return

    # Index each face to Elasticsearch
    for idx, face in enumerate(faces):
        emb_vec = face.normed_embedding
        box_coords = face.bbox.tolist()

        # Generate a unique face ID
        face_id = f"{Path(image_path).stem}_face_{idx+1}_{uuid.uuid4().hex[:8]}"
        
        # Create the Elasticsearch document for this face
        doc = {
            "image_name": s3_url,
            "embeds": emb_vec.tolist(),
            "box": box_coords
        }

        # Index the face into Elasticsearch
        for client, host in es_clients:
            try:
                client.index(index=INDEX_NAME, id=face_id, document=doc)
                logger.info(f"✅ Indexed face {idx+1} from '{Path(image_path).name}' into Elasticsearch ({host})")
            except Exception as e:
                logger.error(f"❌ Failed to index face {idx+1} from '{Path(image_path).name}' into ES ({host}): {e}")
    
    # Log S3 URL and the number of faces detected
    logger.info(f"Uploaded to S3: {s3_url} with {num_faces} face(s) indexed into Elasticsearch.")



# ─── Main flow ─────────────────────────────────────────────────────────────────
def main():
    create_index_on_both()

    # Setup the face model
    face_app = setup_face_model()
    if not face_app:
        logger.error("❌ Face model loading failed. Exiting.")
        return

    # Gather all image files under INPUT_DIR
    valid_exts = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp")
    all_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(valid_exts)]
    if not all_files:
        logger.info(f"ℹ️  No images found under '{INPUT_DIR}'. Exiting.")
        return

    logger.info(f"🔍 Found {len(all_files)} image(s) in '{INPUT_DIR}'. Beginning processing...\n")
    time.sleep(0.5)

    # Process each image with a tqdm progress bar
    for image_name in tqdm(all_files, desc="Processing images"):
        full_path = os.path.join(INPUT_DIR, image_name)
        try:
            process_and_index_image(full_path, face_app)
        except KeyboardInterrupt:
            logger.info("\n🚨 Interrupted by user. Exiting.")
            return
        except Exception as e:
            logger.error(f"⚠️ Unexpected error while processing '{image_name}': {e}")

    logger.info("\n🏁 All done.")

if __name__ == "__main__":
    main()
