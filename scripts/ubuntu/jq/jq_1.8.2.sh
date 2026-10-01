set -e

TARGET_VERSION="1.8.2"
BINARY_URL="https://github.com/jqlang/jq/releases/download/jq-1.8.2/jq-linux64"
INSTALL_PATH="/usr/bin/jq"

echo "Checking if jq $TARGET_VERSION is already installed..."
if [ -f "$INSTALL_PATH" ]; then
    CURRENT_VERSION=$("$INSTALL_PATH" --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || true)
    if [ "$CURRENT_VERSION" = "$TARGET_VERSION" ]; then
        echo "jq $TARGET_VERSION is already installed. Exiting."
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=jq"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$CURRENT_VERSION"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

echo "Downloading jq binary v$TARGET_VERSION..."
# Download to /opt instead of /tmp to avoid noexec issues
DOWNLOAD_DIR="/opt/jq_install"
mkdir -p "$DOWNLOAD_DIR"
curl -sSL "$BINARY_URL" -o "$DOWNLOAD_DIR/jq-bin"

if [ ! -s "$DOWNLOAD_DIR/jq-bin" ]; then
    echo "ERROR: Failed to download jq binary"
    exit 1
fi

echo "Verifying downloaded binary..."
chmod +x "$DOWNLOAD_DIR/jq-bin"
# Extract version from binary output safely
DOWNLOADED_VERSION=$("$DOWNLOAD_DIR/jq-bin" --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || true)

if [ "$DOWNLOADED_VERSION" != "$TARGET_VERSION" ]; then
    echo "ERROR: VERSION_MISMATCH (Expected $TARGET_VERSION, got $DOWNLOADED_VERSION)"
    rm -rf "$DOWNLOAD_DIR"
    exit 1
fi

echo "Installing jq to $INSTALL_PATH..."
# Move to final destination
mv "$DOWNLOAD_DIR/jq-bin" "$INSTALL_PATH"
chmod 755 "$INSTALL_PATH"
rm -rf "$DOWNLOAD_DIR"

echo "Verifying installation..."
FINAL_VERSION=$("$INSTALL_PATH" --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || true)
if [ -z "$FINAL_VERSION" ]; then
    echo "ERROR: Verification failed - could not determine version"
    exit 1
fi

echo "DEPLOYIQ_RESULT_START"
echo "APPLICATION=jq"
echo "INSTALLATION_STATUS=SUCCESS"
echo "VERIFICATION_STATUS=SUCCESS"
echo "INSTALLED_VERSION=$FINAL_VERSION"
echo "DEPLOYIQ_RESULT_END"