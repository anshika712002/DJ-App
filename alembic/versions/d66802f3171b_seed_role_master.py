"""seed role_master

Revision ID: d66802f3171b
Revises: e9c1e8a6176c
Create Date: 2026-10-07 23:37:29.868314

Reference data required by the authentication flow: /auth/signup and
/auth/login look the requested role up in role_master and fail with
"Invalid role specified" when the row does not exist.
Inserts are idempotent (ON CONFLICT DO NOTHING) so re-running is safe.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd66802f3171b'
down_revision: Union[str, Sequence[str], None] = 'e9c1e8a6176c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = (
    ("user", "Requests songs from the DJ"),
    ("dj", "Accepts, mixes and plays song requests"),
    ("admin", "Administrator with full access"),
)


def upgrade() -> None:
    role_master = sa.table(
        "role_master",
        sa.column("roleName", sa.String),
        sa.column("description", sa.Text),
        sa.column("isActive", sa.Boolean),
    )

    for role_name, description in ROLES:
        stmt = (
            sa.dialects.postgresql.insert(role_master)
            .values(roleName=role_name, description=description, isActive=True)
            .on_conflict_do_nothing(index_elements=["roleName"])
        )
        op.execute(stmt)


def downgrade() -> None:
    # Only remove roles that are not referenced by any user (keeps FK intact).
    for role_name, _ in ROLES:
        op.get_bind().execute(
            sa.text(
                'DELETE FROM role_master '
                'WHERE "roleName" = :role_name '
                'AND NOT EXISTS (SELECT 1 FROM users WHERE users."roleId" = role_master.id)'
            ),
            {"role_name": role_name},
        )
