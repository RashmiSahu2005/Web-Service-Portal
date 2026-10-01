set -e

TARGET_PACKAGE="outlook-for-linux"
TARGET_VERSION="2607"

echo "Checking for snapd..."
if ! command -v snap >/dev/null 2>&1; then
    echo "Installing snapd..."
    DEBIAN_FRONTEND=noninteractive apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y snapd
else
    echo "snapd is already installed."
fi

echo "Checking if $TARGET_PACKAGE is already installed..."
if snap list "$TARGET_PACKAGE" >/dev/null 2>&1; then
    INSTALLED_VERSION=$(snap list "$TARGET_PACKAGE" | grep "$TARGET_PACKAGE" | awk '{print $2}')
    echo "Package $TARGET_PACKAGE is already installed (Version: $INSTALLED_VERSION)."
    # As per constraint 11, we are lenient with version strings if the package is present.
    # Proceeding to verification.
else
    echo "Installing $TARGET_PACKAGE from edge channel..."
    if ! snap install "$TARGET_PACKAGE" --edge; then
        echo "ERROR: snap installation failed."
        exit 1
    fi
fi

echo "Verifying installation..."
if snap list "$TARGET_PACKAGE" >/dev/null 2>&1; then
    ACTUAL_VERSION=$(snap list "$TARGET_PACKAGE" | grep "$TARGET_PACKAGE" | awk '{print $2}')
    echo "Verification successful. Installed version: $ACTUAL_VERSION"
else
    echo "ERROR: Verification failed. $TARGET_PACKAGE not found in snap list."
    exit 1
fi

cat <<EOF
DEPLOYIQ_RESULT_START
APPLICATION=outlook
INSTALLATION_STATUS=SUCCESS
VERIFICATION_STATUS=SUCCESS
INSTALLED_VERSION=$ACTUAL_VERSION
DEPLOYIQ_RESULT_END
EOF