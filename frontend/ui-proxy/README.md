# UI Proxy

A FastAPI-based reverse proxy for forwarding requests to a remote server locally.

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create `.env` file:
```bash
cp .env.example .env
```

3. Edit `.env` to configure your target server and port:
```
TARGET_BASE=https://staging.ai4inclusion.org
PORT=8000
HOST=127.0.0.1
```

## Running Locally

### Option 1: Using Uvicorn directly
```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Option 2: Using Python
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

## Configuration

- `TARGET_BASE`: The remote server URL to proxy requests to
- `PORT`: Local port to listen on (default: 8000)
- `HOST`: Local host to bind to (default: 127.0.0.1)

## Usage

Once running, access the proxied service at `http://localhost:8000`

All requests to `http://localhost:8000/*` will be forwarded to `TARGET_BASE/*`

## Example

If `TARGET_BASE=https://staging.ai4inclusion.org`:
- Request to `http://localhost:8000/api/v1/test` 
- → Proxied to `https://staging.ai4inclusion.org/api/v1/test`
