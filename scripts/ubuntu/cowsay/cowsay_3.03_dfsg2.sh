# Application Configuration
APP_NAME="cowsay"
EXPECTED_VERSION="3.8.4"
PKG_NAME="cowsay"
EXEC_PATH="/usr/bin/cowsay"
VERIFICATION_CMD="/usr/games/cowsay \"Hello, Linux!\"" # Ubuntu's cowsay is often in /usr/games/

# Result printing function
print_result() {
    local status=$1
    local category=$2
    local version=$3
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    if [ "$status" == "SUCCESS" ]; then
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$version"
    else
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=$category"
    fi
    echo "DEPLOYIQ_RESULT_END"
}

# Check if already installed and version matches
if command -v cowsay >/dev/null 2>&1; then
    # apt-cache policy gives us the installed version
    CURRENT_VERSION=$(dpkg-query -W -f='${Version}' $PKG_NAME 2>/dev/null | cut -d':' -f2 | cut -d'-' -f1)
    if [ "$CURRENT_VERSION" == "$EXPECTED_VERSION" ]; then
        print_result "SUCCESS" "" "$CURRENT_VERSION"
        exit 0
    fi
fi

echo "Starting installation of $APP_NAME..."

# Handle APT update with network failure detection
# We capture output to distinguish between GPG errors and DNS/Network errors
UPDATE_LOG=$(export DEBIAN_FRONTEND=noninteractive; apt-get update 2>&1)
UPDATE_EXIT_CODE=$?

if [ $UPDATE_EXIT_CODE -ne 0 ]; then
    if echo "$UPDATE_LOG" | grep -qiE "Could not resolve host|Temporary failure in name resolution"; then
        print_result "FAILED" "DNS_FAILURE" ""
        exit 1
    elif echo "$UPDATE_LOG" | grep -qiE "Connection failed|Network is unreachable"; then
        print_result "FAILED" "NETWORK_FAILURE" ""
        exit 1
    elif echo "$UPDATE_LOG" | grep -qiE "NO_PUBKEY|EXPKEY|GPG error"; then
        echo "Warning: GPG errors detected in some repositories, attempting to proceed with installation..."
    else
        print_result "FAILED" "APT_REPOSITORY_FAILURE" ""
        exit 1
    fi
fi

# Install package
echo "Installing $PKG_NAME..."
export DEBIAN_FRONTEND=noninteractive
if ! apt-get install -y $PKG_NAME; then
    print_result "FAILED" "PACKAGE_MANAGER_FAILURE" ""
    exit 1
fi

# Ubuntu installs cowsay to /usr/games/cowsay. 
# If the requirements insist on /usr/bin/cowsay, we must symlink it.
if [ ! -f "$EXEC_PATH" ]; then
    if [ -f "/usr/games/cowsay" ]; then
        ln -sf /usr/games/cowsay "$EXEC_PATH"
    fi
fi

# Verification
echo "Verifying installation..."
# Use the binary path directly to avoid PATH issues in non-interactive shells
if /usr/games/cowsay "Hello, Linux!" > /dev/null 2>&1; then
    # Get actual installed version for the report
    INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' $PKG_NAME 2>/dev/null | cut -d':' -f2 | cut -d'-' -f1)
    print_result "SUCCESS" "" "$INSTALLED_VERSION"
    exit 0
else
    print_result "FAILED" "VERIFICATION_FAILURE" ""
    exit 1
fi