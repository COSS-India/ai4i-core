from sqlalchemy import BigInteger, Column, Date, DateTime, Index, Integer, String, Text, func, text

from app.models import Base


class UsageReportSendLog(Base):
    """One row per (period, Usage Viewer): the scheduled report's delivery
    record — period, recipient, timestamp and status — and its retry state.

    status: SENT | FAILED (attempts counts tries, one per run) | NOT_READY
    (a period-level row, recipient_user_id NULL, written when the report's
    figures could not be collected; one per run that found it not ready).

    recipient_user_id is the auth DB users.id, not the email: emails are
    encrypted at rest there and are not copied out in plain text.
    """

    __tablename__ = "usage_report_send_log"
    __table_args__ = (
        # One delivery row per recipient per period; NOT_READY rows (no
        # recipient) are a run history and aren't unique.
        Index(
            "uq_usage_report_send_log_period_recipient",
            "frequency", "period_start", "period_end", "recipient_user_id",
            unique=True,
            postgresql_where=text("recipient_user_id IS NOT NULL"),
        ),
        Index("ix_usage_report_send_log_period_end", "period_end"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    frequency = Column(String(16), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    recipient_user_id = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False)
    attempts = Column(Integer, nullable=False, server_default="0")
    last_error = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
