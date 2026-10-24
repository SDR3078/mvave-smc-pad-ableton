"""Offline behavior tests; real Live MidiNoteVector support needs hardware QA."""
import copy
import unittest
import stepseq_selftest as f


class NoteVector(list):
    pass


class ProbabilityClip(f.FakeClip):
    def get_notes_extended(self, *args):
        result = NoteVector()
        for original in super().get_notes_extended(*args):
            note = copy.copy(original)
            note.note_id = id(original)
            result.append(note)
        return result

    def apply_note_modifications(self, notes):
        assert isinstance(notes, NoteVector), 'original vector must be preserved'
        for note in notes:
            original = next(n for n in self.notes if id(n) == note.note_id)
            original.probability = note.probability
        self._fire('notes')


class ProbabilityTests(f.SeqTest):
    def setUp(self):
        super().setUp()
        self.clip = ProbabilityClip(loop_start=2.0, loop_end=6.0)
        self.song.view.select(self.clip)
        self.messages = []
        self.seq.show_message = self.messages.append

    def hold(self, index=0):
        self.seq._on_pad(index, True, 127)

    def release(self, index=0):
        self.seq._on_pad(index, False)

    def test_four_levels_and_clamps_preserve_note(self):
        self.press(0)
        note = self.clip.notes[0]
        original = (note.pitch, note.start_time, note.duration, note.velocity, note.mute)
        self.assertEqual(self.seq._grid[0], 64)
        self.hold()
        for chance, color in ((.75, 9), (.5, 21), (.25, 7), (.25, 7)):
            self.button(f.C.BTN_LEFT)
            self.assertEqual(note.probability, chance)
            self.assertEqual(self.seq._grid[0], color)
        for chance, color in ((.5, 21), (.75, 9), (1., 64), (1., 64)):
            self.button(f.C.BTN_RIGHT)
            self.assertEqual(note.probability, chance)
            self.assertEqual(self.seq._grid[0], color)
        self.release()
        self.assertIs(self.clip.notes[0], note)
        self.assertEqual(len(self.clip.notes), 1)
        self.assertEqual(original,
            (note.pitch, note.start_time, note.duration, note.velocity, note.mute))

    def test_multiple_held_steps_and_other_pitch_untouched(self):
        self.press(0)
        self.press(1)
        other = f.FakeNote(37, 2., .25, 73)
        self.clip.notes.append(other)
        self.hold(0)
        self.hold(1)
        self.button(f.C.BTN_LEFT)
        self.release(0)
        self.release(1)
        self.assertEqual([n.probability for n in self.clip.notes], [.75, .75, 1.])

    def test_empty_hold_consumed_without_navigation_or_note_creation(self):
        self.hold()
        self.button(f.C.BTN_LEFT)
        self.release()
        self.assertEqual(self.clip.notes, [])
        self.assertEqual(self.seq._bank, 0)
        self.assertIn('hold an active step', self.messages[-1])

    def test_mouse_edit_redraw_and_nonpreset_chance(self):
        self.press(0)
        note = self.clip.notes[0]
        note.probability = .6
        self.clip._fire('notes')
        self.assertEqual(self.seq._grid[0], 21)
        self.assertEqual(note.probability, .6)
        self.hold()
        self.button(f.C.BTN_LEFT)
        self.assertEqual(note.probability, .5)
        self.release()

    def test_failed_api_does_not_delete_note(self):
        self.press(0)
        def fail(notes):
            raise RuntimeError('API unavailable')
        self.clip.apply_note_modifications = fail
        self.hold()
        self.button(f.C.BTN_LEFT)
        self.release()
        self.assertEqual(len(self.clip.notes), 1)
        self.assertEqual(self.clip.notes[0].probability, 1.)
        self.assertIn('failed', self.messages[-1])
        self.expect_logged_exception = True

    def test_stacked_notes_display_highest_chance(self):
        for chance in (.25, .75):
            note = f.FakeNote(36, 2., .25, 80)
            note.probability = chance
            self.clip.notes.append(note)
        self.seq._render()
        self.assertEqual(self.seq._grid[0], 9)
        self.hold()
        self.button(f.C.BTN_LEFT)
        self.release()
        self.assertEqual([n.probability for n in self.clip.notes], [.25, .5])

    def test_requested_mapping(self):
        self.assertEqual(f.C.PROBABILITY_LEVELS, (.25, .5, .75, 1.))
        self.assertEqual(f.C.PROBABILITY_COLORS, (7, 21, 9, 64))

    def test_playhead_overlay_restores_probability_color(self):
        self.press(0)
        self.hold()
        self.button(f.C.BTN_LEFT)
        self.release()
        self.seq._playhead = 0
        self.seq._paint()
        self.assertEqual(self.seq._led[0], f.C.COLOR_PLAYHEAD_ON)
        self.seq._playhead = None
        self.seq._paint()
        self.assertEqual(self.seq._led[0], 9)


if __name__ == '__main__':
    unittest.main()
