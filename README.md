# AgentSphere

AgentSphere is a FastAPI-based project designed for scalability and flexibility. It supports multiple environments (development, staging, production) and includes a robust logging setup, Docker support, and modular architecture.

---

## Features

- **FastAPI Framework**: High-performance Python web framework.
- **Environment-Specific Configurations**: Easily switch between `dev`, `staging`, and `prod` environments using .env files.
- **Docker Support**: Build and run the application in isolated containers.
- **Logging**: Configurable logging for debugging and production.
- **Modular Design**: Organized structure for routes, services, and models.
- **Health Check**: Built-in `/health` endpoint to verify the server status.

---

## Project Structure

```
agentsphere/
├── app/
│   ├── __init__.py
│   ├── main.py          # Entry point for the FastAPI app
│   ├── config.py        # Configuration and logger setup
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py    # API routes
│   ├── services/
│   │   ├── __init__.py
│   │   ├── example_service.py  # Example service
│   ├── models/
│       ├── __init__.py
│       ├── example.py   # Example model
├── tests/
│   ├── __init__.py
│   ├── test_main.py     # Tests for the main app
│   ├── test_server.py   # Tests for server startup
├── .env                 # Default environment variables
├── .env.dev             # Development environment variables
├── .env.staging         # Staging environment variables
├── .env.prod            # Production environment variables
├── Dockerfile           # Docker image definition
├── docker-compose.yml   # Docker Compose configuration
├── requirements.txt     # Python dependencies
├── README.md            # Project documentation
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Docker and Docker Compose

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/agentsphere.git
   cd agentsphere
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   - Copy .env to `.env.dev`, `.env.staging`, and `.env.prod` as needed.
   - Update the values for your environment.

---

## Running the Application

### Development
Run the application locally with hot-reloading:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker
Build and run the application using Docker:
```bash
docker-compose up --build
```

### Staging/Production
Run the application in staging or production mode:
```bash
docker-compose --env-file .env.staging up --build
docker-compose --env-file .env.prod up --build
```

---

## Endpoints

### Root Endpoint
- **GET `/`**
  - Returns a welcome message.

### Health Check
- **GET `/health`**
  - Returns the server status.

---

## Testing

Run the tests using `pytest`:
```bash
pytest tests/
```

---

## Logging

Logs are configured dynamically based on the environment:
- **Development**: `DEBUG` level logs.
- **Production**: `INFO` level logs.

Example log format:
```
2025-03-26 12:00:00 - INFO - AgentSphere - Root endpoint accessed
```

---

## Building the Docker Image

To build the Docker image manually:
```bash
docker build -t agentsphere .
```

---

## Contributing

Contributions are welcome! Please follow these steps:
1. Fork the repository.
2. Create a new branch (`feature/my-feature`).
3. Commit your changes.
4. Push to the branch and open a pull request.

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

Let me know if you need further adjustments!