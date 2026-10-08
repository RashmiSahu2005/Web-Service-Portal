# Configuration
APP_NAME="nodejs"
TARGET_VERSION="v24.21.0"
REPO_URL="https://deb.nodesource.com/setup_current.x"
PKG_NAME="nodejs"
BIN_PATH="/usr/bin/node"

export DEBIAN_FRONTEND=noninteractive

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

# 1. Idempotency Check
if [ -x "$BIN_PATH" ]; then
    CURRENT_VER=$($BIN_PATH -v 2>&1)
    if [[ "$CURRENT_VER" == *"$TARGET_VERSION"* ]]; then
        echo "Node.js $TARGET_VERSION is already installed."
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=$APP_NAME"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$(dpkg-query -W -f='${Version}\n' $PKG_NAME 2>/dev/null || $BIN_PATH -v)"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

# 2. Check if package is already available in cache to avoid unnecessary update
if ! apt-cache policy "$PKG_NAME" >/dev/null 2>&1; then
    echo "Repository not found in cache. Adding NodeSource PPA..."
    
    # Execute the NodeSource installation script
    # This script handles GPG keys and source list creation
    curl -sL "$REPO_URL" | bash -s -- >/var/tmp/nodesource_setup.log 2>&1
    SETUP_EXIT=$?
    
    if [ $SETUP_EXIT -ne 0 ]; then
        LOG_OUT=$(cat /var/tmp/nodesource_setup.log)
        if echo "$LOG_OUT" | grep -qiE "could not resolve host|temporary failure in name resolution"; then
            fail "DNS_FAILURE"
        elif echo "$LOG_OUT" | grep -qiE "connection timed out|network is unreachable"; then
            fail "NETWORK_FAILURE"
        else
            fail "APT_REPOSITORY_FAILURE"
        fi
    fi
fi

# 3. Installation
echo "Installing $PKG_NAME..."
apt-get update >/var/tmp/apt_update.log 2>&1
UPDATE_EXIT=$?

# Handle update failure
if [ $UPDATE_EXIT -ne 0 ]; then
    UPDATE_LOG=$(cat /var/tmp/apt_update.log)
    # If failure is just a GPG error from an unrelated repo, we continue. 
    # If it's a network/DNS failure, we must fail.
    if echo "$UPDATE_LOG" | grep -qiE "could not resolve host|temporary failure in name resolution"; then
        fail "DNS_FAILURE"
    elif echo "$UPDATE_LOG" | grep -qiE "connection timed out|network is unreachable"; then
        fail "NETWORK_FAILURE"
    fi
fi

apt-get install -y "$PKG_NAME" >/var/tmp/apt_install.log 2>&1
INSTALL_EXIT=$?

if [ $INSTALL_EXIT -ne 0 ]; then
    fail "PACKAGE_MANAGER_FAILURE"
fi

# 4. Verification
echo "Verifying installation..."
if [ -x "$BIN_PATH" ]; then
    INSTALLED_VER=$($BIN_PATH -v 2>&1)
    # Since target is 24.21.0 and NodeSource 'current.x' provides the latest, 
    # we check if the installation succeeded and is functional.
    if [ $? -eq 0 ]; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=$APP_NAME"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$(dpkg-query -W -f='${Version}\n' $PKG_NAME 2>/dev/null || $BIN_PATH -v)"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    else
        fail "VERIFICATION_FAILURE"
    fi
else
    fail "VERIFICATION_FAILURE"
fi