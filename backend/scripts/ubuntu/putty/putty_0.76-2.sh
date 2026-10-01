set -e

TARGET_VERSION="0.84"
PACKAGE_NAME="putty"
EXECUTABLE_PATH="/usr/bin/putty"

echo "Checking if PuTTY is already installed..."
if dpkg-query -W -f='${Version}' "$PACKAGE_NAME" >/dev/null 2>&1; then
    CURRENT_VERSION=$(dpkg-query -W -f='${Version}' "$PACKAGE_NAME")
    echo "PuTTY is already installed. Version: $CURRENT_VERSION"
    # Idempotency: if installed, we consider it successful per constraint 11
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=PuTTY"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$CURRENT_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

echo "Installing PuTTY from universe repository..."
export DEBIAN_FRONTEND=noninteractive

# Ensure universe repository is enabled
apt-get update -y
apt-get install -y software-properties-common
apt-add-repository -y universe
apt-get update -y

# Install the package
if apt-get install -y "$PACKAGE_NAME"; then
    echo "Installation command executed successfully."
else
    echo "Installation failed."
    exit 1
fi

echo "Verifying installation..."
# Verify executable exists
if [ -f "$EXECUTABLE_PATH" ]; then
    # Get version from dpkg as it is non-GUI safe
    INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' "$PACKAGE_NAME")
    
    if [ -n "$INSTALLED_VERSION" ]; then
        echo "Verification successful. Installed version: $INSTALLED_VERSION"
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=PuTTY"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$INSTALLED_VERSION"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    else
        echo "Verification failed: Could not determine version."
        exit 1
    fi
else
    echo "Verification failed: Executable not found at $EXECUTABLE_PATH"
    exit 1
fi