import requests
import os
from dotenv import load_dotenv

load_dotenv()

MATCHIVE_API_URL = os.getenv("MATCHIVE_API_URL", "https://api.matchive.io.vn")
MATCHIVE_API_KEY = os.getenv("MATCHIVE_API_KEY", "")

def test_update():
    script_id = "01KFR5ZNEXE1J936J9BRCHFZ4J"
    url = f"{MATCHIVE_API_URL}/manager/lesson-manager/scripts/{script_id}"
    
    headers = {
        "accept": "*/*",
        "Content-Type": "application/json",
        "Authorization": f"Apikey {MATCHIVE_API_KEY}"
    }
    
    payload = {
        "videoUrl": "http://localhost:8000/api/v1/download?file=7a02abad-a10a-4e53-bc4b-e2c749661c43.mp4",
        "status": "WAIT_FOR_REVIEW"
    }
    
    print(f"URL: {url}")
    print(f"Headers: {headers}")
    print(f"Payload: {payload}")
    
    response = requests.put(url, headers=headers, json=payload)
    
    print(f"Status Code: {response.status_code}")
    try:
        print(f"Response Body: {response.json()}")
    except:
        print(f"Response Text (bytes): {response.content}")

if __name__ == "__main__":
    test_update()
