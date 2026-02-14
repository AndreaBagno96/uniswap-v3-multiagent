# Uniswap V3 Multi-Agent Risk Analysis System

A microservices-based multi-agent system for comprehensive Uniswap V3 pool risk analysis using LangGraph, A2A Protocol, and MCP (Model Context Protocol).

## Architecture

```
Backend Orchestrator (port 5000)
    ├── Pool Risk Service (port 8001) + MCP Server (port 8002)
    └── Token Intel Service (port 8003) + MCP Server (port 8004)
```

## Key Features

- **Plan-and-Execute Pattern**: Agents dynamically select and execute only the tools needed for each query
- **MCP Protocol**: Dynamic tool discovery and calling via HTTP transport
- **A2A Protocol**: Agent-to-agent communication for multi-service orchestration
- **LangGraph Workflows**: State-based agent workflows with graceful fallbacks
- **Parallel Tool Execution**: Efficient multi-tool analysis for comprehensive requests

## Quick Start

### Prerequisites

- Python >= 3.11
- OpenAI API key
- The Graph API key

### Installation

```bash
# Install dependencies with uv (recommended)
uv sync
source .venv/bin/activate

# Or use pip
pip install -e .
```

### Environment Setup

Create a `.env` file with:

```env
OPENAI_API_KEY=your_key_here
THE_GRAPH_API_KEY=your_key_here
POOL_RISK_MCP_URL=http://localhost:8002/mcp  # Optional
TAVILY_API_KEY=your_key_here                  # Optional
LANGCHAIN_API_KEY=your_key_here               # Optional
```

### Running Services

```bash
# Start all services
./start_services.sh

# Stop all services
./stop_services.sh

# Launch Streamlit UI
streamlit run streamlit_app.py
```

### Docker Deployment

```bash
docker-compose up --build
```

## API Endpoints

### Pool Risk Service

- `POST /v1/invoke` - Invoke agent with question
- `GET /health` - Health check with MCP status
- `GET /tools` - List available MCP tools
- `POST /refresh-tools` - Reconnect to MCP server

### Orchestrator

- `POST /v1/orchestrator/invoke` - Multi-agent orchestration

## Example Usage

```bash
# Single tool analysis
curl -X POST http://localhost:8001/v1/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "user_question": "What is the concentration risk?",
    "pool_address": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
  }'

# Comprehensive analysis (parallel execution)
curl -X POST http://localhost:8001/v1/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "user_question": "Give me a full risk analysis",
    "pool_address": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
  }'
```

## Project Structure

```
├── backend/                  # Orchestrator service
├── pool_risk_service/        # Pool risk analysis agent + MCP server
├── token_intel_service/      # Token intelligence agent + MCP server
├── a2a_orchestrator/         # A2A protocol implementation
├── common_ai/                # Shared AI utilities
└── streamlit_app.py          # Web UI
```

## Development

See [.github/copilot-instructions.md](.github/copilot-instructions.md) for detailed architecture documentation and development patterns.

## License

MIT
