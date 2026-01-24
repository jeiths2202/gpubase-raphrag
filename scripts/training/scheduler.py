#!/usr/bin/env python3
"""
Training Scheduler for Smarter RAG System

매일 00:00에 QLoRA 학습을 자동으로 실행합니다.

Usage:
    python scheduler.py              # 스케줄러 시작
    python scheduler.py --run-now    # 즉시 실행
"""
import os
import sys
import asyncio
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TrainingScheduler:
    """학습 스케줄러"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.dsn = None
        self._setup_dsn()

    def _setup_dsn(self):
        """PostgreSQL DSN 설정"""
        from dotenv import load_dotenv
        load_dotenv("/opt/kms/.env")

        self.dsn = (
            f"postgresql://{os.getenv('POSTGRES_USER')}:"
            f"{os.getenv('POSTGRES_PASSWORD')}@"
            f"{os.getenv('POSTGRES_HOST')}:"
            f"{os.getenv('POSTGRES_PORT')}/"
            f"{os.getenv('POSTGRES_DB')}"
        )

    async def get_schedule_config(self) -> dict:
        """DB에서 스케줄 설정 조회"""
        conn = await asyncpg.connect(self.dsn)
        try:
            row = await conn.fetchrow(
                "SELECT * FROM training_schedule ORDER BY id LIMIT 1"
            )
            if row:
                return dict(row)
            return {
                "cron_expression": "0 0 * * *",
                "is_enabled": True,
                "min_samples_required": 10,
                "auto_deploy": False,
            }
        finally:
            await conn.close()

    async def update_schedule_status(
        self,
        last_run_at: datetime,
        last_batch_id: str,
        last_status: str,
        next_run_at: datetime
    ):
        """스케줄 상태 업데이트"""
        conn = await asyncpg.connect(self.dsn)
        try:
            await conn.execute("""
                UPDATE training_schedule SET
                    last_run_at = $1,
                    last_batch_id = $2,
                    last_status = $3,
                    next_run_at = $4,
                    updated_at = NOW()
            """, last_run_at, last_batch_id, last_status, next_run_at)
        finally:
            await conn.close()

    async def check_training_ready(self) -> tuple[int, int]:
        """학습 준비된 샘플 수 확인"""
        conn = await asyncpg.connect(self.dsn)
        try:
            # Training ready count
            train_count = await conn.fetchval("""
                SELECT COUNT(*) FROM verified_knowledge
                WHERE status = 'active'
                  AND is_trained = FALSE
                  AND feedback_score >= 0.8
                  AND thumbs_up_count >= 1
            """)

            # Unlearn required count
            unlearn_count = await conn.fetchval("""
                SELECT COUNT(*) FROM verified_knowledge
                WHERE status = 'unlearn_required'
                  AND is_trained = TRUE
                  AND unlearn_completed_at IS NULL
            """)

            return train_count, unlearn_count
        finally:
            await conn.close()

    async def run_training(self):
        """학습 실행"""
        logger.info("=" * 60)
        logger.info("Starting scheduled training job")
        logger.info("=" * 60)

        try:
            # Check config
            config = await self.get_schedule_config()
            if not config.get("is_enabled", True):
                logger.info("Training is disabled in schedule config")
                return

            # Check sample counts
            train_count, unlearn_count = await self.check_training_ready()
            min_samples = config.get("min_samples_required", 10)

            logger.info(f"Training samples ready: {train_count}")
            logger.info(f"Unlearn samples pending: {unlearn_count}")
            logger.info(f"Minimum required: {min_samples}")

            if train_count < min_samples and unlearn_count == 0:
                logger.info(f"Not enough samples ({train_count} < {min_samples}). Skipping.")
                await self.update_schedule_status(
                    last_run_at=datetime.now(),
                    last_batch_id="",
                    last_status="skipped_insufficient_samples",
                    next_run_at=datetime.now() + timedelta(days=1)
                )
                return

            # Generate batch ID
            batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Run QLoRA trainer
            logger.info(f"Starting training batch: {batch_id}")

            from qlora_trainer import main_async
            import argparse

            args = argparse.Namespace(
                batch_id=batch_id,
                auto=False,
                min_score=0.8,
                min_thumbs_up=1,
                limit=1000
            )

            await main_async(args)

            # Update schedule status
            await self.update_schedule_status(
                last_run_at=datetime.now(),
                last_batch_id=batch_id,
                last_status="completed",
                next_run_at=datetime.now() + timedelta(days=1)
            )

            logger.info(f"Training completed successfully: {batch_id}")

        except Exception as e:
            logger.error(f"Training failed: {e}")

            await self.update_schedule_status(
                last_run_at=datetime.now(),
                last_batch_id="",
                last_status=f"failed: {str(e)[:100]}",
                next_run_at=datetime.now() + timedelta(days=1)
            )

    def start(self):
        """스케줄러 시작"""
        # Add job: 매일 00:00
        self.scheduler.add_job(
            self.run_training,
            CronTrigger(hour=0, minute=0),
            id="daily_training",
            name="Daily QLoRA Training",
            replace_existing=True
        )

        logger.info("Training scheduler started")
        logger.info("Scheduled: Daily at 00:00")

        self.scheduler.start()

    async def run_once(self):
        """즉시 1회 실행"""
        logger.info("Running training immediately...")
        await self.run_training()


async def main():
    parser = argparse.ArgumentParser(description="Training Scheduler")
    parser.add_argument("--run-now", action="store_true", help="Run training immediately")

    args = parser.parse_args()

    scheduler = TrainingScheduler()

    if args.run_now:
        await scheduler.run_once()
    else:
        scheduler.start()

        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped")


if __name__ == "__main__":
    asyncio.run(main())
