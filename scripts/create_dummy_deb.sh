#!/bin/bash
set -e

REPO_DIR="repository/vscode"
mkdir -p "$REPO_DIR"

DEB_DIR="dummy_deb_build"
mkdir -p "$DEB_DIR/DEBIAN"
mkdir -p "$DEB_DIR/usr/local/bin"

# Create a control file
cat <<EOF > "$DEB_DIR/DEBIAN/control"
Package: code
Version: 1.85.1
Section: custom
Priority: optional
Architecture: amd64
Maintainer: Application Hub <admin@example.com>
Description: Dummy VS Code Package
 A dummy package used for testing the Application Hub deployment pipeline.
EOF

# Create a dummy executable
cat <<EOF > "$DEB_DIR/usr/local/bin/code"
#!/bin/bash
echo "Dummy VS Code is running!"
EOF
chmod +x "$DEB_DIR/usr/local/bin/code"

# Build the deb
dpkg-deb --build "$DEB_DIR" "$REPO_DIR/code_1.85.1_amd64.deb"

# Cleanup
rm -rf "$DEB_DIR"

echo "Dummy package created at $REPO_DIR/code_1.85.1_amd64.deb"
