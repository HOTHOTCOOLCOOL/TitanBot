"""Skills loader for agent capabilities."""

import importlib.util
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class HookResult:
    """Result from a pre-execute hook (SK5)."""
    proceed: bool = True
    message: str = ""

# Default builtin skills directory (relative to this file)
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"

# Standard skill categories (Phase 22A SK2)
SKILL_CATEGORIES = frozenset({
    "library_api",
    "code_quality",
    "frontend_design",
    "business_workflow",
    "product_verification",
    "content_generation",
    "data_fetching",
    "service_debugging",
    "infra_ops",
})

# Maximum execution log entries per skill (Phase 22A SK3)
_MAX_EXECUTION_LOG = 100


class SkillsLoader:
    """
    Loader for agent skills.
    
    Skills are markdown files (SKILL.md) that teach the agent how to use
    specific tools or perform certain tasks.
    """
    
    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None):
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
    
    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        """
        List all available skills.
        
        Args:
            filter_unavailable: If True, filter out skills with unmet requirements.
        
        Returns:
            List of skill info dicts with 'name', 'path', 'source'.
        """
        skills = []
        
        # Workspace skills (highest priority)
        if self.workspace_skills.exists():
            for skill_dir in self.workspace_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skills.append({"name": skill_dir.name, "path": str(skill_file), "source": "workspace"})
        
        # Built-in skills
        if self.builtin_skills and self.builtin_skills.exists():
            for skill_dir in self.builtin_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists() and not any(s["name"] == skill_dir.name for s in skills):
                        skills.append({"name": skill_dir.name, "path": str(skill_file), "source": "builtin"})
        
        # Filter by requirements
        if filter_unavailable:
            return [s for s in skills if self._check_requirements(self._get_skill_meta(s["name"]))]
        return skills
    
    def load_skill(self, name: str) -> str | None:
        """
        Load a skill by name.
        
        Args:
            name: Skill name (directory name).
        
        Returns:
            Skill content or None if not found.
        """
        # Check workspace first
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")
        
        # Check built-in
        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                return builtin_skill.read_text(encoding="utf-8")
        
        return None
    
    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """
        Load specific skills for inclusion in agent context.
        
        Args:
            skill_names: List of skill names to load.
        
        Returns:
            Formatted skills content.
        """
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")
        
        return "\n\n---\n\n".join(parts) if parts else ""
    
    def build_skills_summary(self) -> str:
        """
        Build a summary of all skills (name, description, category, path, availability).
        
        This is used for progressive loading - the agent can read the full
        skill content using read_file when needed.
        
        Returns:
            XML-formatted skills summary grouped by category.
        """
        all_skills = self.list_skills(filter_unavailable=False)
        if not all_skills:
            return ""
        
        def escape_xml(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        # Group skills by category (SK2)
        categorized: dict[str, list[dict]] = {}
        uncategorized: list[dict] = []
        for s in all_skills:
            meta = self.get_skill_metadata(s["name"])
            cat = meta.get("category", "") if meta else ""
            if cat and cat in SKILL_CATEGORIES:
                categorized.setdefault(cat, []).append(s)
            else:
                uncategorized.append(s)
        
        lines = ["<skills>"]
        
        # Emit categorized skills
        for cat in sorted(categorized.keys()):
            lines.append(f'  <category name="{cat}">')
            for s in categorized[cat]:
                self._emit_skill_xml(s, lines, escape_xml, indent=4)
            lines.append("  </category>")
        
        # Emit uncategorized skills
        if uncategorized:
            lines.append('  <category name="other">')
            for s in uncategorized:
                self._emit_skill_xml(s, lines, escape_xml, indent=4)
            lines.append("  </category>")
        
        lines.append("</skills>")
        return "\n".join(lines)
    
    def _emit_skill_xml(self, s: dict, lines: list[str], escape_xml, indent: int = 2) -> None:
        """Emit XML for a single skill entry."""
        prefix = " " * indent
        name = escape_xml(s["name"])
        path = s["path"]
        desc = escape_xml(self._get_skill_description(s["name"]))
        skill_meta = self._get_skill_meta(s["name"])
        available = self._check_requirements(skill_meta)
        
        lines.append(f'{prefix}<skill available="{str(available).lower()}">')
        lines.append(f"{prefix}  <name>{name}</name>")
        lines.append(f"{prefix}  <description>{desc}</description>")
        lines.append(f"{prefix}  <location>{path}</location>")
        
        # Show missing requirements for unavailable skills
        if not available:
            missing = self._get_missing_requirements(skill_meta)
            if missing:
                lines.append(f"{prefix}  <requires>{escape_xml(missing)}</requires>")
        
        # SK4: Include configurable keys if config exists
        cfg = self.load_skill_config(s["name"])
        if cfg:
            keys_str = ", ".join(sorted(cfg.keys())[:10])  # Cap at 10 keys
            lines.append(f"{prefix}  <config_keys>{escape_xml(keys_str)}</config_keys>")
        
        # SK3: Include recent execution summary if available
        recent = self.get_recent_executions(s["name"], n=2)
        if recent:
            exec_summary = "; ".join(
                f"{'✓' if e.get('success') else '✗'} {e.get('input', '')[:60]}"
                for e in recent
            )
            lines.append(f"{prefix}  <recent_executions>{escape_xml(exec_summary)}</recent_executions>")
        
        lines.append(f"{prefix}</skill>")
    
    def list_skills_by_category(self) -> dict[str, list[dict[str, str]]]:
        """
        List all skills grouped by category (SK2).
        
        Returns:
            Dict mapping category name to list of skill info dicts.
            Uncategorized skills are under the "other" key.
        """
        result: dict[str, list[dict[str, str]]] = {}
        for s in self.list_skills(filter_unavailable=False):
            meta = self.get_skill_metadata(s["name"])
            cat = meta.get("category", "other") if meta else "other"
            if cat not in SKILL_CATEGORIES:
                cat = "other"
            result.setdefault(cat, []).append(s)
        return result
    
    def _get_missing_requirements(self, skill_meta: dict) -> str:
        """Get a description of missing requirements."""
        missing = []
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not shutil.which(b):
                missing.append(f"CLI: {b}")
        for env in requires.get("env", []):
            if not os.environ.get(env):
                missing.append(f"ENV: {env}")
        return ", ".join(missing)
    
    def _get_skill_description(self, name: str) -> str:
        """Get the description of a skill from its frontmatter."""
        meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        return name  # Fallback to skill name
    
    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter from markdown content."""
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content
    
    def _parse_nanobot_metadata(self, raw: str) -> dict:
        """Parse skill metadata JSON from frontmatter (supports nanobot and openclaw keys)."""
        try:
            data = json.loads(raw)
            return data.get("nanobot", data.get("openclaw", {})) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def _check_requirements(self, skill_meta: dict) -> bool:
        """Check if skill requirements are met (bins, env vars)."""
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not shutil.which(b):
                return False
        for env in requires.get("env", []):
            if not os.environ.get(env):
                return False
        return True
    
    def _get_skill_meta(self, name: str) -> dict:
        """Get nanobot metadata for a skill (cached in frontmatter)."""
        meta = self.get_skill_metadata(name) or {}
        return self._parse_nanobot_metadata(meta.get("metadata", ""))
    
    def get_always_skills(self) -> list[str]:
        """Get skills marked as always=true that meet requirements."""
        result = []
        for s in self.list_skills(filter_unavailable=True):
            meta = self.get_skill_metadata(s["name"]) or {}
            skill_meta = self._parse_nanobot_metadata(meta.get("metadata", ""))
            if skill_meta.get("always") or meta.get("always"):
                result.append(s["name"])
        return result
    
    def get_skill_metadata(self, name: str) -> dict | None:
        """
        Get metadata from a skill's frontmatter.
        
        Handles both simple `key: value` and YAML multi-line `>` / `|` syntax.
        
        Args:
            name: Skill name.
        
        Returns:
            Metadata dict or None.
        """
        content = self.load_skill(name)
        if not content:
            return None
        
        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                return self._parse_yaml_frontmatter(match.group(1))
        
        return None
    
    def _parse_yaml_frontmatter(self, raw: str) -> dict:
        """
        Lightweight YAML frontmatter parser.
        
        Handles:
        - Simple `key: value`
        - Multi-line folded scalar `key: >` (joins continuation lines with spaces)
        - Quoted values
        - Inline JSON values (for metadata fields)
        """
        metadata: dict[str, str] = {}
        current_key: str | None = None
        continuation_lines: list[str] = []
        is_multiline = False

        for line in raw.split("\n"):
            # Check if this is a continuation line (starts with whitespace)
            if is_multiline and current_key and (line.startswith("  ") or line.startswith("\t")):
                continuation_lines.append(line.strip())
                continue
            
            # If we were accumulating multi-line, save the result
            if is_multiline and current_key and continuation_lines:
                metadata[current_key] = " ".join(continuation_lines)
                current_key = None
                continuation_lines = []
                is_multiline = False
            
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                
                # Check for multi-line scalar indicator
                if value == ">" or value == "|":
                    current_key = key
                    continuation_lines = []
                    is_multiline = True
                    continue
                
                # Strip quotes
                value = value.strip("\"'")
                metadata[key] = value
                current_key = None
                is_multiline = False
        
        # Don't forget trailing multi-line value
        if is_multiline and current_key and continuation_lines:
            metadata[current_key] = " ".join(continuation_lines)
        
        return metadata
    
    # ── SK3: Skill-Level Memory ─────────────────────────────────────────
    
    def _get_skill_dir(self, skill_name: str) -> Path | None:
        """Resolve skill directory path (workspace first, then builtin)."""
        ws = self.workspace_skills / skill_name
        if ws.is_dir():
            return ws
        if self.builtin_skills:
            bi = self.builtin_skills / skill_name
            if bi.is_dir():
                return bi
        return None
    
    def log_execution(
        self,
        skill_name: str,
        input_summary: str,
        output_summary: str,
        duration_ms: int,
        success: bool,
    ) -> None:
        """
        Log a skill execution to per-skill memory (SK3).
        
        Appends a JSON line to {skill_dir}/memory/executions.jsonl.
        Caps at _MAX_EXECUTION_LOG entries (FIFO eviction).
        """
        skill_dir = self._get_skill_dir(skill_name)
        if not skill_dir:
            logger.debug(f"Skill dir not found for '{skill_name}', skipping execution log")
            return
        
        memory_dir = skill_dir / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        log_file = memory_dir / "executions.jsonl"
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "input": input_summary[:200],     # Cap input summary
            "output": output_summary[:500],   # Cap output summary
            "duration_ms": duration_ms,
            "success": success,
        }
        
        try:
            # Append new entry
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            
            # Enforce FIFO cap
            lines = log_file.read_text(encoding="utf-8").strip().split("\n")
            if len(lines) > _MAX_EXECUTION_LOG:
                # Keep only the last _MAX_EXECUTION_LOG entries
                trimmed = lines[-_MAX_EXECUTION_LOG:]
                log_file.write_text("\n".join(trimmed) + "\n", encoding="utf-8")
            
            logger.debug(f"Logged execution for skill '{skill_name}' (success={success})")
        except Exception as e:
            logger.warning(f"Failed to log skill execution for '{skill_name}': {e}")
    
    def get_recent_executions(self, skill_name: str, n: int = 3) -> list[dict]:
        """
        Get the N most recent execution records for a skill (SK3).
        
        Args:
            skill_name: Skill name.
            n: Number of recent executions to return.
        
        Returns:
            List of execution dicts (most recent first), or empty list.
        """
        skill_dir = self._get_skill_dir(skill_name)
        if not skill_dir:
            return []
        
        log_file = skill_dir / "memory" / "executions.jsonl"
        if not log_file.exists():
            return []
        
        try:
            lines = log_file.read_text(encoding="utf-8").strip().split("\n")
            # Take last N lines, reverse for most-recent-first
            recent_lines = lines[-n:] if len(lines) >= n else lines
            recent_lines.reverse()
            
            results = []
            for line in recent_lines:
                line = line.strip()
                if line:
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            return results
        except Exception as e:
            logger.debug(f"Failed to read execution log for '{skill_name}': {e}")
            return []
    
    def format_execution_context(self, skill_name: str, n: int = 3) -> str:
        """
        Format recent execution records as a concise context string (SK3).
        
        Args:
            skill_name: Skill name.
            n: Number of recent executions.
        
        Returns:
            Formatted string for context injection, or empty string.
        """
        records = self.get_recent_executions(skill_name, n)
        if not records:
            return ""
        
        parts = [f"Recent executions of '{skill_name}':"]
        for r in records:
            status = "✓" if r.get("success") else "✗"
            ts = r.get("timestamp", "")[:16]  # YYYY-MM-DDTHH:MM
            inp = r.get("input", "")[:80]
            dur = r.get("duration_ms", 0)
            parts.append(f"  {status} [{ts}] {inp} ({dur}ms)")
        
        return "\n".join(parts)

    # ── SK4: Configurable Skill Behavior ─────────────────────────────────

    def load_skill_config(self, skill_name: str) -> dict:
        """
        Load per-skill configuration from config.json (SK4).
        
        Returns the user's config overlay, or empty dict if not found.
        """
        skill_dir = self._get_skill_dir(skill_name)
        if not skill_dir:
            return {}
        config_file = skill_dir / "config.json"
        if not config_file.exists():
            return {}
        try:
            return json.loads(config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load config for skill '{skill_name}': {e}")
            return {}

    def save_skill_config(self, skill_name: str, config: dict) -> bool:
        """
        Save per-skill configuration to config.json (SK4).
        
        Uses atomic write (temp file + os.replace) per L7 lessons.
        Returns True on success.
        """
        skill_dir = self._get_skill_dir(skill_name)
        if not skill_dir:
            logger.warning(f"Skill dir not found for '{skill_name}', cannot save config")
            return False
        config_file = skill_dir / "config.json"
        try:
            data = json.dumps(config, indent=2, ensure_ascii=False)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(skill_dir), suffix=".tmp", prefix="config_"
            )
            try:
                os.write(fd, data.encode("utf-8"))
                os.close(fd)
                os.replace(tmp_path, str(config_file))
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
            logger.debug(f"Saved config for skill '{skill_name}'")
            return True
        except Exception as e:
            logger.warning(f"Failed to save config for skill '{skill_name}': {e}")
            return False

    def get_effective_config(self, skill_name: str) -> dict:
        """
        Get merged configuration: defaults + user overlay (SK4).
        
        Reads config.defaults.json (author defaults) and config.json (user
        overrides). User values take precedence.
        """
        skill_dir = self._get_skill_dir(skill_name)
        if not skill_dir:
            return {}
        
        # Load author defaults
        defaults = {}
        defaults_file = skill_dir / "config.defaults.json"
        if defaults_file.exists():
            try:
                defaults = json.loads(defaults_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load defaults config for '{skill_name}': {e}")
        
        # Load user overlay
        user_config = self.load_skill_config(skill_name)
        
        # Merge: user overrides defaults
        merged = {**defaults, **user_config}
        return merged

    # ── SK5: Dynamic Hooks System ────────────────────────────────────────

    # Built-in hook types that can be referenced by name in SKILL.md frontmatter
    _BUILTIN_HOOKS = {
        "confirm_destructive",
        "notify_completion",
        "log_execution",
    }

    def get_skill_hooks(self, skill_name: str) -> dict[str, list[str]]:
        """
        Get hook definitions for a skill (SK5).
        
        Sources:
        1. SKILL.md frontmatter: `hooks_pre` and `hooks_post` fields
        2. Presence of hooks.py in skill dir
        
        Returns:
            {"pre_execute": [...], "post_execute": [...]}
        """
        hooks: dict[str, list[str]] = {"pre_execute": [], "post_execute": []}
        
        # Source 1: Frontmatter
        meta = self.get_skill_metadata(skill_name)
        if meta:
            pre = meta.get("hooks_pre", "")
            if pre:
                hooks["pre_execute"] = [h.strip() for h in pre.split(",") if h.strip()]
            post = meta.get("hooks_post", "")
            if post:
                hooks["post_execute"] = [h.strip() for h in post.split(",") if h.strip()]
        
        # Source 2: hooks.py presence
        skill_dir = self._get_skill_dir(skill_name)
        if skill_dir and (skill_dir / "hooks.py").exists():
            if "hooks_py" not in hooks["pre_execute"]:
                hooks["pre_execute"].append("hooks_py")
            if "hooks_py" not in hooks["post_execute"]:
                hooks["post_execute"].append("hooks_py")
        
        return hooks

    async def run_pre_hooks(
        self, skill_name: str, context: dict[str, Any]
    ) -> HookResult:
        """
        Run all pre-execute hooks for a skill (SK5).
        
        Returns HookResult. If any hook sets proceed=False, execution
        should be blocked with the provided message.
        """
        hooks = self.get_skill_hooks(skill_name)
        for hook_name in hooks.get("pre_execute", []):
            try:
                result = await self._run_single_hook(
                    skill_name, hook_name, "pre_execute", context
                )
                if result and not result.proceed:
                    return result
            except Exception as e:
                logger.warning(
                    f"Pre-hook '{hook_name}' for skill '{skill_name}' failed: {e}"
                )
        return HookResult(proceed=True)

    async def run_post_hooks(
        self,
        skill_name: str,
        context: dict[str, Any],
        result: str,
    ) -> None:
        """
        Run all post-execute hooks for a skill (SK5).
        
        Fire-and-forget with error logging. Never raises.
        """
        hooks = self.get_skill_hooks(skill_name)
        for hook_name in hooks.get("post_execute", []):
            try:
                await self._run_single_hook(
                    skill_name, hook_name, "post_execute", context, result
                )
            except Exception as e:
                logger.warning(
                    f"Post-hook '{hook_name}' for skill '{skill_name}' failed: {e}"
                )

    async def _run_single_hook(
        self,
        skill_name: str,
        hook_name: str,
        phase: str,
        context: dict[str, Any],
        result: str | None = None,
    ) -> HookResult | None:
        """
        Execute a single hook by name (SK5).
        
        Handles built-in hooks and hooks.py scripts.
        """
        # Built-in: confirm_destructive
        if hook_name == "confirm_destructive" and phase == "pre_execute":
            return HookResult(
                proceed=False,
                message=f"Skill '{skill_name}' is marked as destructive. "
                        f"Please confirm before proceeding.",
            )
        
        # Built-in: log_execution
        if hook_name == "log_execution" and phase == "post_execute":
            self.log_execution(
                skill_name,
                input_summary=context.get("input", "")[:200],
                output_summary=(result or "")[:500],
                duration_ms=context.get("duration_ms", 0),
                success=context.get("success", True),
            )
            return None
        
        # Built-in: notify_completion
        if hook_name == "notify_completion" and phase == "post_execute":
            logger.info(f"Skill '{skill_name}' completed. Result length: {len(result or '')}")
            return None
        
        # hooks.py script
        if hook_name == "hooks_py":
            return await self._run_hooks_py(skill_name, phase, context, result)
        
        return None

    # Phase 23A R2: Dangerous import patterns blocked in hooks.py
    _DANGEROUS_IMPORTS = frozenset({
        "import os", "import subprocess", "import shutil", "import sys",
        "from os ", "from subprocess ", "from shutil ", "from sys ",
    })

    async def _run_hooks_py(
        self,
        skill_name: str,
        phase: str,
        context: dict[str, Any],
        result: str | None = None,
    ) -> HookResult | None:
        """
        Load and execute hooks.py from skill directory (SK5).
        
        Uses importlib with full error isolation — a bad hook
        cannot crash the agent (L7 lesson).
        
        Phase 23A R2: Added three security layers:
        1. Only workspace skills may have hooks.py (not builtins)
        2. File size limit: 50KB
        3. Static scan for dangerous imports (os, subprocess, shutil, sys)
        """
        skill_dir = self._get_skill_dir(skill_name)
        if not skill_dir:
            return None
        hooks_file = skill_dir / "hooks.py"
        if not hooks_file.exists():
            return None

        # R2-1: Only allow hooks in workspace skills, not builtins
        if not hooks_file.is_relative_to(self.workspace_skills):
            logger.warning(f"hooks.py blocked: {hooks_file} is outside workspace skills")
            return None

        # R2-2: Size limit (50KB)
        file_size = hooks_file.stat().st_size
        if file_size > 51_200:
            logger.warning(f"hooks.py too large ({file_size} bytes): {hooks_file}")
            return None

        # R2-3: Static check for dangerous imports
        source = hooks_file.read_text(encoding="utf-8")
        for pattern in self._DANGEROUS_IMPORTS:
            if pattern in source:
                logger.warning(f"hooks.py blocked: contains '{pattern}' in {hooks_file}")
                return None

        try:
            spec = importlib.util.spec_from_file_location(
                f"skill_hooks_{skill_name}", str(hooks_file)
            )
            if not spec or not spec.loader:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if phase == "pre_execute" and hasattr(module, "pre_execute"):
                hook_result = await module.pre_execute(context)
                if isinstance(hook_result, dict):
                    return HookResult(
                        proceed=hook_result.get("proceed", True),
                        message=hook_result.get("message", ""),
                    )
            elif phase == "post_execute" and hasattr(module, "post_execute"):
                await module.post_execute(context, result)
            
        except Exception as e:
            logger.warning(
                f"hooks.py execution failed for skill '{skill_name}' "
                f"(phase={phase}): {e}"
            )
        
        return None

    # ── SK7: Skill Registry & Versioning ─────────────────────────────────

    def _registry_path(self) -> Path:
        """Path to the skills registry file."""
        return self.workspace / "skills_registry.json"

    def _load_registry(self) -> dict:
        """
        Load the skill registry (SK7). Auto-creates if missing.
        """
        path = self._registry_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load skill registry: {e}")
            return {}

    def _save_registry(self, data: dict) -> None:
        """
        Save the skill registry atomically (SK7, L7 lesson).
        """
        path = self._registry_path()
        try:
            content = json.dumps(data, indent=2, ensure_ascii=False)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.workspace), suffix=".tmp", prefix="registry_"
            )
            try:
                os.write(fd, content.encode("utf-8"))
                os.close(fd)
                os.replace(tmp_path, str(path))
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except Exception as e:
            logger.warning(f"Failed to save skill registry: {e}")

    def update_registry(self, skill_name: str) -> None:
        """
        Update registry entry for a skill (SK7).
        
        Records version, last_updated, usage_count, last_used,
        and pip dependencies from frontmatter.
        """
        registry = self._load_registry()
        entry = registry.get(skill_name, {})
        
        # Get version from frontmatter
        meta = self.get_skill_metadata(skill_name)
        version = "1.0.0"
        pip_deps: list[str] = []
        if meta:
            version = meta.get("version", version)
            # Parse nanobot metadata for pip dependencies
            nanobot_meta = self._parse_nanobot_metadata(meta.get("metadata", ""))
            requires = nanobot_meta.get("requires", {})
            if isinstance(requires, dict):
                pip_deps = requires.get("pip", [])
        
        # Get file modification time
        skill_dir = self._get_skill_dir(skill_name)
        last_updated = entry.get("last_updated", "")
        if skill_dir:
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                mtime = skill_file.stat().st_mtime
                last_updated = datetime.fromtimestamp(mtime).isoformat()
        
        # Update entry
        entry["version"] = version
        entry["last_updated"] = last_updated
        entry["usage_count"] = entry.get("usage_count", 0) + 1
        entry["last_used"] = datetime.now().isoformat()
        if pip_deps:
            entry["dependencies"] = pip_deps
        
        registry[skill_name] = entry
        self._save_registry(registry)

    def check_dependencies(self, skill_name: str) -> list[str]:
        """
        Check if pip dependencies for a skill are available (SK7).
        
        Uses importlib.util.find_spec() — no subprocess calls.
        
        Returns:
            List of missing package names. Empty if all present.
        """
        meta = self.get_skill_metadata(skill_name)
        if not meta:
            return []
        nanobot_meta = self._parse_nanobot_metadata(meta.get("metadata", ""))
        requires = nanobot_meta.get("requires", {})
        if not isinstance(requires, dict):
            return []
        pip_deps = requires.get("pip", [])
        if not pip_deps:
            return []
        
        missing = []
        for pkg in pip_deps:
            # Normalize package name for import (e.g., "python-docx" -> "docx")
            import_name = pkg.replace("-", "_").split("[")[0]
            if importlib.util.find_spec(import_name) is None:
                missing.append(pkg)
        return missing

    def get_registry_summary(self) -> str:
        """
        Get a formatted summary of the skill registry (SK7).
        
        Returns:
            Human-readable registry summary, or empty string if no data.
        """
        registry = self._load_registry()
        if not registry:
            return ""
        
        lines = ["Skill Registry:"]
        for name, entry in sorted(registry.items()):
            ver = entry.get("version", "?")
            uses = entry.get("usage_count", 0)
            last = entry.get("last_used", "")[:16]
            deps = entry.get("dependencies", [])
            dep_str = f" deps=[{','.join(deps)}]" if deps else ""
            lines.append(f"  {name} v{ver} (used {uses}x, last: {last}{dep_str})")
        
        return "\n".join(lines)
