"""Outbound email delivery seam.

No provider account exists yet (Resend/Postmark are the candidates); this
module is the single place a provider client gets wired in. Until then dev
logs the code, and a deployed environment logs that delivery is unconfigured
without the code itself, so sign-in codes never land in Cloud Logging.
"""

import logging

from app.api import sessions

logger = logging.getLogger(__name__)


async def send_sign_in_code(email: str, code: str) -> None:
    if sessions.dev_mode():
        logger.warning("Sign-in code for %s: %s", email, code)
        return
    # No address in the log line: Cloud Logging is project-wide readable.
    logger.error("No email provider configured; a sign-in code was not sent")
