"""Prototype checks; envelope semantics still require verification in Live."""
import unittest
import stepseq_selftest as fixture
from MVave_SMC_STEPSEQ.ParameterLocks import ParameterLocks


class Parameter:
    min, max, value, is_quantized, name = 0, 127, 64, False, 'Transpose'
    def re_enable_automation(self):
        self.enabled = True


class Envelope:
    def __init__(self):
        self.writes = []
    def insert_step(self, time, duration, value):
        self.writes.append((time, duration, value))
    def value_at_time(self, time):
        for start, duration, value in reversed(self.writes):
            if start <= time < start + duration:
                return value
        return 64


class Clip:
    loop_start, loop_end, is_arrangement_clip = 0, 4, False
    envelope = None
    def automation_envelope(self, parameter):
        return self.envelope
    def create_automation_envelope(self, parameter):
        self.envelope = Envelope()
        return self.envelope


class EnvelopeTests(unittest.TestCase):
    def test_locked_step_and_neighbours(self):
        clip, parameter, locks = Clip(), Parameter(), ParameterLocks()
        locks.adjust(clip, parameter, [3], 12, .25)
        self.assertEqual(clip.envelope.value_at_time(.75), 76)
        self.assertEqual(clip.envelope.value_at_time(.5), 64)
        self.assertEqual(clip.envelope.value_at_time(1), 64)
        locks.adjust(clip, parameter, [4], -8, .25)
        self.assertEqual(clip.envelope.value_at_time(.75), 76)
        self.assertEqual(clip.envelope.value_at_time(1), 56)
        self.assertTrue(locks.adjust_base(clip, parameter, 2, .25))
        self.assertEqual(clip.envelope.value_at_time(.5), 66)
        self.assertEqual(clip.envelope.value_at_time(.75), 76)
        self.assertEqual(clip.envelope.value_at_time(1), 56)
        for n in range(16):
            expected = 76 if n == 3 else 56 if n == 4 else 66
            self.assertEqual(clip.envelope.value_at_time(n * .25), expected)
        self.assertEqual(len(clip.envelope.writes[-4:]), 4)
        self.assertAlmostEqual(sum(duration for _, duration, _ in clip.envelope.writes[-4:]), 4)

    def test_existing_envelope_not_reset(self):
        clip, parameter, locks = Clip(), Parameter(), ParameterLocks()
        clip.envelope = Envelope()
        clip.envelope.insert_step(0, 4, 42)
        locks.adjust(clip, parameter, [15], 200, .25)
        self.assertEqual(clip.envelope.value_at_time(0), 42)
        self.assertEqual(clip.envelope.value_at_time(3.75), 127)
        self.assertTrue(locks.adjust_base(clip, parameter, 1, .25))
        self.assertEqual(clip.envelope.value_at_time(0), 43)
        self.assertEqual(clip.envelope.value_at_time(3.75), 127)

    def test_arrangement_refused(self):
        clip = Clip()
        clip.is_arrangement_clip = True
        with self.assertRaises(RuntimeError):
            ParameterLocks().adjust(clip, Parameter(), [0], 1, .25)


class GestureTests(fixture.SeqTest):
    def setUp(self):
        super().setUp()
        self.seq.show_message = lambda message: None
        self.queue = []
        self.seq.schedule_message = lambda ticks, callback: self.queue.append(callback)
        self.clip.automation_envelope = lambda parameter: self.clip.envelope
        self.clip.envelope = None
        def create(parameter):
            self.clip.envelope = Envelope()
            return self.clip.envelope
        self.clip.create_automation_envelope = create

    def test_hold_turn_keeps_note(self):
        self.press(0)
        self.seq._on_pad(0, True, 127)
        self.assertTrue(self.seq.handle_macro_lock(Parameter(), 10))
        self.seq._on_pad(0, False)
        self.assertEqual(len(self.clip.notes), 1)
        self.assertEqual(self.clip.envelope.value_at_time(0), 74)

    def test_duplicate_press_preserves_lock_and_note(self):
        self.press(0)
        self.seq._on_pad(0, True, 127)
        parameter = Parameter()
        self.seq.handle_macro_lock(parameter, 10)
        self.seq._on_pad(0, True, 127)
        self.seq._on_pad(0, False)
        self.assertEqual(len(self.clip.notes), 1)

    def test_live_base_changes_preserve_lock_after_deferred_flush(self):
        self.press(0)
        parameter = Parameter()
        self.seq._on_pad(0, True, 127)
        self.seq.handle_macro_lock(parameter, 10)
        self.seq._on_pad(0, False)
        self.seq._lock_release_time = -1
        self.song.is_playing = True
        self.assertTrue(self.seq.handle_macro_lock(parameter, 20))
        self.assertEqual(self.clip.envelope.value_at_time(.25), 64)
        self.assertEqual(self.clip.envelope.value_at_time(0), 74)
        before = len(self.clip.envelope.writes)
        self.queue.pop(0)()
        self.assertEqual(self.clip.envelope.value_at_time(.25), 84)
        self.assertEqual(self.clip.envelope.value_at_time(0), 74)
        self.assertEqual(len(self.clip.envelope.writes) - before, 2)

    def test_many_knob_messages_coalesce_into_one_flush(self):
        self.press(0)
        parameter = Parameter()
        self.seq._on_pad(0, True, 127)
        self.seq.handle_macro_lock(parameter, 10)
        self.seq._on_pad(0, False)
        self.seq._lock_release_time = -1
        before = len(self.clip.envelope.writes)
        for _ in range(20):
            self.seq.handle_macro_lock(parameter, 1)
        self.assertEqual(len(self.queue), 1)
        self.assertEqual(len(self.clip.envelope.writes), before)
        self.queue.pop(0)()
        self.assertEqual(self.clip.envelope.value_at_time(.25), 84)
        self.assertEqual(self.clip.envelope.value_at_time(0), 74)

    def test_base_recovers_existing_locks_after_restart(self):
        parameter = Parameter()
        self.clip.envelope = Envelope()
        self.clip.envelope.insert_step(0, 4, 60)
        self.clip.envelope.insert_step(1, .25, 90)
        self.seq.handle_macro_lock(parameter, 2)
        self.queue.pop(0)()
        self.assertEqual(self.clip.envelope.value_at_time(0), 62)
        self.assertEqual(self.clip.envelope.value_at_time(1), 90)
        self.assertEqual(self.clip.envelope.value_at_time(1.25), 62)

    def test_release_tail_is_not_a_base_edit(self):
        self.press(0)
        parameter = Parameter()
        self.seq._on_pad(0, True, 127)
        self.seq.handle_macro_lock(parameter, 10)
        self.seq._on_pad(0, False)
        self.assertTrue(self.seq.handle_macro_lock(parameter, 20))
        self.assertEqual(self.clip.envelope.value_at_time(.25), 64)

    def test_hold_across_clip_change_cannot_edit_new_clip(self):
        self.seq._on_pad(0, True, 127)
        other = fixture.FakeClip()
        self.song.view.select(other)
        self.seq._on_pad(0, False)
        self.assertEqual(other.notes, [])

    def test_empty_lock_does_not_add_note(self):
        self.seq._on_pad(0, True, 127)
        self.assertTrue(self.seq.handle_macro_lock(Parameter(), 10))
        self.seq._on_pad(0, False)
        self.assertEqual(self.clip.notes, [])


if __name__ == '__main__':
    unittest.main()
