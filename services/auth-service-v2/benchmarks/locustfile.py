"""
Auth-service performance benchmark — login focused.

Run:
    locust -f benchmarks/locustfile.py --host http://localhost:8081
"""

import os
import time

from locust import HttpUser, between, task

TEST_EMAIL = os.getenv("BENCH_EMAIL", "admin@ai4inclusion.org")
TEST_PASSWORD = os.getenv("BENCH_PASSWORD", "ADMIN_PASSWORD")


class AuthServiceUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task
    def login(self):
        self.client.post(
            "/api/v1/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            name="/auth/login",
        )
