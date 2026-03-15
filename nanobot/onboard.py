"""Onboard utility for Nanobot.

Copies skills from the resources/ directory into the active plugins/ directory
so they can be dynamically loaded by the plugin_loader at runtime.

Usage (CLI):
    python -m nanobot.onboard ssrs-report
    python -m nanobot.onboard outlook-email-analysis

Usage (Python):
    from nanobot.onboard import onboard_skill
    onboard_skill("ssrs-report", resources_dir, plugins_dir)
"""

import shutil
import subprocess
import sys
from pathlib import Path

from loguru import logger


def onboard_skill(
    skill_name: str,
    resources_dir: Path | None = None,
    plugins_dir: Path | None = None,
) -> str:
    """Copy a skill from resources/ to plugins/ and install dependencies.

    Args:
        skill_name: Name of the skill directory (e.g., 'ssrs-report').
        resources_dir: Path to the resources/ directory.
                       Defaults to <project_root>/resources/.
        plugins_dir: Path to the plugins/ directory.
                     Defaults to <project_root>/nanobot/plugins/.

    Returns:
        A status message describing what was done.
    """
    project_root = Path(__file__).parent.parent

    if resources_dir is None:
        resources_dir = project_root / "resources"
    if plugins_dir is None:
        plugins_dir = project_root / "nanobot" / "plugins"

    skill_src = resources_dir / skill_name
    if not skill_src.exists():
        available = [
            d.name for d in resources_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ] if resources_dir.exists() else []
        return (
            f"Error: Skill '{skill_name}' not found in {resources_dir}.\n"
            f"Available skills: {', '.join(available) if available else '(none)'}"
        )

    # Ensure plugins directory exists
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Copy .py files
    copied_files: list[str] = []
    copied_assets: list[str] = []

    for item in skill_src.iterdir():
        if item.name.startswith("__"):
            continue
        dest = plugins_dir / item.name
        if item.is_file():
            shutil.copy2(item, dest)
            if item.suffix == ".py":
                copied_files.append(item.name)
            else:
                copied_assets.append(item.name)
        elif item.is_dir() and not item.name.startswith("__"):
            # Copy subdirectories (e.g., config, data)
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
            copied_assets.append(f"{item.name}/")

    # Install dependencies if requirements.txt exists
    deps_installed = False
    req_file = skill_src / "requirements.txt"
    if req_file.exists():
        logger.info(f"Onboard: installing dependencies from {req_file}")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            deps_installed = True
        except subprocess.CalledProcessError as e:
            logger.warning(f"Onboard: pip install failed: {e}")

    # Build summary
    lines = [f"✅ Skill '{skill_name}' onboarded successfully!"]
    if copied_files:
        lines.append(f"  Python files: {', '.join(copied_files)}")
    if copied_assets:
        lines.append(f"  Assets: {', '.join(copied_assets)}")
    if deps_installed:
        lines.append("  Dependencies installed from requirements.txt")
    lines.append(f"\nUse /reload in chat to activate the new tools.")

    result = "\n".join(lines)
    logger.info(result)
    return result


def list_available_skills(resources_dir: Path | None = None) -> list[str]:
    """List all available skills in the resources directory."""
    if resources_dir is None:
        resources_dir = Path(__file__).parent.parent / "resources"
    if not resources_dir.exists():
        return []
    return [
        d.name for d in sorted(resources_dir.iterdir())
        if d.is_dir() and not d.name.startswith(".")
    ]


# CLI entry point
if __name__ == "__main__":
    if len(sys.argv) < 2:
        skills = list_available_skills()
        print("Usage: python -m nanobot.onboard <skill_name>")
        print(f"\nAvailable skills: {', '.join(skills) if skills else '(none)'}")
        sys.exit(1)

    skill = sys.argv[1]
    print(onboard_skill(skill))
