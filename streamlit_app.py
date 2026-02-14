"""
Streamlit Web App - Uniswap V3 Multi-Agent Risk Analysis System
Microservices Edition

Interactive chat interface that connects to:
- Backend Orchestrator (Port 5000): Coordinates analysis across agents
- Pool Risk Service (Port 8001): On-chain liquidity and market analysis
- Token Intelligence Service (Port 8002): Token security and sentiment analysis
"""

import os
import re
import httpx
import streamlit as st
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Uniswap V3 Risk Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Service URLs (configurable via environment variables)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000")
POOL_RISK_URL = os.getenv("POOL_RISK_URL", "http://localhost:8001")
TOKEN_INTEL_URL = os.getenv("TOKEN_INTEL_URL", "http://localhost:8003")

# Ethereum address validation regex
ETH_ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")

# Orchestrator endpoint (always used)
ORCHESTRATOR_URL = f"{BACKEND_URL}/v1/orchestrator/invoke"


def init_session_state():
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pool_validated" not in st.session_state:
        st.session_state.pool_validated = False
    if "current_pool" not in st.session_state:
        st.session_state.current_pool = None


def validate_pool_address(address: str) -> bool:
    """Validate Ethereum pool address format."""
    if not address:
        return False
    return bool(ETH_ADDRESS_PATTERN.match(address))


def invoke_orchestrator(user_question: str, pool_address: str) -> dict:
    """
    Invoke the orchestrator via A2A protocol.
    
    Args:
        user_question: User's question
        pool_address: Pool address
        
    Returns:
        Dict with answer and metadata
    """
    payload = {
        "query": user_question,
        "pool_address": pool_address,
        "language": "en"
    }
    
    try:
        response = httpx.post(
            ORCHESTRATOR_URL,
            json=payload,
            timeout=180.0  # 3 minute timeout for analysis
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        return {
            "answer": f"❌ Service error: {str(e)}",
            "metadata": {"error": str(e)},
            "risk_score": 0.0
        }
    except Exception as e:
        return {
            "answer": f"❌ Unexpected error: {str(e)}",
            "metadata": {"error": str(e)},
            "risk_score": 0.0
        }


def clear_chat():
    """Clear chat history."""
    st.session_state.messages = []


def render_sidebar():
    """Render sidebar with pool input and settings."""
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Pool address input
        st.subheader("Pool Address")
        pool_address = st.text_input(
            "Enter Uniswap V3 Pool Address",
            placeholder="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
            help="Ethereum address of the Uniswap V3 liquidity pool (0x + 40 hex characters)"
        )
        
        # Validate pool address
        if pool_address:
            if validate_pool_address(pool_address):
                st.success("✅ Valid pool address")
                
                # Check if pool changed
                if st.session_state.current_pool and st.session_state.current_pool != pool_address.lower():
                    st.info("🔄 Pool address changed. Chat history cleared.")
                    clear_chat()
                
                st.session_state.current_pool = pool_address.lower()
                st.session_state.pool_validated = True
            else:
                st.error("❌ Invalid address format. Must be 0x followed by 40 hex characters.")
                st.session_state.pool_validated = False
        else:
            st.session_state.pool_validated = False
        
        # st.divider()
        
        # # Environment info
        # st.subheader("📍 Service URLs")
        # st.caption(f"Backend: `{BACKEND_URL}`")
        # st.caption(f"Pool Risk: `{POOL_RISK_URL}`")
        # st.caption(f"Token Intel: `{TOKEN_INTEL_URL}`")
        
        st.divider()
        
        # Chat controls
        st.subheader("Chat Controls")
        if st.button("🗑️ Clear Chat History", use_container_width=True):
            clear_chat()
            st.rerun()
        
        # Display current pool info
        if st.session_state.pool_validated:
            st.divider()
            st.subheader("Current Pool")
            st.code(st.session_state.current_pool, language=None)


def render_chat():
    """Render main chat interface."""
    st.title("📊 Uniswap V3 Multi-Agent Risk Analyzer")
    st.caption("Microservices Edition - Powered by LangGraph, A2A Protocol, and Fast MCP")
    
    # Check if pool is validated
    if not st.session_state.pool_validated:
        st.warning("👈 Enter a valid pool address in the sidebar to start analyzing.")
        
        # Show example queries
        st.markdown("### 💡 Example Queries")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📊 Risk Analysis**")
            st.markdown("""
            - "Analyze this pool comprehensively"
            - "What are all the risks?"
            - "Check liquidity concentration"
            - "What's the slippage for 100k?"
            """)
        
        with col2:
            st.markdown("**🔐 Token Security**")
            st.markdown("""
            - "Are these tokens safe?"
            - "Check for honeypot risks"
            - "Is this pool safe to use?"
            - "Analyze MEV activity"
            """)
        
        st.divider()
        
        # Show example pool addresses
        st.markdown("### 📝 Example Pool Addresses")
        example_pools = {
            "USDC/ETH (0.05%)": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
            "WBTC/ETH (0.3%)": "0xcbcdf9626bc03e24f779434178a73a0b4bad62ed",
            "DAI/USDC (0.01%)": "0x5777d92f208679db4b9778590fa3cab3ac9e2168"
        }
        
        cols = st.columns(len(example_pools))
        for idx, (name, address) in enumerate(example_pools.items()):
            with cols[idx]:
                st.caption(name)
                st.code(address, language=None)
        
        return
    
    # Display chat messages
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # Show metadata if available
            if message["role"] == "assistant":
                if message.get("agent"):
                    st.caption(f"📌 Agent: {message['agent']}")
                
                if message.get("risk_score") is not None:
                    risk_score = message["risk_score"]
                    color = "red" if risk_score > 60 else "orange" if risk_score > 30 else "green"
                    st.markdown(f"**Risk Score**: :{color}[{risk_score:.1f}/100]")
                
                if message.get("metadata"):
                    with st.expander("📋 View Metadata"):
                        st.json(message["metadata"])
    
    # Chat input
    if prompt := st.chat_input(
        "Ask about pool risks, liquidity, tokens, or request comprehensive analysis...",
        disabled=not st.session_state.pool_validated
    ):
        # Add user message
        st.session_state.messages.append({
            "role": "user",
            "content": prompt
        })
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Get agent response
        with st.chat_message("assistant"):
            with st.spinner("🎯 Coordinating multi-agent analysis via A2A protocol..."):
                try:
                    # Invoke orchestrator
                    result = invoke_orchestrator(
                        user_question=prompt,
                        pool_address=st.session_state.current_pool
                    )
                    
                    answer = result.get("answer", "No response generated.")
                    metadata = result.get("metadata", {})
                    risk_score = result.get("risk_score", 0.0)
                    
                    # Display answer
                    st.markdown(answer)
                    
                    # Display risk score if available
                    if risk_score > 0:
                        color = "red" if risk_score > 60 else "orange" if risk_score > 30 else "green"
                        st.markdown(f"**Risk Score**: :{color}[{risk_score:.1f}/100]")
                    
                    # Display metadata
                    if metadata and metadata.get("error"):
                        st.error(f"⚠️ Error: {metadata['error']}")
                    elif metadata:
                        with st.expander("📋 View Metadata"):
                            st.json(metadata)
                    
                    # Save to history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer,
                        "agent": "Multi-Agent Orchestrator",
                        "risk_score": risk_score,
                        "metadata": metadata
                    })
                    
                except Exception as e:
                    error_msg = f"❌ Error during analysis: {str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_msg,
                        "agent": "Multi-Agent Orchestrator"
                    })


def main():
    """Main entry point."""
    init_session_state()
    render_sidebar()
    render_chat()
    
    # Footer
    st.divider()
    st.caption("""
    🏗️ Built with LangGraph • A2A Protocol • Fast MCP • Docker Microservices
    """)


if __name__ == "__main__":
    main()
