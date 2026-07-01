# Copyright (c) Microsoft. All rights reserved.
# Benefits Benchmarking — Provision Foundry Skills for the Benefits Advisor agent.

"""Provision Foundry Skills used by the Benefits Cost Advisor.

For each skills/<name>/SKILL.md file in this directory, this script packages
the file as an in-memory ZIP and imports it through the Foundry project's
AIProjectClient so the skill becomes downloadable by the hosted agent.

If a skill with the same name already exists, it is deleted first so the
script is safe to re-run after editing a SKILL.md file.

Usage (from this directory, with venv activated and az login done):

    python provision_skills.py

Required env vars (also read from .env):
    FOUNDRY_PROJECT_ENDPOINT   e.g. https://<account>.services.ai.azure.com/api/projects/<project>

Your identity needs the Azure AI User role on the Foundry project.
"""

import asyncio
import io
import os
import zipfile
from pathlib import Path

from azure.ai.projects.aio import AIProjectClient
from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

SKILLS_DIR = Path(__file__).parent / "skills"


def _zip_skill_md(skill_md: Path) -> bytes:
    """Return the bytes of a ZIP archive containing SKILL.md at the root."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", skill_md.read_text(encoding="utf-8"))
    return buffer.getvalue()


async def _delete_skill_if_exists(project: AIProjectClient, name: str) -> None:
    try:
        await project.beta.skills.delete(name)
        print(f"  Deleted existing skill '{name}'.")
    except ResourceNotFoundError:
        return


async def main() -> None:
    load_dotenv()

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    skill_files = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    if not skill_files:
        raise RuntimeError(f"No SKILL.md files found under {SKILLS_DIR}.")

    print(f"Found {len(skill_files)} skill(s) to provision:")
    for sf in skill_files:
        print(f"  - {sf.parent.name} ({sf})")

    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as project,
    ):
        for skill_md in skill_files:
            name = skill_md.parent.name
            print(f"\nProvisioning skill '{name}' from {skill_md.relative_to(SKILLS_DIR.parent)}...")
            await _delete_skill_if_exists(project, name)
            imported = await project.beta.skills.create_from_package(_zip_skill_md(skill_md))
            print(f"  Imported skill '{imported.name}' (id={imported.skill_id}, has_blob={imported.has_blob}).")

        print("\nVerifying skills via project.beta.skills.list()...")
        listed = {skill.name: skill async for skill in project.beta.skills.list()}
        for skill_md in skill_files:
            name = skill_md.parent.name
            skill = listed.get(name)
            if skill is None:
                raise RuntimeError(
                    f"Skill '{name}' was imported but is not present in the project listing."
                )
            print(
                f"  OK '{skill.name}': id={skill.skill_id}, "
                f"description={skill.description!r}, has_blob={skill.has_blob}"
            )

    print("\nDone. Skills are ready for the agent to download at startup.")


if __name__ == "__main__":
    asyncio.run(main())
