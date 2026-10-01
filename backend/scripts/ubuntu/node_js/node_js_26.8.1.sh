set -e

TARGET_VERSION="26.8.1"
PACKAGE_NAME="nodejs"

echo "Checking if $PACKAGE_NAME is already installed..."
if dpkg-query -l "$PACKAGE_NAME" > /dev/null 2>&1; then
    INSTALLED_VERSION=$(node -v 2>/dev/null | sed 's/v//')
    echo "Found installed version: $INSTALLED_VERSION"
    # Leniency: if installed, we consider it a success as per constraint 11
    echo "Package $PACKAGE_NAME is already installed. Skipping installation."
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Node.js"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

echo "Installing $PACKAGE_NAME via NodeSource..."
export DEBIAN_FRONTEND=noninteractive

# Ensure curl is present
apt-get update -y
apt-get install -y curl

# Execute provided NodeSource installation command
# Note: The strategy provided a specific sequence of commands
curl -sL https://deb.nodesource.com/setup_current.x | bash -
apt-get install -y nodejs

echo "Verifying installation..."
if dpkg-query -l "$PACKAGE_NAME" > /dev/null 2>&1; then
    FINAL_VERSION=$(node -v 2>/dev/null | sed 's/v//' || echo "unknown")
    echo "Installation successful. Version: $FINAL_VERSION"
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Node.js"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$FINAL_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "Verification failed: $PACKAGE_NAME not found in dpkg"
    exit 1
fi