set -e

PACKAGE_NAME="openjdk-17-jdk"
EXECUTABLE_PATH="/usr/bin/java"

echo "Checking if $PACKAGE_NAME is already installed..."
if dpkg-query -W -f='${Status}' "$PACKAGE_NAME" 2>/dev/null | grep -q "ok installed"; then
    echo "Package $PACKAGE_NAME is already installed."
    if [ -x "$EXECUTABLE_PATH" ]; then
        INSTALLED_VERSION=$("$EXECUTABLE_PATH" -version 2>&1 | head -n 1 | awk -F '"' '{print $2}')
        echo "Verification successful: $INSTALLED_VERSION"
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=Java"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$INSTALLED_VERSION"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

echo "Installing $PACKAGE_NAME..."
export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get install -y "$PACKAGE_NAME"

if [ $? -ne 0 ]; then
    echo "Installation failed"
    exit 1
fi

echo "Verifying installation..."
if [ -x "$EXECUTABLE_PATH" ]; then
    INSTALLED_VERSION=$("$EXECUTABLE_PATH" -version 2>&1 | head -n 1 | awk -F '"' '{print $2}')
    echo "Successfully installed $INSTALLED_VERSION"
    
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Java"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "Verification failed: executable not found at $EXECUTABLE_PATH"
    exit 1
fi