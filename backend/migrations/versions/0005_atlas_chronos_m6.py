"""Bring the pre-created Atlas and Chronos tables up to their M6 model shape.

Revision ID: 0005_atlas_chronos_m6
Revises: 0004_collaboration_m5
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_atlas_chronos_m6"
down_revision: Union[str, None] = "0004_collaboration_m5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The tables were introduced early, but these model columns and invariants
    # were absent from the original migration. Keep the repair additive.
    op.add_column(
        "map_markers",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "map_regions",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    op.add_column(
        "calendars",
        sa.Column("created_by", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "calendars",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute(
        sa.text(
            """
            UPDATE calendars AS calendar
            SET created_by = universe.owner_user_id
            FROM universes AS universe
            WHERE calendar.universe_id = universe.id
              AND calendar.created_by IS NULL
            """
        )
    )
    op.alter_column("calendars", "created_by", nullable=False)
    op.create_foreign_key(
        "fk_calendars_created_by",
        "calendars",
        "users",
        ["created_by"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.add_column(
        "eras",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    op.add_column(
        "timeline_events",
        sa.Column(
            "start_day_index",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "timeline_events",
        sa.Column("end_day_index", sa.Integer(), nullable=True),
    )
    op.add_column(
        "timeline_events",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_timeline_events_calendar_start",
        "timeline_events",
        ["calendar_id", "start_day_index"],
    )

    # Complete the asset relationship after both tables exist.
    op.create_foreign_key(
        "fk_maps_image_asset",
        "maps",
        "assets",
        ["image_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_map_markers_x_norm_range",
        "map_markers",
        "x_norm >= 0 AND x_norm <= 1",
    )
    op.create_check_constraint(
        "ck_map_markers_y_norm_range",
        "map_markers",
        "y_norm >= 0 AND y_norm <= 1",
    )
    op.create_check_constraint(
        "ck_timeline_events_day_range",
        "timeline_events",
        "end_day_index IS NULL OR end_day_index >= start_day_index",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_timeline_events_day_range", "timeline_events", type_="check"
    )
    op.drop_constraint(
        "ck_map_markers_y_norm_range", "map_markers", type_="check"
    )
    op.drop_constraint(
        "ck_map_markers_x_norm_range", "map_markers", type_="check"
    )
    op.drop_constraint("fk_maps_image_asset", "maps", type_="foreignkey")
    op.drop_index(
        "ix_timeline_events_calendar_start", table_name="timeline_events"
    )
    op.drop_column("timeline_events", "version")
    op.drop_column("timeline_events", "end_day_index")
    op.drop_column("timeline_events", "start_day_index")
    op.drop_column("eras", "version")
    op.drop_constraint(
        "fk_calendars_created_by", "calendars", type_="foreignkey"
    )
    op.drop_column("calendars", "version")
    op.drop_column("calendars", "created_by")
    op.drop_column("map_regions", "version")
    op.drop_column("map_markers", "version")
