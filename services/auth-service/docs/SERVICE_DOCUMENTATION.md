# Auth Service - Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Features](#features)
4. [Prerequisites](#prerequisites)
5. [Installation & Setup](#installation--setup)
6. [Configuration](#configuration)
7. [API Reference](#api-reference)
8. [Authentication Flow](#authentication-flow)
9. [OAuth2 Integration](#oauth2-integration)
10. [Usage Examples](#usage-examples)
11. [Deployment](#deployment)
12. [Troubleshooting](#troubleshooting)
13. [Development](#development)

---

## Overview

The **Auth Service** is a microservice responsible for identity management, authentication, and authorization across the platform. It provides JWT-based authentication, OAuth2 provider integration, role-based access control (RBAC), API key management, and session management.

### Key Capabilities

- **User Registration & Authentication**: User signup, login, password management
- **JWT Token Management**: Access and refresh token generation and validation
- **OAuth2 Integration**: Google, GitHub, Microsoft OAuth2 providers
- **Role-Based Access Control**: User roles and permissions management
- **API Key Management**: Generate, list, and revoke API keys
- **Session Management**: Multi-device session tracking and management
- **Password Security**: Secure password hashing and validation

---

## Architecture

### System Architecture

```
Client → API Gateway → Auth Service → PostgreSQL (User Data)
                              ↓
                        Redis (Session Cache)
```

### Internal Architecture

The service follows a simple, focused architecture:

```
┌─────────────────────────────────────┐
│         FastAPI Application         │
│  (main.py - Entry Point)            │
└──────────────┬──────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼──────┐  ┌──────▼──────────┐
│   Endpoints │  │   Dependencies   │
│             │  │                 │
│ - /register │  │ - get_db()      │
│ - /login    │  │ - get_current_user()│
│ - /refresh  │  │ - security       │
│ - /logout   │  └──────────────────┘
│ - /api-keys │
│ - /oauth2   │
└──────┬──────┘
       │
┌──────▼──────┐
│   Models    │
│             │
│ - User      │
│ - UserSession│
│ - APIKey    │
│ - Role      │
└──────┬──────┘
       │
┌──────▼──────┐
│   Utils     │
│             │
│ - AuthUtils │
│ - OAuthUtils│
└─────────────┘
```

### Components

1. **Main Application** (`main.py`): FastAPI application with all endpoints
2. **Models** (`models.py`): SQLAlchemy database models and Pydantic schemas
3. **Utilities**:
   - `auth_utils.py`: JWT token generation, password hashing, user management
   - `oauth_utils.py`: OAuth2 provider integration (Google, GitHub, Microsoft)
4. **Database**: PostgreSQL for persistent storage
5. **Redis**: Optional session caching (gracefully degrades if unavailable)

---

## Features

### Core Features

1. **User Management**
   - User registration with email/username
   - Email uniqueness validation
   - Password strength validation
   - User profile management
   - Account activation/deactivation

2. **Authentication**
   - Email/password login
   - JWT access tokens (15-minute expiry)
   - JWT refresh tokens (7-day expiry, configurable)
   - Remember me functionality
   - Token refresh mechanism

3. **OAuth2 Integration**
   - Google OAuth2
   - GitHub OAuth2
   - Microsoft OAuth2 (configurable)
   - Automatic user creation from OAuth
   - OAuth token storage

4. **Role-Based Access Control**
   - Role assignment (USER, ADMIN, etc.)
   - Permission management
   - Role-based endpoint protection
   - Admin-only operations

5. **API Key Management**
   - API key generation
   - Key hashing and secure storage
   - Key expiration support
   - Key revocation
   - Usage tracking

6. **Session Management**
   - Multi-device session tracking
   - Session expiration
   - Session invalidation on logout
   - Device information tracking
   - Concurrent session limits

7. **Security Features**
   - Password hashing (bcrypt/argon2)
   - JWT token signing and verification
   - CSRF protection for OAuth
   - Secure session tokens
   - Password reset flow (placeholder)

---

## Prerequisites

### System Requirements

- **Python**: 3.11 or higher
- **PostgreSQL**: 15+ (for user and session data)
- **Redis**: 7+ (optional, for session caching)
- **Docker**: Optional, for containerized deployment

### Dependencies

Key Python packages (see `requirements.txt` for complete list):

- `fastapi>=0.104.0`: Web framework
- `uvicorn[standard]>=0.24.0`: ASGI server
- `sqlalchemy>=2.0.0`: ORM
- `asyncpg>=0.29.0`: PostgreSQL async driver
- `redis>=5.0.0`: Redis client
- `python-jose[cryptography]>=3.3.0`: JWT handling
- `passlib[argon2]>=1.7.4`: Password hashing
- `httpx>=0.25.0`: HTTP client for OAuth
- `authlib>=1.2.0`: OAuth2 client

---

## Installation & Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd aiv4-core/services/auth-service
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp env.template .env
# Edit .env with your configuration
```

### 4. Database Setup

Create the database schema:

```bash
# Run the create_tables script
python create_tables.py
```

Or use the provided SQL schema from the infrastructure/postgres directory.

### 5. Redis Setup (Optional)

Ensure Redis is running if you want session caching. The service will work without Redis but with reduced session management capabilities.

### 6. Start Service

```bash
# Development
uvicorn main:app --host 0.0.0.0 --port 8081 --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8081 --workers 4
```

### 7. Verify Installation

```bash
curl http://localhost:8081/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "auth-service",
  "redis": "healthy",
  "postgres": "healthy",
  "timestamp": 1234567890.123
}
```

---

## Configuration

### Environment Variables

All configuration is done via environment variables. See `env.template` for the complete list.

#### Service Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_NAME` | Service identifier | `auth-service` |
| `SERVICE_PORT` | HTTP port | `8081` |
| `LOG_LEVEL` | Logging level | `INFO` |

#### Database Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `DB_POOL_SIZE` | Connection pool size | `20` |
| `DB_MAX_OVERFLOW` | Max overflow connections | `10` |

#### Redis Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_HOST` | Redis hostname | `redis` |
| `REDIS_PORT` | Redis port | `6379` |
| `REDIS_PASSWORD` | Redis password | - |

#### JWT Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_SECRET_KEY` | Secret key for access tokens | `dhruva-jwt-secret-key-2024...` |
| `JWT_REFRESH_SECRET_KEY` | Secret key for refresh tokens | `dhruva-refresh-secret-key-2024...` |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token expiry | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token expiry | `7` |

#### OAuth2 Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | - |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | - |
| `GOOGLE_REDIRECT_URI` | Google OAuth redirect URI | - |
| `GITHUB_CLIENT_ID` | GitHub OAuth client ID | - |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth client secret | - |
| `MICROSOFT_CLIENT_ID` | Microsoft OAuth client ID | - |
| `MICROSOFT_CLIENT_SECRET` | Microsoft OAuth client secret | - |
| `FRONTEND_URL` | Frontend URL for OAuth callback | `http://localhost:3000` |

#### Session Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SESSION_TIMEOUT_MINUTES` | Session timeout | `30` |
| `MAX_CONCURRENT_SESSIONS` | Max concurrent sessions per user | `3` |

---

## API Reference

### Base URL

```
http://localhost:8081
```

### Endpoints

#### 1. Health Check

**GET** `/health`

Check service health and dependencies.

**Response:**
```json
{
  "status": "healthy",
  "service": "auth-service",
  "redis": "healthy",
  "postgres": "healthy",
  "timestamp": 1234567890.123
}
```

#### 2. Readiness Check

**GET** `/ready`

Kubernetes readiness probe endpoint.

**Response:**
```json
{
  "status": "ready",
  "service": "auth-service"
}
```

#### 3. Service Status

**GET** `/api/v1/auth/status`

Get authentication service status and features.

**Response:**
```json
{
  "service": "auth-service",
  "version": "v1",
  "status": "operational",
  "features": [
    "JWT token generation",
    "OAuth2 provider integration",
    "Role-based access control",
    "API key management",
    "Session management"
  ]
}
```

#### 4. User Registration

**POST** `/api/v1/auth/register`

Register a new user account.

**Request Body:**
```json
{
  "email": "user@example.com",
  "username": "username",
  "password": "SecurePassword123!",
  "confirm_password": "SecurePassword123!",
  "full_name": "John Doe",
  "phone_number": "+1234567890",
  "timezone": "UTC",
  "language": "en"
}
```

**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "username",
  "full_name": "John Doe",
  "is_active": true,
  "is_verified": false,
  "created_at": "2024-01-01T00:00:00Z"
}
```

#### 5. User Login

**POST** `/api/v1/auth/login`

Authenticate user and receive tokens.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "remember_me": false
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### 6. Token Refresh

**POST** `/api/v1/auth/refresh`

Refresh access token using refresh token.

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 900
}
```

#### 7. Token Validation

**GET** `/api/v1/auth/validate`

Validate access token and get user info.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "valid": true,
  "user_id": 1,
  "username": "username",
  "permissions": ["read", "write"],
  "roles": ["USER"]
}
```

#### 8. Get Current User

**GET** `/api/v1/auth/me`

Get current authenticated user information.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "username",
  "full_name": "John Doe",
  "is_active": true,
  "roles": ["USER"],
  "created_at": "2024-01-01T00:00:00Z"
}
```

#### 9. Update Current User

**PUT** `/api/v1/auth/me`

Update current user profile.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "full_name": "John Updated",
  "phone_number": "+1234567890"
}
```

#### 10. Change Password

**POST** `/api/v1/auth/change-password`

Change user password.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "current_password": "OldPassword123!",
  "new_password": "NewPassword123!",
  "confirm_password": "NewPassword123!"
}
```

#### 11. Logout

**POST** `/api/v1/auth/logout`

Logout user and invalidate session.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response:**
```json
{
  "message": "Logged out successfully",
  "logged_out": true
}
```

#### 12. Create API Key

**POST** `/api/v1/auth/api-keys`

Create a new API key.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "key_name": "My API Key",
  "permissions": ["read", "write"],
  "expires_days": 90
}
```

**Response:**
```json
{
  "id": 1,
  "key_name": "My API Key",
  "key_value": "ak_xxxxxxxxxxxxxxxxxxxx",
  "permissions": ["read", "write"],
  "is_active": true,
  "created_at": "2024-01-01T00:00:00Z",
  "expires_at": "2024-04-01T00:00:00Z"
}
```

#### 13. List API Keys

**GET** `/api/v1/auth/api-keys`

List user's API keys.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**
```json
[
  {
    "id": 1,
    "key_name": "My API Key",
    "key_value": "***",
    "permissions": ["read", "write"],
    "is_active": true,
    "created_at": "2024-01-01T00:00:00Z",
    "expires_at": "2024-04-01T00:00:00Z",
    "last_used": "2024-01-15T00:00:00Z"
  }
]
```

#### 14. Revoke API Key

**DELETE** `/api/v1/auth/api-keys/{key_id}`

Revoke an API key.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "message": "API key revoked successfully"
}
```

#### 15. OAuth2 Providers

**GET** `/api/v1/auth/oauth2/providers`

Get available OAuth2 providers.

**Response:**
```json
[
  {
    "provider": "google",
    "client_id": "xxx.apps.googleusercontent.com",
    "authorization_url": "/api/v1/auth/oauth2/google/authorize",
    "scope": ["openid", "email", "profile"]
  }
]
```

#### 16. Google OAuth2 Authorize

**GET** `/api/v1/auth/oauth2/google/authorize`

Initiate Google OAuth flow (redirects to Google).

#### 17. Google OAuth2 Callback

**GET** `/api/v1/auth/oauth2/google/callback`

Handle Google OAuth callback (creates/logs in user, redirects to frontend with tokens).

**Query Parameters:**
- `code`: Authorization code from Google
- `state`: CSRF protection token

#### 18. Role Management (Admin Only)

**POST** `/api/v1/auth/roles/assign`

Assign role to user.

**POST** `/api/v1/auth/roles/remove`

Remove role from user.

**GET** `/api/v1/auth/roles/user/{user_id}`

Get user roles.

**GET** `/api/v1/auth/roles/list`

List all available roles.

---

## Authentication Flow

### Standard Login Flow

1. User submits email/password to `/api/v1/auth/login`
2. Service validates credentials
3. Service generates JWT access token (15 min) and refresh token (7 days)
4. Service creates session record in database
5. Client stores tokens and uses access token for API calls
6. When access token expires, client uses refresh token to get new access token
7. On logout, client calls `/api/v1/auth/logout` to invalidate session

### Token Usage

```python
# Include access token in requests
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

response = requests.get("http://api.example.com/protected", headers=headers)
```

### Token Refresh Flow

```python
# When access token expires (401 response)
refresh_response = requests.post(
    "http://auth-service:8081/api/v1/auth/refresh",
    json={"refresh_token": refresh_token}
)
new_access_token = refresh_response.json()["access_token"]
```

---

## OAuth2 Integration

### Google OAuth2 Setup

1. **Create Google OAuth2 Credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create OAuth2 client ID
   - Set authorized redirect URI: `http://your-domain/api/v1/auth/oauth2/google/callback`

2. **Configure Environment Variables**:
   ```bash
   GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your_client_secret
   GOOGLE_REDIRECT_URI=http://your-domain/api/v1/auth/oauth2/google/callback
   FRONTEND_URL=http://your-frontend-url
   ```

3. **OAuth Flow**:
   - User clicks "Login with Google"
   - Redirect to `/api/v1/auth/oauth2/google/authorize`
   - Service redirects to Google authorization page
   - User authorizes
   - Google redirects to callback with code
   - Service exchanges code for tokens
   - Service creates/updates user account
   - Service redirects to frontend with JWT tokens

### GitHub OAuth2 Setup

Similar to Google, but using GitHub OAuth App credentials.

---

## Usage Examples

### Python Example - Registration and Login

```python
import requests

BASE_URL = "http://localhost:8081"

# Register user
register_data = {
    "email": "user@example.com",
    "username": "username",
    "password": "SecurePassword123!",
    "confirm_password": "SecurePassword123!",
    "full_name": "John Doe"
}

response = requests.post(f"{BASE_URL}/api/v1/auth/register", json=register_data)
print(response.json())

# Login
login_data = {
    "email": "user@example.com",
    "password": "SecurePassword123!"
}

response = requests.post(f"{BASE_URL}/api/v1/auth/login", json=login_data)
tokens = response.json()
access_token = tokens["access_token"]
refresh_token = tokens["refresh_token"]

# Use access token
headers = {"Authorization": f"Bearer {access_token}"}
response = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=headers)
print(response.json())
```

### Python Example - API Key Management

```python
# Create API key
headers = {"Authorization": f"Bearer {access_token}"}
api_key_data = {
    "key_name": "Production API Key",
    "permissions": ["read", "write"],
    "expires_days": 90
}

response = requests.post(
    f"{BASE_URL}/api/v1/auth/api-keys",
    json=api_key_data,
    headers=headers
)
api_key = response.json()["key_value"]
print(f"API Key: {api_key}")  # Save this securely!

# List API keys
response = requests.get(f"{BASE_URL}/api/v1/auth/api-keys", headers=headers)
print(response.json())

# Revoke API key
response = requests.delete(
    f"{BASE_URL}/api/v1/auth/api-keys/1",
    headers=headers
)
print(response.json())
```

---

## Deployment

### Docker Deployment

#### Build Image

```bash
docker build -t auth-service:latest .
```

#### Run Container

```bash
docker run -d \
  --name auth-service \
  -p 8081:8081 \
  --env-file .env \
  auth-service:latest
```

### Production Considerations

1. **Security**:
   - Use strong, unique JWT secret keys
   - Enable HTTPS
   - Secure Redis and PostgreSQL connections
   - Rotate secrets regularly

2. **Performance**:
   - Use connection pooling for database
   - Enable Redis caching for sessions
   - Use multiple workers for high load

3. **Monitoring**:
   - Monitor authentication failures
   - Track token refresh rates
   - Monitor session counts
   - Alert on unusual activity

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Failed

**Problem**: Cannot connect to PostgreSQL

**Solutions**:
- Verify `DATABASE_URL` is correct
- Check PostgreSQL is running
- Verify network connectivity
- Check database credentials

#### 2. JWT Token Invalid

**Problem**: Tokens are rejected

**Solutions**:
- Verify `JWT_SECRET_KEY` matches across services
- Check token expiration
- Verify token format
- Ensure algorithm matches (HS256)

#### 3. OAuth2 Callback Fails

**Problem**: OAuth callback returns error

**Solutions**:
- Verify redirect URI matches Google/GitHub settings
- Check OAuth client credentials
- Verify state token validation
- Check frontend URL configuration

#### 4. Password Validation Fails

**Problem**: Password doesn't meet requirements

**Solutions**:
- Check password strength requirements
- Ensure password and confirm_password match
- Verify password length (minimum 8 characters)
- Check for required character types

---

## Development

### Project Structure

```
auth-service/
├── main.py              # FastAPI application with all endpoints
├── models.py            # SQLAlchemy models and Pydantic schemas
├── auth_utils.py        # Authentication utilities
├── oauth_utils.py       # OAuth2 utilities
├── create_tables.py     # Database schema creation
├── requirements.txt     # Python dependencies
├── Dockerfile          # Docker image definition
└── env.template        # Environment variable template
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

---

## Additional Resources

- **API Documentation**: Available at `http://localhost:8081/docs` (Swagger UI)
- **ReDoc**: Available at `http://localhost:8081/redoc`
- **OpenAPI Spec**: Available at `http://localhost:8081/openapi.json`


