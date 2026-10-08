set -e

TARGET_PACKAGE="remmina"
TARGET_VERSION="1.4.43"
REQUIRED_PLUGINS="remmina-plugin-vnc remmina-plugin-rdp"

echo "Checking if $TARGET_PACKAGE is already installed..."
if dpkg-query -W -f='${Version}' "$TARGET_PACKAGE" 2>/dev/null | grep -q "$TARGET_VERSION"; then
    echo "$TARGET_PACKAGE version $TARGET_VERSION is already installed. Exiting."
    INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' "$TARGET_PACKAGE")
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Remmina"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

echo "Updating package lists..."
DEBIAN_FRONTEND=noninteractive apt-get update -y

echo "Installing dependencies and $TARGET_PACKAGE..."
# Dependencies are listed first as per requirements, though apt handles resolution.
DEBIAN_FRONTEND=noninteractive apt-get install -y $REQUIRED_PLUGINS $TARGET_PACKAGE

echo "Verifying installation..."
if dpkg-query -l "$TARGET_PACKAGE" > /dev/null 2>&1; then
    INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' "$TARGET_PACKAGE")
    echo "Installation verified successfully."
    
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Remmina"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "Verification failed: $TARGET_PACKAGE not found in dpkg."
    exit 1
fi