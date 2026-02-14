#!/bin/bash

# Stop all Uniswap V3 Multi-Agent services

echo "Stopping Uniswap V3 Multi-Agent Services..."
echo

if [ -f ".pids" ]; then
    echo "📋 Stopping services from .pids file..."
    kill $(cat .pids) 2>/dev/null
    rm .pids
    echo "✅ Services stopped from .pids"
else
    echo "🔍 Finding and stopping services on ports..."
    
    # Kill processes on specific ports
    echo "  • Stopping Backend Orchestrator (port 5000)..."
    lsof -ti:5000 | xargs -r kill -9 2>/dev/null
    
    echo "  • Stopping Pool Risk Service (port 8001)..."
    lsof -ti:8001 | xargs -r kill -9 2>/dev/null
    
    echo "  • Stopping Pool Risk MCP (port 8002)..."
    lsof -ti:8002 | xargs -r kill -9 2>/dev/null
    
    echo "  • Stopping Token Intel Service (port 8003)..."
    lsof -ti:8003 | xargs -r kill -9 2>/dev/null
    
    echo "  • Stopping Token Intel MCP (port 8004)..."
    lsof -ti:8004 | xargs -r kill -9 2>/dev/null
    
    echo "  • Stopping Streamlit (port 8501, if running)..."
    lsof -ti:8501 | xargs -r kill -9 2>/dev/null
    
    echo
    echo "✅ All services stopped"
fi

echo
echo "Verify services stopped:"
echo "  lsof -i:5000 -i:8001 -i:8002 -i:8003 -i:8004 -i:8501"
echo
