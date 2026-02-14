"""
Token Intelligence StateGraph - LangGraph workflow for token security analysis.
"""

from langgraph.graph import StateGraph, START, END
from .state import InputState, OutputState, OverallState
from .nodes import TokenIntelligenceNodes


class TokenIntelligenceGraph:
    """StateGraph for token intelligence analysis workflow."""
    
    def __init__(
        self,
        llm,
        config,
        system_prompt
    ):
        """
        Initialize the token intelligence graph.
        
        Args:
            llm: Language model
            config: Configuration dict
            system_prompt: System prompt string
        """
        self.nodes = TokenIntelligenceNodes(
            llm=llm,
            config=config,
            system_prompt=system_prompt
        )
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build the StateGraph workflow."""
        builder = StateGraph(
            OverallState,
            input=InputState,
            output=OutputState
        )
        
        # Add nodes
        builder.add_node("enhance_query", self.nodes.enhance_query)
        builder.add_node("resolve_tokens", self.nodes.resolve_tokens)
        builder.add_node("check_security", self.nodes.check_security)
        builder.add_node("search_sentiment", self.nodes.search_sentiment)
        builder.add_node("classify_tokens", self.nodes.classify_tokens)
        builder.add_node("synthesize_answer", self.nodes.synthesize_answer)
        builder.add_node("finalize_output", self.nodes.finalize_output)
        
        # Define flow
        builder.add_edge(START, "enhance_query")
        builder.add_edge("enhance_query", "resolve_tokens")
        
        # Conditional edge to check for errors
        def check_exit(state: OverallState) -> str:
            if state.get("exit_flag", False):
                return "finalize_output"
            return "check_security"
        
        builder.add_conditional_edges(
            "resolve_tokens",
            check_exit,
            {
                "check_security": "check_security",
                "finalize_output": "finalize_output"
            }
        )
        
        builder.add_edge("check_security", "search_sentiment")
        builder.add_edge("search_sentiment", "classify_tokens")
        builder.add_edge("classify_tokens", "synthesize_answer")
        builder.add_edge("synthesize_answer", "finalize_output")
        builder.add_edge("finalize_output", END)
        
        return builder.compile()
