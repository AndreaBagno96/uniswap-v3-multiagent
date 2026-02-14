"""
Utility functions for Orchestrator RAG workflow.
"""

from typing import Dict
from a2a.types import AgentCard


def format_agents_info(cards: Dict[str, AgentCard]) -> str:
    """
    Format agent cards into a string for LLM routing decisions.
    
    Args:
        cards: Dictionary mapping agent names to their AgentCard
        
    Returns:
        Formatted string describing available agents and capabilities
    """
    if not cards:
        return "No agents available."
    
    lines = ["Available Agents:\n"]
    
    for name, card in cards.items():
        lines.append(f"- **{card.name}**")
        if card.description:
            lines.append(f"  Description: {card.description}")
        if card.skills:
            skills_str = ", ".join([skill.name for skill in card.skills])
            lines.append(f"  Skills: {skills_str}")
        lines.append("")
    
    return "\n".join(lines)
