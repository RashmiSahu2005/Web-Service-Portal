set -e

TARGET_VERSION="22.1.5"
PACKAGE_NAME="@angular/cli"

echo "Checking for existing Angular CLI installation..."
if command -v ng >/dev/null 2>&1; then
    CURRENT_VERSION=$(ng version | grep "Angular CLI" | awk '{print $4}' || echo "unknown")
    if [ "$CURRENT_VERSION" = "$TARGET_VERSION" ]; then
        echo "Angular CLI version $TARGET_VERSION is already installed. Exiting."
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=Angular"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$CURRENT_VERSION"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

echo "Installing dependencies: Node.js and npm..."
DEBIAN_FRONTEND=noninteractive apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y curl gnupg build-essential

# Install Node.js (LTS) which includes npm
curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -
DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs

# Verify npm installation
if ! command -v npm >/dev/null 2>&1; then
    echo "FATAL: npm installation failed"
    exit 1
fi

echo "Installing Angular CLI version $TARGET_VERSION..."
# Install the specific version of @angular/cli globally
npm install -g "@angular/cli@$TARGET_VERSION"

# Ensure the executable path is in the path or exists in /usr/local/bin
# npm global installs usually go to /usr/local/bin or /usr/bin on Ubuntu
if [ ! -f "/usr/local/bin/ng" ] && [ ! -f "/usr/bin/ng" ]; then
    npm config get prefix | xargs -I {} ln -sf {}/bin/ng /usr/local/bin/ng
fi

echo "Verifying installation..."
if command -v ng >/dev/null 2>&1; then
    INSTALLED_VERSION=$(ng version | grep "Angular CLI" | awk '{print $4}' || echo "installed")
    echo "Successfully installed Angular CLI version: $INSTALLED_VERSION"
    
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Angular"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "FATAL: Angular CLI verification failed. Command 'ng' not found."
    exit 1
fi