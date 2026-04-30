# Troubleshooting Guide

## Common Issues and Solutions

### Service Startup Issues

#### Issue: Services fail to start
**Symptoms**: `docker-compose up` fails, containers exit immediately

**Solutions**:
1. Check logs: `./scripts/logs.sh <service-name>`
2. Verify environment variables: `docker-compose config`
3. Check port conflicts: `netstat -tulpn | grep <port>`
4. Verify Docker resources: `docker system df`
5. Clean and rebuild: `docker-compose down -v && docker-compose up -d --build`

#### Issue: Database connection errors
**Symptoms**: Services log "could not connect to PostgreSQL"

**Solutions**:
1. Verify PostgreSQL is running: `docker-compose ps postgres`
2. Check PostgreSQL health: `docker-compose exec postgres pg_isready -U dhruva_user`
3. Verify credentials in .env match database configuration
4. Check database logs: `docker-compose logs postgres`
5. Restart PostgreSQL: `docker-compose restart postgres`

#### Issue: Redis connection errors
**Symptoms**: Services log "Error connecting to Redis"

**Solutions**:
1. Verify Redis is running: `docker-compose ps redis`
2. Test Redis connection: `docker-compose exec redis redis-cli ping`
3. Check Redis password in .env
4. Verify Redis is healthy: `docker-compose exec redis redis-cli --no-auth-warning -a <password> ping`

### ASR Service Issues

#### Issue: ASR inference returns empty transcript
**Symptoms**: Response is 200 OK but transcript is empty

**Solutions**:
1. Verify audio format is supported (WAV, MP3, FLAC)
2. Check audio sample rate (8000-48000 Hz)
3. Verify audio is not silent (check amplitude)
4. Check Triton server connectivity: `curl http://localhost:8000/v2/health/ready`
5. Verify ASR model is loaded in Triton: `curl http://localhost:8000/v2/models/asr_am_ensemble`
6. Check ASR service logs for preprocessing errors

#### Issue: ASR streaming disconnects immediately
**Symptoms**: WebSocket connection closes after connect

**Solutions**:
1. Verify query parameters are correct (serviceId, language, samplingRate)
2. Check API key is valid (if authentication enabled)
3. Verify Socket.IO client uses websocket transport
4. Check ASR streaming service logs: `docker-compose logs asr-service | grep streaming`
5. Test with simple Socket.IO client to isolate issue

#### Issue: ASR rate limiting too aggressive
**Symptoms**: Getting 429 errors frequently

**Solutions**:
1. Check rate limit configuration in `services/asr-service/.env`
2. Increase limits: `RATE_LIMIT_PER_MINUTE=120`, `RATE_LIMIT_PER_HOUR=2000`
3. Verify Redis is working (rate limits use Redis counters)
4. Check if multiple API keys are sharing same user_id
5. Clear Redis rate limit keys: `docker-compose exec redis redis-cli --no-auth-warning -a <password> KEYS "rate_limit:*" | xargs docker-compose exec redis redis-cli --no-auth-warning -a <password> DEL`

### TTS Service Issues

#### Issue: TTS generates distorted audio
**Symptoms**: Audio plays but sounds distorted or robotic

**Solutions**:
1. Verify sample rate matches expected output (22050 Hz default)
2. Check audio format conversion (WAV is most reliable)
3. Verify text preprocessing (check for special characters)
4. Test with shorter text (< 100 characters)
5. Check Triton TTS model health
6. Review TTS service logs for audio processing errors

#### Issue: TTS voice not available for language
**Symptoms**: 404 error when requesting specific voice

**Solutions**:
1. List available voices: `curl http://localhost:8088/api/v1/tts/voices`
2. Verify voice_id exists in voice catalog
3. Check language is supported by voice: `curl http://localhost:8088/api/v1/tts/voices/language/<lang>`
4. Use default voice for language if specific voice unavailable

### NMT Service Issues

#### Issue: NMT translation quality is poor
**Symptoms**: Translation is incorrect or nonsensical

**Solutions**:
1. Verify language pair is supported: `curl http://localhost:8089/api/v1/nmt/models`
2. Check source language detection (if using auto-detect)
3. Verify text preprocessing (check for special characters, newlines)
4. Test with simpler text (single sentence)
5. Check if script code is needed (e.g., hi_Deva for Hindi)
6. Review NMT service logs for preprocessing errors

#### Issue: NMT batch processing fails
**Symptoms**: Request with multiple texts fails

**Solutions**:
1. Verify batch size <= 90 texts (Triton limitation)
2. Check total text length is reasonable
3. Verify all texts are non-empty
4. Test with single text to isolate issue
5. Check Triton NMT model capacity

### Frontend Issues

#### Issue: Simple UI shows "API connection error"
**Symptoms**: Frontend cannot connect to backend

**Solutions**:
1. Verify API Gateway is running: `curl http://localhost:8080/health`
2. Check NEXT_PUBLIC_API_URL in frontend/.env
3. Verify CORS is enabled in API Gateway
4. Check browser console for detailed error messages
5. Test API directly with curl to isolate frontend vs backend issue

#### Issue: Audio recording not working
**Symptoms**: Microphone button does nothing or shows permission error

**Solutions**:
1. Grant microphone permission in browser
2. Use HTTPS (some browsers require HTTPS for getUserMedia)
3. Check browser console for errors
4. Verify Recorder.js is loaded: check Network tab for /recorder.js
5. Test in different browser (Chrome, Firefox)

#### Issue: WebSocket streaming not working
**Symptoms**: Streaming button does nothing or shows connection error

**Solutions**:
1. Verify ASR/TTS services are running
2. Check WebSocket URLs in frontend/.env
3. Verify Socket.IO client version matches server version
4. Check browser console for WebSocket errors
5. Test WebSocket connection with standalone client

### Authentication Issues

#### Issue: API key validation fails
**Symptoms**: All requests return 401 even with valid API key

**Solutions**:
1. Verify API key exists in database: `docker-compose exec postgres psql -U dhruva_user -d auth_db -c "SELECT * FROM api_keys;"`
2. Check API key is active: `is_active=true`
3. Check API key is not expired: `expires_at IS NULL OR expires_at > NOW()`
4. Verify API key hash matches (use same hashing algorithm)
5. Clear Redis cache: `docker-compose exec redis redis-cli --no-auth-warning -a <password> FLUSHDB`
6. Check auth-service logs for validation errors

#### Issue: Rate limiting not working
**Symptoms**: Can send unlimited requests without 429 errors

**Solutions**:
1. Verify Redis is running and accessible
2. Check rate limit configuration in service .env files
3. Verify RateLimitMiddleware is added to app in main.py
4. Check Redis for rate limit keys: `docker-compose exec redis redis-cli --no-auth-warning -a <password> KEYS "rate_limit:*"`
5. Review service logs for rate limiting errors

### Performance Issues

#### Issue: Slow response times
**Symptoms**: Requests take > 5 seconds

**Solutions**:
1. Check Triton server load: `curl http://localhost:8000/v2/models/stats`
2. Verify database connection pool is not exhausted
3. Check Redis latency: `docker-compose exec redis redis-cli --no-auth-warning -a <password> --latency`
4. Review service logs for slow queries or processing
5. Monitor resource usage: `docker stats`
6. Consider scaling services: `docker-compose up -d --scale asr-service=3`

#### Issue: High memory usage
**Symptoms**: Services consume excessive RAM, OOM errors

**Solutions**:
1. Check for memory leaks in service logs
2. Reduce database connection pool sizes
3. Configure Docker memory limits in docker-compose.yml
4. Restart services periodically: `./scripts/restart-service.sh <service>`
5. Monitor memory usage: `docker stats --no-stream`

### Database Issues

#### Issue: Database disk space full
**Symptoms**: "No space left on device" errors

**Solutions**:
1. Check disk usage: `df -h`
2. Clean old request/result records: `docker-compose exec postgres psql -U dhruva_user -d auth_db -c "SELECT cleanup_old_ai_service_data(30);"`
3. Vacuum database: `docker-compose exec postgres psql -U dhruva_user -d auth_db -c "VACUUM FULL;"`
4. Configure data retention policy
5. Increase disk space or add volume

### Logging and Debugging

#### Viewing Logs
```bash
# All services
./scripts/logs.sh

# Specific service
./scripts/logs.sh asr-service

# Follow logs in real-time
./scripts/logs.sh -f tts-service

# Last 100 lines
./scripts/logs.sh --tail=100 nmt-service
```

#### Debugging Service Issues
```bash
# Enter service container
docker-compose exec asr-service /bin/bash

# Check Python dependencies
pip list

# Test database connection
python -c "import asyncpg; print('OK')"

# Test Redis connection
python -c "import redis; r=redis.Redis(host='redis', port=6379, password='<password>'); print(r.ping())"
```

### Getting Help

1. **Check Logs**: Always start with service logs
2. **Review Documentation**: Check service-specific README.md files
3. **Search Issues**: Look for similar issues in repository
4. **Create Issue**: Provide logs, configuration, and steps to reproduce
5. **Community Support**: Ask in project forums or Slack channel

