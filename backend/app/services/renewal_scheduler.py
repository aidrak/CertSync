"""
Renewal Scheduler Service

This service runs periodic checks for certificates that need renewal
and triggers the automatic renewal process.
"""

import asyncio
import logging
from typing import Optional

from app.services.auto_renewal_service import auto_renewal_service
from app.crud import crud_log
from app.db.database import SessionLocal
from app.schemas import schemas

logger = logging.getLogger(__name__)


class RenewalScheduler:
    """
    Background scheduler for automatic certificate renewals.
    """

    def __init__(self, check_interval_hours: int = 12):
        self.check_interval_hours = check_interval_hours
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.logger = logging.getLogger(__name__)

    def start(self):
        """Start the renewal scheduler."""
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._scheduler_loop())
            self.logger.info(
                f"Renewal scheduler started with {self.check_interval_hours}h interval"
            )

    def stop(self):
        """Stop the renewal scheduler."""
        self.running = False
        if self.task:
            self.task.cancel()
            self.logger.info("Renewal scheduler stopped")

    async def _scheduler_loop(self):
        """Main scheduler loop that runs renewal checks."""
        while self.running:
            try:
                self.logger.info("Running automatic certificate renewal check...")

                # Run the renewal check
                renewal_results = (
                    await auto_renewal_service.check_and_renew_due_certificates()
                )

                # Log the results
                await self._log_renewal_results(renewal_results)

                # Wait for next check
                await asyncio.sleep(
                    self.check_interval_hours * 3600
                )  # Convert hours to seconds

            except asyncio.CancelledError:
                self.logger.info("Renewal scheduler cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in renewal scheduler: {e}")
                # Wait a bit before retrying to avoid rapid failure loops
                await asyncio.sleep(300)  # 5 minutes

    async def _log_renewal_results(self, renewal_results: list):
        """Log the renewal results to the database."""
        db = SessionLocal()
        try:
            if not renewal_results:
                self.logger.info("No certificates were due for renewal")
                crud_log.create_log(
                    db=db,
                    log=schemas.LogCreate(
                        level="INFO",
                        action="RenewalScheduler",
                        target="System",
                        message="Automatic renewal check completed - no certificates due for renewal",  # noqa: E501
                    ),
                )
            else:
                successful_renewals = [
                    r for r in renewal_results if r.get("success", False)
                ]
                failed_renewals = [
                    r for r in renewal_results if not r.get("success", False)
                ]

                summary_message = f"Automatic renewal check completed: {len(successful_renewals)} successful, {len(failed_renewals)} failed"  # noqa: E501
                self.logger.info(summary_message)

                crud_log.create_log(
                    db=db,
                    log=schemas.LogCreate(
                        level="INFO",
                        action="RenewalScheduler",
                        target="System",
                        message=summary_message,
                    ),
                )

                # Log details for each renewal
                for result in renewal_results:
                    cert_name = result.get("certificate_name", "Unknown")
                    deployment_id = result.get("deployment_id", "Unknown")

                    if result.get("success", False):
                        message = f"Certificate '{cert_name}' (deployment {deployment_id}) renewed and deployed successfully"  # noqa: E501
                        crud_log.create_log(
                            db=db,
                            log=schemas.LogCreate(
                                level="INFO",
                                action="AutoRenewal",
                                target="System",
                                message=message,
                            ),
                        )
                    else:
                        error = result.get("error", "Unknown error")
                        phase = result.get("phase", "Unknown phase")
                        message = f"Certificate '{cert_name}' (deployment {deployment_id}) renewal failed in {phase}: {error}"  # noqa: E501
                        crud_log.create_log(
                            db=db,
                            log=schemas.LogCreate(
                                level="ERROR",
                                action="AutoRenewal",
                                target="System",
                                message=message,
                            ),
                        )

            db.commit()
        except Exception as e:
            self.logger.error(f"Failed to log renewal results: {e}")
            db.rollback()
        finally:
            db.close()

    async def run_manual_check(self) -> list:
        """
        Run a manual renewal check (for testing or manual triggering).
        Returns the renewal results.
        """
        self.logger.info("Running manual certificate renewal check...")
        renewal_results = await auto_renewal_service.check_and_renew_due_certificates()
        await self._log_renewal_results(renewal_results)
        return renewal_results


# Global scheduler instance
renewal_scheduler = RenewalScheduler()
