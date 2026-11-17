import struct
import unittest

from kwce import home_sound
from kwce.home_sound_v3 import HomeSounds as HomeSoundsV3


class ConstantInstrument(HomeSoundsV3):
    """A constant PCM note makes the note-off envelope observable (home-ui v8 renderer)."""

    def __init__(self):
        self.d = bytearray(32)
        self.d[7] = 125

    def score(self, index):
        return 0, [(0, 0, 60, 1, 1, 0.01)], 0.01, 1

    def samples(self, bank, program):
        return [(10000, 10000)] * 32000, 32000, 0, False, 60, 127, 1

    def instrument(self, bank, program):
        return 0, 0, 0


class DvdHomeReleaseTest(unittest.TestCase):
    def test_note_release_continues_and_decays_after_note_off(self):
        pcm, record = ConstantInstrument().render(0)
        self.assertGreaterEqual(record['frames'], 2200)
        self.assertEqual(struct.unpack_from('>h', pcm, 300 * 4)[0], 10000)
        early = struct.unpack_from('>h', pcm, 500 * 4)[0]
        late = struct.unpack_from('>h', pcm, 1500 * 4)[0]
        self.assertGreater(early, late)
        self.assertGreater(late, 0)


class EnvelopeInstrument(home_sound.HomeSounds):
    """Instrument ADSR 127/127/127/125 (as HOME program 0); the score sets overrides."""

    def __init__(self, override, duration=0.083, seconds=3):
        self.d = bytearray(32)
        self.d[4:8] = bytes((127, 127, 127, 125))
        self.override, self.duration, self.seconds = override, duration, seconds

    def score(self, index):
        return 0, [(0, 0, 60, 1, 1, self.duration, self.override)], self.duration, 1

    def samples(self, bank, program):
        return [(10000, 10000)] * (32000 * self.seconds), 32000, 0, False, 60, 127, 1

    def instrument(self, bank, program):
        return 0, 0, 0


def level(pcm, seconds):
    return struct.unpack_from('>h', pcm, int(seconds * 32000) * 4)[0]


class Nw4rEnvelopeTest(unittest.TestCase):
    def test_sequence_release_override_keeps_the_tail(self):
        # CLOSE_CONTROLLER/CANCEL: 'release 105' before the note. 904 / (60/21/5) ms after note-off.
        pcm, record = EnvelopeInstrument((None, None, None, 105)).render(0)
        self.assertAlmostEqual(record['frames'] / 32000, 0.083 + 1.582, delta=0.01)
        self.assertEqual(level(pcm, 0.05), 10000)
        self.assertGreater(level(pcm, 0.4), level(pcm, 0.8))
        self.assertGreater(level(pcm, 0.8), level(pcm, 1.4))
        self.assertGreater(level(pcm, 1.4), 0)

    def test_instrument_release_without_override(self):
        pcm, record = EnvelopeInstrument((None, None, None, None)).render(0)
        self.assertAlmostEqual(record['frames'] / 32000, 0.083 + 0.0753, delta=0.004)

    def test_tail_reaches_silence_instead_of_a_cut(self):
        for release in (105, 123, 125):
            pcm, record = EnvelopeInstrument((None, None, None, release)).render(0)
            last = struct.unpack_from('>h', pcm, (record['frames'] - 1) * 4)[0]
            self.assertLessEqual(abs(last), 3, release)

    def test_attack_override_fades_in(self):
        pcm, _ = EnvelopeInstrument((120, None, None, 123)).render(0)
        self.assertEqual(level(pcm, 0), 0)
        self.assertLess(level(pcm, 0.003), 1000)
        self.assertGreater(level(pcm, 0.04), 9900)

    def test_unreviewed_envelope_values_are_refused(self):
        with self.assertRaises(ValueError):
            EnvelopeInstrument((100, None, None, None)).render(0)


if __name__ == '__main__':
    unittest.main()
