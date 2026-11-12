"""Chronicle M4 hardening: revision sources, slugs, and comment lookup indexes.

Revision ID: 0003_chronicle_m4
Revises: 0002_core_worldweave
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_chronicle_m4"
down_revision: Union[str, None] = "0002_core_worldweave"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_revisions",
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="manual",
        ),
    )

    # Deduplicate historical slugs before enforcing the uniqueness invariant.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY universe_id, slug
                           ORDER BY created_at ASC, id ASC
                       ) AS rn
                FROM documents
            )
            UPDATE documents
            SET slug = left(documents.slug, 185) || '-' || ranked.rn
            FROM ranked
            WHERE documents.id = ranked.id AND ranked.rn > 1
            """
        )
    )
    op.create_unique_constraint(
        "uq_documents_universe_slug", "documents", ["universe_id", "slug"]
    )
    op.create_unique_constraint(
        "uq_document_revisions_doc_num",
        "document_revisions",
        ["document_id", "revision_number"],
    )
    op.create_index(
        "ix_comments_universe_target_created",
        "comments",
        ["universe_id", "target_type", "target_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_comments_universe_target_created", table_name="comments"
    )
    op.drop_constraint(
        "uq_document_revisions_doc_num",
        "document_revisions",
        type_="unique",
    )
    op.drop_constraint(
        "uq_documents_universe_slug", "documents", type_="unique"
    )
    op.drop_column("document_revisions", "source")
