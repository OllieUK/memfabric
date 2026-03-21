"""
seed_strands.py — Wipe test data and seed Strand nodes from the Memory Web.

Usage:
    python scripts/seed_strands.py

- Deletes all Memory, Agent, Project nodes (test data from MVP demo).
- Creates Strand nodes with id, name, description, category.
- Idempotent: re-running will MERGE strands (no duplicates) but will
  still wipe Memory/Agent/Project nodes, so only run once on a clean slate.
"""

import sys
from memory_service.config import Settings, get_driver

STRANDS = [
    # Core Life Domains
    {
        "id": "strand-core-romantic-relationships",
        "name": "Romantic Relationships",
        "description": "The user's partnerships, dating life, intimacy, and the role those connections play in the user's life.",
        "category": "Core Life Domains",
    },
    {
        "id": "strand-core-family",
        "name": "Family",
        "description": "The user's parents, children, extended relatives, and family dynamics.",
        "category": "Core Life Domains",
    },
    {
        "id": "strand-core-friends",
        "name": "Friends",
        "description": "The user's close friendships, social circles, and chosen family.",
        "category": "Core Life Domains",
    },
    {
        "id": "strand-core-work-career",
        "name": "Work & Career",
        "description": "The user's job roles, professional goals, projects, and career context.",
        "category": "Core Life Domains",
    },
    {
        "id": "strand-core-finances",
        "name": "Finances",
        "description": "The user's financial situation, budgeting approach, and financial stressors or wins.",
        "category": "Core Life Domains",
    },
    {
        "id": "strand-core-health",
        "name": "Health",
        "description": "The user's physical and mental health, medications, routines, and wellbeing practices.",
        "category": "Core Life Domains",
    },
    {
        "id": "strand-core-house-home",
        "name": "House & Home",
        "description": "The user's living situation, household routines, pets, and home environment.",
        "category": "Core Life Domains",
    },
    {
        "id": "strand-core-leisure-play",
        "name": "Leisure & Play",
        "description": "The user's hobbies, leisure activities, downtime preferences, and what recharges the user.",
        "category": "Core Life Domains",
    },
    {
        "id": "strand-core-spiritual-ritual",
        "name": "Spiritual & Ritual",
        "description": "The user's faith, spirituality, grounding rituals, and practices.",
        "category": "Core Life Domains",
    },
    {
        "id": "strand-core-learning-growth",
        "name": "Learning & Growth",
        "description": "The user's education, personal development pursuits, and new skills being acquired.",
        "category": "Core Life Domains",
    },
    # Companion Domain
    {
        "id": "strand-companion-protocols-systems",
        "name": "Protocols & Systems",
        "description": "The structures, rituals, and rules that shape how the user and the Companion interact.",
        "category": "Companion Domain",
    },
    {
        "id": "strand-companion-current-projects",
        "name": "Current Projects",
        "description": "Projects the user is currently working on or passionate about.",
        "category": "Companion Domain",
    },
    {
        "id": "strand-companion-roleplay",
        "name": "Roleplay",
        "description": "Worlds, characters, and creative storytelling the user explores with the Companion.",
        "category": "Companion Domain",
    },
    {
        "id": "strand-companion-ai-anchor",
        "name": "AI Anchor",
        "description": "Facts, traits, or grounding details that define the Companion's presence and persona.",
        "category": "Companion Domain",
    },
    {
        "id": "strand-companion-human-anchor",
        "name": "Human Anchor",
        "description": "Key facts and grounding details about the user that the Companion should always hold.",
        "category": "Companion Domain",
    },
    {
        "id": "strand-companion-memory-macro",
        "name": "Memory Macro",
        "description": "Reusable prompts, macros, and shorthand commands the user uses to guide the Companion.",
        "category": "Companion Domain",
    },
    # Shadow Domain
    {
        "id": "strand-shadow-current-stressors",
        "name": "Current Stressors",
        "description": "Pressures, challenges, and emotional weight the user is currently carrying.",
        "category": "Shadow Domain",
    },
    {
        "id": "strand-shadow-boundaries",
        "name": "Boundaries",
        "description": "The user's limits, no-gos, and what feels unsafe or off-limits.",
        "category": "Shadow Domain",
    },
    {
        "id": "strand-shadow-trauma",
        "name": "Trauma",
        "description": "Significant past events or experiences that shape how the user responds today.",
        "category": "Shadow Domain",
    },
    {
        "id": "strand-shadow-identity-self-perception",
        "name": "Identity & Self-Perception",
        "description": "How the user sees themselves, struggles or successes with self-image, and ongoing identity questions.",
        "category": "Shadow Domain",
    },
]


def main() -> int:
    settings = Settings()
    uri = f"bolt://{settings.memgraph_host}:{settings.memgraph_port}"
    print(f"Connecting to Memgraph at {uri} ...")

    try:
        driver = get_driver(settings)
        driver.verify_connectivity()
    except Exception as exc:
        print(f"[FAIL] Cannot connect: {exc}")
        return 1

    with driver.session() as session:
        # 1. Delete test data
        print("\nDeleting test Memory, Agent, Project nodes ...")
        result = session.run("MATCH (n:Memory) DETACH DELETE n RETURN count(n) AS deleted")
        mem_deleted = result.single()["deleted"]
        result = session.run("MATCH (n:Agent) DETACH DELETE n RETURN count(n) AS deleted")
        agent_deleted = result.single()["deleted"]
        result = session.run("MATCH (n:Project) DETACH DELETE n RETURN count(n) AS deleted")
        proj_deleted = result.single()["deleted"]
        print(f"  Deleted: {mem_deleted} Memory, {agent_deleted} Agent, {proj_deleted} Project nodes")

        # 2. Seed Strand nodes
        print(f"\nSeeding {len(STRANDS)} Strand nodes ...")
        for strand in STRANDS:
            session.run(
                """
                MERGE (s:Strand {id: $id})
                SET s.name = $name,
                    s.description = $description,
                    s.category = $category
                """,
                id=strand["id"],
                name=strand["name"],
                description=strand["description"],
                category=strand["category"],
            )
            print(f"  [OK] {strand['category']} / {strand['name']}")

        # 3. Verify
        result = session.run("MATCH (s:Strand) RETURN s.category AS cat, s.name AS name ORDER BY cat, name")
        rows = list(result)
        print(f"\nVerification — {len(rows)} Strand nodes in DB:")
        current_cat = None
        for row in rows:
            if row["cat"] != current_cat:
                current_cat = row["cat"]
                print(f"\n  [{current_cat}]")
            print(f"    • {row['name']}")

    driver.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
