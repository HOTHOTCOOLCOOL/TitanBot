"""
ApprovalStore for Smart HITL authorization memory.
Records which high-risk tool actions the user has chosen to "Always Approve".
"""
import json
from pathlib import Path
from typing import Any
import fnmatch
from loguru import logger

class ApprovalStore:
    def __init__(self, workspace: Path):
        self.filepath = workspace / ".nanobot" / "approvals.json"
        self._rules = []
        self._load()
    
    def _load(self):
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self._rules = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load approvals: {e}")
                self._rules = []
        else:
            self._rules = []
            
    def _save(self):
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self._rules, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save approvals: {e}")
            
    def add_approval(self, tool_name: str, action: str, match_context: dict[str, Any] = None):
        """
        Add a sticky approval rule.
        match_context can contain partial argument matching.
        A tool-level rule (action="") matches ALL actions for that tool.
        """
        # Dedup: skip if an equivalent or broader rule already exists
        for existing in self._rules:
            if existing["tool"] != tool_name:
                continue
            # A tool-level rule (action="") already covers everything
            if not existing["action"]:
                logger.debug(f"SmartHITL: Broader rule already exists for {tool_name} (tool-level)")
                return
            # Exact match (same tool + same action + same context)
            if existing["action"] == action and existing.get("context", {}) == (match_context or {}):
                logger.debug(f"SmartHITL: Duplicate rule skipped for {tool_name}:{action}")
                return

        rule = {
            "tool": tool_name,
            "action": action,
            "context": match_context or {}
        }
        self._rules.append(rule)
        self._save()
        logger.info(f"SmartHITL: Auto-approve rule added for {tool_name}:{action or '*'}")
        
    def is_approved(self, tool_name: str, arguments: dict[str, Any]) -> bool:
        """Check if a specific tool invocation matches any pre-approved rule."""
        action = arguments.get("action", "")
        for rule in self._rules:
            if rule["tool"] != tool_name:
                continue
            if rule["action"] and rule["action"] != action:
                continue
            
            # Context matching
            context = rule.get("context", {})
            matches = True
            for k, expected_v in context.items():
                if k not in arguments:
                    matches = False
                    break
                actual_v = arguments[k]
                
                if isinstance(expected_v, str) and isinstance(actual_v, str):
                    if not fnmatch.fnmatch(actual_v.lower(), expected_v.lower()):
                        matches = False
                        break
                elif expected_v != actual_v:
                    matches = False
                    break
                    
            if matches:
                return True
                
        return False
