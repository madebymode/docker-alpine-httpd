#!/bin/bash

# Source the environment variables from the .env file
source .env

# Use docker build with the provided arguments
docker build \
  --build-arg APACHE_VERSION=$APACHE_VERSION \
  --build-arg ALPINE_VERSION=$ALPINE_VERSION \
  -t mxmd/httpd:2.4 .

