# Configuration
APP_NAME="brave browser"
PKG_NAME="brave-browser"
REQUIRED_VERSION="1.95.101"
GPG_KEY_URL="https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg"
GPG_KEY_PATH="/usr/share/keyrings/brave-browser-archive-keyring.gpg"
REPO_LINE="deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg arch=amd64] https://brave-browser-apt-release.s3.brave.com/ stable main"
REPO_FILE="/etc/apt/sources.list.d/brave-browser-release.list"
BIN_PATH="/usr/bin/brave-browser"

# Helper to print failure and exit
fail() {
    local category=$1
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=$category"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
}

# 1. Idempotency check
if dpkg -l | grep -q "^ii  $PKG_NAME "; then
    CURRENT_VERSION=$(dpkg-query -W -f='${Version}' "$PKG_NAME")
    if [[ "$CURRENT_VERSION" == *"$REQUIRED_VERSION"* ]]; then
        echo "Package $PKG_NAME version $REQUIRED_VERSION already installed."
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=$APP_NAME"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$CURRENT_VERSION"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

echo "Starting installation of $APP_NAME..."

# 2. GPG Key setup
echo "Downloading GPG key..."
if ! curl -fsSLo "$GPG_KEY_PATH" "$GPG_KEY_URL"; then
    # Check if failure was DNS or Network
    if ! ping -c 1 google.com >/dev/null 2>&1; then
        fail "NETWORK_FAILURE"
    else
        fail "DOWNLOAD_FAILURE"
    fi
fi

# 3. Repository setup
echo "Configuring repository..."
echo "$REPO_LINE" | tee "$REPO_FILE" > /dev/null

# 4. APT Update handling
echo "Updating package lists..."
# Check if candidate already exists to avoid unnecessary update
if ! apt-cache policy "$PKG_NAME" | grep -q "Candidate"; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update >"/var/tmp/apt_update.log" 2>&1
    UPDATE_EXIT=$?
    
    if [ $UPDATE_EXIT -ne 0 ]; then
        # Analysis of the update log for critical failures
        if grep -qiE "Could not resolve|Temporary failure in name resolution" "/var/tmp/apt_update.log"; then
            fail "DNS_FAILURE"
        elif grep -qiE "Failed to fetch|Connection failed" "/var/tmp/apt_update.log"; then
            # If it's just one broken 3rd party repo, we continue, but if it's our target repo, fail.
            if grep -q "brave-browser-apt-release.s3.brave.com" "/var/tmp/apt_update.log"; then
                fail "NETWORK_FAILURE"
            fi
        fi
    fi
fi

# 5. Package Installation
echo "Installing $PKG_NAME..."
export DEBIAN_FRONTEND=noninteractive
if ! apt-get install -y "$PKG_NAME"; then
    fail "PACKAGE_MANAGER_FAILURE"
fi

# 6. Verification
echo "Verifying installation..."
if [ -x "$BIN_PATH" ]; then
    ACTUAL_VERSION=$(dpkg-query -W -f='${Version}' "$PKG_NAME")
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$ACTUAL_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    fail "VERIFICATION_FAILURE"
fi