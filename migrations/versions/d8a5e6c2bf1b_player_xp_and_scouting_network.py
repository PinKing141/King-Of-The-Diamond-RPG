"""player xp and scouting network tables

Revision ID: d8a5e6c2bf1b
Revises: a362b9a5b089
Create Date: 2025-12-08 00:00:00.000000
"""
from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d8a5e6c2bf1b"
down_revision = "a362b9a5b089"
branch_labels = None
depends_on = None


player_xp = sa.table(
    "player_xp",
    sa.column("id", sa.Integer),
    sa.column("player_id", sa.Integer),
    sa.column("stat_key", sa.String),
    sa.column("xp", sa.Float),
)

players = sa.table(
    "players",
    sa.column("id", sa.Integer),
    sa.column("training_xp", sa.Text),
)

scouting_network = sa.table(
    "scouting_network",
    sa.column("id", sa.Integer),
    sa.column("school_id", sa.Integer),
    sa.column("scope", sa.String),
    sa.column("rating", sa.Integer),
)

schools = sa.table(
    "schools",
    sa.column("id", sa.Integer),
    sa.column("scouting_network", sa.Text),
)


_DEFAULT_RATING = 50


def _decode_json(payload: Any) -> dict:
    if not payload:
        return {}
    if isinstance(payload, dict):
        return payload
    try:
        return json.loads(payload)
    except Exception:
        return {}


def upgrade() -> None:
    op.create_table(
        "player_xp",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("stat_key", sa.String(), nullable=False),
        sa.Column("xp", sa.Float(), server_default="0"),
    )
    op.create_index("ix_player_xp_player_id", "player_xp", ["player_id"], unique=False)
    op.create_unique_constraint("uq_player_xp_player_stat", "player_xp", ["player_id", "stat_key"])

    op.create_table(
        "scouting_network",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("rating", sa.Integer(), server_default=str(_DEFAULT_RATING)),
    )
    op.create_index("ix_scouting_network_school_id", "scouting_network", ["school_id"], unique=False)
    op.create_unique_constraint("uq_scouting_network_scope", "scouting_network", ["school_id", "scope"])

    bind = op.get_bind()

    # Migrate existing training_xp blobs into player_xp rows.
    for row in bind.execute(sa.select(players.c.id, players.c.training_xp)):
        payload = _decode_json(row.training_xp)
        for stat_key, value in payload.items():
            try:
                xp_value = float(value or 0)
            except (TypeError, ValueError):
                continue
            bind.execute(
                player_xp.insert().values(
                    player_id=row.id,
                    stat_key=str(stat_key),
                    xp=xp_value,
                )
            )

    # Migrate existing scouting network blobs into table rows.
    for row in bind.execute(sa.select(schools.c.id, schools.c.scouting_network)):
        payload = _decode_json(row.scouting_network)
        for scope, rating in payload.items():
            try:
                rating_int = int(rating)
            except (TypeError, ValueError):
                rating_int = _DEFAULT_RATING
            bind.execute(
                scouting_network.insert().values(
                    school_id=row.id,
                    scope=str(scope),
                    rating=rating_int,
                )
            )


def downgrade() -> None:
    op.drop_constraint("uq_scouting_network_scope", "scouting_network", type_="unique")
    op.drop_index("ix_scouting_network_school_id", table_name="scouting_network")
    op.drop_table("scouting_network")

    op.drop_constraint("uq_player_xp_player_stat", "player_xp", type_="unique")
    op.drop_index("ix_player_xp_player_id", table_name="player_xp")
    op.drop_table("player_xp")
