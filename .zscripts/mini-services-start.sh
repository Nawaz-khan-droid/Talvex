#!/bin/sh

# Configuration
DIST_DIR="./mini-services-dist"

# Store child process IDs
pids=""

# Cleanup function: gracefully stop all services
cleanup() {
    echo ""
    echo "🛑 Stopping all services..."
    
    # Send SIGTERM to all child processes
    for pid in $pids; do
        if kill -0 "$pid" 2>/dev/null; then
            service_name=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
            echo "   Stopping process $pid ($service_name)..."
            kill -TERM "$pid" 2>/dev/null
        fi
    done
    
    # Wait for all processes to exit (up to 5 seconds)
    sleep 1
    for pid in $pids; do
        if kill -0 "$pid" 2>/dev/null; then
            # If still running, wait up to 4 more seconds
            timeout=4
            while [ $timeout -gt 0 ] && kill -0 "$pid" 2>/dev/null; do
                sleep 1
                timeout=$((timeout - 1))
            done
            # Force-kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                echo "   Force-killing process $pid..."
                kill -KILL "$pid" 2>/dev/null
            fi
        fi
    done
    
    echo "✅ All services stopped"
}

main() {
    echo "🚀 Starting all mini-services..."
    
    # Check dist directory exists
    if [ ! -d "$DIST_DIR" ]; then
        echo "ℹ️  Directory $DIST_DIR does not exist"
        return
    fi
    
    # Discover mini-service-*.js files
    service_files=""
    for file in "$DIST_DIR"/mini-service-*.js; do
        if [ -f "$file" ]; then
            if [ -z "$service_files" ]; then
                service_files="$file"
            else
                service_files="$service_files $file"
            fi
        fi
    done
    
    # Count service files
    service_count=0
    for file in $service_files; do
        service_count=$((service_count + 1))
    done
    
    if [ $service_count -eq 0 ]; then
        echo "ℹ️  No mini-service files found"
        return
    fi
    
    echo "📦 Found $service_count services, starting..."
    echo ""
    
    # Start each service
    for file in $service_files; do
        service_name=$(basename "$file" .js | sed 's/mini-service-//')
        echo "▶️  Starting service: $service_name..."
        
        # Run service with bun in background
        bun "$file" &
        pid=$!
        if [ -z "$pids" ]; then
            pids="$pid"
        else
            pids="$pids $pid"
        fi
        
        # Wait briefly to verify startup
        sleep 0.5
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "❌ $service_name failed to start"
            # Remove failed PID from the list
            pids=$(echo "$pids" | sed "s/\b$pid\b//" | sed 's/  */ /g' | sed 's/^ *//' | sed 's/ *$//')
        else
            echo "✅ $service_name started (PID: $pid)"
        fi
    done
    
    # Count running services
    running_count=0
    for pid in $pids; do
        if kill -0 "$pid" 2>/dev/null; then
            running_count=$((running_count + 1))
        fi
    done
    
    echo ""
    echo "🎉 Startup complete. Running services: $running_count"
    echo ""
    echo "💡 Press Ctrl+C to stop all services"
    echo ""
    
    # Wait for background processes
    wait
}

main
