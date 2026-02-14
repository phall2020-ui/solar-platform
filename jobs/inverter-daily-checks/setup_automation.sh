#!/bin/bash
# Inverter Monitor Automation Setup Script
# 
# This script sets up the launchd service to run the inverter monitor every 2 hours.
# 
# Usage:
#   ./setup_automation.sh install   - Install and start the service
#   ./setup_automation.sh uninstall - Stop and remove the service
#   ./setup_automation.sh status    - Check if the service is running
#   ./setup_automation.sh logs      - View recent logs

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.peterhall.inverter-monitor.plist"
PLIST_SOURCE="$SCRIPT_DIR/$PLIST_NAME"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"

case "$1" in
    install)
        echo "Installing inverter monitor automation..."
        
        # Create LaunchAgents directory if it doesn't exist
        mkdir -p "$HOME/Library/LaunchAgents"
        
        # Create logs directory
        mkdir -p "$SCRIPT_DIR/logs"
        
        # Copy plist to LaunchAgents
        cp "$PLIST_SOURCE" "$PLIST_DEST"
        
        # Load the service
        launchctl load "$PLIST_DEST"
        
        echo "✅ Service installed and started!"
        echo ""
        echo "The script will run:"
        echo "  - Immediately (on load)"
        echo "  - Every 2 hours after that"
        echo ""
        echo "To check status: ./setup_automation.sh status"
        echo "To view logs: ./setup_automation.sh logs"
        ;;
        
    uninstall)
        echo "Uninstalling inverter monitor automation..."
        
        # Unload the service
        launchctl unload "$PLIST_DEST" 2>/dev/null
        
        # Remove plist
        rm -f "$PLIST_DEST"
        
        echo "✅ Service uninstalled!"
        ;;
        
    status)
        echo "Checking service status..."
        if launchctl list | grep -q "com.peterhall.inverter-monitor"; then
            echo "✅ Service is RUNNING"
            echo ""
            echo "Service details:"
            launchctl list | grep "inverter-monitor"
        else
            echo "❌ Service is NOT running"
            echo ""
            echo "To install: ./setup_automation.sh install"
        fi
        ;;
        
    logs)
        echo "=== Recent stdout logs ==="
        tail -50 "$SCRIPT_DIR/logs/launchd_stdout.log" 2>/dev/null || echo "(no logs yet)"
        echo ""
        echo "=== Recent stderr logs ==="
        tail -20 "$SCRIPT_DIR/logs/launchd_stderr.log" 2>/dev/null || echo "(no errors)"
        ;;
        
    run-now)
        echo "Manually triggering the service..."
        launchctl start "com.peterhall.inverter-monitor"
        echo "✅ Service triggered! Check logs with: ./setup_automation.sh logs"
        ;;
        
    *)
        echo "Inverter Monitor Automation Setup"
        echo ""
        echo "Usage: $0 {install|uninstall|status|logs|run-now}"
        echo ""
        echo "Commands:"
        echo "  install   - Install and start the service (runs every 2 hours)"
        echo "  uninstall - Stop and remove the service"
        echo "  status    - Check if the service is running"
        echo "  logs      - View recent logs"
        echo "  run-now   - Manually trigger the script immediately"
        exit 1
        ;;
esac
