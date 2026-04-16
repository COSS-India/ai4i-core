"""
Auth-service performance benchmark.

Run:
    locust -f benchmarks/locustfile.py --host http://localhost:8081

Configure:
    - TEST_EMAIL / TEST_PASSWORD: credentials for a test user
    - Set number of users and spawn rate in the UI
"""

import os
import time

from locust import HttpUser, between, task

TEST_EMAIL = os.getenv("BENCH_EMAIL", "admin@ai4inclusion.org")
TEST_PASSWORD = os.getenv("BENCH_PASSWORD", "ADMIN_PASSWORD")


class AuthServiceUser(HttpUser):
    wait_time = between(0.1, 0.5)

    access_token: str = ""
    refresh_token: str = ""

    def on_start(self):
        """Login with retries to ensure all users get tokens."""
        for attempt in range(5):
            resp = self.client.post(
                "/api/v1/auth/login",
                json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            )
            if resp.status_code == 200:
                data = resp.json()
                self.access_token = data.get("access_token", "")
                self.refresh_token = data.get("refresh_token", "")
                return
            time.sleep(1 + attempt)

    def _auth_header(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    @task(10)
    def validate_token(self):
        """Simulates APISIX calling /auth/validate on every request.
        Weight 10 = most frequent operation."""
        self.client.get(
            "/api/v1/auth/validate",
            headers=self._auth_header(),
            name="/auth/validate",
        )

    @task(3)
    def get_me(self):
        """Protected endpoint — triggers get_current_user dependency chain."""
        self.client.get(
            "/api/v1/auth/me",
            headers=self._auth_header(),
            name="/auth/me",
        )

    @task(1)
    def login(self):
        """Full login flow."""
        self.client.post(
            "/api/v1/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            name="/auth/login",
        )

    @task(1)
    def refresh(self):
        """Token refresh."""
        if self.refresh_token:
            self.client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": self.refresh_token},
                name="/auth/refresh",
            )
