import unittest
from services.realtime_windows import Mode, ClockGate, make_windows


class WindowTests(unittest.TestCase):
    def test_mean_and_boundaries(self):
        windows = make_windows([(0, {"NH4": 2}), (5, {"NH4": 4}), (300, {"NH4": 8})])
        self.assertEqual([w.inputs["NH4"] for w in windows], [3, 8])
        self.assertEqual(windows[0].end_ms, 300000)

    def test_gap_rejected(self):
        with self.assertRaises(ValueError):
            make_windows([(0, {"NH4": 2}), (600, {"NH4": 8})])

    def test_replay_never_sleeps(self):
        gate = ClockGate(Mode.REPLAY, clock=lambda: 0, sleeper=lambda _: self.fail_test())
        gate.await_window(100)

    def fail_test(self):
        raise AssertionError("Replay must not sleep")

    def test_live_waits(self):
        delays = []
        gate = ClockGate(Mode.LIVE, clock=lambda: 0, sleeper=delays.append)
        gate.await_window(0)
        self.assertEqual(delays, [300])


if __name__ == "__main__":
    unittest.main()


def test_negative_observations_are_zero_before_window_mean():
    window = make_windows([(0, {'DO': -2}), (10, {'DO': 4})])[0]
    assert window.inputs['DO'] == 2
