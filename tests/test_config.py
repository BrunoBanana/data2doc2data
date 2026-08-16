import json
from pathlib import Path
import tempfile
import unittest

from data2doc2data.config import Profile, ProfileError, ProfileStore


class ProfileStoreTests(unittest.TestCase):
    def test_old_demo_profile_defaults_to_the_primary_scenario(self):
        profile = Profile.from_dict({"mode": "demo", "data_path": "", "knowledge_path": ""})

        self.assertEqual(profile.demo_scenario, "growth-quality-alert")

    def test_demo_scenario_round_trip_is_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "config.json")
            profile = Profile.demo("strategy-data-conflict")

            store.save(profile)

            self.assertEqual(store.load(), profile)
            self.assertEqual(
                json.loads(store.path.read_text(encoding="utf-8"))["demo_scenario"],
                "strategy-data-conflict",
            )

    def test_demo_profile_rejects_unknown_or_path_like_scenario_ids(self):
        for scenario_id in ("missing", "../../private"):
            with self.subTest(scenario_id=scenario_id):
                with self.assertRaisesRegex(ProfileError, "scenario"):
                    Profile.demo(scenario_id)

    def test_save_then_load_preserves_local_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "config.json")
            profile = Profile(mode="local", data_path="/tmp/metrics.csv", knowledge_path="/tmp/notes")

            store.save(profile)

            self.assertEqual(store.load(), profile)

    def test_load_returns_none_before_a_profile_is_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "config.json")

            self.assertIsNone(store.load())

    def test_profile_rejects_non_text_source_paths(self):
        with self.assertRaisesRegex(ProfileError, "paths must be text"):
            Profile.from_dict({"mode": "local", "data_path": [], "knowledge_path": "/tmp/notes"})

    def test_local_profile_keeps_path_validation_independent_of_demo_selection(self):
        profile = Profile(
            mode="local",
            data_path="/tmp/metrics.csv",
            knowledge_path="/tmp/notes",
            demo_scenario="not-a-built-in-scenario",
        )

        self.assertEqual(profile.demo_scenario, "not-a-built-in-scenario")


if __name__ == "__main__":
    unittest.main()
