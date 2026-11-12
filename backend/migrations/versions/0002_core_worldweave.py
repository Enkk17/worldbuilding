"""Create core WORLDWEAVE tables for Universes, Society, Codex, Chronicle, Atlas, and Chronos.

Revision ID: 0002_core_worldweave
Revises: 0001_identity
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_core_worldweave"
down_revision: Union[str, None] = "0001_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Universes & Society
    op.create_table(
        "universes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("cover_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("settings_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("slug", name="uq_universes_slug"),
    )
    op.create_index("ix_universes_status_updated_at", "universes", ["status", "updated_at"])
    op.create_index("ix_universes_owner_user_id", "universes", ["owner_user_id"])

    op.create_table(
        "universe_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="viewer"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("universe_id", "user_id", name="uq_universe_members_universe_user"),
    )
    op.create_index("ix_universe_members_user_id", "universe_members", ["user_id"])
    op.create_index("ix_universe_members_universe_id", "universe_members", ["universe_id"])
    op.create_index("ix_universe_members_role", "universe_members", ["role"])

    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="viewer"),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
    )
    op.create_index("ix_invitations_universe_email", "invitations", ["universe_id", "email"])
    op.create_index("ix_invitations_expires_at", "invitations", ["expires_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before_hash", sa.String(length=64), nullable=True),
        sa.Column("after_hash", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_audit_logs_universe_created", "audit_logs", ["universe_id", "created_at"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    op.create_table(
        "activity_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_activity_events_universe_created", "activity_events", ["universe_id", "created_at"])

    # 2. Codex
    op.create_table(
        "entity_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("schema_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("universe_id", "key", name="uq_entity_types_universe_key"),
    )
    op.create_index("ix_entity_types_universe_id", "entity_types", ["universe_id"])

    op.create_table(
        "relation_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("inverse_label", sa.String(length=80), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("allowed_source_types", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("allowed_target_types", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_directional", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_symmetric", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("universe_id", "key", name="uq_relation_types_universe_key"),
    )
    op.create_index("ix_relation_types_universe_id", "relation_types", ["universe_id"])

    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entity_types.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.String(length=1000), nullable=True),
        sa.Column("body_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("custom_fields", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="universe"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("universe_id", "entity_type_id", "slug", name="uq_entities_universe_type_slug"),
    )
    op.create_index("ix_entities_universe_status", "entities", ["universe_id", "status"])
    op.create_index("ix_entities_universe_updated", "entities", ["universe_id", "updated_at"])
    op.create_index("ix_entities_type_id", "entities", ["entity_type_id"])

    op.create_table(
        "entity_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("relation_types.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attributes_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_entity_relations_universe_source", "entity_relations", ["universe_id", "source_entity_id"])
    op.create_index("ix_entity_relations_universe_target", "entity_relations", ["universe_id", "target_entity_id"])
    op.create_index("ix_entity_relations_relation_type", "entity_relations", ["relation_type_id"])

    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("universe_id", "slug", name="uq_tags_universe_slug"),
    )
    op.create_index("ix_tags_universe_id", "tags", ["universe_id"])

    op.create_table(
        "entity_tags",
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    # 3. Chronicle
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=True),
        sa.Column("document_type", sa.String(length=32), nullable=False, server_default="chapter"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="universe"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_documents_universe_parent", "documents", ["universe_id", "parent_id"])
    op.create_index("ix_documents_universe_updated", "documents", ["universe_id", "updated_at"])

    op.create_table(
        "document_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("markdown_snapshot", sa.Text(), nullable=True),
        sa.Column("change_summary", sa.String(length=500), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_document_revisions_doc_num", "document_revisions", ["document_id", "revision_number"])

    op.create_table(
        "document_entity_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("anchor_json", sa.JSON(), nullable=True),
        sa.Column("link_kind", sa.String(length=32), nullable=False, server_default="mention"),
    )
    op.create_index("ix_doc_entity_links_doc", "document_entity_links", ["document_id"])
    op.create_index("ix_doc_entity_links_entity", "document_entity_links", ["entity_id"])

    op.create_table(
        "comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_comment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("comments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("body", sa.String(length=5000), nullable=False),
        sa.Column("anchor_json", sa.JSON(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_comments_universe_target", "comments", ["universe_id", "target_type", "target_id"])

    # 4. Realtime Collab
    op.create_table(
        "document_collab_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ydoc_state", sa.LargeBinary(), nullable=False),
        sa.Column("state_vector", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_doc_collab_snapshots_doc", "document_collab_snapshots", ["document_id", "created_at"])

    op.create_table(
        "document_collab_updates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("update_blob", sa.LargeBinary(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_doc_collab_updates_doc", "document_collab_updates", ["document_id", "created_at"])

    # 5. Atlas
    op.create_table(
        "maps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("image_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("coordinate_system", sa.String(length=32), nullable=False, server_default="normalized"),
        sa.Column("width", sa.Integer(), nullable=False, server_default=sa.text("1920")),
        sa.Column("height", sa.Integer(), nullable=False, server_default=sa.text("1080")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_maps_universe_id", "maps", ["universe_id"])

    op.create_table(
        "map_markers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("map_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("x_norm", sa.Float(), nullable=False),
        sa.Column("y_norm", sa.Float(), nullable=False),
        sa.Column("marker_type", sa.String(length=64), nullable=False, server_default="poi"),
        sa.Column("linked_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("style_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_map_markers_map_id", "map_markers", ["map_id"])
    op.create_index("ix_map_markers_universe_id", "map_markers", ["universe_id"])

    op.create_table(
        "map_regions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("map_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("geometry_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("linked_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("style_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_map_regions_map_id", "map_regions", ["map_id"])
    op.create_index("ix_map_regions_universe_id", "map_regions", ["universe_id"])

    # 6. Chronos
    op.create_table(
        "calendars",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_calendars_universe_id", "calendars", ["universe_id"])

    op.create_table(
        "eras",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("calendar_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("calendars.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("start_day_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("description", sa.String(length=1000), nullable=True),
    )
    op.create_index("ix_eras_calendar_id", "eras", ["calendar_id"])

    op.create_table(
        "timeline_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("calendar_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("calendars.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=5000), nullable=True),
        sa.Column("start_date_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("end_date_json", sa.JSON(), nullable=True),
        sa.Column("date_precision", sa.String(length=32), nullable=False, server_default="day"),
        sa.Column("uncertainty_json", sa.JSON(), nullable=True),
        sa.Column("linked_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_timeline_events_universe_calendar", "timeline_events", ["universe_id", "calendar_id"])

    # 7. Assets
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_assets_universe_id", "assets", ["universe_id"])


def downgrade() -> None:
    for tbl in [
        "assets",
        "timeline_events",
        "eras",
        "calendars",
        "map_regions",
        "map_markers",
        "maps",
        "document_collab_updates",
        "document_collab_snapshots",
        "comments",
        "document_entity_links",
        "document_revisions",
        "documents",
        "entity_tags",
        "tags",
        "entity_relations",
        "entities",
        "relation_types",
        "entity_types",
        "activity_events",
        "audit_logs",
        "invitations",
        "universe_members",
        "universes",
    ]:
        op.drop_table(tbl)
