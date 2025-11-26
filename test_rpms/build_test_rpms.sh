#!/bin/bash
# Script to build test RPM packages for integration testing using rpmbuild

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_ROOT="${HOME}/rpmbuild"

# Setup rpmbuild directory structure
mkdir -p "${BUILD_ROOT}"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

echo "Building test RPM packages..."

# Create hello-world spec file
cat > "${BUILD_ROOT}/SPECS/hello-world.spec" << 'EOF'
Name:           hello-world
Version:        1.0.0
Release:        1.el9
Summary:        Test package that installs a Hello World message
License:        MIT
BuildArch:      x86_64

%description
Test package that installs a Hello World message file.

%install
mkdir -p %{buildroot}/usr/share/hello-world
echo "Hello World" > %{buildroot}/usr/share/hello-world/message.txt

%files
/usr/share/hello-world/message.txt

%changelog
* Mon Nov 25 2025 Test User <test@example.com> - 1.0.0-1.el9
- Initial test package
EOF

# Create goodbye-forever spec file
cat > "${BUILD_ROOT}/SPECS/goodbye-forever.spec" << 'EOF'
Name:           goodbye-forever
Version:        2.0.0
Release:        1.el9
Summary:        Test package that installs a Goodbye Forever message
License:        MIT
BuildArch:      x86_64

%description
Test package that installs a Goodbye Forever message file.

%install
mkdir -p %{buildroot}/usr/share/goodbye-forever
echo "Goodbye Forever" > %{buildroot}/usr/share/goodbye-forever/message.txt

%files
/usr/share/goodbye-forever/message.txt

%changelog
* Mon Nov 25 2025 Test User <test@example.com> - 2.0.0-1.el9
- Initial test package
EOF

# Build the RPMs
echo "Building hello-world RPM..."
rpmbuild -bb "${BUILD_ROOT}/SPECS/hello-world.spec" 2>&1 | grep -v "Executing(%"

echo "Building goodbye-forever RPM..."
rpmbuild -bb "${BUILD_ROOT}/SPECS/goodbye-forever.spec" 2>&1 | grep -v "Executing(%"

# Copy RPMs to test_rpms directory
cp "${BUILD_ROOT}/RPMS/x86_64/hello-world-1.0.0-1.el9.x86_64.rpm" "${SCRIPT_DIR}/"
cp "${BUILD_ROOT}/RPMS/x86_64/goodbye-forever-2.0.0-1.el9.x86_64.rpm" "${SCRIPT_DIR}/"

echo ""
echo "✓ Test RPMs created successfully:"
ls -lh "${SCRIPT_DIR}"/*.rpm
