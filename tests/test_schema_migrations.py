import json
import tempfile
import unittest
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from database import setup_db


class SchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self._temp_dir.name) / "schema.db"
        self.engine = sa.create_engine(f"sqlite:///{db_path}")
        self.session_factory = sessionmaker(bind=self.engine)

        self._original_engine = setup_db.engine
        self._original_session_factory = setup_db.SessionLocal

        setup_db.engine = self.engine
        setup_db.SessionLocal = self.session_factory

    def tearDown(self):
        setup_db.engine = self._original_engine
        setup_db.SessionLocal = self._original_session_factory
        self.engine.dispose()
        self._temp_dir.cleanup()

    def test_ensure_school_schema_backfills_scouting_defaults(self):
        with self.engine.begin() as conn:
            conn.execute(sa.text("CREATE TABLE schools (id INTEGER PRIMARY KEY, name TEXT)"))
            conn.execute(sa.text("INSERT INTO schools (id, name) VALUES (1, 'Test High')"))

        setup_db.ensure_school_schema()

        inspector = sa.inspect(self.engine)
        column_names = {col['name'] for col in inspector.get_columns('schools')}
        self.assertTrue({"scouting_network", "current_era", "era_momentum"}.issubset(column_names))

        with self.engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT scouting_network, current_era, era_momentum FROM schools WHERE id = 1")
            ).one()

        network_blob, era_label, era_momentum = row
        network = json.loads(network_blob)
        self.assertEqual(network.get("Local"), 50)
        self.assertEqual(era_label, "REBUILDING")
        self.assertEqual(era_momentum, 0)

    def test_ensure_coach_schema_backfills_archetype_defaults(self):
        with self.engine.begin() as conn:
            conn.execute(sa.text("CREATE TABLE coaches (id INTEGER PRIMARY KEY, name TEXT)"))
            conn.execute(sa.text("INSERT INTO coaches (id, name) VALUES (1, 'Legendary Coach')"))

        setup_db.ensure_coach_schema()

        inspector = sa.inspect(self.engine)
        column_names = {col['name'] for col in inspector.get_columns('coaches')}
        self.assertTrue(
            {"drive", "loyalty", "volatility", "archetype", "scouting_ability"}.issubset(column_names)
        )

        with self.engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT drive, loyalty, volatility, archetype, scouting_ability FROM coaches WHERE id = 1"
                )
            ).one()

        drive, loyalty, volatility, archetype, scouting_ability = row
        self.assertEqual(drive, 50)
        self.assertEqual(loyalty, 50)
        self.assertEqual(volatility, 50)
        self.assertEqual(archetype, "TRADITIONALIST")
        self.assertEqual(scouting_ability, 50)


if __name__ == "__main__":
    unittest.main()
