#!/bin/bash

# Configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$PROJECT_DIR/mini-services"

main() {
    echo "🚀 Starting batch dependency install..."
    
    # Check root directory exists
    if [ ! -d "$ROOT_DIR" ]; then
        echo "ℹ️  Directory $ROOT_DIR does not exist, skipping"
        return
    fi
    
    # Counters
    success_count=0
    fail_count=0
    failed_projects=""
    
    # Iterate mini-services subdirectories
    for dir in "$ROOT_DIR"/*; do
        # Install only directories that contain package.json
        if [ -d "$dir" ] && [ -f "$dir/package.json" ]; then
            project_name=$(basename "$dir")
            echo ""
            echo "📦 Installing dependencies: $project_name..."
            
            # Run bun install inside project directory
            if (cd "$dir" && bun install); then
                echo "✅ $project_name dependency install succeeded"
                success_count=$((success_count + 1))
            else
                echo "❌ $project_name dependency install failed"
                fail_count=$((fail_count + 1))
                if [ -z "$failed_projects" ]; then
                    failed_projects="$project_name"
                else
                    failed_projects="$failed_projects $project_name"
                fi
            fi
        fi
    done
    
    # Summary
    echo ""
    echo "=================================================="
    if [ $success_count -gt 0 ] || [ $fail_count -gt 0 ]; then
        echo "🎉 Installation finished"
        echo "✅ Success: $success_count"
        if [ $fail_count -gt 0 ]; then
            echo "❌ Failed: $fail_count"
            echo ""
            echo "Failed projects:"
            for project in $failed_projects; do
                echo "  - $project"
            done
        fi
    else
        echo "ℹ️  No projects with package.json were found"
    fi
    echo "=================================================="
}

main
