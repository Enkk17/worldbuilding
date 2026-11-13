"""Add PostgreSQL full-text search GIN indexes for M7.

Revision ID: 0006_search_m7
Revises: 0005_atlas_chronos_m6
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006_search_m7"
down_revision: Union[str, None] = "0005_atlas_chronos_m6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Expression indexes keep PostgreSQL authoritative while SQLite test
    # databases continue to use the ILIKE fallback without FTS extensions.
    op.execute(
        """
        CREATE INDEX ix_entities_search_fts ON entities USING gin (
            to_tsvector('simple', concat_ws(' ',
                coalesce(title, ''),
                coalesce(summary, ''),
                coalesce(custom_fields::text, '')
            ))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_documents_search_fts ON documents USING gin (
            to_tsvector('simple', concat_ws(' ',
                coalesce(title, ''),
                coalesce(slug, ''),
                coalesce(content_json::text, '')
            ))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_timeline_events_search_fts ON timeline_events USING gin (
            to_tsvector('simple', concat_ws(' ',
                coalesce(title, ''),
                coalesce(description, '')
            ))
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_timeline_events_search_fts", table_name="timeline_events")
    op.drop_index("ix_documents_search_fts", table_name="documents")
    op.drop_index("ix_entities_search_fts", table_name="entities")
