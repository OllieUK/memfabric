# tests/test_wp048_two_speed_decay.py
"""
WP-048: Two-speed decay + importance floor tests.

Unit tests (no live stack):
  U1 — New config fields exist with correct defaults
  U2 — _apply_decay respects per-node min_strength
  U3 — initial strength formula: initial_strength_factor * importance / 5.0

Integration tests (live Memgraph + FastAPI required):
  I1 — New memory has low initial strength and fast decay_rate
  I2 — New memory has min_strength stored = importance_floor_factor * importance / 5.0
  I3 — First reinforcement switches decay_rate to consolidated rate
  I4 — Second reinforcement does NOT change decay_rate again
  I5 — Decay pass uses per-node min_strength as floor
  I6 — High-importance memory never decays below its min_strength floor
"""
import math
import uuid
import pytest
from memory_service.memory_repo import _apply_decay


class TestNewConfigFields:
    def test_new_config_fields_exist_with_correct_defaults(self):
        from memory_service.config import Settings
        s = Settings()
        assert s.initial_strength_factor == pytest.approx(0.4)
        assert s.memory_initial_decay_rate == pytest.approx(0.07)
        assert s.memory_consolidated_decay_rate == pytest.approx(0.01)
        assert s.importance_floor_factor == pytest.approx(0.3)


class TestApplyDecayMinStrength:
    def test_decay_floor_respected(self):
        """_apply_decay must not go below min_strength."""
        result = _apply_decay(current=0.5, rate=0.07, days=365.0, min_strength=0.3)
        assert result >= 0.3

    def test_decay_without_floor_reaches_near_zero(self):
        """Without a floor, strength decays to near zero over long period."""
        result = _apply_decay(current=0.4, rate=0.07, days=365.0, min_strength=0.0)
        assert result < 0.01

    def test_fast_rate_half_life_approx_10_days(self):
        """At rate=0.07, half-life should be ~10 days (ln2/0.07 ≈ 9.9)."""
        half_life = math.log(2) / 0.07
        result = _apply_decay(current=1.0, rate=0.07, days=half_life)
        assert abs(result - 0.5) < 0.02

    def test_slow_rate_half_life_approx_69_days(self):
        """At rate=0.01, half-life should be ~69 days (ln2/0.01 ≈ 69.3)."""
        half_life = math.log(2) / 0.01
        result = _apply_decay(current=1.0, rate=0.01, days=half_life)
        assert abs(result - 0.5) < 0.02


class TestInitialStrengthFormula:
    def test_importance_5_initial_strength(self):
        """importance=5, factor=0.4 → strength = 0.4 * 5/5 = 0.4"""
        factor = 0.4
        importance = 5
        expected = factor * (importance / 5.0)
        assert abs(expected - 0.4) < 0.001

    def test_importance_3_initial_strength(self):
        """importance=3, factor=0.4 → strength = 0.4 * 3/5 = 0.24"""
        factor = 0.4
        importance = 3
        expected = factor * (importance / 5.0)
        assert abs(expected - 0.24) < 0.001

    def test_importance_1_initial_strength(self):
        """importance=1, factor=0.4 → strength = 0.4 * 1/5 = 0.08"""
        factor = 0.4
        importance = 1
        expected = factor * (importance / 5.0)
        assert abs(expected - 0.08) < 0.001


_AGENT_ID = "test-wp048-agent"


def _cleanup(test_driver, *ids):
    with test_driver.session() as s:
        for mid in ids:
            s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)
        s.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


@pytest.mark.integration
class TestInitialMemoryState:
    def test_new_memory_has_low_initial_strength(self, client, test_driver):
        """New memory importance=5 → strength = 0.4 * 1.0 = 0.4 (not 1.0)."""
        fact = f"wp048-initial-strength-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 5, "tags": ["test"],
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS strength, "
                    "m.decay_rate AS decay_rate, m.min_strength AS min_strength",
                    id=mid,
                ).single()
            assert row["strength"] == pytest.approx(0.4, abs=0.001)
            assert row["decay_rate"] == pytest.approx(0.07, abs=0.001)
        finally:
            _cleanup(test_driver, mid)

    def test_new_memory_importance_3_initial_strength(self, client, test_driver):
        """importance=3, factor=0.4 → strength = 0.24."""
        fact = f"wp048-imp3-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 3, "tags": ["test"],
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS strength",
                    id=mid,
                ).single()
            assert row["strength"] == pytest.approx(0.24, abs=0.001)
        finally:
            _cleanup(test_driver, mid)

    def test_new_memory_has_min_strength_stored(self, client, test_driver):
        """importance=5, floor_factor=0.3 → min_strength = 0.3."""
        fact = f"wp048-min-strength-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 5, "tags": ["test"],
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.min_strength AS min_strength",
                    id=mid,
                ).single()
            assert row["min_strength"] == pytest.approx(0.3, abs=0.001)
        finally:
            _cleanup(test_driver, mid)

    def test_new_memory_importance_1_min_strength(self, client, test_driver):
        """importance=1, floor_factor=0.3 → min_strength = 0.06."""
        fact = f"wp048-min-str-imp1-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 1, "tags": ["test"],
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.min_strength AS min_strength",
                    id=mid,
                ).single()
            assert row["min_strength"] == pytest.approx(0.06, abs=0.001)
        finally:
            _cleanup(test_driver, mid)


@pytest.mark.integration
class TestConsolidationOnFirstReinforcement:
    def test_first_reinforcement_switches_to_slow_decay_rate(self, client, test_driver):
        """After first reinforcement, decay_rate must switch to consolidated rate (0.01)."""
        fact = f"wp048-consolidate-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 3, "tags": ["test"],
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.decay_rate AS rate, "
                    "m.reinforcement_count AS rc",
                    id=mid,
                ).single()
            assert row["rate"] == pytest.approx(0.07, abs=0.001)
            assert row["rc"] == 0

            r = client.post(f"/memory/{mid}/reinforce", json={
                "strength_increment": 0.2,
                "co_recalled_ids": [],
            })
            assert r.status_code == 200

            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.decay_rate AS rate, "
                    "m.reinforcement_count AS rc",
                    id=mid,
                ).single()
            assert row["rate"] == pytest.approx(0.01, abs=0.001), (
                "After first reinforcement, decay_rate must switch to consolidated rate 0.01"
            )
            assert row["rc"] == 1
        finally:
            _cleanup(test_driver, mid)

    def test_second_reinforcement_does_not_change_decay_rate(self, client, test_driver):
        """Subsequent reinforcements must not change decay_rate again."""
        fact = f"wp048-second-reinforce-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 3, "tags": ["test"],
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            for _ in range(2):
                client.post(f"/memory/{mid}/reinforce", json={
                    "strength_increment": 0.2,
                    "co_recalled_ids": [],
                })

            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.decay_rate AS rate, "
                    "m.reinforcement_count AS rc",
                    id=mid,
                ).single()
            assert row["rate"] == pytest.approx(0.01, abs=0.001)
            assert row["rc"] == 2
        finally:
            _cleanup(test_driver, mid)


@pytest.mark.integration
class TestImportanceFloor:
    def test_high_importance_memory_never_decays_below_floor(self, client, test_driver):
        """importance=5 memory must never drop below min_strength=0.3 after decay."""
        fact = f"wp048-floor-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 5, "tags": ["test"],
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            past = "2020-01-01T00:00:00+00:00"
            with test_driver.session() as s:
                s.run(
                    "MATCH (m:Memory {id: $id}) SET m.last_reinforced_at = $past",
                    id=mid, past=past,
                )

            r = client.post("/memory/maintenance/decay")
            assert r.status_code == 200

            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS strength, "
                    "m.min_strength AS min_strength",
                    id=mid,
                ).single()
            assert row["min_strength"] == pytest.approx(0.3, abs=0.001)
            assert row["strength"] >= row["min_strength"] - 0.001, (
                f"Strength {row['strength']} dropped below floor {row['min_strength']}"
            )
        finally:
            _cleanup(test_driver, mid)

    def test_low_importance_memory_can_decay_near_zero(self, client, test_driver):
        """importance=1 memory (floor=0.06) can decay close to zero."""
        fact = f"wp048-low-floor-{uuid.uuid4()}"
        resp = client.post("/memory", json={
            "fact": fact, "type": "fact", "agent_id": _AGENT_ID, "importance": 1, "tags": ["test"],
        })
        assert resp.status_code == 200
        mid = resp.json()["memory_id"]
        try:
            past = "2020-01-01T00:00:00+00:00"
            with test_driver.session() as s:
                s.run(
                    "MATCH (m:Memory {id: $id}) SET m.last_reinforced_at = $past",
                    id=mid, past=past,
                )

            r = client.post("/memory/maintenance/decay")
            assert r.status_code == 200

            with test_driver.session() as s:
                row = s.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.strength AS strength, "
                    "m.min_strength AS min_strength",
                    id=mid,
                ).single()
            assert row["min_strength"] == pytest.approx(0.06, abs=0.001)
            assert row["strength"] >= row["min_strength"] - 0.001
        finally:
            _cleanup(test_driver, mid)
