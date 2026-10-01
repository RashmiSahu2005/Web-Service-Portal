#!/bin/bash

set -e

# Configuration
APP_NAME="Microsoft teams"
PACKAGE_NAME="teams-for-linux"
TARGET_VERSION="5.6.210.0"
INSTALL_CMD="snap install teams-for-linux"
VERIFY_CMD="snap list teams-for-linux"
EXEC_PATH="/snap/bin/teams-for-linux"

export DEBIAN_FRONTEND=noninteractive

echo "Checking for existing installation of ${PACKAGE_NAME}..."

# Idempotency Check
if snap list "$PACKAGE_NAME" >/dev/null 2>&1; then
    CURRENT_VERSION=$(snap list "$PACKAGE_NAME" | grep "$PACKAGE_NAME" | awk '{print $2}')
    echo "Package ${PACKAGE_NAME} is already installed. Version: ${CURRENT_VERSION}"
    
    # If it is already installed, we consider it a success per constraints
    # unless specific version enforcement was required (which it isn't per Constraint 10)
    echo "Verification successful: ${EXEC_PATH} exists."
    if [ -f "$EXEC_PATH" ]; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=${APP_NAME}"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=${CURRENT_VERSION}"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

echo "Installing ${PACKAGE_NAME} via snap..."

# Installation
if ! $INSTALL_CMD; then
    echo "Error: Failed to install ${PACKAGE_NAME}."
    exit 1
fi

echo "Verifying installation..."

# Verification
if $VERIFY_CMD >/dev/null 2>&1; then
    if [ -f "$EXEC_PATH" ]; then
        INSTALLED_VERSION=$(snap list "$PACKAGE_NAME" | grep "$PACKAGE_NAME" | awk '{print $2}')
        echo "Installation and verification succeeded."
        
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=${APP_NAME}"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=${INSTALLED_VERSION}"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    else
        echo "Error: Executable not found at ${EXEC_PATH}."
        exit 1
    fi
else
    echo "Error: Verification command ${VERIFY_CMD} failed."
    exit 1
fi