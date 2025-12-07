"""initial_baseline_v1

Revision ID: a362b9a5b089
Revises: e48e53e228fa
Create Date: 2025-12-07 14:47:50.966741

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a362b9a5b089'
down_revision = 'e48e53e228fa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('geolocations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('prefecture', sa.String(), nullable=True),
        sa.Column('city_name', sa.String(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('population', sa.Integer(), nullable=True),
        sa.Column('tier', sa.String(), nullable=True),
        sa.Column('school_count', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('schools',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('prefecture', sa.String(), nullable=True),
        sa.Column('city_name', sa.String(), nullable=True),
        sa.Column('geo_location_id', sa.Integer(), nullable=True),
        sa.Column('prestige', sa.Integer(), nullable=True),
        sa.Column('budget', sa.Integer(), nullable=True),
        sa.Column('scouting_network', sa.Text(), nullable=True),
        sa.Column('current_era', sa.String(), nullable=True),
        sa.Column('era_momentum', sa.Integer(), nullable=True),
        sa.Column('philosophy', sa.String(), nullable=True),
        sa.Column('focus', sa.String(), nullable=True),
        sa.Column('seniority_weight', sa.Float(), nullable=True),
        sa.Column('trust_weight', sa.Float(), nullable=True),
        sa.Column('stats_weight', sa.Float(), nullable=True),
        sa.Column('injury_tolerance', sa.Float(), nullable=True),
        sa.Column('training_style', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['geo_location_id'], ['geolocations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('coaches',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('school_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('tradition', sa.Float(), nullable=True),
        sa.Column('logic', sa.Float(), nullable=True),
        sa.Column('temper', sa.Float(), nullable=True),
        sa.Column('ambition', sa.Float(), nullable=True),
        sa.Column('seniority_weight', sa.Float(), nullable=True),
        sa.Column('trust_weight', sa.Float(), nullable=True),
        sa.Column('stats_weight', sa.Float(), nullable=True),
        sa.Column('fatigue_penalty_weight', sa.Float(), nullable=True),
        sa.Column('drive', sa.Integer(), nullable=True),
        sa.Column('loyalty', sa.Integer(), nullable=True),
        sa.Column('volatility', sa.Integer(), nullable=True),
        sa.Column('archetype', sa.String(), nullable=True),
        sa.Column('scouting_ability', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('players',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('school_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('first_name', sa.String(), nullable=True),
        sa.Column('last_name', sa.String(), nullable=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('position', sa.String(), nullable=True),
        sa.Column('jersey_number', sa.Integer(), nullable=True),
        sa.Column('is_captain', sa.Boolean(), nullable=True),
        sa.Column('is_starter', sa.Boolean(), nullable=True),
        sa.Column('role', sa.String(), nullable=True),
        sa.Column('overall', sa.Integer(), nullable=True),
        sa.Column('potential_grade', sa.String(), nullable=True),
        sa.Column('growth_tag', sa.String(), nullable=True),
        sa.Column('theme_song', sa.String(), nullable=True),
        sa.Column('pitcher_personality', sa.String(), nullable=True),
        sa.Column('catcher_leadership', sa.Integer(), nullable=True),
        sa.Column('catcher_ability', sa.Integer(), nullable=True),
        sa.Column('battery_xp', sa.Integer(), nullable=True),
        sa.Column('trust_baseline', sa.Integer(), nullable=True),
        sa.Column('mental', sa.Integer(), nullable=True),
        sa.Column('discipline', sa.Integer(), nullable=True),
        sa.Column('clutch', sa.Integer(), nullable=True),
        sa.Column('academic_skill', sa.Integer(), nullable=True),
        sa.Column('test_score', sa.Integer(), nullable=True),
        sa.Column('drive', sa.Integer(), nullable=True),
        sa.Column('loyalty', sa.Integer(), nullable=True),
        sa.Column('volatility', sa.Integer(), nullable=True),
        sa.Column('determination', sa.Integer(), nullable=True),
        sa.Column('morale', sa.Integer(), nullable=True),
        sa.Column('slump_timer', sa.Integer(), nullable=True),
        sa.Column('archetype', sa.String(), nullable=True),
        sa.Column('height_cm', sa.Integer(), nullable=True),
        sa.Column('height_potential', sa.Integer(), nullable=True),
        sa.Column('weight_kg', sa.Integer(), nullable=True),
        sa.Column('is_two_way', sa.Boolean(), nullable=True),
        sa.Column('secondary_position', sa.String(), nullable=True),
        sa.Column('stamina', sa.Integer(), nullable=True),
        sa.Column('velocity', sa.Integer(), nullable=True),
        sa.Column('control', sa.Integer(), nullable=True),
        sa.Column('command', sa.Integer(), nullable=True),
        sa.Column('movement', sa.Integer(), nullable=True),
        sa.Column('arm_slot', sa.String(), nullable=True),
        sa.Column('fielding', sa.Integer(), nullable=True),
        sa.Column('speed', sa.Integer(), nullable=True),
        sa.Column('contact', sa.Integer(), nullable=True),
        sa.Column('power', sa.Integer(), nullable=True),
        sa.Column('throwing', sa.Integer(), nullable=True),
        sa.Column('fatigue', sa.Integer(), nullable=True),
        sa.Column('injury_status', sa.String(), nullable=True),
        sa.Column('injury_days', sa.Integer(), nullable=True),
        sa.Column('conditioning', sa.Integer(), nullable=True),
        sa.Column('ability_points', sa.Integer(), nullable=True),
        sa.Column('training_xp', sa.Text(), nullable=True),
        sa.Column('mechanics_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('player_skills',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('skill_key', sa.String(), nullable=False),
        sa.Column('acquired_date', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_player_skills_player_id', 'player_skills', ['player_id'], unique=False)

    op.create_table('player_milestones',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('milestone_key', sa.String(), nullable=False),
        sa.Column('milestone_label', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('skill_key', sa.String(), nullable=True),
        sa.Column('season_year', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_player_milestone_key', 'player_milestones', ['milestone_key'], unique=False)
    op.create_index('ix_player_milestone_player_id', 'player_milestones', ['player_id'], unique=False)

    op.create_table('battery_trust',
        sa.Column('pitcher_id', sa.Integer(), nullable=False),
        sa.Column('catcher_id', sa.Integer(), nullable=False),
        sa.Column('trust', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['catcher_id'], ['players.id'], ),
        sa.ForeignKeyConstraint(['pitcher_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('pitcher_id', 'catcher_id')
    )

    op.create_table('roster',
        sa.Column('school_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.String(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('school_id', 'position')
    )

    op.create_table('games',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('home_school_id', sa.Integer(), nullable=True),
        sa.Column('away_school_id', sa.Integer(), nullable=True),
        sa.Column('home_score', sa.Integer(), nullable=True),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('date', sa.String(), nullable=True),
        sa.Column('round', sa.String(), nullable=True),
        sa.Column('season_year', sa.Integer(), nullable=True),
        sa.Column('tournament', sa.String(), nullable=True),
        sa.Column('is_completed', sa.Boolean(), nullable=True),
        sa.Column('weather_label', sa.String(), nullable=True),
        sa.Column('weather_condition', sa.String(), nullable=True),
        sa.Column('weather_precip', sa.String(), nullable=True),
        sa.Column('weather_temperature_f', sa.Integer(), nullable=True),
        sa.Column('weather_wind_speed', sa.Float(), nullable=True),
        sa.Column('weather_wind_direction', sa.String(), nullable=True),
        sa.Column('weather_summary', sa.Text(), nullable=True),
        sa.Column('umpire_name', sa.String(), nullable=True),
        sa.Column('umpire_description', sa.Text(), nullable=True),
        sa.Column('umpire_zone_bias', sa.Float(), nullable=True),
        sa.Column('umpire_home_bias', sa.Float(), nullable=True),
        sa.Column('umpire_temperament', sa.Float(), nullable=True),
        sa.Column('umpire_favored_home', sa.Integer(), nullable=True),
        sa.Column('umpire_squeezed_home', sa.Integer(), nullable=True),
        sa.Column('umpire_favored_away', sa.Integer(), nullable=True),
        sa.Column('umpire_squeezed_away', sa.Integer(), nullable=True),
        sa.Column('error_summary', sa.Text(), nullable=True),
        sa.Column('rivalry_summary', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['away_school_id'], ['schools.id'], ),
        sa.ForeignKeyConstraint(['home_school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('player_game_stats',
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('innings_pitched', sa.Float(), nullable=True),
        sa.Column('pitches_thrown', sa.Integer(), nullable=True),
        sa.Column('hits', sa.Integer(), nullable=True),
        sa.Column('runs', sa.Integer(), nullable=True),
        sa.Column('strikeouts', sa.Integer(), nullable=True),
        sa.Column('walks', sa.Integer(), nullable=True),
        sa.Column('at_bats', sa.Integer(), nullable=True),
        sa.Column('hits_batted', sa.Integer(), nullable=True),
        sa.Column('rbi', sa.Integer(), nullable=True),
        sa.Column('homeruns', sa.Integer(), nullable=True),
        sa.Column('fielding_errors', sa.Integer(), nullable=True),
        sa.Column('strikeouts_pitched', sa.Integer(), nullable=True),
        sa.Column('runs_allowed', sa.Integer(), nullable=True),
        sa.Column('confidence', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('game_id', 'player_id')
    )

    op.create_table('scouting_data',
        sa.Column('school_id', sa.Integer(), nullable=False),
        sa.Column('knowledge_level', sa.Integer(), nullable=True),
        sa.Column('rivalry_score', sa.Integer(), nullable=True),
        sa.Column('last_scouted_week', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('school_id')
    )

    op.create_table('player_relationships',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('captain_id', sa.Integer(), nullable=True),
        sa.Column('battery_partner_id', sa.Integer(), nullable=True),
        sa.Column('rival_id', sa.Integer(), nullable=True),
        sa.Column('captain_rel', sa.Integer(), nullable=True),
        sa.Column('battery_rel', sa.Integer(), nullable=True),
        sa.Column('rivalry_score', sa.Integer(), nullable=True),
        sa.Column('last_captain_event_week', sa.Integer(), nullable=True),
        sa.Column('last_rival_event_week', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['battery_partner_id'], ['players.id'], ),
        sa.ForeignKeyConstraint(['captain_id'], ['players.id'], ),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.ForeignKeyConstraint(['rival_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('player_id')
    )

    op.create_table('coach_strategy_mods',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('school_id', sa.Integer(), nullable=True),
        sa.Column('effect_type', sa.String(), nullable=True),
        sa.Column('games_remaining', sa.Integer(), nullable=True),
        sa.Column('target_player_id', sa.Integer(), nullable=True),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.ForeignKeyConstraint(['target_player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('pitch_repertoire',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('pitch_name', sa.String(), nullable=True),
        sa.Column('quality', sa.Integer(), nullable=True),
        sa.Column('break_level', sa.Integer(), nullable=True),
        sa.Column('mastery_xp', sa.Integer(), nullable=True),
        sa.Column('mastery_level', sa.Integer(), nullable=True),
        sa.Column('signature_tag', sa.String(), nullable=True),
        sa.Column('signature_ready', sa.Boolean(), nullable=True),
        sa.Column('signature_unlocked', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('gamestate',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('current_day', sa.String(), nullable=True),
        sa.Column('current_week', sa.Integer(), nullable=True),
        sa.Column('current_month', sa.Integer(), nullable=True),
        sa.Column('current_year', sa.Integer(), nullable=True),
        sa.Column('active_player_id', sa.Integer(), nullable=True),
        sa.Column('last_error_summary', sa.Text(), nullable=True),
        sa.Column('last_coach_order_result', sa.Text(), nullable=True),
        sa.Column('last_telemetry_blob', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('gamestate')
    op.drop_table('pitch_repertoire')
    op.drop_table('coach_strategy_mods')
    op.drop_table('player_relationships')
    op.drop_table('scouting_data')
    op.drop_table('player_game_stats')
    op.drop_table('games')
    op.drop_table('roster')
    op.drop_table('battery_trust')
    op.drop_index('ix_player_milestone_player_id', table_name='player_milestones')
    op.drop_index('ix_player_milestone_key', table_name='player_milestones')
    op.drop_table('player_milestones')
    op.drop_index('ix_player_skills_player_id', table_name='player_skills')
    op.drop_table('player_skills')
    op.drop_table('players')
    op.drop_table('coaches')
    op.drop_table('schools')
    op.drop_table('geolocations')
