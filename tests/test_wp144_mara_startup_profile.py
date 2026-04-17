"""
tests/test_wp144_mara_startup_profile.py — structured wake-up for Mara startup v2.

Integration tests:
  I1 — global/project/user sections split correctly and exact dedup follows priority
  I2 — topic refinement augments project scope without leaking into global sections
"""

import uuid

import pytest

from memory_service.embeddings import get_embedding


@pytest.fixture
def cleanup_wp144(test_driver):
    memory_ids: list[str] = []
    extra_nodes: dict[str, list[str]] = {
        "Agent": [],
        "Person": [],
        "Project": [],
    }
    yield memory_ids, extra_nodes
    with test_driver.session() as session:
        for memory_id in memory_ids:
            session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=memory_id)
        for label, ids in extra_nodes.items():
            for node_id in ids:
                session.run(f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n", id=node_id)


def _create_memory(session, *, memory_id: str, text: str, importance: int, strand_id: str, about: list[tuple[str | None, str]]):
    session.run(
        """
        CREATE (m:Memory {
            id: $id,
            fact: $text,
            text: $text,
            type: 'fact',
            tags: ['test'],
            importance: $importance,
            created_at: $created_at,
            strength: $strength,
            min_strength: 0.3,
            recall_count: 0,
            reinforcement_count: 0,
            decay_rate: 0.01,
            embedding: $embedding,
            status: 'active',
            ephemeral: false
        })
        WITH m
        MATCH (s:Strand {id: $strand_id})
        CREATE (m)-[:IN_STRAND {weight: 1.0}]->(s)
        """,
        id=memory_id,
        text=text,
        importance=importance,
        created_at="2026-04-17T00:00:00+00:00",
        strength=importance / 5.0,
        embedding=get_embedding(text),
        strand_id=strand_id,
    )
    for label, target_id in about:
        label_clause = f":{label}" if label else ""
        session.run(
            f"""
            MERGE (n{label_clause} {{id: $target_id}})
            WITH n
            MATCH (m:Memory {{id: $memory_id}})
            CREATE (m)-[:ABOUT]->(n)
            """,
            target_id=target_id,
            memory_id=memory_id,
        )


@pytest.mark.integration
class TestMaraStartupProfile:
    def test_i1_sections_split_and_exact_dedup_priority(self, client, test_driver, cleanup_wp144):
        memory_ids, extra_nodes = cleanup_wp144
        global_agent_id = f"mara-global-test-{uuid.uuid4()}"
        project_agent_id = f"mara-repo-test-{uuid.uuid4()}"
        person_id = f"oliver-test-{uuid.uuid4()}"
        project_id = f"project-test-{uuid.uuid4()}"
        extra_nodes["Agent"].extend([global_agent_id, project_agent_id])
        extra_nodes["Person"].append(person_id)
        extra_nodes["Project"].append(project_id)

        shared_id = f"wp144-shared-{uuid.uuid4()}"
        user_id = f"wp144-user-{uuid.uuid4()}"
        project_id_mem = f"wp144-project-{uuid.uuid4()}"
        memory_ids.extend([shared_id, user_id, project_id_mem])

        with test_driver.session() as session:
            _create_memory(
                session,
                memory_id=shared_id,
                text="Mara baseline: rollback-first remains the standing operating rule.",
                importance=5,
                strand_id="strand-companion-ai-anchor",
                about=[("Agent", global_agent_id), ("Agent", project_agent_id)],
            )
            _create_memory(
                session,
                memory_id=user_id,
                text="Oliver baseline: prefers explicit structure over vague guidance.",
                importance=4,
                strand_id="strand-companion-human-anchor",
                about=[("Person", person_id)],
            )
            _create_memory(
                session,
                memory_id=project_id_mem,
                text="Project baseline: the backlog is the current source of truth for execution order.",
                importance=4,
                strand_id="strand-core-work-career",
                about=[("Project", project_id)],
            )

        response = client.get(
            "/memory/wake-up",
            params={
                "scope_profile": "mara_startup_v2",
                "global_agent_id": global_agent_id,
                "project_agent_id": project_agent_id,
                "person_id": person_id,
                "project_id": project_id,
                "global_mara_limit": 3,
                "global_user_limit": 3,
                "project_mara_limit": 3,
                "project_baseline_limit": 3,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert [m["id"] for m in data["global_mara_baseline"]] == [shared_id]
        assert [m["id"] for m in data["global_user_baseline"]] == [user_id]
        assert data.get("project_mara_persona") is None
        assert [m["id"] for m in data["project_baseline"]] == [project_id_mem]

    def test_i2_topic_refinement_stays_in_project_scope(self, client, test_driver, cleanup_wp144):
        memory_ids, extra_nodes = cleanup_wp144
        global_agent_id = f"mara-global-test-{uuid.uuid4()}"
        project_agent_id = f"mara-repo-test-{uuid.uuid4()}"
        project_id = f"project-test-{uuid.uuid4()}"
        extra_nodes["Agent"].extend([global_agent_id, project_agent_id])
        extra_nodes["Project"].append(project_id)

        anchor_id = f"wp144-anchor-{uuid.uuid4()}"
        topic_id = f"wp144-topic-{uuid.uuid4()}"
        global_id = f"wp144-global-{uuid.uuid4()}"
        memory_ids.extend([anchor_id, topic_id, global_id])

        with test_driver.session() as session:
            _create_memory(
                session,
                memory_id=anchor_id,
                text="Project baseline: backlog review is ongoing this week.",
                importance=5,
                strand_id="strand-core-work-career",
                about=[("Project", project_id)],
            )
            _create_memory(
                session,
                memory_id=topic_id,
                text="Project baseline: authentication bug triage is urgent for the next sprint.",
                importance=3,
                strand_id="strand-core-work-career",
                about=[("Project", project_id)],
            )
            _create_memory(
                session,
                memory_id=global_id,
                text="Mara baseline: authentication bug triage is urgent for the next sprint.",
                importance=5,
                strand_id="strand-companion-ai-anchor",
                about=[("Agent", global_agent_id)],
            )

        response = client.get(
            "/memory/wake-up",
            params={
                "scope_profile": "mara_startup_v2",
                "global_agent_id": global_agent_id,
                "project_agent_id": project_agent_id,
                "project_id": project_id,
                "topic": "authentication bug triage",
                "global_mara_limit": 2,
                "project_baseline_limit": 2,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert [m["id"] for m in data["global_mara_baseline"]] == [global_id]
        assert [m["id"] for m in data["project_baseline"]] == [anchor_id, topic_id]
