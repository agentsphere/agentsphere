from multiprocessing import Process
import os
import time
import requests
import uvicorn

def run_server():
    os.environ["MILVUSDBFILE"] = "t1.db"
    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=8000)

def test_server_startup():
    server_process = Process(target=run_server, daemon=True)
    server_process.start()
    time.sleep(5)  # Allow time for the server to start

    try:
        response = requests.get("http://127.0.0.1:8000/")
        assert response.status_code == 200
        assert response.json() == {"message": "Welcome to the FastAPI project!"}
    finally:
        server_process.terminate()
        server_process.join()