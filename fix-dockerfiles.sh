#!/bin/bash

# Fix Dockerfile permission issues for all services
services=("metrics-service" "telemetry-service" "alerting-service" "dashboard-service")

for service in "${services[@]}"; do
    dockerfile_path="./services/$service/Dockerfile"
    if [ -f "$dockerfile_path" ]; then
        echo "Fixing $service Dockerfile..."
        
        # Create a backup
        cp "$dockerfile_path" "$dockerfile_path.backup"
        
        # Fix the permission issue
        sed -i 's|COPY --from=builder /root/.local /root/.local|COPY --from=builder /root/.local /home/app/.local|g' "$dockerfile_path"
        sed -i 's|ENV PATH=/root/.local/bin:\$PATH|ENV PATH=/home/app/.local/bin:\$PATH|g' "$dockerfile_path"
        
        # Fix the user creation and ownership order
        sed -i '/Create non-root user/a RUN useradd --create-home --shell /bin/bash app' "$dockerfile_path"
        sed -i 's|RUN useradd --create-home --shell /bin/bash app && \\|# Create non-root user first|g' "$dockerfile_path"
        sed -i 's|    chown -R app:app /app|# Change ownership to app user\nRUN chown -R app:app /app /home/app/.local|g' "$dockerfile_path"
        
        echo "Fixed $service Dockerfile"
    else
        echo "Dockerfile not found for $service"
    fi
done

echo "All Dockerfiles fixed!"
