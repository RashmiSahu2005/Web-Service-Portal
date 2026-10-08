#!/bin/bash

set -e

TARGET_VERSION="3.7.0"
PACKAGE_NAME="appium"
INSTALL_CMD="npm install -g appium@${TARGET_VERSION}"
VERIFY_CMD="command -v appium"

echo "Checking for existing installation..."
if $VERIFY_CMD >/dev/null 2>&1; then
    CURRENT_VERSION=$(appium -v 2>/dev/null | tr -d 'v' || echo "unknown")
    if [ "$CURRENT_VERSION" = "$TARGET_VERSION" ]; then
        echo "Appium version $TARGET_VERSION is already installed. Skipping."
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=appium"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$CURRENT_VERSION"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

echo "Installing dependencies (Node.js and npm)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y curl gnupg

# Install Node.js (LTS) via NodeSource (Official signed-by keyring method)
if ! command -v node >/dev/null 2>&1; then
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list
    apt-get update -y
    apt-get install -y nodejs
fi

echo "Installing $PACKAGE_NAME version $TARGET_VERSION..."
if ! $INSTALL_CMD; then
    echo "Installation of Appium failed."
    exit 1
fi

echo "Verifying installation..."
if $VERIFY_CMD >/dev/null 2>&1; then
    ACTUAL_VERSION=$(appium -v 2>/dev/null | tr -d 'v' || echo "installed")
    echo "Verification successful."
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=appium"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$ACTUAL_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "Verification failed: appium command not found."
    exit 1
fi