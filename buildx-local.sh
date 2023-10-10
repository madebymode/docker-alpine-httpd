#!/bin/bash

FORCE_BUILD=false

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --force) FORCE_BUILD=true ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

DATE_CMD=date
if [[ "$(uname)" == "Darwin" ]]; then
    # If on macOS, check if gdate is available
    if command -v gdate > /dev/null; then
        DATE_CMD=gdate
    else
        echo "Error: GNU date (gdate) is not installed. Install it using Homebrew (brew install coreutils)."
        exit 1
    fi
fi

# Exit immediately if a command exits with a non-zero status
set -e

# Handle script termination gracefully
cleanup() {
    echo "Cleaning up..."
    docker context use default || true
    docker builder ls | awk 'NR>1 {print $1}' | grep -v "default" | grep -v "builder" | xargs -I {} docker builder rm {} || true
    docker context rm builder || true
}

# Function to check when the image was last created locally
was_created_last_day() {
    local image="$1"

    # Get the image creation time using docker inspect
    local timestamp=$(docker inspect --format '{{.Created}}' "$image")

    # Convert the timestamp to seconds
    local created_time=$($DATE_CMD --date="$timestamp" +%s)
    local current_time=$($DATE_CMD +%s)
    local one_day_in_seconds=86400

    # Calculate the difference in time
    local time_diff=$((current_time - created_time))

    # If the time difference is less than a day (86400 seconds), return 0 (true)
    if [ "$time_diff" -lt "$one_day_in_seconds" ]; then
        return 0
    else
        return 1
    fi
}

trap 'echo "Error on line $LINENO"' ERR
trap cleanup SIGINT SIGTERM

cleanup

docker context create builder

# Enable Docker experimental features
export DOCKER_CLI_EXPERIMENTAL=enabled

# Create a new builder instance
docker buildx create --use builder

# Load .env file for Apache version and Alpine version
set -a
source .env
set +a

TAG_NAME="mxmd/httpd:${APACHE_VERSION}-alpine${ALPINE_VERSION}"

# Disable the 'exit on error' behavior
set +e

# Attempt to pull the image and capture the output/error
PULL_OUTPUT=$(docker pull "${TAG_NAME}" 2>&1)
PULL_STATUS=$?

# Print the output for debugging
echo "Pull output for ${TAG_NAME}:"
echo "--------------------------------------"
echo "$PULL_OUTPUT"
echo "--------------------------------------"

# Check for errors in the pull command output
if [[ $PULL_OUTPUT == *"Error: No such object:"* ]] || [[ $PULL_OUTPUT == *"manifest unknown: manifest unknown"* ]] || [[ $PULL_STATUS -ne 0 ]]; then
    echo "Warning: Image ${TAG_NAME} not found or other error occurred."
else
    if $FORCE_BUILD; then
        echo "Force build enabled. Building ${TAG_NAME} regardless of its creation date."
    elif was_created_last_day "${TAG_NAME}"; then
        echo "Image ${TAG_NAME} was created within the last day. Skipping build."
        cleanup
        exit
    fi
fi

# Exit immediately if a command exits with a non-zero status
set -e

docker buildx build \
  --push \
  --platform linux/amd64,linux/arm64 \
  --tag "${TAG_NAME}" \
  --build-arg APACHE_VERSION="${APACHE_VERSION}" \
  --build-arg ALPINE_VERSION="${ALPINE_VERSION}" \
  --file "./Dockerfile" .

cleanup
exit;
