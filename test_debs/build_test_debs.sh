#!/bin/bash
# Build test Debian packages for testing debs3

set -e

echo "Building test Debian packages..."

# Create hello-world package
mkdir -p hello-world/DEBIAN
mkdir -p hello-world/usr/bin

cat > hello-world/DEBIAN/control <<EOF
Package: hello-world
Version: 1.0.0
Architecture: amd64
Maintainer: Test User <test@example.com>
Description: Hello World test package
 This is a test package for debs3.
 It contains a simple hello world script.
Section: utils
Priority: optional
EOF

cat > hello-world/usr/bin/hello-world <<'EOF'
#!/bin/bash
echo "Hello, World!"
EOF

chmod +x hello-world/usr/bin/hello-world

dpkg-deb --build hello-world
mv hello-world.deb hello-world_1.0.0_amd64.deb

# Create goodbye-forever package
mkdir -p goodbye-forever/DEBIAN
mkdir -p goodbye-forever/usr/bin

cat > goodbye-forever/DEBIAN/control <<EOF
Package: goodbye-forever
Version: 2.0.0
Architecture: amd64
Maintainer: Test User <test@example.com>
Description: Goodbye Forever test package
 This is another test package for debs3.
 It contains a simple goodbye script.
Section: utils
Priority: optional
EOF

cat > goodbye-forever/usr/bin/goodbye-forever <<'EOF'
#!/bin/bash
echo "Goodbye, Forever!"
EOF

chmod +x goodbye-forever/usr/bin/goodbye-forever

dpkg-deb --build goodbye-forever
mv goodbye-forever.deb goodbye-forever_2.0.0_amd64.deb

# Clean up build directories
rm -rf hello-world goodbye-forever

echo "✓ Test packages built successfully:"
ls -lh *.deb
