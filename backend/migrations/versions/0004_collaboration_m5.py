"""Realtime collaboration M5: ordered Yjs updates and verified snapshots.

Revision ID: 0004_collaboration_m5
Revises: 0003_chronicle_m4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_collaboration_m5"
down_revision: Union[str, None] = "0003_chronicle_m4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "collab_generation",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # A collaboration snapshot is always universe-scoped. The redundant
    # universe_id makes cross-tenant integrity checks cheap and explicit.
    op.add_column(
        "document_collab_snapshots",
        sa.Column("universe_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE document_collab_snapshots AS snapshot
            SET universe_id = document.universe_id
            FROM documents AS document
            WHERE document.id = snapshot.document_id
            """
        )
    )
    op.alter_column(
        "document_collab_snapshots", "universe_id", nullable=False
    )
    op.create_foreign_key(
        "fk_doc_collab_snapshots_universe",
        "document_collab_snapshots",
        "universes",
        ["universe_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column(
        "document_collab_snapshots",
        "state_vector",
        existing_type=sa.LargeBinary(),
        nullable=False,
    )
    op.add_column(
        "document_collab_snapshots",
        sa.Column(
            "last_update_sequence",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "document_collab_snapshots",
        sa.Column(
            "update_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "document_collab_snapshots",
        sa.Column(
            "reason",
            sa.String(length=32),
            nullable=False,
            server_default="compaction",
        ),
    )
    op.add_column(
        "document_collab_snapshots",
        sa.Column("created_by", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_doc_collab_snapshots_created_by",
        "document_collab_snapshots",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_doc_collab_snapshots_universe",
        "document_collab_snapshots",
        ["universe_id", "created_at"],
    )

    op.add_column(
        "document_collab_updates",
        sa.Column("universe_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "document_collab_updates",
        sa.Column("sequence", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_collab_updates",
        sa.Column("actor_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "document_collab_updates",
        sa.Column(
            "byte_size", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE document_collab_updates AS update
            SET universe_id = document.universe_id
            FROM documents AS document
            WHERE document.id = update.document_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY document_id
                           ORDER BY created_at ASC, id ASC
                       ) AS rn
                FROM document_collab_updates
            )
            UPDATE document_collab_updates
            SET sequence = ranked.rn
            FROM ranked
            WHERE document_collab_updates.id = ranked.id
            """
        )
    )
    op.alter_column(
        "document_collab_updates", "universe_id", nullable=False
    )
    op.alter_column("document_collab_updates", "sequence", nullable=False)
    op.create_foreign_key(
        "fk_doc_collab_updates_universe",
        "document_collab_updates",
        "universes",
        ["universe_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_doc_collab_updates_actor",
        "document_collab_updates",
        "users",
        ["actor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_doc_collab_updates_doc_sequence",
        "document_collab_updates",
        ["document_id", "sequence"],
    )
    op.create_index(
        "ix_doc_collab_updates_universe",
        "document_collab_updates",
        ["universe_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_doc_collab_updates_universe",
        table_name="document_collab_updates",
    )
    op.drop_constraint(
        "uq_doc_collab_updates_doc_sequence",
        "document_collab_updates",
        type_="unique",
    )
    op.drop_constraint(
        "fk_doc_collab_updates_actor",
        "document_collab_updates",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_doc_collab_updates_universe",
        "document_collab_updates",
        type_="foreignkey",
    )
    op.drop_column("document_collab_updates", "byte_size")
    op.drop_column("document_collab_updates", "actor_id")
    op.drop_column("document_collab_updates", "sequence")
    op.drop_column("document_collab_updates", "universe_id")

    op.drop_index(
        "ix_doc_collab_snapshots_universe",
        table_name="document_collab_snapshots",
    )
    op.drop_constraint(
        "fk_doc_collab_snapshots_created_by",
        "document_collab_snapshots",
        type_="foreignkey",
    )
    op.drop_column("document_collab_snapshots", "created_by")
    op.drop_column("document_collab_snapshots", "reason")
    op.drop_column("document_collab_snapshots", "update_count")
    op.drop_column("document_collab_snapshots", "last_update_sequence")
    op.alter_column(
        "document_collab_snapshots",
        "state_vector",
        existing_type=sa.LargeBinary(),
        nullable=True,
    )
    op.drop_constraint(
        "fk_doc_collab_snapshots_universe",
        "document_collab_snapshots",
        type_="foreignkey",
    )
    op.drop_column("document_collab_snapshots", "universe_id")

    op.drop_column("documents", "collab_generation")
