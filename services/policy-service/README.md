# policy-service

A FastAPI microservice scaffold for policy-related functionality. This is an initial skeleton; business logic and endpoints will be added later.

## Structure
```
policy-service/
  app/
    api/
      routes/
        health.py
        policy.py
    core/
      config.py
      logging.py
    main.py
  Dockerfile
  env.template
  requirements.txt
```

## Run (dev)
```bash
uvicorn app.main:get_app --reload --host 0.0.0.0 --port 8099
```

