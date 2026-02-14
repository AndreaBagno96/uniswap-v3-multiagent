#!/bin/bash

# Start all services using uv

echo "================================================"
echo "Starting Uniswap V3 Multi-Agent Services (UV)"
echo "================================================"
echo

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ UV is not installed"
    echo "Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment and installing dependencies..."
    uv sync
    echo
fi

# Activate virtual environment
source .venv/bin/activate

# Check .env file
if [ ! -f ".env" ]; then
    echo "⚠️  WARNING: .env file not found"
    echo "Copy .env.example to .env and configure API keys"
    exit 1
fi

# Export environment variables
export $(cat .env | grep -v '^#' | xargs)

# Get absolute paths
PROJECT_ROOT="$(pwd)"
LOGS_DIR="$PROJECT_ROOT/logs"

echo "Starting services in background..."
echo

# Start MCP servers FIRST (optional - tools available when main services start)
echo "🔧 Starting Pool Risk MCP Server (port 8002)..."
(cd "$PROJECT_ROOT/pool_risk_service" && uv run python mcp_server/server.py) > "$LOGS_DIR/pool_mcp.log" 2>&1 &
POOL_MCP_PID=$!
echo "   PID: $POOL_MCP_PID"

echo "🔧 Starting Token Intel MCP Server (port 8004)..."
(cd "$PROJECT_ROOT/token_intel_service" && uv run python mcp_server/server.py) > "$LOGS_DIR/token_mcp.log" 2>&1 &
TOKEN_MCP_PID=$!
echo "   PID: $TOKEN_MCP_PID"

# Wait for MCP servers to start
sleep 2

# Start sub-services BEFORE backend (backend needs to discover them via A2A)
echo "🏊 Starting Pool Risk Service with A2A (port 8001)..."
(cd "$PROJECT_ROOT/pool_risk_service" && PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH" uv run python pool_risk_app.py) > "$LOGS_DIR/pool_risk.log" 2>&1 &
POOL_PID=$!
echo "   PID: $POOL_PID"

echo "🔐 Starting Token Intelligence Service with A2A (port 8003)..."
(cd "$PROJECT_ROOT/token_intel_service" && PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH" uv run python token_intel_app.py) > "$LOGS_DIR/token_intel.log" 2>&1 &
TOKEN_PID=$!
echo "   PID: $TOKEN_PID"

# Wait for sub-services to initialize A2A endpoints
sleep 3

# Start Backend Orchestrator LAST (connects to sub-services via A2A protocol)
echo "🎯 Starting Backend Orchestrator with A2A Client (port 5000)..."
(cd "$PROJECT_ROOT/backend" && PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH" uv run python app.py) > "$LOGS_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "   PID: $BACKEND_PID"

# Wait for backend to initialize
sleep 2

echo
echo "================================================"
echo "All services started with A2A Protocol!"
echo "================================================"
echo
echo "Architecture:"
echo "  Backend Orchestrator uses A2A Client to communicate with sub-services"
echo "  Sub-services expose A2A endpoints for agent-to-agent communication"
echo
echo "Service PIDs:"
echo "  Backend:         $BACKEND_PID"
echo "  Pool Risk:       $POOL_PID"
echo "  Token Intel:     $TOKEN_PID"
echo "  Pool MCP:        $POOL_MCP_PID"
echo "  Token Intel MCP: $TOKEN_MCP_PID"
echo
echo "Endpoints:"
echo "  • Backend Orchestrator:  http://localhost:5000"
echo "  • Pool Risk (A2A):       http://localhost:8001/a2a"
echo "  • Pool Risk MCP:         http://localhost:8002/mcp"
echo "  • Token Intel (A2A):     http://localhost:8003/a2a"
echo "  • Token Intel MCP:       http://localhost:8004/mcp"
echo
echo "Agent Cards:"
echo "  • Pool Risk:    http://localhost:8001/a2a/.well-known/agent.json"
echo "  • Token Intel:  http://localhost:8003/a2a/.well-known/agent.json"
echo
echo "Logs:"
echo "  • Backend:      logs/backend.log"
echo "  • Pool Risk:    logs/pool_risk.log"
echo "  • Token Intel:  logs/token_intel.log"
echo "  • Pool MCP:     logs/pool_mcp.log"
echo "  • Token MCP:    logs/token_mcp.log"
echo
echo "Test A2A Orchestrator:"
echo "  curl -X POST http://localhost:5000/v1/orchestrator/invoke \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"query\": \"What is the concentration risk?\", \"pool_address\": \"0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640\"}'"
echo
echo "To launch Streamlit UI:"
echo "  uv run streamlit run streamlit_app.py"
echo
echo "To stop all services:"
echo "  ./stop_services.sh"
echo "  # Or manually: kill $BACKEND_PID $POOL_PID $TOKEN_PID $POOL_MCP_PID $TOKEN_MCP_PID"
echo
