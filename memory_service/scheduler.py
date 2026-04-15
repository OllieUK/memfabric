# memory_service/scheduler.py
#
# Built-in maintenance scheduler. Runs as an asyncio background task inside the
# FastAPI lifespan — no external cron or systemd timers required.
#
# Schedule:
#   short-rest  every short_rest_interval_hours (default: 6h)
#   long-rest   daily at long_rest_utc_hour UTC (default: 03:00)
#               OR immediately if more than long_rest_overdue_hours have elapsed
#               (handles the "service was down at 03:00" case).

import asyncio
import logging
from datetime import datetime, timezone

from memory_service import memory_repo
from memory_service.config import Settings

logger = logging.getLogger(__name__)


def _hours_since(iso_str: str | None) -> float:
    """Hours elapsed since iso_str, or infinity if never run."""
    if iso_str is None:
        return float("inf")
    try:
        last = datetime.fromisoformat(iso_str)
        return (datetime.now(tz=timezone.utc) - last).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return float("inf")


def _short_rest_due(last_iso: str | None, interval_hours: int) -> bool:
    return _hours_since(last_iso) >= interval_hours


def _long_rest_due(last_iso: str | None, settings: Settings) -> bool:
    hours = _hours_since(last_iso)
    if hours < settings.long_rest_min_interval_hours:
        return False  # too soon — avoid double-run
    # ASAP: missed the window by more than overdue_hours
    if hours >= settings.long_rest_overdue_hours:
        return True
    # Scheduled window: we're in the target UTC hour (±poll interval)
    now = datetime.now(tz=timezone.utc)
    window_minutes = max(10, settings.scheduler_poll_interval_seconds // 60 + 2)
    return now.hour == settings.long_rest_utc_hour and now.minute < window_minutes


async def _run_short_rest(driver, settings: Settings) -> None:
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        with driver.session() as session:
            result = memory_repo.short_rest(
                session,
                now_iso=now_iso,
                recency_days=settings.short_rest_recency_days,
                min_strength=settings.min_memory_strength,
                edge_modulation_factor=settings.edge_modulation_factor,
                edge_modulation_cap=settings.edge_modulation_cap,
            )
        logger.info(
            "Scheduled short-rest complete: nodes_decayed=%d edges_decayed=%d",
            result["nodes_decayed"],
            result["edges_decayed"],
        )
    except Exception:
        logger.exception("Scheduled short-rest failed")


async def _run_long_rest(driver, settings: Settings) -> None:
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        with driver.session() as session:
            result = memory_repo.long_rest(
                session,
                now_iso=now_iso,
                min_strength=settings.min_memory_strength,
                edge_modulation_factor=settings.edge_modulation_factor,
                edge_modulation_cap=settings.edge_modulation_cap,
                rediscovery_strength_threshold=settings.rediscovery_strength_threshold,
                edge_hard_prune_floor=settings.edge_hard_prune_floor,
                edge_hard_prune_min_days=settings.edge_hard_prune_min_days,
                edge_decay_rate=settings.edge_decay_rate,
                memory_index_capacity=settings.memory_index_capacity,
                near_duplicate_threshold=settings.near_duplicate_threshold,
                near_duplicate_preview_limit=settings.near_duplicate_limit,
                auto_merge_threshold=settings.auto_merge_threshold,
            )
        logger.info(
            "Scheduled long-rest complete: nodes_decayed=%d edges_decayed=%d "
            "edges_discovered=%d near_dups=%d auto_merged=%d index=%.1f%%",
            result["nodes_decayed"],
            result["edges_decayed"],
            result["edges_discovered"],
            result["near_duplicate_count"],
            result.get("auto_merged_count", 0),
            result.get("index_utilisation_pct") or 0.0,
        )
        if result.get("index_near_capacity"):
            logger.warning(
                "Memory index near capacity: %d/%d (%.1f%%) — consider raising "
                "MEMORY_INDEX_CAPACITY or running WP-116 embedding migration",
                result["embedded_memory_count"],
                result["index_capacity"],
                result.get("index_utilisation_pct") or 0.0,
            )
        if result["near_duplicate_count"] > 0:
            logger.info(
                "%d near-duplicate pairs above threshold — review via GET /memory/duplicates",
                result["near_duplicate_count"],
            )
        auto_merged = result.get("auto_merged_count", 0)
        if auto_merged > 0:
            logger.info("Auto-merged %d near-duplicate pairs during long-rest", auto_merged)
    except Exception:
        logger.exception("Scheduled long-rest failed")


async def run_scheduler(driver, settings: Settings) -> None:
    """Asyncio background task: check and run maintenance on each poll cycle.

    Designed to be launched as an asyncio.Task inside the FastAPI lifespan and
    cancelled on shutdown. On first cycle (startup) it checks immediately so that
    a missed long-rest window is caught as soon as the service comes back up.
    """
    logger.info(
        "Maintenance scheduler started — short-rest every %dh, "
        "long-rest at %02d:00 UTC (poll every %ds)",
        settings.short_rest_interval_hours,
        settings.long_rest_utc_hour,
        settings.scheduler_poll_interval_seconds,
    )

    while True:
        try:
            with driver.session() as session:
                ts = memory_repo.get_system_timestamps(session)
        except Exception:
            logger.warning("Scheduler: could not read system timestamps; skipping cycle")
            await asyncio.sleep(settings.scheduler_poll_interval_seconds)
            continue

        if _short_rest_due(ts.get("last_short_rest_at"), settings.short_rest_interval_hours):
            hours = _hours_since(ts.get("last_short_rest_at"))
            logger.info("Scheduler: short-rest due (%.1fh since last run)", hours)
            await _run_short_rest(driver, settings)

        if _long_rest_due(ts.get("last_long_rest_at"), settings):
            hours = _hours_since(ts.get("last_long_rest_at"))
            logger.info("Scheduler: long-rest due (%.1fh since last run)", hours)
            await _run_long_rest(driver, settings)

        await asyncio.sleep(settings.scheduler_poll_interval_seconds)
