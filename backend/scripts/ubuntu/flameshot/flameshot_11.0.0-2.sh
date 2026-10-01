set -e

PACKAGE_NAME="flameshot"
TARGET_VERSION="v14.0.0"

echo "Checking if ${PACKAGE_NAME} is already installed..."
if dpkg-query -l '${PACKAGE_NAME}' > /dev/null 2>&1; then
    echo "${PACKAGE_NAME} is already installed. Skipping installation."
else
    echo "Installing ${PACKAGE_NAME} via apt..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    if ! apt-get install -y ${PACKAGE_NAME}; then
        echo "ERROR: Failed to install ${PACKAGE_NAME}"
        exit 1
    fi
fi

echo "Verifying installation..."
if dpkg-query -W -f='${Version}' ${PACKAGE_NAME} > /dev/null 2>&1; then
    INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' ${PACKAGE_NAME})
    echo "Verification successful. Installed version: ${INSTALLED_VERSION}"
else
    echo "ERROR: Verification failed. ${PACKAGE_NAME} not found in dpkg database."
    exit 1
fi

echo "DEPLOYIQ_RESULT_START"
echo "APPLICATION=Flameshot"
echo "INSTALLATION_STATUS=SUCCESS"
echo "VERIFICATION_STATUS=SUCCESS"
echo "INSTALLED_VERSION=${INSTALLED_VERSION}"
echo "DEPLOYIQ_RESULT_END"