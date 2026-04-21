"""Wiki Syncer for Phase 50 Knowledge Graph Wiki Export.

Reads `graph.json` and `experiences.json` to generate Markdown files
compatbile with Obsidian locally in `workspace/wiki/`.
"""

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from loguru import logger


def sanitize_title(name: str) -> str:
    """Replace Windows-illegal chars with underscore. Preserves CJK Unicode."""
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()

class WikiSyncer:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory_dir = workspace / "memory"
        self.wiki_dir = workspace / "wiki"
        self.entities_dir = self.wiki_dir / "entities"
        self.concepts_dir = self.wiki_dir / "concepts"
        self.directives_dir = self.wiki_dir / "directives"
        self.last_sync_time = 0.0

    def sync(self, force: bool = False) -> tuple[int, int, int]:
        """Synchronize Knowledge Graph to Markdown Wiki.
        
        Returns:
            tuple[int, int, int]: (entities_count, triples_count, directives_count)
        """
        graph_file = self.memory_dir / "graph.json"
        experiences_file = self.memory_dir / "experiences.json"

        # Check if we need to sync based on file modification time
        mtime = 0.0
        if graph_file.exists():
            mtime = max(mtime, graph_file.stat().st_mtime)
        if experiences_file.exists():
            mtime = max(mtime, experiences_file.stat().st_mtime)

        if not force and mtime <= self.last_sync_time and mtime > 0:
            return 0, 0, 0

        # Do sync
        logger.info("WikiSyncer: Starting static wiki sync")

        # 1. Clear directories for authentic mirror (File Trashing)
        if self.entities_dir.exists():
            shutil.rmtree(self.entities_dir)
        if self.directives_dir.exists():
            shutil.rmtree(self.directives_dir)
        if self.concepts_dir.exists():
            shutil.rmtree(self.concepts_dir)

        self.entities_dir.mkdir(parents=True, exist_ok=True)
        self.concepts_dir.mkdir(parents=True, exist_ok=True)
        self.directives_dir.mkdir(parents=True, exist_ok=True)
        self.wiki_dir.mkdir(parents=True, exist_ok=True)

        # 2. Process graph.json
        entities_count = 0
        triples_count = 0
        try:
            if graph_file.exists():
                data = json.loads(graph_file.read_text(encoding="utf-8"))
                triples = data.get("triples", [])
                aliases = data.get("_aliases", {})  # For Future use maybe

                # Group triples by entity (source)
                entity_map = {}
                for t in triples:
                    src = t.get("source", "")
                    if not src:
                        continue
                    if src not in entity_map:
                        entity_map[src] = []
                    entity_map[src].append(t)
                    triples_count += 1

                for entity, t_list in entity_map.items():
                    # extract simple aliases if present
                    entity_aliases = []
                    for k, v in aliases.items():
                        if v == entity:
                            entity_aliases.append(k)
                    self._write_entity(entity, t_list, entity_aliases)
                    entities_count += 1
        except Exception as e:
            logger.error(f"WikiSyncer: Failed to process graph.json: {e}")

        # 3. Process experiences.json
        directives_count = 0
        try:
            if experiences_file.exists():
                data = json.loads(experiences_file.read_text(encoding="utf-8"))
                experiences = data.get("experiences", [])
                for idx, exp in enumerate(experiences):
                    self._write_directive(exp, idx)
                    directives_count += 1
        except Exception as e:
            logger.error(f"WikiSyncer: Failed to process experiences.json: {e}")

        # Update last sync
        self.last_sync_time = mtime

        # Log entry
        log_txt = f"## [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Synced {entities_count} entities, {triples_count} triples, {directives_count} directives\n"
        log_file = self.wiki_dir / "_log.md"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_txt)

        # Create empty _index if not exists
        index_file = self.wiki_dir / "_index.md"
        if not index_file.exists():
            index_file.write_text("# Nanobot Knowledge Wiki\n\nAuto-generated index of Knowledge Graph entities and learned Directives.\n", encoding="utf-8")

        return entities_count, triples_count, directives_count

    def _write_entity(self, entity: str, triples: list, aliases: list[str]):
        sane = sanitize_title(entity)
        if not sane:
            sane = "Unknown"

        out_file = self.entities_dir / f"{sane}.md"
        if out_file.exists():
            h4 = hashlib.md5(entity.encode()).hexdigest()[:4]
            out_file = self.entities_dir / f"{sane}_{h4}.md"

        aliases_json = json.dumps(aliases)
        content = f"""---
aliases: {aliases_json}
updated: "{datetime.now().isoformat()}"
type: "kg_entity"
nanobot_source: "graph.json"
---

> [!WARNING]
> This file is **auto-generated** by Nanobot's Knowledge Graph.
> **Local edits will be OVERWRITTEN** on the next sync.
> To update knowledge, use `/remember` or the standard Knowledge Workflow.

# {entity}

## Knowledge Graph Connections

| Predicate | Target | Context |
|-----------|--------|---------|
"""
        for t in triples:
            pred = t.get("predicate", "")
            target = t.get("target", "")
            ctx = t.get("context", "")
            # escape pipes for markdown table
            pred = pred.replace("|", "\\|").replace("\n", " ")
            target = target.replace("|", "\\|").replace("\n", " ")
            ctx = ctx.replace("|", "\\|").replace("\n", " ")
            content += f"| {pred} | [[{target}]] | {ctx} |\n"

        out_file.write_text(content, encoding="utf-8")

    def _write_directive(self, exp: dict, idx: int):
        trigger = exp.get("trigger", "Unknown")
        prompt = exp.get("prompt", "")
        # auto naming
        date_str = datetime.now().strftime("%Y%m%d")
        sane_trigger = sanitize_title(trigger)[:20]
        if not sane_trigger:
            sane_trigger = f"experience_{idx}"

        out_file = self.directives_dir / f"{date_str}-{sane_trigger}-auto.md"
        if out_file.exists():
             h4 = hashlib.md5(prompt.encode()).hexdigest()[:4]
             out_file = self.directives_dir / f"{date_str}-{sane_trigger}-{h4}-auto.md"

        content = f"""---
updated: "{datetime.now().isoformat()}"
type: "directive"
nanobot_source: "experiences.json"
---

> [!WARNING]
> This file is **auto-generated** by Nanobot's Experience Bank.
> **Local edits will be OVERWRITTEN** on the next sync.

# Directive: {trigger}

## Prompt Details
{prompt}
"""
        out_file.write_text(content, encoding="utf-8")
