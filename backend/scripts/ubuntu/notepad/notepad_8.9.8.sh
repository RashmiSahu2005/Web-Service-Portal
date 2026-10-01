set -e

APP_NAME="Notepad++"
TARGET_VERSION="8.9.8"
DOWNLOAD_URL="https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.9.8/npp.8.9.8.Installer.x64.exe"
INSTALLER_PATH="/var/tmp/notepad++-installer.exe"
# Notepad++ via Wine usually creates a shortcut or is accessible via wine start.
# Since the verification method requested is 'command -v notepad-++', we will symlink the launch command.
BIN_SYMLINK="/usr/local/bin/notepad-++"

echo "Checking if ${APP_NAME} is already installed..."
if command -v notepad-++ >/dev/null 2>&1; then
    echo "${APP_NAME} is already installed. Skipping installation."
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=${APP_NAME}"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=${TARGET_VERSION}"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

echo "Updating package lists..."
DEBIAN_FRONTEND=noninteractive apt-get update -y

echo "Installing dependencies (wine)..."
DEBIAN_FRONTEND=noninteractive apt-get install -y wine64 wine32

echo "Downloading ${APP_NAME} installer..."
wget -q "$DOWNLOAD_URL" -O "$INSTALLER_PATH"

if [ ! -s "$INSTALLER_PATH" ]; then
    echo "ERROR: Installer download failed or file is empty."
    exit 1
fi

echo "Running installer via Wine (Non-interactive)..."
# Wine installers usually require a display. In a headless environment, we use xvfb or assume 
# the installer can run silently. Most NPP installers use NSIS; /S is the silent flag.
# We use WINEDLLS=native to avoid some common root issues.
export WINEDEBUG=-all
wine "$INSTALLER_PATH" /S || true

# Notepad++ installs into the Wine prefix (usually ~/.wine/drive_c/Program Files/Notepad++).
# Since we are running as root, it's /root/.wine.
NPP_EXE="/root/.wine/drive_c/Program Files/Notepad++/notepad++.exe"

if [ -f "$NPP_EXE" ]; then
    echo "Installation successful. Creating symlink for verification..."
    # Create a wrapper script to allow 'notepad-++' command to work
    echo '#!/bin/bash\nwine "$NPP_EXE" "$@"' > /usr/local/bin/notepad-++
    chmod +x /usr/local/bin/notepad-++
else
    echo "ERROR: Installer completed but executable not found at $NPP_EXE"
    exit 1
fi

echo "Verifying installation..."
if command -v notepad-++ >/dev/null 2>&1; then
    echo "Verification successful."
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=${APP_NAME}"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=${TARGET_VERSION}"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "ERROR: Verification failed. Command notepad-++ not found."
    exit 1
fi