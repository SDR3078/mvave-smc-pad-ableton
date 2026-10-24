import unittest
from types import SimpleNamespace as Obj
import stepseq_selftest as f


class DrumActivity(f.SeqTest):
    def setUp(self):
        super().setUp()
        self.seq.show_message = lambda message: None
        self.drum_pads = [Obj(note=p, mute=False, chains=[Obj(devices=[])])
                          for p in (36, 37, 38, 52)]
        self.rack = Obj(can_have_drum_pads=True, drum_pads=self.drum_pads,
                        view=Obj(selected_drum_pad=None))
        self.song.view.selected_track.devices = [self.rack]
        self.clip.notes = [f.FakeNote(36, 0., .25, 100),
                           f.FakeNote(36, .25, .25, 100),
                           f.FakeNote(37, .25, .25, 100),
                           f.FakeNote(52, .25, .25, 100)]
        self.clip.is_playing = True

    def position(self, beats):
        self.clip.playing_position = beats
        self.seq._on_playhead()

    def test_selection_pulses_then_restores_selected_and_unprogrammed(self):
        self.button(f.C.BTN_MOD)
        self.assertEqual(self.seq._led[12], f.C.COLOR_DRUM_ACTIVITY)
        self.assertEqual(self.seq._led[13], 5)
        self.assertEqual(self.seq._led[14], 5)
        self.position(.15)
        self.assertEqual(self.seq._led[12], 40)
        self.position(.25)
        self.assertEqual(self.seq._led[12], f.C.COLOR_DRUM_ACTIVITY)
        self.assertEqual(self.seq._led[13], f.C.COLOR_DRUM_ACTIVITY)
        self.assertEqual(self.seq._led[14], 5)
        self.position(.40)
        self.assertEqual(self.seq._led[12], 40)
        self.assertEqual(self.seq._led[13], 5)

    def test_muted_drum_shows_programming_then_restores_red(self):
        self.drum_pads[0].mute = True
        self.button(f.C.BTN_VIEW)
        self.assertEqual(self.seq._led[12], f.C.COLOR_DRUM_ACTIVITY)
        self.position(.15)
        self.assertEqual(self.seq._led[12], 14)
        self.assertTrue(self.drum_pads[0].mute)

    def test_skipped_probability_is_still_pattern_activity_disabled_note_is_not(self):
        self.clip.notes[0].probability = 0.
        self.clip.notes[2].mute = True
        self.button(f.C.BTN_VIEW)
        self.assertEqual(self.seq._led[12], f.C.COLOR_DRUM_ACTIVITY)
        self.position(.25)
        self.assertEqual(self.seq._led[13], 5)

    def test_stop_and_release_clear_overlay_without_changing_notes(self):
        before = [vars(n).copy() for n in self.clip.notes]
        self.button(f.C.BTN_MOD)
        self.clip.is_playing = False
        self.seq._on_playhead()
        self.assertEqual(self.seq._led[12], 40)
        self.button(f.C.BTN_MOD, False)
        self.assertEqual(self.seq._activity_state, (None, False))
        self.assertEqual(self.seq._activity_notes, {})
        self.assertEqual(self.seq._led[0], 64)
        self.assertEqual(before, [vars(n) for n in self.clip.notes])

    def test_external_note_edits_refresh_activity(self):
        self.button(f.C.BTN_MOD)
        self.clip.notes = []
        self.clip._fire('notes')
        self.assertEqual(self.seq._led[12], 40)
        self.clip.notes.append(f.FakeNote(37, 0., .25, 100))
        self.clip._fire('notes')
        self.assertEqual(self.seq._led[13], f.C.COLOR_DRUM_ACTIVITY)

    def test_new_drum_bank_uses_matching_pitches(self):
        self.button(f.C.BTN_MOD)
        self.button(f.C.BTN_RIGHT)
        self.position(.25)
        self.assertEqual(self.seq._lane_base, 52)
        self.assertEqual(self.seq._led[12], f.C.COLOR_DRUM_ACTIVITY)
        self.assertEqual(self.seq._led[13], 0)

    def test_no_note_reads_or_writes_during_same_page_playback(self):
        self.button(f.C.BTN_MOD)
        def fail(*args):
            raise AssertionError('playhead queried or wrote notes')
        self.clip.get_notes_extended = fail
        self.clip.add_new_notes = fail
        self.clip.remove_notes_extended = fail
        self.position(.02)
        self.position(.15)
        self.position(.25)
        self.position(.40)
        self.assertEqual(self.seq._led[13], 5)

    def test_offset_loop_and_wrap(self):
        self.clip.loop_start, self.clip.loop_end = 2., 6.
        self.clip.notes = [f.FakeNote(36, 2., .25, 100),
                           f.FakeNote(37, 6., .25, 100)]
        self.clip.playing_position = 2.
        self.button(f.C.BTN_VIEW)
        self.assertEqual(self.seq._led[12], f.C.COLOR_DRUM_ACTIVITY)
        self.position(5.9)
        self.assertEqual(self.seq._led[13], 5)
        self.position(2.)
        self.assertEqual(self.seq._led[12], f.C.COLOR_DRUM_ACTIVITY)


if __name__ == '__main__':
    unittest.main()
