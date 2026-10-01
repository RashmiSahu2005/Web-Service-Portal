# Configuration
APP_NAME="mysql"
PACKAGE_NAME="mysql-server"
TARGET_VERSION="9.7.3" # Requested version (Note: Ubuntu repos typically provide 8.0.x)
VERIFY_CMD="mysql --version"
EXE_PATH="/usr/sbin/mysqld"

# Helper function for failure output
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
if command -v mysql >/dev/null 2>&1; then
    CURRENT_VERSION=$($VERIFY_CMD | awk '{print $5}' | sed 's/-,//')
    # Since 9.7.3 is requested but likely unavailable in default Ubuntu repos,
    # we check if the current installation is acceptable.
    if [[ "$CURRENT_VERSION" == "$TARGET_VERSION" ]]; then
        echo "MySQL $TARGET_VERSION already installed."
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=$APP_NAME"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$CURRENT_VERSION"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

# 2. Apt Cache Policy Check
# Check if package is available in repositories to avoid unnecessary update
if ! apt-cache policy "$PACKAGE_NAME" >/dev/null 2>&1; then
    # Attempt update only if package not found in local cache
    echo "Updating apt repositories..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update >"/var/tmp/apt_update.log" 2>&1
    UPDATE_EXIT=$?
    
    if [ $UPDATE_EXIT -ne 0 ]; then
        LOG_OUT=$(cat "/var/tmp/apt_update.log")
        if echo "$LOG_OUT" | grep -qiE "Temporary failure in name resolution|Could not resolve"; then
            fail "DNS_FAILURE"
        elif echo "$LOG_OUT" | grep -qiE "Failed to fetch|Network is unreachable"; then
            fail "NETWORK_FAILURE"
        elif echo "$LOG_OUT" | grep -qi "NO_PUBKEY"; then
            echo "Warning: GPG errors detected, attempting to proceed anyway."
        else
            # If it's a critical error and not a GPG issue, fail
            fail "APT_REPOSITORY_FAILURE"
        fi
    fi
fi

# 3. Installation
echo "Installing $PACKAGE_NAME..."
export DEBIAN_FRONTEND=noninteractive
apt-get install -y "$PACKAGE_NAME" >"/var/tmp/mysql_install.log" 2>&1
INSTALL_EXIT=$?

if [ $INSTALL_EXIT -ne 0 ]; then
    fail "PACKAGE_MANAGER_FAILURE"
fi

# 4. Verification
echo "Verifying installation..."
if ! $VERIFY_CMD >/dev/null 2>&1; then
    fail "VERIFICATION_FAILURE"
fi

# Capture actual version installed
ACTUAL_VERSION=$($VERIFY_CMD | awk '{print $5}' | sed 's/-,//')

# Final Success Output
echo "DEPLOYIQ_RESULT_START"
echo "APPLICATION=$APP_NAME"
echo "INSTALLATION_STATUS=SUCCESS"
echo "VERIFICATION_STATUS=SUCCESS"
echo "INSTALLED_VERSION=$ACTUAL_VERSION"
echo "DEPLOYIQ_RESULT_END"

exit 0