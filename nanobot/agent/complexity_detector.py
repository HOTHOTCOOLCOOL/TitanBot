"""Complexity Detector for Phase 52 (Group-Aware Parallel Reasoning).

Uses zero-LLM deterministic rules to detect if a given query requires
convergent reasoning execution (parallel subagents).
"""

from typing import Any

from nanobot.config.loader import get_config


class ComplexityDetector:
    """Detects if a task warrants parallel group-aware reasoning."""

    @staticmethod
    def should_parallelize(task_request: str, kb_graph: Any = None) -> bool:
        """Evaluate deterministic rules to trigger GroupRAG parallelization.
        
        Trigger if ANY 2 of the 4 rules are met:
        1. Token estimate (chars/4) > config threshold (default 500)
        2. Knowledge Graph estimated entities > config threshold (default 8)
        3. Explicit command: contains "/parallel" or "/deep-analyze"
        4. Structured keywords indicating high comparative complexity.
        """
        config = get_config()
        if not config.features.parallel_reasoning:
            return False

        rules_met = 0

        # Rule 1: High Token Count
        token_threshold = config.features.parallel_complexity_token_threshold
        # Quick token heuristic: chars / 4
        if (len(task_request) / 4) > token_threshold:
            rules_met += 1

        # Rule 2: Knowledge Graph Entities
        entity_threshold = config.features.parallel_complexity_entity_threshold
        if kb_graph and hasattr(kb_graph, 'get_entity_count'):
            try:
                count = kb_graph.get_entity_count()
                if count > entity_threshold:
                    rules_met += 1
            except Exception:
                pass

        # Rule 3: Explicit User Command
        if "/parallel" in task_request or "/deep-analyze" in task_request:
            rules_met += 1

        # Rule 4: Structural Keywords
        keywords = ["对比", "分析", "综合", "compare", "analyze", "summarize"]
        lower_req = task_request.lower()
        if any(kw in lower_req for kw in keywords):
            rules_met += 1

        return rules_met >= 2
