set -e

TARGET_VERSION="37.0.1"
PACKAGE_NAME="android-sdk-platform-tools"

echo "Checking if ADB is already installed..."
if command -v adb >/dev/null 2>&1; then
    CURRENT_VERSION=$(adb version | grep "Android Debug Bridge version" | awk '{print $4}')
    echo "Found ADB version: $CURRENT_VERSION"
    # If installed, we treat it as a success per constraint 11 (version leniency)
    echo "ADB is already installed. Skipping installation."
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=ADB"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$CURRENT_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

echo "Installing $PACKAGE_NAME via apt..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y $PACKAGE_NAME

if [ $? -ne 0 ]; then
    echo "ERROR: apt-get install failed"
    exit 1
fi

echo "Verifying installation..."
if command -v adb >/dev/null 2>&1; then
    INSTALLED_VERSION=$(adb version | grep "Android Debug Bridge version" | awk '{print $4}')
    echo "Verification successful. Version: $INSTALLED_VERSION"
    
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=ADB"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "ERROR: ADB binary not found after installation"
    exit 1
fi