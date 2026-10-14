# Configuration
APP_NAME="jmeter"
PACKAGE_NAME="jmeter"
EXPECTED_VERSION="2.13"
VERIFY_CMD="jmeter -v"

# Function to print failure and exit
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
if command -v jmeter >/dev/null 2>&1; then
    CURRENT_VER=$(jmeter -v 2>&1 | grep -oP '(?<=version )[^ ]+' || dpkg-query -W -f='${Version}' $PACKAGE_NAME 2>/dev/null)
    if [[ "$CURRENT_VER" == *"$EXPECTED_VERSION"* ]]; then
        echo "jmeter $EXPECTED_VERSION is already installed."
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=$APP_NAME"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$CURRENT_VER"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

# 2. APT Availability Check
# Check if package exists in current cache to avoid unnecessary update
if ! apt-cache policy "$PACKAGE_NAME" >/dev/null 2>&1; then
    echo "Updating package lists..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update >"/var/tmp/apt_update.log" 2>&1
    UPDATE_EXIT=$?
    
    if [ $UPDATE_EXIT -ne 0 ]; then
        LOG_OUT=$(cat /var/tmp/apt_update.log)
        if echo "$LOG_OUT" | grep -qiE "Temporary failure in name resolution|Could not resolve"; then
            fail "DNS_FAILURE"
        elif echo "$LOG_OUT" | grep -qiE "Failed to fetch|Network is unreachable"; then
            fail "NETWORK_FAILURE"
        elif echo "$LOG_OUT" | grep -qi "NO_PUBKEY"; then
            # GPG errors in 3rd party repos shouldn't block if package is still available
            echo "Warning: GPG errors detected in some repositories, proceeding..."
        else
            fail "APT_REPOSITORY_FAILURE"
        fi
    fi
fi

# 3. Installation
echo "Installing $PACKAGE_NAME..."
export DEBIAN_FRONTEND=noninteractive
apt-get install -y "$PACKAGE_NAME" >"/var/tmp/apt_install.log" 2>&1
if [ $? -ne 0 ]; then
    fail "PACKAGE_MANAGER_FAILURE"
fi

# 4. Verification
echo "Verifying installation..."
if ! $VERIFY_CMD >/dev/null 2>&1; then
    fail "VERIFICATION_FAILURE"
fi

# Get final version for output
FINAL_VER=$(dpkg-query -W -f='${Version}' "$PACKAGE_NAME" 2>/dev/null || $VERIFY_CMD 2>&1 | grep -oP '(?<=version )[^ ]+')

echo "DEPLOYIQ_RESULT_START"
echo "APPLICATION=$APP_NAME"
echo "INSTALLATION_STATUS=SUCCESS"
echo "VERIFICATION_STATUS=SUCCESS"
echo "INSTALLED_VERSION=$FINAL_VER"
echo "DEPLOYIQ_RESULT_END"

exit 0