#!/bin/bash

# CVAT Development Stack Deploy Script
# Rebuilds and starts all services with development configuration

set -e

echo "Pulling latest changes..."
git pull

export CVAT_VERSION=dev

echo "Rebuilding and deploying CVAT development stack..."

docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

echo "Deploy complete!"
echo "CVAT UI: https://cvat-everex.mora.center"
