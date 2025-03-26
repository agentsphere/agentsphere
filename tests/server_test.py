import subprocess
import time
import requests

def test_server_startup():
    # Start the server in a subprocess
    process = subprocess.Popen(
        ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)  # Give the server time to start

    try:
        # Check if the server is running
        response = requests.get("http://127.0.0.1:8000/")
        assert response.status_code == 200
        assert response.json() == {"message": "Welcome to the FastAPI project!"}
    finally:
        # Terminate the server process
        process.terminate()
        process.wait()