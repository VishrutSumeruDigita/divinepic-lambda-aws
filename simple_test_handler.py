import json

def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Simple test handler working",
            "event_received": event
        })
    } 