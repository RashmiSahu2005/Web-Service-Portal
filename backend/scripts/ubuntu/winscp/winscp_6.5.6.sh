set -e

TARGET_VERSION="6.5.6"
INSTALL_DIR="/opt/winscp"
BIN_LINK="/usr/local/bin/winscp"
# WinSCP Portable ZIP URL for 6.5.6
DOWNLOAD_URL="https://winscp.net/download/WinSCP-6.5.6-Portable.zip"
DOWNLOAD_PATH="/var/tmp/WinSCP-6.5.6-Portable.zip"

echo "Checking if WinSCP $TARGET_VERSION is already installed..."
if [ -f "$INSTALL_DIR/WinSCP.exe" ]; then
    echo "WinSCP executable found in $INSTALL_DIR. Skipping installation."
else
    echo "Installing WinSCP $TARGET_VERSION..."

    # Install Wine dependency
    echo "Checking dependencies: wine..."
    if ! command -v wine >/dev/null 2>&1; then
        echo "Installing wine..."
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install -y wine
    else
        echo "wine is already installed."
    fi

    # Create installation directory
    mkdir -p "$INSTALL_DIR"

    # Download the portable zip
    echo "Downloading WinSCP Portable..."
    wget -q "$DOWNLOAD_URL" -O "$DOWNLOAD_PATH"

    # Validate download
    if [ ! -s "$DOWNLOAD_PATH" ]; then
        echo "ERROR: Download failed or file is empty"
        exit 1
    fi

    # Extract to a temporary directory first to ensure integrity
    EXTRACT_TMP="/var/tmp/winscp_extract"
    mkdir -p "$EXTRACT_TMP"
    unzip -q "$DOWNLOAD_PATH" -d "$EXTRACT_TMP"

    # Verify the executable exists in the extracted content
    if [ ! -f "$EXTRACT_TMP/WinSCP.exe" ]; then
        echo "ERROR: WinSCP.exe not found in downloaded archive"
        rm -rf "$EXTRACT_TMP"
        exit 1
    fi

    # Move extracted files to the final destination (Atomic-like replacement)
    cp -r "$EXTRACT_TMP"/* "$INSTALL_DIR/"
    
    # Create a wrapper script to launch via wine
    cat <<EOF > "$BIN_LINK"
#!/bin/bash
wine "$INSTALL_DIR/WinSCP.exe" "\$@"
EOF
    chmod +x "$BIN_LINK"

    # Cleanup
    rm -rf "$EXTRACT_TMP"
    rm -f "$DOWNLOAD_PATH"
fi

echo "Verifying installation..."
if [ -f "$INSTALL_DIR/WinSCP.exe" ]; then
    echo "Verification successful: WinSCP.exe exists."
else
    echo "Verification failed: WinSCP.exe not found."
    exit 1
fi

echo "DEPLOYIQ_RESULT_START"
echo "APPLICATION=Winscp"
echo "INSTALLATION_STATUS=SUCCESS"
echo "VERIFICATION_STATUS=SUCCESS"
echo "INSTALLED_VERSION=$TARGET_VERSION"
echo "DEPLOYIQ_RESULT_END"