# Contributing to Dhruva AI/ML Microservices Platform

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker 20.10+
- Git 2.30+

### Development Setup

1. **Fork and Clone**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Ai4V-C.git
   cd Ai4V-C
   ```

2. **Set Up Environment**:
   ```bash
   cp env.template .env
   # Configure environment variables
   ```

3. **Start Services**:
   ```bash
   ./scripts/start-all.sh
   ```

4. **Verify Setup**:
   ```bash
   ./scripts/health-check-all.sh
   ```

## Development Workflow

### Creating a Feature Branch
```bash
git checkout -b feature/your-feature-name
```

### Making Changes

1. **Code Style**:
   - Python: Follow PEP 8, use Black formatter
   - TypeScript: Follow Airbnb style guide, use Prettier
   - Use meaningful variable and function names
   - Add docstrings for all public functions/classes

2. **Testing**:
   - Write tests for new features
   - Ensure existing tests pass
   - Aim for >80% code coverage
   - Run tests: `./scripts/run-tests.sh`

3. **Documentation**:
   - Update README.md if adding new features
   - Add docstrings and comments
   - Update API documentation if changing endpoints
   - Add examples for new functionality

### Committing Changes

**Commit Message Format**:
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Example**:
```
feat(asr-service): add support for Punjabi language

Implemented Punjabi language support in ASR service with
new language model integration and validation.

Closes #123
```

### Submitting Pull Request

1. **Push Changes**:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create Pull Request**:
   - Go to GitHub repository
   - Click "New Pull Request"
   - Select your feature branch
   - Fill in PR template

3. **PR Checklist**:
   - [ ] Tests pass locally
   - [ ] Code follows style guidelines
   - [ ] Documentation updated
   - [ ] No merge conflicts
   - [ ] Descriptive PR title and description

## Code Review Process

1. **Automated Checks**: CI/CD pipeline runs tests and linters
2. **Peer Review**: At least one maintainer reviews code
3. **Feedback**: Address review comments
4. **Approval**: Maintainer approves PR
5. **Merge**: Squash and merge to main branch

## Testing Guidelines

### Writing Tests

**Python Services**:
- Use pytest for all tests
- Use pytest-asyncio for async tests
- Mock external dependencies (Triton, Redis)
- Use fixtures for common setup

**Frontend**:
- Use Jest and React Testing Library
- Test user interactions, not implementation details
- Mock API calls
- Test accessibility

### Test Categories

- **Unit Tests**: Test individual functions/classes in isolation
- **Integration Tests**: Test service endpoints with real dependencies
- **E2E Tests**: Test complete user workflows with browser automation
- **Performance Tests**: Test response times and throughput

## Adding New Services

### Service Template

1. **Create Service Directory**:
   ```bash
   mkdir -p services/new-service/{models,services,repositories,routers,utils,middleware}
   ```

2. **Required Files**:
   - `main.py` - FastAPI application
   - `Dockerfile` - Container definition
   - `requirements.txt` - Python dependencies
   - `env.template` - Environment variables
   - `README.md` - Service documentation

3. **Follow Patterns**:
   - Copy structure from existing services (ASR, TTS, NMT)
   - Use async SQLAlchemy for database operations
   - Implement authentication middleware
   - Add comprehensive error handling
   - Include health check endpoints

4. **Update Infrastructure**:
   - Add service to `docker-compose.yml`
   - Add routes to API Gateway
   - Add health check to `scripts/health-check-all.sh`
   - Create database schema in `infrastructure/postgres/`

## Code Quality Standards

### Python
- Use type hints for all function parameters and return values
- Use async/await for I/O operations
- Handle exceptions gracefully
- Log errors with context
- Use Pydantic for data validation

### TypeScript
- Use strict TypeScript configuration
- Define interfaces for all data structures
- Use functional components with hooks
- Avoid any type (use unknown or specific types)
- Use async/await for promises

## Documentation Standards

### Code Documentation
- Add docstrings to all public functions/classes
- Include parameter descriptions and return types
- Add usage examples for complex functions
- Document exceptions that can be raised

### API Documentation
- Use FastAPI's automatic OpenAPI generation
- Add descriptions to all endpoints
- Include request/response examples
- Document error responses

## Release Process

1. **Version Bump**: Update version in package.json, main.py files
2. **Changelog**: Update CHANGELOG.md with changes
3. **Tag Release**: Create Git tag (e.g., v1.0.0)
4. **Build Images**: Build and tag Docker images
5. **Deploy**: Deploy to staging, then production
6. **Announce**: Notify users of new release

## Getting Help

- **Documentation**: Check docs/ directory
- **Issues**: Search existing issues on GitHub
- **Discussions**: Use GitHub Discussions for questions
- **Slack**: Join project Slack channel (if available)
