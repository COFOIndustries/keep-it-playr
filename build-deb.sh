#!/bin/bash
set -e

# 1️⃣ Metadata
VERSION="1.0.3"
PKG="keep-it-playr"
BUILD="${PKG}_${VERSION}"

# 2️⃣ Clean old build
rm -rf "${BUILD}"

# 3️⃣ Create package layout
mkdir -p "${BUILD}/DEBIAN"
mkdir -p "${BUILD}/usr/local/bin"
mkdir -p "${BUILD}/usr/share/${PKG}"
mkdir -p "${BUILD}/usr/share/applications"

# 4️⃣ Copy application files + assets + vendor
cp main.py mpv_controller.py "${BUILD}/usr/share/${PKG}/"
cp -r assets art vendor "${BUILD}/usr/share/${PKG}/"

# 5️⃣ Create launcher script and install it
cat > keep-it-playr-launcher.sh << 'LAUNCHER'
#!/bin/sh
exec python3 /usr/share/keep-it-playr/main.py
LAUNCHER
chmod +x keep-it-playr-launcher.sh
cp keep-it-playr-launcher.sh "${BUILD}/usr/local/bin/keep-it-playr"

# 6️⃣ Create desktop entry
cat > "${BUILD}/usr/share/applications/keep-it-playr.desktop" << 'DESKTOP'
[Desktop Entry]
Name=KEEP-IT PLAYR
Exec=/usr/local/bin/keep-it-playr
Icon=/usr/share/keep-it-playr/art/officiallogo.png
Type=Application
Categories=Audio;Player;
Terminal=false
DESKTOP


# 7️⃣ Write DEBIAN/control (variables WILL expand because we’re using << EOF)
cat > "${BUILD}/DEBIAN/control" << EOF
Package: ${PKG}
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: all
Depends: python3, python3-tk, python3-pil, mpv, yt-dlp, python3-requests
Maintainer: cosas.malas
Description: KEEP-IT PLAYR — a CustomTkinter YouTube/Audio player
EOF

# 8️⃣ Build the .deb (force root ownership)
dpkg-deb --build --root-owner-group "${BUILD}"
echo "Built ${PKG}_${VERSION}.deb successfully."
