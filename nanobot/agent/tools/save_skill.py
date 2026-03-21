"""Save skill tool for converting successful workflows into reusable skills."""

from pathlib import Path
from typing import Any
import json

from nanobot.agent.tools.base import Tool
from nanobot.utils.helpers import ensure_dir


class SaveSkillTool(Tool):
    """
    Tool for saving a successful workflow as a reusable skill.
    
    This allows the agent to convert a complex task (like reading Outlook emails,
    analyzing attachments, and sending reports) into a skill that can be reused
    in the future.
    """
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.skills_dir = ensure_dir(workspace / "skills")
    
    @property
    def name(self) -> str:
        return "save_skill"
    
    @property
    def description(self) -> str:
        return """Save a successful workflow as a reusable skill. 
Use this after completing a complex task that you want to remember and reuse later.
The skill will be stored in the workspace/skills directory and can be loaded
by other agents or yourself in the future."""
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for the skill (e.g., 'outlook-email-analysis')",
                    "minLength": 2,
                    "maxLength": 50
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what the skill does",
                    "minLength": 10,
                    "maxLength": 200
                },
                "summary": {
                    "type": "string",
                    "description": "Detailed summary of the task and what was accomplished",
                    "minLength": 20
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "What action was taken (e.g., 'read outlook emails', 'analyze attachment', 'send report')"
                            },
                            "tools": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Tools used in this step"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Important notes or parameters for this step"
                            }
                        },
                        "required": ["action"]
                    },
                    "description": "Step-by-step breakdown of the workflow"
                },
                "requirements": {
                    "type": "object",
                    "properties": {
                        "bins": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Required CLI binaries (e.g., ['python', 'outlook-cli'])"
                        },
                        "env": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Required environment variables"
                        }
                    },
                    "description": "Requirements for using this skill"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorizing the skill (e.g., ['email', 'analysis', 'automation'])"
                },
                "category": {
                    "type": "string",
                    "description": "Skill category: library_api, code_quality, frontend_design, business_workflow, product_verification, content_generation, data_fetching, service_debugging, or infra_ops",
                    "enum": ["library_api", "code_quality", "frontend_design", "business_workflow", "product_verification", "content_generation", "data_fetching", "service_debugging", "infra_ops"]
                },
                "version": {
                    "type": "string",
                    "description": "Skill version in semver format (default: '1.0.0')"
                },
                "config": {
                    "type": "object",
                    "description": "Default configuration for the skill. Saved as config.defaults.json. Users can override via config.json."
                },
                "pip_dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Required pip packages (e.g., ['openpyxl', 'fpdf2'])"
                }
            },
            "required": ["name", "description", "summary", "steps"]
        }
    
    async def execute(self, **kwargs: Any) -> str:
        """Save a skill to the workspace/skills directory."""
        name = kwargs["name"]
        description = kwargs["description"]
        summary = kwargs["summary"]
        steps = kwargs.get("steps", [])
        requirements = kwargs.get("requirements", {})
        tags = kwargs.get("tags", [])
        category = kwargs.get("category", "")
        version = kwargs.get("version", "1.0.0")
        config = kwargs.get("config")
        pip_dependencies = kwargs.get("pip_dependencies", [])
        
        # Create skill directory
        skill_dir = self.skills_dir / name
        ensure_dir(skill_dir)
        
        # Create SKILL.md with frontmatter and content
        skill_file = skill_dir / "SKILL.md"
        
        # Build frontmatter
        frontmatter_lines = ["---"]
        frontmatter_lines.append(f'name: "{name}"')
        frontmatter_lines.append(f'description: "{description}"')
        if category:
            frontmatter_lines.append(f'category: {category}')
        frontmatter_lines.append(f'created: "{self._current_timestamp()}"')
        
        # Version field in frontmatter (SK7)
        frontmatter_lines.append(f'version: {version}')
        
        # Add nanobot metadata
        nanobot_requires = {**requirements}
        if pip_dependencies:
            nanobot_requires["pip"] = pip_dependencies
        nanobot_meta = {
            "requires": nanobot_requires,
            "tags": tags,
            "version": version,
            "type": "workflow"
        }
        frontmatter_lines.append(f'metadata: {json.dumps({"nanobot": nanobot_meta}, ensure_ascii=False)}')
        frontmatter_lines.append("---")
        frontmatter_lines.append("")
        
        # Build content
        content_lines = []
        content_lines.append(f"# {name}")
        content_lines.append("")
        content_lines.append(f"**{description}**")
        content_lines.append("")
        content_lines.append("## Summary")
        content_lines.append("")
        content_lines.append(summary)
        content_lines.append("")
        
        if steps:
            content_lines.append("## Steps")
            content_lines.append("")
            for i, step in enumerate(steps, 1):
                content_lines.append(f"### Step {i}: {step.get('action', 'Unknown')}")
                content_lines.append("")
                if step.get("tools"):
                    content_lines.append(f"**Tools used:** {', '.join(step['tools'])}")
                    content_lines.append("")
                if step.get("notes"):
                    content_lines.append(f"**Notes:** {step['notes']}")
                    content_lines.append("")
        
        if requirements.get("bins") or requirements.get("env"):
            content_lines.append("## Requirements")
            content_lines.append("")
            if requirements.get("bins"):
                content_lines.append("### CLI Tools Required:")
                for bin_req in requirements["bins"]:
                    content_lines.append(f"- `{bin_req}`")
                content_lines.append("")
            if requirements.get("env"):
                content_lines.append("### Environment Variables Required:")
                for env_req in requirements["env"]:
                    content_lines.append(f"- `{env_req}`")
                content_lines.append("")
        
        if tags:
            content_lines.append("## Tags")
            content_lines.append("")
            content_lines.append(", ".join(f"`{tag}`" for tag in tags))
            content_lines.append("")
        
        content_lines.append("## Usage")
        content_lines.append("")
        content_lines.append("When you need to perform this task again, read this skill file and follow the steps.")
        content_lines.append("")
        content_lines.append("## Notes")
        content_lines.append("")
        content_lines.append("- This skill was automatically generated by nanobot")
        content_lines.append("- Update this file as you improve the workflow")
        
        # Write file
        skill_content = "\n".join(frontmatter_lines + content_lines)
        skill_file.write_text(skill_content, encoding="utf-8")
        
        # SK4: Write config.defaults.json if config provided
        if config and isinstance(config, dict):
            defaults_file = skill_dir / "config.defaults.json"
            defaults_file.write_text(
                json.dumps(config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        
        # Also create a simple summary file for quick reference
        summary_file = skill_dir / "SUMMARY.md"
        summary_content = f"""# {name}

{description}

## Quick Reference
- **Created**: {self._current_timestamp()}
- **Steps**: {len(steps)}
- **Tags**: {', '.join(tags) if tags else 'none'}

Access the full skill at: {skill_file}
"""
        summary_file.write_text(summary_content, encoding="utf-8")
        
        return f"""Successfully saved skill '{name}' to {skill_file}

The skill includes:
- Frontmatter with metadata for skill discovery
- Step-by-step instructions
- Requirements and tags
- Usage guidance

You can now use this skill in the future by reading the SKILL.md file.
The skill will appear in the skills summary for future sessions."""

    def _current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.now().isoformat()