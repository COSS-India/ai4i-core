"""usage_report_send_log — NOT created in this release (AI4IDS-3278).

Next release (retry + send log): the scheduled report's per-recipient
delivery record. To re-enable: uncomment the model below, re-register it in
app/models/__init__.py, and add a migration with the DDL kept at the end of
this file under a NEW revision id (d3f5a7c9e1b4 is taken upstream by a merge
migration), revising the ai4iplatform_core head at that time.
"""

# from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, Text, func, text
#
# from app.models import Base
#
#
# class UsageReportSendLog(Base):
#     """One row per (period, Usage Viewer): the scheduled report's delivery
#     record — period, recipient, timestamp and status — and its retry state.
#
#     status: SENT | FAILED (attempts counts tries, one per run) | NOT_READY
#     (a period-level row, recipient_user_id NULL, written when the report's
#     figures could not be collected; one per run that found it not ready).
#
#     recipient_user_id is the auth DB users.id, not the email: emails are
#     encrypted at rest there and are not copied out in plain text.
#     """
#
#     __tablename__ = "usage_report_send_log"
#     __table_args__ = (
#         # One delivery row per recipient per period; NOT_READY rows (no
#         # recipient) are a run history and aren't unique.
#         Index(
#             "uq_usage_report_send_log_period_recipient",
#             "frequency", "period_start", "period_end", "recipient_user_id",
#             unique=True,
#             postgresql_where=text("recipient_user_id IS NOT NULL"),
#         ),
#         Index("ix_usage_report_send_log_period_end", "period_end"),
#     )
#
#     id = Column(BigInteger, primary_key=True, autoincrement=True)
#     frequency = Column(String(16), nullable=False)
#     # [period_start, period_end): UTC instants, so sub-day test frequencies fit too.
#     period_start = Column(DateTime(timezone=True), nullable=False)
#     period_end = Column(DateTime(timezone=True), nullable=False)
#     recipient_user_id = Column(String(64), nullable=True)
#     status = Column(String(16), nullable=False)
#     attempts = Column(Integer, nullable=False, server_default="0")
#     last_error = Column(Text, nullable=True)
#     sent_at = Column(DateTime(timezone=True), nullable=True)
#     created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
#
#
# ── migration DDL (upgrade / downgrade) ─────────────────────────────────────
#
# from alembic import op
# import sqlalchemy as sa
#
# TABLE = "usage_report_send_log"
#
#
# def upgrade() -> None:
#     op.create_table(
#         TABLE,
#         sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
#         sa.Column("frequency", sa.String(length=16), nullable=False),
#         sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
#         sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
#         sa.Column("recipient_user_id", sa.String(length=64), nullable=True),
#         sa.Column("status", sa.String(length=16), nullable=False),
#         sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
#         sa.Column("last_error", sa.Text(), nullable=True),
#         sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
#         sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
#         sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
#     )
#     op.create_index(
#         "uq_usage_report_send_log_period_recipient",
#         TABLE,
#         ["frequency", "period_start", "period_end", "recipient_user_id"],
#         unique=True,
#         postgresql_where=sa.text("recipient_user_id IS NOT NULL"),
#     )
#     op.create_index("ix_usage_report_send_log_period_end", TABLE, ["period_end"])
#
#
# def downgrade() -> None:
#     op.drop_index("ix_usage_report_send_log_period_end", table_name=TABLE)
#     op.drop_index("uq_usage_report_send_log_period_recipient", table_name=TABLE)
#     op.drop_table(TABLE)
