set -e

TARGET_VERSION="1.4.9"
PKG_NAME="rustdesk-1.4.9-x86_64.deb"
DOWNLOAD_URL="https://github.com/rustdesk/rustdesk/releases/download/1.4.9/rustdesk-1.4.9-x86_64.deb"
INSTALL_DIR="/var/tmp"
EXE_PATH="/usr/bin/rustdesk"

echo "Checking if RustDesk $TARGET_VERSION is already installed..."
if dpkg-query -W -f='${Version}' rustdesk 2>/dev/null | grep -q "$TARGET_VERSION"; then
    echo "RustDesk $TARGET_VERSION is already installed. Exiting."
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Ruskdesk"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$TARGET_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

echo "Installing dependencies..."
DEBIAN_FRONTEND=noninteractive apt-get update -y
for dep in g++ gcc git; do
    if ! dpkg-query -W -f='${Status}' "$dep" 2>/dev/null | grep -q "ok installed"; then
        echo "Installing $dep..."
        DEBIAN_FRONTEND=noninteractive apt-get install -y "$dep"
    else
        echo "$dep is already installed."
    fi
done

echo "Downloading package..."
wget -q "$DOWNLOAD_URL" -O "$INSTALL_DIR/$PKG_NAME"

if [ ! -s "$INSTALL_DIR/$PKG_NAME" ]; then
    echo "ERROR: Download failed or file is empty"
    exit 1
fi

echo "Validating package version..."
INSTALLED_PKG_VERSION=$(dpkg-deb -f "$INSTALL_DIR/$PKG_NAME" Version)
if [[ "$INSTALLED_PKG_VERSION" != *"$TARGET_VERSION"* ]]; then
    echo "ERROR: VERSION_MISMATCH. Expected $TARGET_VERSION, found $INSTALLED_PKG_VERSION"
    exit 1
fi

echo "Installing RustDesk..."
DEBIAN_FRONTEND=noninteractive apt-get install -y "$INSTALL_DIR/$PKG_NAME"

echo "Verifying installation..."
if [ -f "$EXE_PATH" ] && dpkg-query -W -f='${Status}' rustdesk 2>/dev/null | grep -q "ok installed"; then
    ACTUAL_VERSION=$(dpkg-query -W -f='${Version}' rustdesk)
    echo "Verification successful."
    
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Ruskdesk"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$ACTUAL_VERSION"
    echo "DEPLOYIQ_RESULT_END"
else
    echo "Verification failed: Executable not found or package not registered."
    exit 1
fi