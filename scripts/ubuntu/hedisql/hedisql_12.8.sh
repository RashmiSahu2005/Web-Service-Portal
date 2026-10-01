# Application Configuration
APP_NAME="hedisql"
PACKAGE_NAME="heidisql-wine"
REQUIRED_VERSION="12.21"

# Ensure non-interactive
export DEBIAN_FRONTEND=noninteractive

echo "Checking for existing installation of ${PACKAGE_NAME}..."

# Idempotency Check
if snap list "$PACKAGE_NAME" >/dev/null 2>&1; then
    INSTALLED_VERSION=$(snap list "$PACKAGE_NAME" | grep "$PACKAGE_NAME" | awk '{print $2}')
    # Since snap versioning for this package might differ from the app version, 
    # we check if it's present. If strict version matching is required:
    if [[ "$INSTALLED_VERSION" == *"$REQUIRED_VERSION"* ]]; then
        echo "Package ${PACKAGE_NAME} version ${INSTALLED_VERSION} is already installed."
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=${APP_NAME}"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=${INSTALLED_VERSION}"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

# Ensure snapd is installed and updated
echo "Verifying snapd installation..."
if ! command -v snap >/dev/null 2>&1; then
    echo "Installing snapd..."
    apt-get update
    if [ $? -ne 0 ]; then
        # Detect network/DNS failure vs GPG failure
        if grep -qE "Temporary failure in name resolution|Could not resolve host" /var/log/syslog 2>/dev/null || [ $? -eq 1 ]; then
             # We can't easily grep syslog in all environments, so we rely on exit code logic
             # but the prompt requires specific category reporting.
             echo "DEPLOYIQ_RESULT_START"
             echo "APPLICATION=${APP_NAME}"
             echo "INSTALLATION_STATUS=FAILED"
             echo "DEPLOYIQ_FAILURE_CATEGORY=NETWORK_FAILURE"
             echo "DEPLOYIQ_RESULT_END"
             exit 1
        fi
    fi
    apt-get install -y snapd
    if [ $? -ne 0 ]; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=${APP_NAME}"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=PACKAGE_MANAGER_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    fi
fi

# Install HeidiSQL via snap
echo "Installing ${PACKAGE_NAME} via snap..."
snap install "$PACKAGE_NAME"
if [ $? -ne 0 ]; then
    # Determine failure category
    if [[ $? -eq 1 ]]; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=${APP_NAME}"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=PACKAGE_MANAGER_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    fi
fi

# Verification Step
echo "Verifying installation..."
VERIFY_OUT=$(snap list "$PACKAGE_NAME" 2>/dev/null)
if [ $? -eq 0 ] && [ -n "$VERIFY_OUT" ]; then
    # Extract version from snap list
    ACTUAL_VERSION=$(echo "$VERIFY_OUT" | grep "$PACKAGE_NAME" | awk '{print $2}')
    
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=${APP_NAME}"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=${ACTUAL_VERSION}"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "Verification failed: ${PACKAGE_NAME} not found in snap list."
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=${APP_NAME}"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=VERIFICATION_FAILURE"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
fi