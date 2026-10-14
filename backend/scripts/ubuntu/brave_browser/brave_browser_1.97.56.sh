# Ensure non-interactive apt
export DEBIAN_FRONTEND=noninteractive

APP_NAME="brave browser"
PKG_NAME="brave-browser"
GPG_KEY_URL="https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg"
GPG_KEY_PATH="/usr/share/keyrings/brave-browser-archive-keyring.gpg"
REPO_LINE="deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] https://brave-browser-apt-release.s3.brave.com/ stable main"
REPO_FILE="/etc/apt/sources.list.d/brave-browser-release.list"

# Idempotency check
if apt-cache policy "$PKG_NAME" >/dev/null 2>&1; then
    if /usr/bin/brave-browser --version >/dev/null 2>&1; then
        INSTALLED_VERSION=$(dpkg-query -W -f='${Version}\n' "$PKG_NAME" 2>/dev/null || /usr/bin/brave-browser --version)
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=$APP_NAME"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$INSTALLED_VERSION"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

echo "Starting installation of $APP_NAME..."

# Install curl if missing
apt-get update >"/var/tmp/apt_update.log" 2>&1
UPDATE_EXIT=$?
if [ $UPDATE_EXIT -ne 0 ]; then
    if grep -qE "Temporary failure in name resolution|Could not resolve host" "/var/tmp/apt_update.log"; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=$APP_NAME"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=DNS_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    elif grep -qE "Failed to fetch|Connection failed" "/var/tmp/apt_update.log"; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=$APP_NAME"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=NETWORK_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    fi
fi

apt-get install curl -y >/dev/null 2>&1 || {
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=PACKAGE_MANAGER_FAILURE"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
}

# Handle GPG Key
echo "Adding Brave GPG key..."
curl -fsSLo "$GPG_KEY_PATH" "$GPG_KEY_URL"
if [ $? -ne 0 ]; then
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=APT_GPG_FAILURE"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
fi

# Add Repository
echo "Adding Brave repository..."
echo "$REPO_LINE" | tee "$REPO_FILE" >/dev/null

# Final Installation
echo "Installing package..."
apt-get update >"/var/tmp/apt_update_final.log" 2>&1
# We ignore general update failures here if the specific repo is fine, as per constraint 7.

apt-get install "$PKG_NAME" -y >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=PACKAGE_MANAGER_FAILURE"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
fi

# Verification
echo "Verifying installation..."
if /usr/bin/brave-browser --version >/dev/null 2>&1; then
    INSTALLED_VERSION=$(dpkg-query -W -f='${Version}\n' "$PKG_NAME" 2>/dev/null || /usr/bin/brave-browser --version)
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=VERIFICATION_FAILURE"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
fi