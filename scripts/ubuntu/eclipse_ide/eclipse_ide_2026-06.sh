#!/bin/bash

set -e

# Configuration
APP_NAME="eclipse IDE"
PACKAGE_NAME="eclipse"
INSTALL_CMD="snap install eclipse --classic"
VERIFY_CMD="snap list eclipse"
EXECUTABLE_PATH="/snap/bin/eclipse"

export DEBIAN_FRONTEND=noninteractive

echo "Checking if ${PACKAGE_NAME} is already installed..."

# Idempotency check: If snap list contains the package, we consider it installed
if snap list "$PACKAGE_NAME" >/dev/null 2>&1; then
    echo "${PACKAGE_NAME} is already installed. Skipping installation."
else
    echo "Installing ${PACKAGE_NAME} via snap..."
    
    # Ensure snapd is installed and updated (essential for Ubuntu)
    apt-get update -y >/dev/null
    apt-get install -y snapd >/dev/null
    
    # Perform installation
    if ! $INSTALL_CMD; then
        echo "Error: Failed to install ${PACKAGE_NAME}."
        exit 1
    fi
    echo "Installation command completed successfully."
fi

echo "Verifying installation..."

# Verification Method: snap_list
if $VERIFY_CMD >/dev/null 2>&1; then
    # Check if executable exists
    if [ -f "$EXECUTABLE_PATH" ]; then
        echo "Verification successful: ${PACKAGE_NAME} is installed and executable exists."
        
        # Extract version from snap list output
        INSTALLED_VERSION=$(snap list "$PACKAGE_NAME" | grep "$PACKAGE_NAME" | awk '{print $2}')
        
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=${APP_NAME}"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=${INSTALLED_VERSION}"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    else
        echo "Error: Executable not found at ${EXECUTABLE_PATH}"
        exit 1
    fi
else
    echo "Error: Verification command '${VERIFY_CMD}' failed."
    exit 1
fi