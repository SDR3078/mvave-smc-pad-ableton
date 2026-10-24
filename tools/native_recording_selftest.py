import unittest
from types import SimpleNamespace as Obj
import parameter_lock_selftest as p
from MVave_SMC_STEPSEQ.NativeRecording import NativeRecording


class Parameter(p.Parameter):
    is_enabled = True
    def __init__(self):
        self.begins = self.ends = 0
    def begin_gesture(self):
        self.begins += 1
    def end_gesture(self):
        self.ends += 1


class NativeTests(p.GestureTests):
    def setUp(self):
        super().setUp()
        self.song.session_record = False
        self.song.session_automation_record = False
        self.song.is_playing = True
        self.clip.is_playing = True
        self.track = self.song.view.selected_track
        self.track.arm = True
        self.song.tracks = [self.track]
        self.parameter = Parameter()
        self.seq.drum_macro_target = lambda: (True, Obj(parameters=[None, self.parameter]))

    def test_start_stop_recording_keeps_transport_and_restores_flags(self):
        C = p.fixture.C
        self.seq._on_button(C.BTN_MOD, True)
        self.seq._on_button(C.BTN_PLAY, True)
        self.seq._on_button(C.BTN_MOD, False)
        self.assertTrue(self.song.session_record)
        self.assertTrue(self.song.is_playing)
        self.seq.handle_macro_lock(self.parameter, 5)
        self.seq.handle_macro_lock(self.parameter, 2)
        self.assertEqual(self.parameter.value, 71)
        self.assertEqual(self.parameter.begins, 1)
        self.assertIsNone(self.clip.envelope)
        self.assertEqual(self.queue, [])
        self.seq._on_button(C.BTN_MOD, True)
        self.seq._on_button(C.BTN_PLAY, True)
        self.seq._on_button(C.BTN_MOD, False)
        self.assertFalse(self.song.session_record)
        self.assertFalse(self.song.session_automation_record)
        self.assertTrue(self.song.is_playing)
        self.assertEqual(self.parameter.ends, 1)
        self.assertEqual(self.seq._btn_led[C.BTN_MOD], C.BTN_LED_OFF)

    def test_play_alone_stops_recording_and_transport(self):
        self.seq._toggle_native_recording()
        self.seq._on_button(p.fixture.C.BTN_PLAY, True)
        self.assertFalse(self.song.is_playing)
        self.assertFalse(self.song.session_record)
        self.assertIsNone(self.seq._native_recording)

    def test_target_arms_automatically_and_restores(self):
        self.track.arm = False
        self.seq._toggle_native_recording()
        self.assertIsNotNone(self.seq._native_recording)
        self.assertTrue(self.track.arm)
        self.seq._stop_native_recording()
        self.assertFalse(self.track.arm)

    def test_other_armed_track_temporarily_disarmed_and_restored(self):
        other = Obj(arm=True)
        self.song.tracks.append(other)
        self.seq._toggle_native_recording()
        self.assertIsNotNone(self.seq._native_recording)
        self.assertFalse(other.arm)
        self.seq._stop_native_recording()
        self.assertTrue(other.arm)

    def test_preexisting_automation_arm_restored(self):
        self.song.session_automation_record = True
        self.seq._toggle_native_recording()
        self.seq._stop_native_recording()
        self.assertTrue(self.song.session_automation_record)

    def test_notification_cleanup_is_deferred(self):
        self.seq._toggle_native_recording()
        self.song.view.select(p.fixture.FakeClip())
        self.assertIsNone(self.seq._native_recording)
        self.assertTrue(self.song.session_record)
        self.queue.pop(0)()
        self.assertFalse(self.song.session_record)

    def test_native_curve_bypasses_base_envelope_rewrites(self):
        self.seq._toggle_native_recording()
        self.seq.handle_macro_lock(self.parameter, 1)
        self.seq._stop_native_recording()
        self.clip.envelope = p.Envelope()
        self.parameter.enabled = False
        self.assertTrue(self.seq.handle_macro_lock(self.parameter, 1))
        self.assertEqual(self.clip.envelope.writes, [])
        self.assertFalse(self.parameter.enabled)
        self.assertEqual(len(self.queue), 1)
        self.seq._continuous_previews[0]['time'] = 0
        self.queue.pop(0)()
        self.assertTrue(self.parameter.enabled)
        self.assertEqual(self.clip.envelope.writes, [])

    def test_many_preview_knob_messages_use_one_timer(self):
        self.seq._continuous_envelopes.append((self.clip, self.parameter))
        for _ in range(20):
            self.seq.handle_macro_lock(self.parameter, 1)
        self.assertEqual(len(self.queue), 1)
        self.assertEqual(len(self.seq._continuous_previews), 1)
        self.queue.pop(0)()
        self.assertEqual(len(self.queue), 1)  # Not idle yet; one retry only.
        self.seq._continuous_previews[0]['time'] = 0
        self.queue.pop(0)()
        self.assertEqual(self.seq._continuous_previews, [])
        self.assertEqual(self.queue, [])


if __name__ == '__main__':
    unittest.main()
