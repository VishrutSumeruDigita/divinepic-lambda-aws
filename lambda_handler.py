import json
import logging

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Simple Lambda handler for testing."""
    try:
        logger.info("🚀 Lambda function invoked!")
        logger.info(f"Event: {json.dumps(event)}")
        
        # Handle Function URL events
        if "requestContext" in event:
            logger.info("📡 Function URL event detected")
            
            # Handle GET request
            if event.get("requestContext", {}).get("http", {}).get("method") == "GET":
                return {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "message": "🎉 DivinePic Face Detection API is LIVE!",
                        "status": "Active",
                        "endpoint": "POST /",
                        "usage": "Send JSON with 'images' array containing base64 image data"
                    })
                }
            
            # Handle POST request
            elif event.get("requestContext", {}).get("http", {}).get("method") == "POST":
                try:
                    body = event.get("body", "{}")
                    if event.get("isBase64Encoded", False):
                        import base64
                        body = base64.b64decode(body).decode('utf-8')
                    
                    data = json.loads(body)
                    
                    return {
                        "statusCode": 200,
                        "headers": {"Content-Type": "application/json"},
                        "body": json.dumps({
                            "message": "✅ POST request received successfully!",
                            "received_data": data,
                            "note": "Face detection processing will be implemented next"
                        })
                    }
                except Exception as e:
                    return {
                        "statusCode": 400,
                        "headers": {"Content-Type": "application/json"},
                        "body": json.dumps({
                            "error": f"Invalid request body: {str(e)}"
                        })
                    }
            
            else:
                return {
                    "statusCode": 405,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "error": "Method not allowed. Use GET or POST."
                    })
                }
        
        # Handle direct invocation
        else:
            logger.info("🎯 Direct invocation detected")
            return {
                "message": "Direct invocation successful!",
                "event_received": event
            }
            
    except Exception as e:
        logger.error(f"❌ Handler error: {e}")
        
        if "requestContext" in event:
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "error": f"Internal server error: {str(e)}"
                })
            }
        else:
            return {
                "error": str(e)
            } 