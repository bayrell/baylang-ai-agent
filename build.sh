#!/bin/bash

IMAGE="bayrell/baylang-ai-agent"
VERSION="1.0.0"

case $1 in
    docker)
        docker build -t $IMAGE:$VERSION .
    ;;
    *)
        echo "$0 {docker}"
    ;;
esac