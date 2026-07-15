import sys
from pathlib import Path
import unittest


CLIENT_SRC = Path(__file__).resolve().parents[1] / "client_src"
sys.path.insert(0, str(CLIENT_SRC))

from checks import DEFAULT_PROFILE, _grade, merged_profile
from models import CheckReport, CheckResult


class ModelAndRuleTests(unittest.TestCase):
    def test_network_threshold_edges(self):
        self.assertEqual(_grade(1.0, 1.0, 3.0), "PASS")
        self.assertEqual(_grade(1.1, 1.0, 3.0), "WARNING")
        self.assertEqual(_grade(3.1, 1.0, 3.0), "FAIL")

    def test_remote_profile_only_overrides_known_fields(self):
        profile = merged_profile({"packet_loss_fail": 4, "unknown": 10})
        self.assertEqual(profile["packet_loss_fail"], 4)
        self.assertNotIn("unknown", profile)
        self.assertEqual(profile["upload_multiplier"], DEFAULT_PROFILE["upload_multiplier"])

    def test_report_result_precedence(self):
        report = CheckReport("客户", "直播间", "DEVICE-1", "2.0.0", [
            CheckResult("a", "网络", "PASS", "A"),
            CheckResult("b", "设备", "WARNING", "B"),
        ])
        report.finalize()
        self.assertEqual(report.overall_status, "WARNING")
        report.results.append(CheckResult("c", "设备", "FAIL", "C"))
        report.finalize()
        self.assertEqual(report.overall_status, "FAIL")


if __name__ == "__main__":
    unittest.main()

