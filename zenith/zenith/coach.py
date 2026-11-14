"""
Zenith Coach: Curriculum & Scenario Director
Manages diverse skill drills, state resets, and adaptive difficulty.
"""
from __future__ import annotations

import numpy as np


class Coach:
    """
    Directs scenarios across arenas in ZenithArenaPool:
      Scenario 0: Standard Soccar Kickoff (40%)
      Scenario 1: High Aerial Boomer / Prejump Defense (15%)
      Scenario 2: Fake Challenge / Low Cut Anti-Overcommit (15%)
      Scenario 3: Shadow Defense & Retreat Rotation (15%)
      Scenario 4: Arsenal Flip Reset Musty Attack Drill (15%)
    """

    SCENARIOS = {
        0: "Standard Kickoff",
        1: "High Aerial Boomer (Prejump)",
        2: "Fake Challenge (Low Cut)",
        3: "Shadow Defense (Retreat)",
        4: "Flip Reset Musty Flick"
    }

    def __init__(
        self,
        num_arenas: int,
        distribution: dict[int, float] | None = None
    ):
        self.num_arenas = num_arenas
        if distribution is None:
            self.distribution = {
                0: 0.40,
                1: 0.15,
                2: 0.15,
                3: 0.15,
                4: 0.15
            }
        else:
            self.distribution = distribution

        self.scenario_ids = list(self.distribution.keys())
        self.scenario_probs = np.array([self.distribution[sid] for sid in self.scenario_ids], dtype=np.float32)
        self.scenario_probs /= self.scenario_probs.sum()

        # Track scenario per arena
        self.arena_scenarios = np.zeros(num_arenas, dtype=np.int32)
        # Stats per scenario: [attempts, successes]
        self.scenario_stats = {sid: {"episodes": 0, "goals_for": 0, "goals_against": 0, "saves": 0, "mustys": 0} for sid in self.scenario_ids}

    def initialize_pool(self, pool):
        """
        Initializes arenas across scenarios according to target curriculum distribution.
        """
        counts = np.round(self.scenario_probs * self.num_arenas).astype(int)
        counts[-1] = self.num_arenas - counts[:-1].sum()  # ensure exact sum

        arena_idx = 0
        for sid, cnt in zip(self.scenario_ids, counts):
            for _ in range(cnt):
                if arena_idx < self.num_arenas:
                    self.arena_scenarios[arena_idx] = sid
                    pool.set_scenario(arena_idx, sid)
                    arena_idx += 1

    def handle_terminals(self, pool, terminals: np.ndarray, goals_blue: int, goals_orange: int):
        """
        When arenas terminate (goal or timeout), reassign scenario according to probabilities.
        terminals has shape (num_arenas * 2,) where even indices are Blue and odd are Orange.
        """
        for arena_idx in range(self.num_arenas):
            p0_term = terminals[arena_idx * 2]
            if p0_term:
                cur_scen = int(self.arena_scenarios[arena_idx])
                self.scenario_stats[cur_scen]["episodes"] += 1

                # Sample next scenario
                next_scen = int(np.random.choice(self.scenario_ids, p=self.scenario_probs))
                self.arena_scenarios[arena_idx] = next_scen
                pool.set_scenario(arena_idx, next_scen)

    def record_mechanic_event(self, scenario_id: int, event_type: str):
        if scenario_id in self.scenario_stats and event_type in self.scenario_stats[scenario_id]:
            self.scenario_stats[scenario_id][event_type] += 1

    def get_curriculum_summary(self) -> dict[str, dict[str, float]]:
        summary = {}
        for sid, name in self.SCENARIOS.items():
            st = self.scenario_stats[sid]
            ep = max(1, st["episodes"])
            summary[name] = {
                "episodes": st["episodes"],
                "goal_diff": st["goals_for"] - st["goals_against"],
                "saves_per_ep": st["saves"] / ep,
                "mustys_per_ep": st["mustys"] / ep
            }
        return summary
