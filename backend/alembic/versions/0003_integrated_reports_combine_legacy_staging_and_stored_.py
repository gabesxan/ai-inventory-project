"""Combine legacy staging and stored replenishment

Revision ID: 0003_integrated_reports
Revises: 0002_legacy_staging, 0002_replenishment_runs
Create Date: 2026-11-24 12:43:08.273152
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003_integrated_reports'
down_revision: Union[str, None] = ('0002_legacy_staging', '0002_replenishment_runs')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
