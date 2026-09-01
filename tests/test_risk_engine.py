import unittest

from pi_ot_probe.analysis.risk_engine import RiskEngine
from pi_ot_probe.simulation.scanner import build_snapshot


class RiskEngineTests(unittest.TestCase):
    def test_ot_finding_is_contextual_and_does_not_claim_vulnerability(self) -> None:
        hmi = next(asset for asset in build_snapshot("changed").assets if asset.device_type == "HMI")
        finding = RiskEngine().evaluate(hmi)[0]
        self.assertGreaterEqual(finding.risk_score, 65)
        self.assertIn("not proof of a vulnerability", finding.human_explanation)
        self.assertEqual(finding.confidence, 0.96)
        self.assertIn("502", finding.technical_reason)


if __name__ == "__main__":
    unittest.main()

