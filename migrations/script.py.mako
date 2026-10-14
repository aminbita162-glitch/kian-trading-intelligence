"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""

from __future__ import annotations

from typing import Any

try:
    from alembic import op  # type: ignore[import-not-found]
    import sqlalchemy as sa  # type: ignore[import-not-found]
except ImportError:
    op = None  # type: ignore[assignment]
    sa = None  # type: ignore[assignment]

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | None = ${repr(branch_labels)}
depends_on: str | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
