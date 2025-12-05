"""Utility CLI for high-volume balance and skill simulations.

This runner aggregates several QA workflows:
- Ghost games: fast exhibitions to populate stats without commentary.
- Seasonal training loops: repeatedly calls AI progression helpers and emits
  skill distribution summaries so we can tune rarity targets.
- Clutch-vs-Control batting study (scaffolding in place for future work).
"""
from __future__ import annotations

import argparse
import logging
import random
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

# Ensure project root is importable when running as script.
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from database.setup_db import (
    School,
    Player,
    PlayerSkill,
    get_session,
    session_scope,
)
from database.populate_japan import populate_world
from game.ai_player_logic import run_ai_skill_progression
from game.skill_system import (
    grant_skill_by_key,
    remove_skill_by_key,
    list_player_skill_keys,
    sync_player_skills,
)
from game.trait_catalog import SKILL_DEFINITIONS
from match_engine import match_sim
from sqlalchemy import func


@dataclass
class SkillSnapshot:
    player_count: int
    sample_size: int
    avg: float
    median: float
    max_skills: int
    distribution: Counter[int]

    def summarize(self) -> str:
        lines = [
            f"Players tallied: {self.sample_size}",
            f"Active players (>=1 skill): {self.player_count}",
            f"Average skills/player: {self.avg:.2f}",
            f"Median skills/player: {self.median:.2f}",
            f"Most-loaded player: {self.max_skills}",
        ]
        top_bins = ", ".join(
            f"{count}x{bin_value}" for bin_value, count in self.distribution.most_common(10)
        )
        if top_bins:
            lines.append(f"Distribution sample: {top_bins}")
        return "\n".join(lines)


class SimulationRunner:
    def __init__(self, seed: int | None = None):
        self.random = random.Random(seed)

    @staticmethod
    def _skill_label(key: str) -> str:
        data = SKILL_DEFINITIONS.get(key.lower()) or {}
        return data.get("name", key)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def ensure_world(self) -> None:
        with session_scope() as session:
            if session.query(School).count() > 1:
                return
        print("World data missing. Populating base schools and rosters...")
        populate_world()
        print("World generation complete.")

    def _random_school_pair(self, session) -> Tuple[School, School]:
        schools: List[School] = session.query(School).all()
        if len(schools) < 2:
            raise RuntimeError("Not enough schools to simulate matches.")
        home, away = self.random.sample(schools, 2)
        return home, away

    # ------------------------------------------------------------------
    # Ghost game simulation
    # ------------------------------------------------------------------
    def run_ghost_games(self, games: int, silent: bool = True) -> None:
        self.ensure_world()
        results: Counter[str] = Counter()
        for idx in range(1, games + 1):
            with session_scope() as session:
                home, away = self._random_school_pair(session)
            winner, score = match_sim.resolve_match(
                home,
                away,
                tournament_name="Ghost Game",
                mode="fast",
            )
            key = getattr(winner, "name", "Draw") if winner else "Draw"
            results[key] += 1
            if idx % 25 == 0:
                print(f"Simulated {idx}/{games} ghost games...")
        print("Ghost-game batch complete. Win table:")
        for name, count in results.most_common():
            print(f" - {name}: {count}")

    # ------------------------------------------------------------------
    # Training season loops
    # ------------------------------------------------------------------
    def simulate_training_seasons(
        self,
        seasons: int,
        cycles_per_season: int = 4,
        school_sample: int | None = None,
    ) -> None:
        self.ensure_world()

        sample_ids: List[int] | None = None
        if school_sample:
            with session_scope() as session:
                all_ids = [row.id for row in session.query(School.id).all()]
            if not all_ids:
                raise RuntimeError("No schools available for sampling.")
            sample_ids = self.random.sample(all_ids, min(school_sample, len(all_ids)))
            print(f"Restricting progression runs to {len(sample_ids)} sampled schools.")

        for season_idx in range(seasons):
            label = f"season-{season_idx + 1}"
            for cycle_idx in range(cycles_per_season):
                cycle_label = f"{label}-cycle-{cycle_idx + 1}"
                with session_scope() as session:
                    unlocks = run_ai_skill_progression(
                        session,
                        cycle_label=cycle_label,
                        prestige_floor=0,
                        school_ids=sample_ids,
                    )
                    session.commit()
                print(
                    f"[{label}] Cycle {cycle_idx + 1}/{cycles_per_season}: "
                    f"Granted {len(unlocks)} skills",
                )
            snapshot = self.collect_skill_snapshot()
            print(f"Skill snapshot after {label}:\n{snapshot.summarize()}\n")

    def collect_skill_snapshot(self) -> SkillSnapshot:
        with session_scope() as session:
            players: List[Player] = session.query(Player).all()
            counts = defaultdict(int)
            skill_counts: Iterable[Tuple[int, int]] = (
                session.query(PlayerSkill.player_id, func.count(PlayerSkill.id))
                .filter(PlayerSkill.is_active.is_(True))
                .group_by(PlayerSkill.player_id)
                .all()
            )
            for player_id, num in skill_counts:
                counts[player_id] = int(num)

        values = [counts.get(player.id, 0) for player in players]
        active_players = sum(1 for value in values if value > 0)
        max_skills = max(values) if values else 0
        avg = statistics.mean(values) if values else 0.0
        median = statistics.median(values) if values else 0.0
        distribution = Counter(values)
        return SkillSnapshot(
            player_count=active_players,
            sample_size=len(values),
            avg=avg,
            median=median,
            max_skills=max_skills,
            distribution=distribution,
        )

    # ------------------------------------------------------------------
    # Clutch vs Control scaffolding
    # ------------------------------------------------------------------
    def run_clutch_vs_control_study(self, at_bats: int) -> None:
        print(
            "Clutch vs Control study scaffolding is not implemented yet. "
            "Use this entry point for future batting micro-sims."
        )
        print(
            "Suggested next steps: instantiate a minimal MatchState, "
            "toggle Clutch Hitter on batters, and log batting averages."
        )

    # ------------------------------------------------------------------
    # Admin helpers
    # ------------------------------------------------------------------
    def manage_player_skills(
        self,
        player_id: int,
        *,
        grant: Optional[List[str]] = None,
        remove: Optional[List[str]] = None,
        list_only: bool = False,
        dry_run: bool = False,
    ) -> None:
        grant = grant or []
        remove = remove or []
        with session_scope() as session:
            player = session.get(Player, player_id)
            if not player:
                print(f"Player {player_id} not found.")
                return

            print(f"Managing skills for {player.name} (ID {player.id})")

            def _print_loadout() -> None:
                keys = list_player_skill_keys(player)
                if not keys:
                    print("  No active skills.")
                    return
                for key in keys:
                    print(f"  - {self._skill_label(key)} [{key}]")

            if list_only or (not grant and not remove):
                _print_loadout()

            changed = False

            for key in grant:
                canonical = key.lower()
                label = self._skill_label(canonical)
                if dry_run:
                    print(f"[dry-run] Would grant {label}")
                    continue
                result = grant_skill_by_key(session, player, canonical)
                if result:
                    print(f"Granted {result}")
                    changed = True
                else:
                    print(f"Skipped {label}: already owned or invalid requirements")

            for key in remove:
                canonical = key.lower()
                label = self._skill_label(canonical)
                if dry_run:
                    print(f"[dry-run] Would remove {label}")
                    continue
                if remove_skill_by_key(session, player, canonical):
                    print(f"Removed {label}")
                    changed = True
                else:
                    print(f"No entry found for {label}")

            if changed and not dry_run:
                session.commit()
                print("Updated skill ledger:")
                _print_loadout()

    def run_skill_sync(
        self,
        *,
        dry_run: bool = False,
        prune_unknown: bool = True,
        fix_duplicates: bool = True,
    ) -> None:
        with session_scope() as session:
            stats = sync_player_skills(
                session,
                prune_unknown=prune_unknown,
                fix_duplicates=fix_duplicates,
                dry_run=dry_run,
            )
            if not dry_run:
                session.commit()

        print(
            "Skill sync complete"
            if not dry_run
            else "Skill sync dry-run report"
        )
        print(
            f" Players scanned: {stats['players_scanned']}\n"
            f" Unknown entries pruned: {stats['unknown_entries_pruned']}\n"
            f" Duplicate entries pruned: {stats['duplicate_entries_pruned']}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Balance simulation harness")
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed")
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level for diagnostics (e.g. INFO, DEBUG)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    ghost = subparsers.add_parser("ghost-games", help="Run fast exhibition matches")
    ghost.add_argument("--games", type=int, default=100, help="Number of games to simulate")

    seasons = subparsers.add_parser("seasons", help="Run multi-season skill loops")
    seasons.add_argument("--count", type=int, default=1, help="Number of seasons to simulate")
    seasons.add_argument(
        "--cycles",
        type=int,
        default=4,
        help="Training cycles per season (calls to run_ai_skill_progression)",
    )
    seasons.add_argument(
        "--sample-schools",
        type=int,
        default=0,
        help="If >0, randomly sample this many schools for each run to speed up simulations",
    )

    clutch = subparsers.add_parser(
        "clutch-study",
        help="Placeholder for 1,000 at-bat Clutch vs Control experiments",
    )
    clutch.add_argument("--at-bats", type=int, default=1000)

    admin = subparsers.add_parser("skill-admin", help="Inspect or modify a player's skills")
    admin.add_argument("--player-id", type=int, required=True, help="Target player id")
    admin.add_argument("--list", action="store_true", help="Only list current skills")
    admin.add_argument("--grant", nargs="*", default=[], help="Skill keys to grant")
    admin.add_argument("--remove", nargs="*", default=[], help="Skill keys to remove")
    admin.add_argument("--dry-run", action="store_true", help="Preview changes without committing")

    sync = subparsers.add_parser("skill-sync", help="Reconcile player skill rows with catalog")
    sync.add_argument("--dry-run", action="store_true", help="Report actions without mutating data")
    sync.add_argument(
        "--keep-unknown",
        action="store_true",
        help="Skip pruning unknown skill keys",
    )
    sync.add_argument(
        "--skip-duplicates",
        action="store_true",
        help="Ignore duplicate clean-up",
    )

    return parser


def main(argv: List[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    log_level = getattr(logging, str(args.log_level).upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    runner = SimulationRunner(seed=args.seed)

    if args.command == "ghost-games":
        runner.run_ghost_games(args.games)
    elif args.command == "seasons":
        runner.simulate_training_seasons(
            args.count,
            cycles_per_season=args.cycles,
            school_sample=args.sample_schools or None,
        )
    elif args.command == "clutch-study":
        runner.run_clutch_vs_control_study(args.at_bats)
    elif args.command == "skill-admin":
        runner.manage_player_skills(
            args.player_id,
            grant=args.grant,
            remove=args.remove,
            list_only=args.list,
            dry_run=args.dry_run,
        )
    elif args.command == "skill-sync":
        runner.run_skill_sync(
            dry_run=args.dry_run,
            prune_unknown=not args.keep_unknown,
            fix_duplicates=not args.skip_duplicates,
        )
    else:  # pragma: no cover
        parser.error("Unknown command")


if __name__ == "__main__":
    main()
