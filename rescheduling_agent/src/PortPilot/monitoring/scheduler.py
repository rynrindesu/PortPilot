"""In-process Singapore-time scheduler for PortPilot automation."""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from PortPilot.database.postgres import automation_job_lock
from PortPilot.monitoring.lifecycle import (
    SINGAPORE_TIMEZONE,
    initialize_current_day,
    run_startup_catchup,
    run_hourly_update,
    singapore_now,
    stage_next_day,
)


logger = logging.getLogger(__name__)


def next_daily_run(now: datetime, hour: int, minute: int = 0) -> datetime:
    """Return the next Singapore-local occurrence of a daily job."""

    local_now = now.astimezone(SINGAPORE_TIMEZONE)
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate


def next_hourly_run(now: datetime, minute: int = 5) -> datetime:
    """Return the next Singapore-local hourly monitoring time."""

    local_now = now.astimezone(SINGAPORE_TIMEZONE)
    candidate = local_now.replace(minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(hours=1)
    return candidate


class AutomationScheduler:
    """Run lifecycle jobs without blocking FastAPI's event loop."""

    def __init__(self, now_provider: Callable[[], datetime] = singapore_now):
        self._now_provider = now_provider
        self._tasks: list[asyncio.Task] = []
        self._last_results: dict[str, dict] = {}
        self._running = False

    @property
    def status(self) -> dict:
        return {
            "running": self._running,
            "timezone": str(SINGAPORE_TIMEZONE),
            "schedule": {
                "stage_next_day": "21:00 daily",
                "initialize_current_day": "00:00 daily",
                "hourly_update": "minute 05 of every hour",
            },
            "last_results": self._last_results,
        }

    async def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._tasks = [
            asyncio.create_task(
                self._daily_loop("stage_next_day", 21, 0, stage_next_day),
                name="portpilot-stage-next-day",
            ),
            asyncio.create_task(
                self._daily_loop(
                    "initialize_current_day", 0, 0, initialize_current_day
                ),
                name="portpilot-initialize-current-day",
            ),
            asyncio.create_task(
                self._hourly_loop("hourly_update", 5, run_hourly_update),
                name="portpilot-hourly-update",
            ),
            # Reconcile the current day after a backend restart instead of
            # waiting until the next midnight boundary.
            asyncio.create_task(
                self._execute("startup_catchup", run_startup_catchup),
                name="portpilot-startup-catchup",
            ),
        ]
        logger.info("PortPilot automation scheduler started in Asia/Singapore")

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        logger.info("PortPilot automation scheduler stopped")

    async def _daily_loop(
        self,
        job_name: str,
        hour: int,
        minute: int,
        job: Callable[[], dict],
    ) -> None:
        while True:
            run_at = next_daily_run(self._now_provider(), hour, minute)
            await asyncio.sleep(
                max(0.0, (run_at - self._now_provider()).total_seconds())
            )
            await self._execute(job_name, job)

    async def _hourly_loop(
        self,
        job_name: str,
        minute: int,
        job: Callable[[], dict],
    ) -> None:
        while True:
            run_at = next_hourly_run(self._now_provider(), minute)
            await asyncio.sleep(
                max(0.0, (run_at - self._now_provider()).total_seconds())
            )
            await self._execute(job_name, job)

    async def _execute(self, job_name: str, job: Callable[[], dict]) -> None:
        started_at = self._now_provider()
        try:
            result = await asyncio.to_thread(self._run_with_lock, job_name, job)
            self._last_results[job_name] = {
                "started_at": started_at.isoformat(),
                "finished_at": self._now_provider().isoformat(),
                **result,
            }
            logger.info("Automation job %s completed: %s", job_name, result)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("Automation job %s failed", job_name)
            self._last_results[job_name] = {
                "started_at": started_at.isoformat(),
                "finished_at": self._now_provider().isoformat(),
                "error": str(error),
            }

    @staticmethod
    def _run_with_lock(job_name: str, job: Callable[[], dict]) -> dict:
        # One shared lock prevents midnight initialization, hourly monitoring,
        # and duplicate web-server workers from overlapping database changes.
        with automation_job_lock("automation-cycle") as acquired:
            if not acquired:
                return {"job": job_name, "skipped": "another automation job is running"}
            return job()


automation_scheduler = AutomationScheduler()
