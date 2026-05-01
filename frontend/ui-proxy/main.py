# proxy.py
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx
from config import TARGET_BASE, HOST, PORT

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(request: Request, path: str):
    # Handle preflight requests
    if request.method == "OPTIONS":
        return Response(status_code=200)
    
    target_url = f"{TARGET_BASE}/{path}"

    # Prepare request
    method = request.method
    headers = dict(request.headers)
    body = await request.body()
    params = dict(request.query_params)

    # Remove host and origin headers to avoid conflicts
    headers.pop("host", None)
    headers.pop("origin", None)

    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.request(
            method=method,
            url=target_url,
            headers=headers,
            content=body,
            params=params
        )
    print(f"Proxied {method} request to {target_url} with status {resp.status_code}")
    
    # Return response with proper headers
    response_headers = dict(resp.headers)
    
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=response_headers
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)