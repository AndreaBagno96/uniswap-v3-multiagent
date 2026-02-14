"""
Pool Risk StateGraph - LangGraph workflow for pool risk analysis.
"""

from langgraph.graph import StateGraph, START, END
from .state import InputState, OutputState, OverallState
from .nodes import PoolRiskNodes


class PoolRiskGraph:
    """StateGraph for pool risk analysis workflow."""
    
    def __init__(
        self,
        llm,
        paginator,
        cache,
        config,
        system_prompt
    ):
        """
        Initialize the pool risk graph.
        
        Args:
            llm: Language model
            paginator: GraphPaginator instance
            cache: CacheManager instance
            config: Configuration dict
            system_prompt: System prompt string
        """
        self.nodes = PoolRiskNodes(
            llm=llm,
            paginator=paginator,
            cache=cache,
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
        builder.add_node("extract_entities", self.nodes.extract_entities)
        builder.add_node("run_analyses", self.nodes.run_analyses)
        builder.add_node("synthesize_answer", self.nodes.synthesize_answer)
        builder.add_node("finalize_output", self.nodes.finalize_output)
        
        # Define flow
        builder.add_edge(START, "enhance_query")
        builder.add_edge("enhance_query", "extract_entities")
        builder.add_edge("extract_entities", "run_analyses")
        
        # Conditional edge to check for errors
        def check_exit(state: OverallState) -> str:
            if state.get("exit_flag", False):
                return "finalize_output"
            return "synthesize_answer"
        
        builder.add_conditional_edges(
            "run_analyses",
            check_exit,
            {
                "synthesize_answer": "synthesize_answer",
                "finalize_output": "finalize_output"
            }
        )
        
        builder.add_edge("synthesize_answer", "finalize_output")
        builder.add_edge("finalize_output", END)
        
        return builder.compile()
