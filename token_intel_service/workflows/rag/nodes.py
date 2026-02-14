"""
Node implementations for Token Intelligence RAG workflow.
"""

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import logging

logger = logging.getLogger(__name__)


class TokenIntelligenceNodes:
    """Node implementations for token intelligence analysis graph."""
    
    def __init__(
        self,
        llm: ChatOpenAI,
        config: Dict[str, Any],
        system_prompt: str
    ):
        """
        Initialize nodes with dependencies.
        
        Args:
            llm: Language model for analysis
            config: Configuration dictionary
            system_prompt: System prompt for the agent
        """
        self.llm = llm
        self.config = config
        self.system_prompt = system_prompt
    
    def enhance_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance user query with pool address context."""
        user_question = state["user_question"]
        pool_address = state.get("pool_address")
        
        if pool_address:
            enhanced = f"Pool/Pair address: {pool_address}\n\nUser query: {user_question}"
        else:
            enhanced = user_question
        
        return {
            "enhanced_query": enhanced,
            "exit_flag": False
        }
    
    def resolve_tokens(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve pool address to tokens using DexScreener."""
        from tools.token_resolver import TokenResolver
        
        pool_address = state.get("pool_address")
        
        if not pool_address:
            return {
                "resolved_tokens": {"error": "No pool address provided"},
                "exit_flag": True
            }
        
        try:
            resolver = TokenResolver(self.config)
            tokens = resolver.resolve_pool(pool_address)  # Fixed method name
            
            return {
                "resolved_tokens": tokens,
                "exit_flag": False
            }
        except Exception as e:
            logger.error(f"Token resolution failed: {e}")
            return {
                "resolved_tokens": {"error": str(e)},
                "exit_flag": True
            }
    
    def check_security(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Check smart contract security using GoPlus."""
        from tools.token_security import TokenSecurityAnalyzer
        
        resolved_tokens = state.get("resolved_tokens", {})
        
        if "error" in resolved_tokens:
            return {"security_results": [], "exit_flag": False}
        
        tokens = resolved_tokens.get("tokens", [])
        chain = resolved_tokens.get("chain", "ethereum")
        
        security_results = []
        analyzer = TokenSecurityAnalyzer(self.config)
        
        for token in tokens:
            try:
                result = analyzer.analyze(chain, token["address"])
                security_results.append({
                    "token": token,
                    "security": result
                })
            except Exception as e:
                logger.error(f"Security check failed for {token['symbol']}: {e}")
                security_results.append({
                    "token": token,
                    "security": {"error": str(e)}
                })
        
        return {
            "security_results": security_results,
            "exit_flag": False
        }
    
    def search_sentiment(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Search for token sentiment and scam reports."""
        from tools.token_sentiment import TokenSentimentAnalyzer
        
        resolved_tokens = state.get("resolved_tokens", {})
        
        if "error" in resolved_tokens:
            return {"sentiment_results": [], "exit_flag": False}
        
        tokens = resolved_tokens.get("tokens", [])
        sentiment_results = []
        
        try:
            analyzer = TokenSentimentAnalyzer(self.config)
            
            for token in tokens:
                try:
                    result = analyzer.analyze(token["symbol"], token["address"])
                    sentiment_results.append({
                        "token": token,
                        "sentiment": result
                    })
                except Exception as e:
                    logger.error(f"Sentiment analysis failed for {token['symbol']}: {e}")
                    sentiment_results.append({
                        "token": token,
                        "sentiment": {"error": str(e)}
                    })
        except Exception as e:
            logger.warning(f"Sentiment analyzer initialization failed: {e}")
        
        return {
            "sentiment_results": sentiment_results,
            "exit_flag": False
        }
    
    def classify_tokens(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Classify tokens as SAFE/RISKY/DANGER."""
        from tools.token_classifier import TokenClassifier
        
        security_results = state.get("security_results", [])
        sentiment_results = state.get("sentiment_results", [])
        
        classifications = {}
        classifier = TokenClassifier(self.config)
        
        for sec_result in security_results:
            token = sec_result["token"]
            security = sec_result.get("security", {})
            
            # Find matching sentiment
            sentiment = {}
            for sent_result in sentiment_results:
                if sent_result["token"]["address"] == token["address"]:
                    sentiment = sent_result.get("sentiment", {})
                    break
            
            # Classify
            classification = classifier.classify(
                token_info=token,
                security_data=security,
                sentiment_data=sentiment
            )
            
            classifications[token["symbol"]] = classification
        
        return {
            "classifications": classifications,
            "exit_flag": False
        }
    
    def synthesize_answer(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize final answer from analysis results."""
        user_question = state["user_question"]
        resolved_tokens = state.get("resolved_tokens", {})
        security_results = state.get("security_results", [])
        sentiment_results = state.get("sentiment_results", [])
        classifications = state.get("classifications", {})
        
        # Build context
        context = f"""
Token Analysis Results:

Resolved Tokens: {len(resolved_tokens.get('tokens', []))} tokens found
"""
        
        for symbol, classification in classifications.items():
            context += f"\n{symbol}: {classification.get('risk_level', 'Unknown')} - Score: {classification.get('risk_score', 'N/A')}/100\n"
            
            if classification.get("risk_flags"):
                context += f"  Flags: {', '.join(classification['risk_flags'])}\n"
        
        # Generate answer
        synthesis_prompt = f"""{self.system_prompt}

Based on the following token analysis results, answer the user's question:

{context}

User Question: {user_question}

Provide a clear, security-focused answer with specific risks and recommendations.
"""
        
        try:
            response = self.llm.invoke([HumanMessage(content=synthesis_prompt)])
            answer = response.content
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            answer = f"Failed to generate answer: {e}"
        
        return {
            "synthesized_answer": answer,
            "exit_flag": False
        }
    
    def finalize_output(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare final output."""
        classifications = state.get("classifications", {})
        
        metadata = {
            "tokens_analyzed": len(classifications),
            "classifications": classifications
        }
        
        # Get synthesized answer with fallback
        answer = state.get("synthesized_answer", state.get("answer", "No answer generated"))
        
        return {
            "answer": answer,
            "metadata": metadata
        }
