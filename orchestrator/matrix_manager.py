"""
Persona matrix manager for fetching, filtering, and caching Onyx personas and tool routing.
"""

import json
import os
from typing import Any, List, Tuple

from orchestrator.config import (
    PERSONAS,
    PRIMARY_PERSONA_ID,
    logger,
)


class MatrixManager:
    def __init__(self, client: Any, cache_file: str):
        self.client = client
        self.cache_file = cache_file

    def build_matrix(self) -> Tuple[str, List[int]]:
        logger.info("Fetching personas and tools for routing matrix")
        try:
            personas = self.client.fetch_personas()
        except Exception as e:
            logger.warning("Failed to fetch personas from Onyx: %s", e)
            personas = []

        try:
            tools = self.client.fetch_tools()
            tool_ids = self.client.extract_tool_ids(tools)
        except Exception as e:
            logger.warning("Failed to fetch tools from Onyx: %s", e)
            tools = []
            tool_ids = []

        filtered_personas = [
            p for p in personas if p.get("id") in PERSONAS and p.get("id") != PRIMARY_PERSONA_ID
        ]

        if filtered_personas:
            logger.info("Programmatically constructing routing matrix from %d active personas", len(filtered_personas))
            manifest_parts = []
            for p in filtered_personas:
                p_id = p.get("id")
                name = p.get("name") or PERSONAS.get(p_id, f"Persona {p_id}")
                desc = p.get("description") or "Route here for tasks corresponding to this assistant."
                clean_desc = desc.replace("\n", " ").strip()
                manifest_parts.append(
                    f"- Persona ID {p_id}: {name}\n"
                    f"  Rule: Route here strictly when the user query is about: {clean_desc}"
                )
            manifest = "\n".join(manifest_parts)
        else:
            logger.info("No active personas fetched. Falling back to default routing matrix.")
            manifest_parts = []
            for p_id, name in PERSONAS.items():
                if p_id == PRIMARY_PERSONA_ID:
                    continue
                desc = "topics related to this specialty."
                if p_id == 1 or p_id == 2:
                    desc = "QA, software testing, test plans, automation, or verification."
                elif p_id == 3:
                    desc = "searching or querying the loaded knowledge base/documents."
                elif p_id == 4:
                    desc = "business analysis, product roadmap, or card suite design requirements."
                elif p_id == 5:
                    desc = "writing, refactoring, debugging, or designing general software code."
                elif p_id == 6:
                    desc = "data analysis, databases, CSV/Excel processing, or metrics analysis."
                elif p_id == 7:
                    desc = "technical documentation, user guides, or markdown wiki articles."
                elif p_id == 8:
                    desc = "high-level system design, cloud architecture, or microservices deployment."
                elif p_id == 9:
                    desc = "code review, security vulnerability audit, or performance optimizations."
                elif p_id == 10:
                    desc = "system design specification, product requirements, and design specifications."
                manifest_parts.append(
                    f"- Persona ID {p_id}: {name}\n"
                    f"  Rule: Route here strictly when user is asking about {desc}"
                )
            manifest = "\n".join(manifest_parts)

        cache_data = {
            "routing_manifest": manifest,
            "global_tool_ids": tool_ids,
            "personas_filtered": filtered_personas,
        }

        try:
            with open(self.cache_file, "w", encoding="utf-8") as file:
                json.dump(cache_data, file, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("Failed to save persona matrix cache: %s", e)

        return manifest, tool_ids

    def get_or_build_matrix(self, force_refresh: bool = False) -> Tuple[str, List[int]]:
        if not force_refresh and os.path.exists(self.cache_file):
            logger.info("Loading routing matrix from %s", self.cache_file)
            with open(self.cache_file, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data.get("routing_manifest", ""), data.get("global_tool_ids", [])
        return self.build_matrix()
