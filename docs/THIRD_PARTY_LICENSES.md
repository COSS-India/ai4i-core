# Third-Party Open Source Dependencies

This document lists all open source third-party libraries used across the services and components in this repository, along with their versions and licenses.

---

## Table of Contents

- [Python Services](#python-services)
  - [auth-service](#auth-service)
  - [inference-service](#inference-service)
  - [platform-core-service](#platform-core-service)
  - [libs/ai4i_core](#libsai4i_core)
  - [infrastructure/databases](#infrastructuredatabases)
  - [tests](#tests)
- [Frontend](#frontend)
  - [frontend/simple-ui](#frontendsimple-ui)
- [Master Dependency Table](#master-dependency-table)
- [License Summary](#license-summary)
- [Non-Permissive License Notes](#non-permissive-license-notes)

---

## Python Services

### auth-service

| Library | Version Constraint | License |
|---|---|---|
| ai4i-core | >=1.0.2 | - |
| fastapi | >=0.104.0 | MIT |
| uvicorn[standard] | >=0.24.0 | BSD-3-Clause |
| pydantic | >=2.5.0 | MIT |
| pydantic-settings | >=2.1.0 | MIT |
| sqlalchemy[asyncio] | >=2.0.0 | MIT |
| asyncpg | >=0.29.0 | Apache-2.0 |
| alembic | >=1.13.0 | MIT |
| redis | >=5.0.0 | MIT |
| PyJWT[cryptography] | >=2.8.0 | MIT |
| cryptography | >=41.0.0 | Apache-2.0 OR BSD-3-Clause |
| passlib[argon2] | >=1.7.4 | BSD |
| httpx | >=0.25.0 | BSD-3-Clause |
| opentelemetry-api | >=1.20.0 | Apache-2.0 |
| opentelemetry-sdk | >=1.20.0 | Apache-2.0 |
| opentelemetry-instrumentation-fastapi | >=0.41b0 | Apache-2.0 |
| opentelemetry-instrumentation-sqlalchemy | >=0.41b0 | Apache-2.0 |
| opentelemetry-instrumentation-redis | >=0.41b0 | Apache-2.0 |
| mako | >=1.3.12 | MIT |
| idna | >=3.15 | BSD-3-Clause |
| starlette | >=1.0.2 | BSD-3-Clause |
| pytest | >=7.4.0 | MIT |
| pytest-asyncio | >=0.21.0 | Apache-2.0 |

---

### inference-service

| Library | Version Constraint | License |
|---|---|---|
| ai4i-core | ==1.0.2 | MIT |
| fastapi | ==0.136.3 | MIT |
| uvicorn[standard] | ==0.49.0 | BSD-3-Clause |
| pydantic | ==2.13.4 | MIT |
| pydantic-settings | ==2.14.1 | MIT |
| httpx | ==0.28.1 | BSD-3-Clause |
| python-dotenv | ==1.2.2 | BSD-3-Clause |
| scipy | ==1.17.1 | BSD-3-Clause |
| numpy | ==2.4.6 | BSD-3-Clause |
| soundfile | ==0.13.1 | BSD-3-Clause |
| python-multipart | >=0.0.6 | Apache-2.0 |
| kafka-python | ==2.3.2 | Apache-2.0 |
| pydub | ==0.25.1 | MIT |
| idna | >=3.15 | BSD-3-Clause |
| starlette | >=1.0.2 | BSD-3-Clause |

---

### platform-core-service

| Library | Version Constraint | License |
|---|---|---|
| ai4i-core | >=1.0.2 | MIT |
| fastapi | >=0.104.0 | MIT |
| uvicorn[standard] | >=0.24.0 | BSD-3-Clause |
| pydantic | >=2.5.0 | MIT |
| pydantic-settings | >=2.1.0 | MIT |
| sqlalchemy[asyncio] | >=2.0.0 | MIT |
| asyncpg | >=0.29.0 | Apache-2.0 |
| alembic | >=1.13.0 | MIT |
| redis | >=5.0.0 | MIT |
| httpx | >=0.25.0 | BSD-3-Clause |
| prometheus-client | >=0.19.0 | Apache-2.0 AND BSD-2-Clause |
| pyyaml | >=6.0 | MIT |
| aiofiles | >=23.0.0 | Apache-2.0 |
| opentelemetry-api | >=1.20.0 | Apache-2.0 |
| opentelemetry-sdk | >=1.20.0 | Apache-2.0 |
| opentelemetry-instrumentation-fastapi | >=0.41b0 | Apache-2.0 |
| opentelemetry-instrumentation-sqlalchemy | >=0.41b0 | Apache-2.0 |
| opentelemetry-instrumentation-redis | >=0.41b0 | Apache-2.0 |
| opensearch-py | >=2.0.0 | Apache-2.0 |
| mako | >=1.3.12 | MIT |
| idna | >=3.15 | BSD-3-Clause |
| starlette | >=1.0.2 | BSD-3-Clause |
| pytest | >=7.4.0 | MIT |
| pytest-asyncio | >=0.21.0 | Apache-2.0 |

---

### libs/ai4i_core

| Library | Version Constraint | License |
|---|---|---|
| fastapi | >=0.104.0 | MIT |
| starlette | >=0.27.0 | BSD-3-Clause |
| pydantic | >=2.5.0 | MIT |
| pydantic-settings | >=2.0.0 | MIT |
| python-dotenv | >=1.0.2 | BSD-3-Clause |
| httpx | >=0.25.0 | BSD-3-Clause |
| redis | >=5.0.0 | MIT |
| sqlalchemy[asyncio] | >=2.0.0 | MIT |
| slowapi | >=0.1.9 | MIT |
| aiosmtplib | >=3.0.0,<4.0.0 | MIT |
| jinja2 | >=3.1.0,<4.0.0 | BSD-3-Clause |
| python-json-logger | >=2.0.7 | BSD-2-Clause |
| kafka-python | >=2.0.2 | Apache-2.0 |
| aiokafka | >=0.8.0 | Apache-2.0 |
| prometheus-client | >=0.19.0 | Apache-2.0 AND BSD-2-Clause |
| psutil | >=5.9.0 | BSD-3-Clause |
| PyJWT | >=2.8.0 | MIT |
| tritonclient[http] | >=2.40.0 | BSD-3-Clause |
| numpy | >=1.24.0 | BSD-3-Clause |
| packaging | >=21.0 | Apache-2.0 OR BSD-2-Clause |
| opentelemetry-api | >=1.20.0 | Apache-2.0 |
| opentelemetry-sdk | >=1.20.0 | Apache-2.0 |
| opentelemetry-instrumentation-fastapi | >=0.41b0 | Apache-2.0 |
| setuptools | >=68.0 | MIT |
| wheel | — | MIT |
| pytest | >=7.4.0 | MIT |
| pytest-asyncio | >=0.21.0 | Apache-2.0 |
| black | >=23.0.0 | MIT |
| flake8 | >=6.0.0 | MIT |
| build | >=1.0.2 | MIT |
| twine | >=4.0.0 | Apache-2.0 |

---

### infrastructure/databases

| Library | Version Constraint | License |
|---|---|---|
| sqlalchemy | >=2.0.0 | MIT |
| asyncpg | >=0.29.0 | Apache-2.0 |
| psycopg2-binary | >=2.9.0 | LGPL |
| redis | >=5.0.0 | MIT |
| elasticsearch | >=8.10.0 | Apache-2.0 |
| kafka-python | >=2.0.2 | Apache-2.0 |
| python-dotenv | >=1.0.2 | BSD-3-Clause |
| pydantic[email] | >=2.4.0 | MIT |
| pydantic-settings | >=2.0.0 | MIT |
| alembic | >=1.12.0 | MIT |
| bcrypt | >=4.0.0 | Apache-2.0 |
| passlib[argon2] | >=1.7.4 | BSD |
| argon2-cffi | >=25.1.0 | MIT |
| mako | >=1.3.12 | MIT |
| idna | >=3.15 | BSD-3-Clause |
| starlette | >=1.0.2 | BSD-3-Clause |

---

### tests

| Library | Version Constraint | License |
|---|---|---|
| pytest | >=7.4.0 | MIT |
| pytest-asyncio | >=0.21.0 | Apache-2.0 |
| pytest-cov | >=4.1.0 | MIT |
| pytest-mock | >=3.11.0 | MIT |
| pytest-timeout | >=2.1.0 | MIT |
| httpx | >=0.25.0 | BSD-3-Clause |
| python-socketio | >=5.10.0 | MIT |
| sqlalchemy | >=2.0.0 | MIT |
| asyncpg | >=0.29.0 | Apache-2.0 |
| redis | >=5.0.0 | MIT |
| playwright | >=1.40.0 | Apache-2.0 |
| faker | >=20.0.0 | MIT |
| factory-boy | >=3.3.0 | MIT |

---

## Frontend

### frontend/simple-ui

#### Runtime Dependencies

| Library | Version Constraint | License |
|---|---|---|
| @chakra-ui/icons | ^2.0.17 | MIT |
| @chakra-ui/react | ^2.4.6 | MIT |
| @emotion/react | ^11.10.5 | MIT |
| @emotion/styled | ^11.10.5 | MIT |
| @tanstack/react-query | ^5.0.0 | MIT |
| @tanstack/react-query-devtools | ^5.0.0 | MIT |
| axios | 1.16.0 | MIT |
| crypto-js | ^4.2.0 | MIT |
| framer-motion | ^8.1.4 | MIT |
| next | 15.5.19 | MIT |
| react | 18.2.0 | MIT |
| react-dom | 18.2.0 | MIT |
| react-icons | ^4.7.1 | MIT |
| socket.io-client | 4.8.3 | MIT |
| zod | ^3.23.8 | MIT |

#### Dev Dependencies

| Library | Version Constraint | License |
|---|---|---|
| @types/jest | ^29.5.14 | MIT |
| @types/crypto-js | ^4.2.2 | MIT |
| @types/node | 18.11.18 | MIT |
| @types/react | 18.0.27 | MIT |
| @types/react-dom | 18.0.10 | MIT |
| eslint | 9.39.4 | MIT |
| eslint-config-next | 15.5.19 | MIT |
| typescript | 4.9.4 | Apache-2.0 |

#### Pinned Transitive Overrides

| Library | Pinned Version | License |
|---|---|---|
| postcss | 8.5.10 | MIT |
| socket.io-parser | 4.2.6 | MIT |
| ws | 8.20.1 | MIT |

---

## Master Dependency Table

Deduplicated across all services. Where a library appears in multiple components, the minimum stated version constraint is shown.

| Library | Min Version | License | Used In |
|---|---|---|---|
| aiofiles | >=23.0.0 | Apache-2.0 | platform-core-service |
| aiokafka | >=0.8.0 | Apache-2.0 | ai4i_core |
| aiosmtplib | >=3.0.0 | MIT | ai4i_core |
| alembic | >=1.12.0 | MIT | auth-service, platform-core-service, databases |
| argon2-cffi | >=25.1.0 | MIT | databases |
| asyncpg | >=0.29.0 | Apache-2.0 | auth-service, platform-core-service, databases, tests |
| @chakra-ui/icons | ^2.0.17 | MIT | simple-ui |
| @chakra-ui/react | ^2.4.6 | MIT | simple-ui |
| axios | 1.16.0 | MIT | simple-ui |
| bcrypt | >=4.0.0 | Apache-2.0 | databases |
| black | >=23.0.0 | MIT | ai4i_core (dev) |
| build | >=1.0.2 | MIT | ai4i_core (dev) |
| crypto-js | ^4.2.0 | MIT | simple-ui |
| cryptography | >=41.0.0 | Apache-2.0 OR BSD-3-Clause | auth-service |
| elasticsearch | >=8.10.0 | Apache-2.0 | databases |
| @emotion/react | ^11.10.5 | MIT | simple-ui |
| @emotion/styled | ^11.10.5 | MIT | simple-ui |
| eslint | 9.39.4 | MIT | simple-ui (dev) |
| eslint-config-next | 15.5.19 | MIT | simple-ui (dev) |
| factory-boy | >=3.3.0 | MIT | tests |
| faker | >=20.0.0 | MIT | tests |
| fastapi | >=0.104.0 | MIT | auth-service, inference-service, platform-core-service, ai4i_core |
| flake8 | >=6.0.0 | MIT | ai4i_core (dev) |
| framer-motion | ^8.1.4 | MIT | simple-ui |
| httpx | >=0.25.0 | BSD-3-Clause | auth-service, inference-service, platform-core-service, ai4i_core, tests |
| idna | >=3.15 | BSD-3-Clause | auth-service, inference-service, platform-core-service, databases |
| jinja2 | >=3.1.0 | BSD-3-Clause | ai4i_core |
| kafka-python | >=2.0.2 | Apache-2.0 | inference-service, ai4i_core, databases |
| mako | >=1.3.12 | MIT | auth-service, platform-core-service, databases |
| next | 15.5.19 | MIT | simple-ui |
| numpy | >=1.24.0 | BSD-3-Clause | ai4i_core, inference-service |
| opentelemetry-api | >=1.20.0 | Apache-2.0 | auth-service, platform-core-service, ai4i_core |
| opentelemetry-instrumentation-fastapi | >=0.41b0 | Apache-2.0 | auth-service, platform-core-service, ai4i_core |
| opentelemetry-instrumentation-redis | >=0.41b0 | Apache-2.0 | auth-service, platform-core-service |
| opentelemetry-instrumentation-sqlalchemy | >=0.41b0 | Apache-2.0 | auth-service, platform-core-service |
| opentelemetry-sdk | >=1.20.0 | Apache-2.0 | auth-service, platform-core-service, ai4i_core |
| opensearch-py | >=2.0.0 | Apache-2.0 | platform-core-service |
| packaging | >=21.0 | Apache-2.0 OR BSD-2-Clause | ai4i_core |
| passlib[argon2] | >=1.7.4 | BSD | auth-service, databases |
| playwright | >=1.40.0 | Apache-2.0 | tests |
| postcss | 8.5.10 | MIT | simple-ui (override) |
| prometheus-client | >=0.19.0 | Apache-2.0 AND BSD-2-Clause | platform-core-service, ai4i_core |
| psutil | >=5.9.0 | BSD-3-Clause | ai4i_core |
| psycopg2-binary | >=2.9.0 | LGPL | databases |
| pydantic | >=2.4.0 | MIT | auth-service, inference-service, platform-core-service, ai4i_core, databases |
| pydantic-settings | >=2.0.0 | MIT | auth-service, inference-service, platform-core-service, ai4i_core, databases |
| pydub | ==0.25.1 | MIT | inference-service |
| PyJWT | >=2.8.0 | MIT | auth-service, ai4i_core |
| python-dotenv | >=1.0.2 | BSD-3-Clause | inference-service, ai4i_core, databases |
| python-json-logger | >=2.0.7 | BSD-2-Clause | ai4i_core |
| python-multipart | >=0.0.6 | Apache-2.0 | inference-service |
| python-socketio | >=5.10.0 | MIT | tests |
| pytest | >=7.4.0 | MIT | auth-service, platform-core-service, ai4i_core, tests |
| pytest-asyncio | >=0.21.0 | Apache-2.0 | auth-service, platform-core-service, ai4i_core, tests |
| pytest-cov | >=4.1.0 | MIT | tests |
| pytest-mock | >=3.11.0 | MIT | tests |
| pytest-timeout | >=2.1.0 | MIT | tests |
| pyyaml | >=6.0 | MIT | platform-core-service |
| react | 18.2.0 | MIT | simple-ui |
| react-dom | 18.2.0 | MIT | simple-ui |
| react-icons | ^4.7.1 | MIT | simple-ui |
| @tanstack/react-query | ^5.0.0 | MIT | simple-ui |
| @tanstack/react-query-devtools | ^5.0.0 | MIT | simple-ui |
| redis | >=5.0.0 | MIT | auth-service, platform-core-service, ai4i_core, databases, tests |
| scipy | ==1.17.1 | BSD-3-Clause | inference-service |
| setuptools | >=68.0 | MIT | ai4i_core (build) |
| slowapi | >=0.1.9 | MIT | ai4i_core |
| socket.io-client | 4.8.3 | MIT | simple-ui |
| socket.io-parser | 4.2.6 | MIT | simple-ui (override) |
| soundfile | ==0.13.1 | BSD-3-Clause | inference-service |
| sqlalchemy | >=2.0.0 | MIT | auth-service, platform-core-service, ai4i_core, databases, tests |
| starlette | >=0.27.0 | BSD-3-Clause | auth-service, inference-service, platform-core-service, databases, ai4i_core |
| tritonclient[http] | >=2.40.0 | BSD-3-Clause | ai4i_core |
| twine | >=4.0.0 | Apache-2.0 | ai4i_core (dev) |
| typescript | 4.9.4 | Apache-2.0 | simple-ui (dev) |
| uvicorn[standard] | >=0.24.0 | BSD-3-Clause | auth-service, inference-service, platform-core-service |
| wheel | — | MIT | ai4i_core (build) |
| ws | 8.20.1 | MIT | simple-ui (override) |
| zod | ^3.23.8 | MIT | simple-ui |

---

## License Summary

| License | Libraries |
|---|---|
| MIT | fastapi, pydantic, pydantic-settings, sqlalchemy, alembic, redis, PyJWT, mako, aiosmtplib, jinja2, argon2-cffi, pydub, setuptools, wheel, slowapi, black, flake8, build, pyyaml, faker, factory-boy, python-socketio, pytest, pytest-cov, pytest-mock, pytest-timeout, @chakra-ui/icons, @chakra-ui/react, @emotion/react, @emotion/styled, @tanstack/react-query, @tanstack/react-query-devtools, axios, crypto-js, framer-motion, next, react, react-dom, react-icons, socket.io-client, socket.io-parser, zod, postcss, ws, eslint, ai4i-core |
| Apache-2.0 | asyncpg, aiokafka, kafka-python, opentelemetry-api, opentelemetry-sdk, opentelemetry-instrumentation-fastapi, opentelemetry-instrumentation-sqlalchemy, opentelemetry-instrumentation-redis, opensearch-py, elasticsearch, aiofiles, python-multipart, bcrypt, playwright, twine, pytest-asyncio, typescript |
| Apache-2.0 AND BSD-2-Clause | prometheus-client |
| Apache-2.0 OR BSD-3-Clause | cryptography |
| Apache-2.0 OR BSD-2-Clause | packaging |
| BSD-3-Clause | uvicorn, httpx, starlette, idna, numpy, scipy, soundfile, psutil, tritonclient, python-dotenv, jinja2 |
| BSD-2-Clause | python-json-logger |
| BSD | passlib |
| LGPL | psycopg2-binary |

---

## Non-Permissive License Notes

### psycopg2-binary (LGPL)

Used only in `infrastructure/databases` migration scripts, which are standalone command-line tools invoked at deploy time — not linked into any running service binary. This usage pattern (dynamic linking via Python's import system) is generally considered compatible with MIT-licensed application code under the LGPL terms, but should be reviewed by a qualified legal professional if there is any doubt.

### @img/sharp-libvips-linux-x64 and @img/sharp-libvips-linuxmusl-x64 (LGPL-3.0-or-later)

These are transitive dependencies pulled in by `next` (the frontend framework) for its image optimization feature. They are dynamically linked native binaries and are not distributed as part of the application source. The same LGPL dynamic-linking reasoning applies.

### axe-core (MPL-2.0)

A transitive dependency pulled in by Next.js development tooling. MPL-2.0 is a file-level copyleft license — it only requires modifications to MPL-licensed files to be shared under MPL. It does not affect the license of the surrounding application.

---

*Last updated: 2026-06-11*
