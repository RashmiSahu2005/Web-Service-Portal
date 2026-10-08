set -e

TARGET_VERSION="5.6.3"
INSTALL_DIR="/opt/apache-jmeter-${TARGET_VERSION}"
DOWNLOAD_URL="https://dlcdn.apache.org/jmeter/binaries/apache-jmeter-${TARGET_VERSION}.tgz"
WORKING_DIR="/var/tmp/jmeter_install"

echo "Checking for Java dependency..."
if ! command -v java >/dev/null 2>&1; then
    echo "Java not found. Installing default-jre..."
    DEBIAN_FRONTEND=noninteractive apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y default-jre
else
    echo "Java is already installed."
fi

# Verify Java installation
if ! java -version >/dev/null 2>&1; then
    echo "ERROR: Java installation failed or binary is not executable."
    exit 1
fi

# Idempotency check: Check if target version is already installed
if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/bin/jmeter" ]; then
    echo "JMeter ${TARGET_VERSION} is already installed at ${INSTALL_DIR}."
    # Verification check for existing install
    if $INSTALL_DIR/bin/jmeter -v | grep -q "5.6.3"; then
        echo "Verification successful."
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=JMeter"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=${TARGET_VERSION}"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

echo "Downloading JMeter ${TARGET_VERSION}..."
mkdir -p "$WORKING_DIR"
wget -q "$DOWNLOAD_URL" -O "$WORKING_DIR/apache-jmeter.tgz"

# Validate download
if [ ! -s "$WORKING_DIR/apache-jmeter.tgz" ]; then
    echo "ERROR: Downloaded file is empty or missing."
    exit 1
fi

if ! tar -tzf "$WORKING_DIR/apache-jmeter.tgz" >/dev/null 2>&1; then
    echo "ERROR: Downloaded tarball is corrupted."
    exit 1
fi

echo "Extracting JMeter..."
# Extract to a temporary sibling directory first to ensure integrity
STAGING_DIR="/var/tmp/jmeter_staging"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
tar -xzf "$WORKING_DIR/apache-jmeter.tgz" -C "$STAGING_DIR"

# Find the extracted directory (tarballs usually contain a root folder)
EXTRACTED_PATH=$(find "$STAGING_DIR" -maxdepth 1 -type d -name "apache-jmeter-*" | head -n 1)

if [ -z "$EXTRACTED_PATH" ] || [ ! -f "$EXTRACTED_PATH/bin/jmeter" ]; then
    echo "ERROR: Extraction failed or binary not found in archive."
    exit 1
fi

echo "Installing to ${INSTALL_DIR}..."
# Atomic move to target location
rm -rf "$INSTALL_DIR"
mv "$EXTRACTED_PATH" "$INSTALL_DIR"

# Cleanup
rm -rf "$WORKING_DIR"
rm -rf "$STAGING_DIR"

# Final Verification
echo "Verifying installation..."
if [ -f "$INSTALL_DIR/bin/jmeter" ]; then
    # Run version check (non-GUI mode)
    if "$INSTALL_DIR/bin/jmeter" -v | grep -q "5.6.3"; then
        echo "Verification successful."
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=JMeter"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=${TARGET_VERSION}"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    else
        echo "ERROR: Version mismatch in installed binary."
        exit 1
    fi
else
    echo "ERROR: Executable path not found after installation."
    exit 1
fi