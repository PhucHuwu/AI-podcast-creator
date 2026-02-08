import uvicorn
import os
from api import app

def run_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """
    Run the FastAPI application using Uvicorn.
    """
    print(f"Starting server at http://{host}:{port}")
    uvicorn.run("api:app", host=host, port=port, reload=reload)

if __name__ == "__main__":
    run_server()
