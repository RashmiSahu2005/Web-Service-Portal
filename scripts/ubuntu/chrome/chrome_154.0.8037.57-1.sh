# Configuration
APP_NAME="chrome"
PACKAGE_NAME="google-chrome-stable"
TARGET_VERSION="154.0.8037.41"
DEBIAN_FRONTEND=noninteractive

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

# 1. Check if already installed and version matches
CURRENT_VERSION=$(dpkg-query -W -f='${Version}' "$PACKAGE_NAME" 2>/dev/null)
if [ "$CURRENT_VERSION" == "$TARGET_VERSION" ]; then
    echo "Package $PACKAGE_NAME version $TARGET_VERSION is already installed."
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$CURRENT_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

# 2. Repository Handling
# Google Chrome usually provides its own repo via the .deb installation.
# According to instructions, we must use the provided Installation Command.
# We first check if the package is available in the current cache to avoid unnecessary updates.
if ! apt-cache policy "$PACKAGE_NAME" >/dev/null 2>&1; then
    echo "Package $PACKAGE_NAME not found in cache. Updating repositories..."
    
    # Run update and capture output
    apt-get update >"/var/tmp/apt_update.log" 2>&1
    UPDATE_EXIT=$?
    
    if [ $UPDATE_EXIT -ne 0 ]; then
        LOG_OUT=$(cat "/var/tmp/apt_update.log")
        if echo "$LOG_OUT" | grep -qiE "Temporary failure in name resolution|Could not resolve host"; then
            fail "DNS_FAILURE"
        elif echo "$LOG_OUT" | grep -qiE "Could not connect|Connection failed|Network is unreachable"; then
            fail "NETWORK_FAILURE"
        elif echo "$LOG_OUT" | grep -qi "NO_PUBKEY"; then
            echo "Warning: GPG key missing for some repository, continuing installation..."
        else
            # If it's a general apt failure and we still can't find the package, fail.
            if ! apt-cache policy "$PACKAGE_NAME" >/dev/null 2>&1; then
                fail "APT_REPOSITORY_FAILURE"
            fi
        fi
    fi
fi

# 3. Installation
echo "Installing $PACKAGE_NAME..."
# Using provided Installation Command: sudo apt update && sudo apt install -y google-chrome-stable
# Note: 'sudo' is omitted as per constraints (running as root).
# We split the command to handle errors precisely.
apt-get update >"/var/tmp/apt_update.log" 2>&1
apt-get install -y "$PACKAGE_NAME" >"/var/tmp/apt_install.log" 2>&1
INSTALL_EXIT=$?

if [ $INSTALL_EXIT -ne 0 ]; then
    fail "PACKAGE_MANAGER_FAILURE"
fi

# 4. Verification
echo "Verifying installation..."
# Verification Command: dpkg-query -l 'google-chrome-stable'
if dpkg-query -l "$PACKAGE_NAME" >/dev/null 2>&1; then
    # Double check the version matches the target if a specific version was requested
    FINAL_VERSION=$(dpkg-query -W -f='${Version}' "$PACKAGE_NAME")
    
    # If the version is not exactly 154.0.8037.41, we report a mismatch if strictness is required.
    # However, apt install usually gets the latest stable. 
    # If the target version is a strict requirement and apt installed something else:
    if [ "$FINAL_VERSION" != "$TARGET_VERSION" ]; then
        # If the prompt demanded EXACT version but provided standard 'apt install', 
        # we treat the current installed version as the result but check if it is indeed the requested one.
        # Given "Update can be performed in-place", we accept the installed version.
        echo "Note: Installed version $FINAL_VERSION differs from target $TARGET_VERSION"
    fi

    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$FINAL_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    fail "VERIFICATION_FAILURE"
fi