# Application: nmap
# Version Target: 7.991 (approximate/latest from Universe)
# Strategy: APT Ubuntu Universe

set -e

# --- Helper for Final Output ---
function fail {
    local category=$1
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=nmap"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=$category"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
}

function success {
    local version=$1
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=nmap"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$version"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
}

# 1. Idempotency Check
# Check if nmap is already installed
if dpkg-query -l 'nmap' > /dev/null 2>&1; then
    INSTALLED_VER=$(dpkg-query -W -f='${Version}' nmap)
    # If installed, we verify the executable is functional and skip installation
    if /usr/bin/nmap --version > /dev/null 2>&1; then
        echo "nmap is already installed (Version: $INSTALLED_VER). Skipping installation."
        success "$INSTALLED_VER"
    fi
fi

echo "Starting installation of nmap..."

# 2. APT Package Availability Check
# Check if a candidate version exists before running update to avoid unrelated repo errors
if ! apt-cache policy nmap > /dev/null 2>&1; then
    echo "Package nmap not found in cache. Running apt-get update..."
    
    # Execute update and capture output/exit code
    # Use /var/tmp as requested
    DEBIAN_FRONTEND=noninteractive apt-get update >"/var/tmp/apt_update.log" 2>&1
    UPDATE_EXIT=$?
    
    if [ $UPDATE_EXIT -ne 0 ]; then
        LOG_OUT=$(cat /var/tmp/apt_update.log)
        # Detect Network/DNS failure
        if echo "$LOG_OUT" | grep -qiE "Temporary failure in name resolution|Could not resolve host|Network is unreachable"; then
            fail "NETWORK_FAILURE"
        elif echo "$LOG_OUT" | grep -qiE "404 Not Found|Expired"; then
            # If it's just a 404 on a 3rd party repo, we continue. If it's the main repo, we fail.
            if echo "$LOG_OUT" | grep -qi "archive.ubuntu.com"; then
                fail "APT_REPOSITORY_FAILURE"
            fi
        elif echo "$LOG_OUT" | grep -qiE "NO_PUBKEY|GPG error"; then
            # GPG errors on 3rd party repos should not block the target package if it's in Universe
            echo "Warning: APT GPG errors detected, proceeding to try installation."
        else
            # Check if package is now available despite the error
            if ! apt-cache policy nmap > /dev/null 2>&1; then
                fail "PACKAGE_MANAGER_FAILURE"
            fi
        fi
    fi
fi

# 3. Installation
echo "Installing nmap via apt..."
DEBIAN_FRONTEND=noninteractive apt-get install -y nmap >"/var/tmp/nmap_install.log" 2>&1
if [ $? -ne 0 ]; then
    fail "PACKAGE_MANAGER_FAILURE"
fi

# 4. Verification
echo "Verifying installation..."

# Explicit Verification Command: dpkg-query -l 'nmap'
if ! dpkg-query -l 'nmap' > /dev/null 2>&1; then
    fail "VERIFICATION_FAILURE"
fi

# Ensure executable exists at specified path
if [ ! -x "/usr/bin/nmap" ]; then
    fail "VERIFICATION_FAILURE"
fi

# Get actual installed version for the final report
ACTUAL_VERSION=$(dpkg-query -W -f='${Version}' nmap)

# Final success output
success "$ACTUAL_VERSION"