import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.run_performance import _pipeline


class PerformanceContractTests(unittest.TestCase):
    def test_benchmark_pipeline_is_deterministic_and_candidates_are_bounded(self):
        first = _pipeline(8)
        second = _pipeline(8)
        self.assertEqual(first[2], second[2])
        self.assertEqual(first[1]["candidate_count"], 8)
        self.assertLessEqual(first[1]["candidate_count"], 8 * 5)
        self.assertGreater(first[3], 0)


if __name__ == "__main__":
    unittest.main()
