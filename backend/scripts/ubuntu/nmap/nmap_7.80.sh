set -e

TARGET_PKG="nmap"
TARGET_BIN="/usr/bin/nmap"

echo "Checking if $TARGET_PKG is already installed..."
if dpkg-query -W -f='${Status}' "$TARGET_PKG" 2>/dev/null | grep -q "ok installed"; then
    if [ -x "$TARGET_BIN" ]; then
        INSTALLED_VERSION=$("$TARGET_BIN" --version | head -n 1 | grep -oE '[0-9]+\.[0-9]+([a-z0-9.]*)')
        echo "Package $TARGET_PKG is already installed. Version: $INSTALLED_VERSION"
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=Nmap"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$INSTALLED_VERSION"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

echo "Installing $TARGET_PKG via apt..."
DEBIAN_FRONTEND=noninteractive apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y nmap

if [ $? -ne 0 ]; then
    echo "ERROR: Installation of $TARGET_PKG failed"
    exit 1
fi

echo "Verifying installation..."
if dpkg-query -W -f='${Status}' "$TARGET_PKG" 2>/dev/null | grep -q "ok installed" && [ -x "$TARGET_BIN" ]; then
    INSTALLED_VERSION=$("$TARGET_BIN" --version | head -n 1 | grep -oE '[0-9]+\.[0-9]+([a-z0-9.]*)')
    echo "Verification successful. Version: $INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Nmap"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "ERROR: Verification failed for $TARGET_PKG"
    exit 1
fi