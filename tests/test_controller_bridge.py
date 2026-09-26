import unittest
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bridge"))

import controller_bridge


class ControllerBridgeLinuxTests(unittest.TestCase):
    def test_linux_gamepad_state_initialization(self):
        state = controller_bridge.LinuxGamepadState()
        self.assertEqual(state.wButtons, 0)
        self.assertEqual(state.sThumbLX, 0)
        self.assertEqual(state.sThumbLY, 0)
        self.assertEqual(state.bLeftTrigger, 0)
        self.assertEqual(state.bRightTrigger, 0)

    def test_quit_chord_mask(self):
        mask = controller_bridge.quit_chord_mask(["select", "start"])
        expected = controller_bridge.XINPUT_GAMEPAD_BACK | controller_bridge.XINPUT_GAMEPAD_START
        self.assertEqual(mask, expected)

    def test_get_gamepad_state_returns_none_or_pad_for_unused_slots(self):
        # Slot 99 should never exist
        state = controller_bridge.get_gamepad_state(99)
        self.assertIsNone(state)


if __name__ == "__main__":
    unittest.main()
