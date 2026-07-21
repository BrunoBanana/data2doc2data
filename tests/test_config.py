from pathlib import Path
import tempfile
import unittest

from data2doc2data.config import Profile, ProfileError, ProfileStore


class ProfileStoreTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
