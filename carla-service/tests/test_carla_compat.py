import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from carla_compat import validate_versions


class CompatibilityTest(unittest.TestCase):
    def test_both_research_releases(self):
        for version in ('0.9.15', '0.9.16'):
            validate_versions(version, version)

    def test_mixed_versions_rejected_including_legacy(self):
        for research in (True, False):
            with self.assertRaisesRegex(RuntimeError, 'version mismatch'):
                validate_versions('0.9.15', '0.9.16', research)

    def test_unreviewed_versions_not_silently_enabled(self):
        for version in ('0.9.14', '0.10.0', '0.9.16-custom'):
            with self.assertRaisesRegex(RuntimeError, 'require matching'):
                validate_versions(version, version)
        validate_versions('0.9.14', '0.9.14', research=False)
