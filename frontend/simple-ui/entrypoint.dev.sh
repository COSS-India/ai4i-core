#!/bin/sh
# Ensure node_modules exists in /app (e.g. when bind mount overwrites with empty host dir)
if [ ! -d /app/node_modules ] || [ -z "$(ls -A /app/node_modules 2>/dev/null)" ]; then
  echo "Copying node_modules from image into /app..."
  cp -a /node_modules_image/. /app/node_modules
fi
exec "$@"
