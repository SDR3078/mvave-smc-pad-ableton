import unittest
from types import SimpleNamespace as Obj
import stepseq_selftest as f


class DrumModes(f.SeqTest):
    def setUp(self):
        super().setUp()
        self.seq.show_message = lambda message: None
        self.kick = Obj(class_name='InstrumentGroupDevice', parameters=[])
        self.clap = Obj(class_name='InstrumentGroupDevice', parameters=[])
        self.pads = [Obj(note=36, name='Kick', mute=False,
                        chains=[Obj(devices=[self.kick])]),
                     Obj(note=37, name='Clap', mute=False,
                        chains=[Obj(devices=[self.clap])]),
                     Obj(note=38, name='Empty', mute=False, chains=[])]
        self.rack = Obj(can_have_drum_pads=True, drum_pads=self.pads,
                        view=Obj(selected_drum_pad=None))
        self.song.view.selected_track.devices = [self.rack]

    def test_select_drums_changes_macro_target(self):
        self.button(f.C.BTN_MOD, True)
        self.press(12)
        self.assertIs(self.seq.drum_macro_target()[1], self.kick)
        self.press(13)
        self.assertIs(self.seq.drum_macro_target()[1], self.clap)
        self.assertIs(self.song.view.selected_device, self.clap)
        self.button(f.C.BTN_MOD, False)
        self.assertEqual(self.clip.notes, [])

    def test_mute_preserves_notes_selection_and_restores_steps(self):
        self.press(0)
        before = list(self.clip.notes)
        self.button(f.C.BTN_VIEW, True)
        self.press(13)
        self.assertTrue(self.pads[1].mute)
        self.assertEqual(self.seq._led[13], 14)
        self.assertEqual(self.seq._lane, 36)
        self.assertEqual(self.clip.notes, before)
        self.button(f.C.BTN_VIEW, False)
        self.assertEqual(self.seq._led[0], f.C.COLOR_STEP_ON)
        self.button(f.C.BTN_VIEW, True)
        self.press(13)
        self.assertFalse(self.pads[1].mute)
        self.assertEqual(self.seq._led[13], 5)

    def test_empty_drum_does_not_use_previous_rack(self):
        self.seq._select_lane(38)
        self.assertEqual(self.seq.drum_macro_target(), (True, None))
        self.assertEqual(self.clip.notes, [])

    def test_selection_lights_occupied_and_selected_pads(self):
        self.button(f.C.BTN_MOD, True)
        self.assertEqual(self.seq._led[12], 40)
        self.assertEqual(self.seq._led[13], 5)
        self.assertEqual(self.seq._led[14], 0)

    def test_entering_modifier_cancels_pending_step(self):
        self.seq._on_pad(0, True, 127)
        self.button(f.C.BTN_VIEW, True)
        self.seq._on_pad(0, False)
        self.assertEqual(self.clip.notes, [])

    def pin_track(self):
        track = self.song.view.selected_track
        track.name = 'Drums 1'
        track.clip_slots = [Obj(has_clip=True, clip=self.clip)]
        self.song.tracks = [track]
        self.seq._rebind()
        return track

    def test_audio_selection_keeps_clip_macros_and_mutes(self):
        track = self.pin_track()
        self.press(0)
        self.song.view.selected_track = f.FakeTrack()
        self.song.view.select(None)
        self.assertIs(self.seq._controlled_track, track)
        self.assertIs(self.seq._clip, self.clip)
        self.assertIs(self.seq.drum_macro_target()[1], self.kick)
        self.press(1)
        self.assertEqual(len(self.clip.notes), 2)
        self.button(f.C.BTN_VIEW, True)
        self.press(12)
        self.assertTrue(self.pads[0].mute)

    def test_arrows_skip_audio_tracks_and_bind_playing_clip(self):
        first = self.pin_track()
        second_clip = f.FakeClip()
        playing_clip = f.FakeClip()
        playing_clip.is_playing = True
        second = f.FakeTrack([self.rack])
        second.name = 'Drums 2'
        second.clip_slots = [Obj(has_clip=True, clip=second_clip),
                             Obj(has_clip=True, clip=playing_clip)]
        self.song.tracks = [first, f.FakeTrack(), second]
        self.button(f.C.BTN_RIGHT)
        self.assertIs(self.seq._controlled_track, second)
        self.assertIs(self.seq._clip, playing_clip)
        self.assertFalse(second_clip.is_playing)
        self.button(f.C.BTN_LEFT)
        self.assertIs(self.seq._controlled_track, first)
        self.assertIs(self.seq._clip, self.clip)

    def test_stop_arrows_page_without_switching_track(self):
        track = self.pin_track()
        self.clip.set_loop_end(8)
        self.button(f.C.BTN_VIEW, True)
        self.button(f.C.BTN_RIGHT)
        self.assertEqual(self.seq._bank, 1)
        self.assertIs(self.seq._controlled_track, track)
        self.assertEqual(self.seq._lane_base, 36)

    def test_record_arrows_bank_drums_without_paging(self):
        track = self.pin_track()
        self.button(f.C.BTN_MOD, True)
        self.button(f.C.BTN_RIGHT)
        self.assertEqual(self.seq._lane_base, 52)
        self.assertEqual(self.rack.view.drum_pads_scroll_position, 13)
        self.assertEqual(self.seq._bank, 0)
        self.assertIs(self.seq._controlled_track, track)


if __name__ == '__main__':
    unittest.main()
