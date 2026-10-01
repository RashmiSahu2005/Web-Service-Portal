set -e

PACKAGE_NAME="google-chrome-stable"
PKG_FILE="/var/tmp/google-chrome-stable_current_amd64.deb"
DOWNLOAD_URL="https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
TARGET_VERSION="151"

echo "Checking if $PACKAGE_NAME is already installed..."
if dpkg-query -W -f='${Version}' "$PACKAGE_NAME" >/dev/null 2>&1; then
    CURRENT_VERSION=$(dpkg-query -W -f='${Version}' "$PACKAGE_NAME")
    echo "Found $PACKAGE_NAME version: $CURRENT_VERSION"
    # Leniency: if installed, we treat it as success unless target is strictly required.
    # Per constraint 11, do not fail solely on version string mismatch if it is installed.
    echo "Google Chrome is already installed."
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=google-chrome"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$CURRENT_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

echo "Downloading package to $PKG_FILE..."
wget -q -O "$PKG_FILE" "$DOWNLOAD_URL"

if [ ! -s "$PKG_FILE" ]; then
    echo "ERROR: Download failed or file is empty"
    exit 1
fi

echo "Validating package metadata..."
# Extract version from .deb to ensure it's not a 404 page or corrupt file
PKG_VERSION=$(dpkg-deb -f "$PKG_FILE" Version)
echo "Package version in .deb: $PKG_VERSION"

if [ -z "$PKG_VERSION" ]; then
    echo "ERROR: Could not extract version from .deb"
    exit 1
fi

echo "Installing Google Chrome..."
# Use DEBIAN_FRONTEND=noninteractive and force-confold to prevent prompts from base-files or other deps
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y -o Dpkg::Options::="--force-confold" "$PKG_FILE"

echo "Verifying installation..."
if dpkg-query -W -f='${Status}' "$PACKAGE_NAME" 2>/dev/null | grep -q "install ok installed"; then
    INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' "$PACKAGE_NAME")
    echo "Verification successful: $INSTALLED_VERSION"
    
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=google-chrome"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "ERROR: Installation verification failed"
    exit 1
fi