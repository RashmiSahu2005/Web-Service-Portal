set -e

TARGET_VERSION="1.132.0"
PKG_NAME="code"
GPG_KEY_URL="https://packages.microsoft.com/keys/microsoft.asc"
GPG_KEYRING="/etc/apt/keyrings/packages.microsoft.gpg"
REPO_LINE="deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] stable main"
REPO_FILE="/etc/apt/sources.list.d/vscode.list"

echo "Checking if VS Code is already installed..."
if command -v code >/dev/null 2>&1; then
    CURRENT_VERSION=$(code --version | head -n 1)
    echo "VS Code is already installed: $CURRENT_VERSION"
    # As per constraint 11, we do not fail on slight version mismatches if installed.
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=VS Code"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$CURRENT_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

echo "Installing dependencies..."
DEBIAN_FRONTEND=noninteractive apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y wget gpg

echo "Configuring Microsoft GPG key..."
mkdir -p /etc/apt/keyrings
# Use wget to download and gpg --dearmor to ensure valid binary format for signed-by
wget -qO- "$GPG_KEY_URL" | gpg --dearmor -o "$GPG_KEYRING"
chmod 644 "$GPG_KEYRING"

echo "Configuring repository..."
echo "$REPO_LINE" > "$REPO_FILE"

echo "Installing VS Code..."
DEBIAN_FRONTEND=noninteractive apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y code

echo "Verifying installation..."
if dpkg-query -W -f='${Status}' code 2>/dev/null | grep -q "ok installed"; then
    INSTALLED_VERSION=$(code --version | head -n 1 || echo "unknown")
    echo "Installation successful: $INSTALLED_VERSION"
    
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=VS Code"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "ERROR: Verification failed. Package 'code' is not installed."
    exit 1
fi