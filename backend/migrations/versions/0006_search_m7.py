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
    #
    # The concatenation must use immutable constructs only: ``concat_ws`` is
    # STABLE, so PostgreSQL rejects it inside an index expression. The
    # ``||``/``coalesce`` form below matches the query in
    # ``backend/modules/search/service.py`` exactly so the planner can use
    # these GIN indexes.
    op.execute(
        """
        CREATE INDEX ix_entities_search_fts ON entities USING gin (
            to_tsvector('simple',
                coalesce(title, '') || ' ' ||
                coalesce(summary, '') || ' ' ||
                coalesce(CAST(custom_fields AS TEXT), '')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_documents_search_fts ON documents USING gin (
            to_tsvector('simple',
                coalesce(title, '') || ' ' ||
                coalesce(slug, '') || ' ' ||
                coalesce(CAST(content_json AS TEXT), '')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_timeline_events_search_fts ON timeline_events USING gin (
            to_tsvector('simple',
                coalesce(title, '') || ' ' ||
                coalesce(description, '')
            )
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_timeline_events_search_fts", table_name="timeline_events")
    op.drop_index("ix_documents_search_fts", table_name="documents")
    op.drop_index("ix_entities_search_fts", table_name="entities")
