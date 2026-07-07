#!/bin/bash

# Redirect stderr to stdout to avoid command wrappers treating stderr as failure.
exec 2>&1

set -e

# Resolve script directory (.zscripts).
# Use $0 for compatibility with sh and bash.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Next.js project path
NEXTJS_PROJECT_DIR="$PROJECT_DIR"

# Validate project directory exists
if [ ! -d "$NEXTJS_PROJECT_DIR" ]; then
    echo "❌ Error: Next.js project directory not found: $NEXTJS_PROJECT_DIR"
    exit 1
fi

echo "🚀 Starting Next.js and mini-services build..."
echo "📁 Next.js project path: $NEXTJS_PROJECT_DIR"

# Move to project directory
cd "$NEXTJS_PROJECT_DIR" || exit 1

# Set environment variables
export NEXT_TELEMETRY_DISABLED=1

BUILD_DIR="/tmp/build_fullstack_$BUILD_ID"
echo "📁 Preparing build directory: $BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Install dependencies
echo "📦 Installing dependencies..."
bun install

# Build Next.js app
echo "🔨 Building Next.js app..."
bun run build

# Build mini-services
# Check whether mini-services exists in project directory
if [ -d "$NEXTJS_PROJECT_DIR/mini-services" ]; then
    echo "🔨 Building mini-services..."
    # Use helper scripts from .zscripts
    sh "$SCRIPT_DIR/mini-services-install.sh"
    sh "$SCRIPT_DIR/mini-services-build.sh"

    # Copy mini-services-start.sh into build directory
    echo "  - Copying mini-services-start.sh to $BUILD_DIR"
    cp "$SCRIPT_DIR/mini-services-start.sh" "$BUILD_DIR/mini-services-start.sh"
    chmod +x "$BUILD_DIR/mini-services-start.sh"
else
    echo "ℹ️  mini-services directory not found, skipping"
fi

# Collect build artifacts in temporary directory
echo "📦 Collecting artifacts into $BUILD_DIR..."

# Copy Next.js standalone output
if [ -d ".next/standalone" ]; then
    echo "  - Copying .next/standalone"
    cp -r .next/standalone "$BUILD_DIR/next-service-dist/"
fi

# Copy Next.js static files
if [ -d ".next/static" ]; then
    echo "  - Copying .next/static"
    mkdir -p "$BUILD_DIR/next-service-dist/.next"
    cp -r .next/static "$BUILD_DIR/next-service-dist/.next/"
fi

# Copy public directory
if [ -d "public" ]; then
    echo "  - Copying public"
    cp -r public "$BUILD_DIR/next-service-dist/"
fi

# Copy test database into build artifact for packaged runtime use
if [ -f "./db/custom.db" ]; then
    echo "🗄️  Copying test database into build output..."
    mkdir -p "$BUILD_DIR/db"
    cp -r ./db/. "$BUILD_DIR/db/"

    echo "🗄️  Synchronizing database schema in build output..."
    DATABASE_URL="file:$BUILD_DIR/db/custom.db" bun run db:push
    echo "✅ Build output database is ready"
    ls -lah "$BUILD_DIR/db"
else
    echo "❌ Missing test database ./db/custom.db; cannot continue packaging"
    exit 1
fi

# Copy Caddyfile when present
if [ -f "Caddyfile" ]; then
    echo "  - Copying Caddyfile"
    cp Caddyfile "$BUILD_DIR/"
else
    echo "ℹ️  Caddyfile not found, skipping"
fi

# Copy start.sh
echo "  - Copying start.sh to $BUILD_DIR"
cp "$SCRIPT_DIR/start.sh" "$BUILD_DIR/start.sh"
chmod +x "$BUILD_DIR/start.sh"

# Archive to $BUILD_DIR.tar.gz
PACKAGE_FILE="${BUILD_DIR}.tar.gz"
echo ""
echo "📦 Archiving build artifacts to $PACKAGE_FILE..."
cd "$BUILD_DIR" || exit 1
tar -czf "$PACKAGE_FILE" .
cd - > /dev/null || exit 1

# # Optional: clean temporary directory
# rm -rf "$BUILD_DIR"

echo ""
echo "✅ Build completed. Package created at $PACKAGE_FILE"
echo "📊 Package size:"
ls -lh "$PACKAGE_FILE"
