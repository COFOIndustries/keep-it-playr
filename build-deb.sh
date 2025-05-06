#!/bin/bash
set -e

# Metadata
VERSION="1.0.3"
PKG="keep-it-playr"
BUILD="${PKG}_${VERSION}"

# Clean old build
rm -rf "${BUILD}"

# Create dirs
mkdir -p "${BUILD}/DEBIAN" \
         "${BUILD}/usr/local/bin" \
         "${BUILD}/usr/share/${PKG}" \
         "${BUILD}/usr/share/applications"

# Copy files & vendor
cp main.py mpv_controller.py "${BUILD}/usr/share/${PKG}/"
cp -r assets art vendor "${BUILD}/usr/share/${PKG}/"

# Launcher script
cat > keep-it-playr-launcher.sh << 'EOF'
#!/bin/sh
exec python3 /usr/share/keep-it-playr/main.py
EOF
chmod +x keep-it-playr-launcher.sh
cp keep-it-playr-launcher.sh "${BUILD}/usr/local/bin/keep-it-playr"

# Desktop entry
cat > "${BUILD}/usr/share/applications/keep-it-playr.desktop" << 'EOF'
[Desktop Entry]
Name=KEEP-IT PLAYR
Exec=keep-it-playr
Icon=/usr/share/keep-it-playr/art/officiallogo.png
Type=Application
Categories=Audio;Player;
Terminal=false
EOF

# Control file
cat > "${BUILD}/DEBIAN/control" << 'EOF'
Package: ${PKG}
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: all
Depends: python3, python3-tk, python3-pil, mpv, yt-dlp, python3-requests
Maintainer: cosas.malas
Description: KEEP-IT PLAYR — a CustomTkinter YouTube/Audio player
EOF

# Build the .deb
dpkg-deb --build --root-owner-group "${BUILD}"
echo "Built ${PKG}_${VERSION}.deb"
