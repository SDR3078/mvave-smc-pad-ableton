#!/usr/bin/env python3
"""Run MVave_SMC_STEPSEQ against a fake Live, on any machine.

    python3 tools/stepseq_selftest.py [-v]

Why this exists: Live has no hot reload. Every change to a Remote Script costs a
full Live restart, and a mistake inside a MIDI callback disables the script
silently -- the controller just stops responding and the only evidence is a
traceback in Log.txt. That is a punishing loop to debug grid arithmetic in.

Everything in the sequencer that is arithmetic rather than I/O -- which
coordinate maps to which step, which note bucket a time falls in, which LED
bytes go out and in what order, what happens when the bound clip is deleted --
can be checked here in a second, with no controller and no DAW. What this cannot
check is the hardware itself: the note numbers, the channel, the palette. Those
are Phase 0, on the device, and they live in MVave_SMC_STEPSEQ/MIDI_Map.py.

The stubs below implement only the slice of the Live API the sequencer touches,
and they deliberately model the half-open [t, t + span) window semantics that
the script's floor-bucketing assumes.
"""

import contextlib
import os
import sys
import unittest


# --------------------------------------------------------------------- stubs

class FakeNote(object):
    def __init__(self, pitch, start_time, duration, velocity, mute=False):
        self.pitch = pitch
        self.start_time = start_time
        self.duration = duration
        self.velocity = velocity
        self.mute = mute

    def __repr__(self):
        return 'Note(%d @ %.3f)' % (self.pitch, self.start_time)


class FakeListenable(object):
    """Live's add_x_listener / remove_x_listener / x_has_listener triple."""

    def __init__(self):
        self._listeners = {}

    def _bucket(self, name):
        return self._listeners.setdefault(name, [])

    def _add(self, name, callback):
        if callback not in self._bucket(name):
            self._bucket(name).append(callback)

    def _remove(self, name, callback):
        # Live raises on a double remove; so does this, so the script's guards
        # are actually exercised rather than merely present.
        self._bucket(name).remove(callback)

    def _has(self, name, callback):
        return callback in self._bucket(name)

    def _fire(self, name):
        for callback in list(self._bucket(name)):
            callback()


class FakeClip(FakeListenable):
    def __init__(self, loop_start=0.0, loop_end=4.0, is_midi=True):
        FakeListenable.__init__(self)
        self.is_midi_clip = is_midi
        self.loop_start = loop_start
        self.loop_end = loop_end
        self.end_marker = loop_end
        self.is_playing = False
        self.playing_position = 0.0
        self.notes = []
        self.dead = False

    def _check(self):
        if self.dead:
            raise RuntimeError('clip has been deleted')

    def get_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        self._check()
        return tuple(n for n in self.notes
                     if from_pitch <= n.pitch < from_pitch + pitch_span
                     and from_time <= n.start_time < from_time + time_span)

    def add_new_notes(self, specs):
        self._check()
        for spec in specs:
            self.notes.append(FakeNote(spec.pitch, spec.start_time,
                                       spec.duration, spec.velocity, spec.mute))
        self._fire('notes')

    def remove_notes_extended(self, from_pitch, pitch_span, from_time, time_span):
        self._check()
        doomed = self.get_notes_extended(from_pitch, pitch_span, from_time, time_span)
        self.notes = [n for n in self.notes if n not in doomed]
        self._fire('notes')

    def add_notes_listener(self, cb):
        self._add('notes', cb)

    def remove_notes_listener(self, cb):
        self._remove('notes', cb)

    def notes_has_listener(self, cb):
        return self._has('notes', cb)

    def add_playing_position_listener(self, cb):
        self._add('position', cb)

    def remove_playing_position_listener(self, cb):
        self._remove('position', cb)

    def playing_position_has_listener(self, cb):
        return self._has('position', cb)

    def add_playing_status_listener(self, cb):
        self._add('status', cb)

    def remove_playing_status_listener(self, cb):
        self._remove('status', cb)

    def playing_status_has_listener(self, cb):
        return self._has('status', cb)

    def play(self, position):
        self.is_playing = True
        self.playing_position = position
        self._fire('position')

    def stop(self):
        self.is_playing = False
        self._fire('status')


class PreLive11Clip(FakeClip):
    """A Live 10 clip. The extended note API arrived in Live 11."""

    @property
    def get_notes_extended(self):
        raise AttributeError('get_notes_extended')


class FakeView(FakeListenable):
    def __init__(self):
        FakeListenable.__init__(self)
        self.detail_clip = None
        self.selected_track = object()

    def select(self, clip):
        self.detail_clip = clip
        self._fire('detail_clip')

    def add_detail_clip_listener(self, cb):
        self._add('detail_clip', cb)

    def remove_detail_clip_listener(self, cb):
        self._remove('detail_clip', cb)

    def detail_clip_has_listener(self, cb):
        return self._has('detail_clip', cb)

    def add_selected_track_listener(self, cb):
        self._add('track', cb)

    def remove_selected_track_listener(self, cb):
        self._remove('track', cb)

    def selected_track_has_listener(self, cb):
        return self._has('track', cb)


class FakeSong(object):
    def __init__(self):
        self.view = FakeView()
        self.is_playing = False

    def start_playing(self):
        self.is_playing = True

    def stop_playing(self):
        self.is_playing = False


class FakeCInstance(object):
    def __init__(self):
        self.log = []

    def handle(self):
        return 'handle'

    def log_message(self, message):
        self.log.append(message)


def install_stubs():
    """Put fake Live and _Framework modules in sys.modules, before import."""
    import types

    live = types.ModuleType('Live')

    class MidiNoteSpecification(object):
        def __init__(self, pitch=0, start_time=0.0, duration=0.0,
                     velocity=100, mute=False):
            self.pitch = pitch
            self.start_time = start_time
            self.duration = duration
            self.velocity = velocity
            self.mute = mute

    clip_module = types.ModuleType('Live.Clip')
    clip_module.MidiNoteSpecification = MidiNoteSpecification

    midi_map = types.ModuleType('Live.MidiMap')
    midi_map.forwarded = []
    midi_map.forward_midi_note = lambda h, m, ch, n: midi_map.forwarded.append(('note', ch, n))
    midi_map.forward_midi_cc = lambda h, m, ch, c: midi_map.forwarded.append(('cc', ch, c))

    live.Clip = clip_module
    live.MidiMap = midi_map

    class ControlSurface(object):
        def __init__(self, c_instance):
            self._c_instance = c_instance
            self.sent = []
            self.forwarded_to_framework = []
            self._song = FakeSong()

        def song(self):
            return self._song

        def log_message(self, message):
            self._c_instance.log_message(message)

        def _send_midi(self, midi_bytes):
            self.sent.append(tuple(midi_bytes))

        @contextlib.contextmanager
        def component_guard(self):
            yield

        def build_midi_map(self, midi_map_handle):
            pass

        def receive_midi(self, midi_bytes):
            self.forwarded_to_framework.append(tuple(midi_bytes))

        def refresh_state(self):
            pass

        def disconnect(self):
            pass

    cs_module = types.ModuleType('_Framework.ControlSurface')
    cs_module.ControlSurface = ControlSurface
    framework = types.ModuleType('_Framework')
    framework.ControlSurface = cs_module

    sys.modules['Live'] = live
    sys.modules['Live.Clip'] = clip_module
    sys.modules['Live.MidiMap'] = midi_map
    sys.modules['_Framework'] = framework
    sys.modules['_Framework.ControlSurface'] = cs_module
    return midi_map


MIDI_MAP = install_stubs()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from MVave_SMC_STEPSEQ import MIDI_Map as C                                  # noqa: E402
from MVave_SMC_STEPSEQ.MVave_SMC_STEPSEQ import (MVave_SMC_STEPSEQ, decode_relative,    # noqa: E402
                                     lane_for_pad, step_at,
                                     VIEW_FOCUS, VIEW_OVERVIEW)

# The package, the module and the class all share one name -- the convention the
# other two scripts follow too -- and __init__.py binds the CLASS over the module
# in the package namespace. So `import MVave_SMC_STEPSEQ.MVave_SMC_STEPSEQ as m`
# hands back the class, not the module, and patching a flag on it silently misses.
# sys.modules is not shadowed, so it is the reliable handle.
SEQ_MODULE = sys.modules['MVave_SMC_STEPSEQ.MVave_SMC_STEPSEQ']


# --------------------------------------------------------------------- helper

def note_on(channel, note, velocity=127):
    return (0x90 | channel, note, velocity)


def cc(channel, number, value):
    return (0xB0 | channel, number, value)


class SeqTest(unittest.TestCase):
    """Base: a loaded script with a bound four-beat clip."""

    def setUp(self):
        MVave_SMC_STEPSEQ._active_instances = []
        self.c_instance = FakeCInstance()
        self.seq = MVave_SMC_STEPSEQ(self.c_instance)
        self.song = self.seq.song()
        self.clip = FakeClip(loop_start=0.0, loop_end=4.0)
        self.song.view.select(self.clip)
        self.seq.sent = []

    def press(self, pad_index, velocity=127):
        self.seq.receive_midi(note_on(C.PAD_CHANNEL, C.PAD_NOTES[pad_index], velocity))
        self.seq.receive_midi(note_on(C.PAD_CHANNEL, C.PAD_NOTES[pad_index], 0))

    def button(self, number, down=True):
        self.seq.receive_midi(note_on(C.BUTTON_CHANNEL, number, 127 if down else 0))

    def leds(self):
        """The colour last sent to each of the 16 pads, in reading order."""
        state = dict((note, None) for note in C.LED_NOTES)
        for status, note, velocity in self.seq.sent:
            if note in state:
                state[note] = velocity
        return [state[note] for note in C.LED_NOTES]

    def btn_led(self, note):
        """The velocity last sent to one button, or None if never written."""
        last = None
        for status, sent_note, velocity in self.seq.sent:
            if sent_note == note:
                last = velocity
        return last

    def btn_writes(self, note):
        return [v for _, n, v in self.seq.sent if n == note]


# ------------------------------------------------------------- pure functions

class PureFunctions(unittest.TestCase):

    def test_step_at_floors_rather_than_rounds(self):
        # A note nudged off the grid must light the step whose half-open window
        # contains it -- the same window remove_notes_extended() will clear.
        self.assertEqual(step_at(0.0, 0.0), 0)
        self.assertEqual(step_at(0.24, 0.0), 0)
        self.assertEqual(step_at(0.25, 0.0), 1)
        self.assertEqual(step_at(0.49, 0.0), 1)
        self.assertEqual(step_at(3.75, 0.0), 15)

    def test_step_at_is_relative_to_loop_start(self):
        self.assertEqual(step_at(4.0, 4.0), 0)
        self.assertEqual(step_at(4.5, 4.0), 2)

    def test_step_at_survives_float_error(self):
        # 0.25 * 3 is 0.7500000000000001 in binary floating point.
        self.assertEqual(step_at(0.25 * 3, 0.0), 3)
        for step in range(64):
            self.assertEqual(step_at(step * 0.25, 0.0), step)

    def test_lane_for_pad_is_drum_rack_oriented(self):
        # Bottom-left is the lowest note, ascending left to right then upward,
        # so the controller matches the rack on screen.
        self.assertEqual(lane_for_pad(12), 36)      # bottom-left
        self.assertEqual(lane_for_pad(15), 39)      # bottom-right
        self.assertEqual(lane_for_pad(0), 48)       # top-left
        self.assertEqual(lane_for_pad(3), 51)       # top-right

    def test_decode_relative_centre(self):
        self.assertEqual(decode_relative(65, 'centre'), 1)
        self.assertEqual(decode_relative(63, 'centre'), -1)
        self.assertEqual(decode_relative(64, 'centre'), 0)

    def test_decode_relative_twos_complement(self):
        self.assertEqual(decode_relative(1, 'twos'), 1)
        self.assertEqual(decode_relative(127, 'twos'), -1)
        self.assertEqual(decode_relative(0, 'twos'), 0)


# -------------------------------------------------------------------- writing

class Writing(SeqTest):

    def test_pad_writes_a_sixteenth_at_the_right_time(self):
        self.press(5)
        self.assertEqual(len(self.clip.notes), 1)
        note = self.clip.notes[0]
        self.assertEqual(note.pitch, C.DEFAULT_LANE)
        self.assertAlmostEqual(note.start_time, 5 * C.STEP)
        self.assertAlmostEqual(note.duration, C.STEP)
        # Velocity-sensitive pads: the strike sets it, not the default.
        self.assertEqual(note.velocity, 127)

    def test_pressing_twice_removes_the_note(self):
        self.press(5)
        self.press(5)
        self.assertEqual(self.clip.notes, [])

    def test_pad_release_writes_nothing(self):
        self.seq.receive_midi(note_on(C.PAD_CHANNEL, C.PAD_NOTES[5], 0))
        self.assertEqual(self.clip.notes, [])

    def test_a_step_past_the_loop_end_is_refused(self):
        self.clip.loop_end = 1.0        # four steps; pad 5 is past the end
        self.press(5)
        self.assertEqual(self.clip.notes, [])

    def test_toggle_clears_an_off_grid_note_in_the_same_window(self):
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 5 * C.STEP + 0.05,
                                        C.STEP, 100))
        self.press(5)
        self.assertEqual(self.clip.notes, [])

    def test_strike_velocity_paints_the_step(self):
        # How hard you hit the pad is the velocity the step gets, Push-style.
        for pad, hit in ((0, 40), (1, 90), (2, 127)):
            self.press(pad, hit)
        self.assertEqual([n.velocity for n in self.clip.notes], [40, 90, 127])

    def test_the_knob_still_applies_when_there_is_no_strike(self):
        # USE_STRIKE_VELOCITY off, or a caller with no velocity to offer, falls
        # back to the painted default the knob adjusts.
        self.seq.receive_midi(cc(C.KNOB_CHANNEL, C.CC_VELOCITY, 63))
        self.seq.toggle_step(C.DEFAULT_LANE, 0)          # no velocity argument
        self.assertEqual(self.clip.notes[0].velocity, C.PAINT_VELOCITY - 1)

    def test_strike_velocity_can_be_turned_off(self):
        # Patch the SEQUENCER module, not MIDI_Map. The script does
        # `from .MIDI_Map import *`, which copies the flag into its own namespace
        # at import time -- rebinding it on MIDI_Map afterwards reaches nothing.
        seqmod = SEQ_MODULE
        original = seqmod.USE_STRIKE_VELOCITY
        try:
            seqmod.USE_STRIKE_VELOCITY = False
            self.press(0, 40)
            self.assertEqual(self.clip.notes[0].velocity, C.PAINT_VELOCITY)
        finally:
            seqmod.USE_STRIKE_VELOCITY = original

    def test_writing_with_no_clip_bound_is_a_no_op(self):
        self.song.view.select(None)
        self.press(0)       # must not raise

    def test_a_mouse_edit_lights_the_pads(self):
        # The notes listener is the whole reason Ctrl+Z and mouse edits work.
        self.seq.sent = []
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 2 * C.STEP, C.STEP, 100))
        self.clip._fire('notes')
        self.assertEqual(self.leds()[2], C.COLOR_STEP_ON)


# ------------------------------------------------------------------ rendering

class Rendering(SeqTest):

    def test_focus_view_lights_the_lane(self):
        self.press(0)
        self.press(4)
        self.press(8)
        self.seq.sent = []
        self.seq.refresh_state()
        lit = [i for i, colour in enumerate(self.leds())
               if colour == C.COLOR_STEP_ON]
        self.assertEqual(lit, [0, 4, 8])

    def test_notes_in_another_lane_are_not_shown(self):
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE + 1, 0.0, C.STEP, 100))
        self.seq.sent = []
        self.seq.refresh_state()
        self.assertNotIn(C.COLOR_STEP_ON, self.leds())

    def test_only_changed_pads_are_sent(self):
        self.press(0)
        self.seq.sent = []
        self.press(1)
        # Pad 0 was already teal and pad 1 was already off, so exactly one pad
        # changes. The diff is what keeps this off the device's input buffer.
        self.assertEqual(len(self.seq.sent), 1)
        self.assertEqual(self.seq.sent[0][1], C.LED_NOTES[1])

    def test_leds_are_note_on_never_note_off(self):
        # A real note-off is ignored by this device, silently.
        self.press(0)
        self.press(0)
        for status, _note, _velocity in self.seq.sent:
            self.assertEqual(status & 0xF0, 0x90)

    def test_steps_beyond_the_loop_are_dark(self):
        self.clip.loop_end = 1.0        # four steps
        self.seq.sent = []
        self.seq.refresh_state()
        self.assertEqual(self.leds()[4:], [C.COLOR_STEP_OFF] * 12)

    def test_disconnect_extinguishes_the_grid(self):
        self.press(0)
        self.seq.sent = []
        self.seq.disconnect()
        self.assertEqual(self.leds(), [0] * 16)


# ------------------------------------------------------------------- playhead

class Playhead(SeqTest):

    def test_playhead_marks_the_current_step(self):
        self.seq.sent = []
        self.clip.play(2 * C.STEP)
        self.assertEqual(self.leds()[2], C.COLOR_PLAYHEAD)

    def test_playhead_over_an_active_step_is_highlighted(self):
        self.press(2)
        self.seq.sent = []
        self.clip.play(2 * C.STEP)
        self.assertEqual(self.leds()[2], C.COLOR_PLAYHEAD_ON)

    def test_playhead_within_one_step_sends_nothing(self):
        self.clip.play(2 * C.STEP)
        self.seq.sent = []
        self.clip.play(2 * C.STEP + 0.05)
        self.clip.play(2 * C.STEP + 0.15)
        # This listener fires per audio buffer; only a step change is work.
        self.assertEqual(self.seq.sent, [])

    def test_the_window_follows_the_playhead(self):
        # A 64-step loop needs no manual paging: the visible 16 are the ones
        # playing. This is the whole reason STEPS_MAX is no longer 32.
        self.clip.loop_end = self.clip.loop_start + 64 * C.STEP
        self.assertEqual(self.seq._bank, 0)
        self.clip.play(20 * C.STEP)
        self.assertEqual(self.seq._bank, 1)
        self.clip.play(50 * C.STEP)
        self.assertEqual(self.seq._bank, 3)

    def test_paging_by_hand_stops_the_chase(self):
        self.clip.loop_end = self.clip.loop_start + 64 * C.STEP
        self.clip.play(20 * C.STEP)           # follows to bank 1
        self.button(C.BTN_LEFT)               # manual page -> stop following
        self.assertFalse(self.seq._follow)
        self.clip.play(50 * C.STEP)
        self.assertEqual(self.seq._bank, 0)   # stayed put

    def test_paging_back_onto_the_playhead_resumes_the_chase(self):
        # Otherwise the only way to re-arm while playing is to stop the
        # transport, which makes paging away a mode you cannot leave mid-jam.
        self.clip.loop_end = self.clip.loop_start + 64 * C.STEP
        self.clip.play(20 * C.STEP)               # follows to bank 1
        self.button(C.BTN_RIGHT)                  # page away -> stops following
        self.assertFalse(self.seq._follow)
        self.assertEqual(self.seq._bank, 2)
        self.button(C.BTN_LEFT)                   # back onto the playing page
        self.assertEqual(self.seq._bank, 1)
        self.assertTrue(self.seq._follow)
        self.clip.play(50 * C.STEP)               # and it chases again
        self.assertEqual(self.seq._bank, 3)

    def test_paging_away_holds_until_the_loop_comes_round(self):
        self.clip.loop_end = self.clip.loop_start + 64 * C.STEP
        self.clip.play(20 * C.STEP)
        self.button(C.BTN_RIGHT)
        self.button(C.BTN_RIGHT)                  # two pages from the playhead
        self.assertFalse(self.seq._follow)
        self.clip.play(50 * C.STEP)               # still playing forwards
        self.assertFalse(self.seq._follow)
        self.assertEqual(self.seq._bank, 3)       # stayed where you put it

    def test_the_loop_wrapping_resumes_the_chase(self):
        self.clip.loop_end = self.clip.loop_start + 64 * C.STEP
        self.clip.play(20 * C.STEP)
        self.button(C.BTN_RIGHT)
        self.assertFalse(self.seq._follow)
        self.clip.play(50 * C.STEP)
        self.assertFalse(self.seq._follow)
        self.clip.play(2 * C.STEP)                # wrapped: step went backwards
        self.assertTrue(self.seq._follow)
        self.assertEqual(self.seq._bank, 0)       # and snapped to the playhead

    def test_wrap_resume_can_be_switched_off(self):
        seqmod = SEQ_MODULE
        original = seqmod.FOLLOW_RESUMES_ON_WRAP
        try:
            seqmod.FOLLOW_RESUMES_ON_WRAP = False
            self.clip.loop_end = self.clip.loop_start + 64 * C.STEP
            self.clip.play(20 * C.STEP)
            self.button(C.BTN_RIGHT)
            self.clip.play(2 * C.STEP)            # wraps, but must not resume
            self.assertFalse(self.seq._follow)
        finally:
            seqmod.FOLLOW_RESUMES_ON_WRAP = original

    def test_paging_with_the_transport_stopped_leaves_follow_alone(self):
        # _playhead is None when stopped, so there is nothing to catch up to.
        self.assertIsNone(self.seq._playhead)
        self.button(C.BTN_RIGHT)
        self.assertFalse(self.seq._follow)

    def test_stopping_restores_the_chase(self):
        self.clip.loop_end = self.clip.loop_start + 64 * C.STEP
        self.clip.play(20 * C.STEP)
        self.button(C.BTN_LEFT)
        self.assertFalse(self.seq._follow)
        self.clip.stop()
        self.assertTrue(self.seq._follow)

    def test_playhead_clears_on_stop(self):
        self.clip.play(2 * C.STEP)
        self.seq.sent = []
        self.clip.stop()
        self.assertEqual(self.leds()[2], C.COLOR_STEP_OFF)

    def test_playhead_on_another_bank_is_not_drawn(self):
        self.clip.loop_end = 8.0        # 32 steps, so bank 1 exists
        self.button(C.BTN_RIGHT)
        self.seq.sent = []
        self.clip.play(2 * C.STEP)      # step 2 lives on bank 0
        self.assertNotIn(C.COLOR_PLAYHEAD, self.leds())


# ----------------------------------------------------------------- navigation

class Navigation(SeqTest):

    def setUp(self):
        SeqTest.setUp(self)
        self.clip.loop_end = 8.0        # 32 steps: two full banks

    def test_right_moves_to_steps_17_to_32(self):
        self.button(C.BTN_RIGHT)
        self.press(0)
        self.assertAlmostEqual(self.clip.notes[0].start_time, 16 * C.STEP)

    def test_banking_is_clamped_to_the_clip(self):
        self.clip.loop_end = 4.0        # one bank only
        self.button(C.BTN_RIGHT)
        self.press(0)
        self.assertAlmostEqual(self.clip.notes[0].start_time, 0.0)

    def test_left_cannot_go_below_the_first_bank(self):
        self.button(C.BTN_LEFT)
        self.press(0)
        self.assertAlmostEqual(self.clip.notes[0].start_time, 0.0)

    def test_shift_pad_selects_a_lane(self):
        self.button(C.BTN_MOD, down=True)
        self.press(15)                  # bottom-right -> 39
        self.button(C.BTN_MOD, down=False)
        self.press(0)
        self.assertEqual(self.clip.notes[0].pitch, 39)

    def test_shift_pad_does_not_write_a_step(self):
        self.button(C.BTN_MOD, down=True)
        self.press(0)
        self.assertEqual(self.clip.notes, [])

    def test_lane_knob_scrolls(self):
        self.seq.receive_midi(cc(C.KNOB_CHANNEL, C.CC_LANE, 65))
        self.press(0)
        self.assertEqual(self.clip.notes[0].pitch, C.DEFAULT_LANE + 1)

    def test_length_knob_sets_the_loop(self):
        self.seq.receive_midi(cc(C.KNOB_CHANNEL, C.CC_LENGTH, 63))
        self.assertAlmostEqual(self.clip.loop_end, 8.0 - C.STEP)

    def test_length_knob_will_not_shrink_below_one_step(self):
        for _ in range(64):
            self.seq.receive_midi(cc(C.KNOB_CHANNEL, C.CC_LENGTH, 63))
        self.assertAlmostEqual(self.clip.loop_end, C.STEP)

    def test_length_knob_keeps_the_end_marker_ahead_of_the_loop(self):
        self.clip.loop_end = 1.0
        self.clip.end_marker = 1.0
        self.seq.receive_midi(cc(C.KNOB_CHANNEL, C.CC_LENGTH, 65))
        self.assertGreaterEqual(self.clip.end_marker, self.clip.loop_end)

    def test_encoder_cc_arrives_the_same_way_from_a_sibling_script(self):
        self.seq.handle_encoder_cc(C.CC_LANE, 65)
        self.press(0)
        self.assertEqual(self.clip.notes[0].pitch, C.DEFAULT_LANE + 1)


# ---------------------------------------------------------------------- views

class Views(SeqTest):

    def setUp(self):
        SeqTest.setUp(self)
        self.clip.loop_end = 8.0
        self.button(C.BTN_VIEW)

    def test_overview_maps_rows_to_lanes_and_columns_to_steps(self):
        self.press(4 + 2)               # row 1, col 2
        note = self.clip.notes[0]
        self.assertEqual(note.pitch, C.DEFAULT_LANE + 1)
        self.assertAlmostEqual(note.start_time, 2 * C.STEP)

    def test_overview_colours_rows_by_lane(self):
        self.press(0)                   # row 0
        self.press(4)                   # row 1
        self.seq.sent = []
        self.seq.refresh_state()
        leds = self.leds()
        self.assertEqual(leds[0], C.LANE_COLORS[0])
        self.assertEqual(leds[4], C.LANE_COLORS[1])

    def test_overview_pages_four_steps_at_a_time(self):
        self.button(C.BTN_RIGHT)
        self.press(0)
        self.assertAlmostEqual(self.clip.notes[0].start_time, 4 * C.STEP)

    def test_overview_playhead_lights_the_whole_column(self):
        self.seq.sent = []
        self.clip.play(1 * C.STEP)
        leds = self.leds()
        self.assertEqual([leds[1], leds[5], leds[9], leds[13]],
                         [C.COLOR_PLAYHEAD] * 4)

    def test_view_toggle_keeps_the_musical_position(self):
        # Focus bank 1 covers steps 16-31; overview page 4 starts at step 16.
        self.button(C.BTN_VIEW)         # back to focus
        self.button(C.BTN_RIGHT)        # bank 1
        self.button(C.BTN_VIEW)         # overview again
        self.press(0)
        self.assertAlmostEqual(self.clip.notes[0].start_time, 16 * C.STEP)

    def test_shift_arrows_move_the_lane_picker_bank(self):
        # SHIFT + pad only reaches 16 pitches from _lane_base, and a drum rack
        # has more rows than that, so the arrows bank the picker while held.
        base = self.seq._lane_base
        self.button(C.BTN_MOD, True)
        self.button(C.BTN_RIGHT)
        self.assertEqual(self.seq._lane_base, base + 16)
        self.button(C.BTN_LEFT)
        self.button(C.BTN_LEFT)
        self.assertEqual(self.seq._lane_base, base - 16)
        self.button(C.BTN_MOD, False)

    def test_shift_arrows_do_not_page_steps(self):
        self.seq._bank = 0
        self.button(C.BTN_MOD, True)
        self.button(C.BTN_RIGHT)
        self.assertEqual(self.seq._bank, 0)
        self.button(C.BTN_MOD, False)

    def test_lane_picker_follows_its_bank(self):
        self.button(C.BTN_MOD, True)
        self.button(C.BTN_RIGHT)              # base += 16
        self.press(0)                         # SHIFT + pad 0
        self.button(C.BTN_MOD, False)
        self.assertEqual(self.seq._lane,
                         lane_for_pad(0, C.LANE_SELECT_BASE + 16))

    def test_shift_pad_scrolls_the_lane_window_into_view(self):
        self.button(C.BTN_MOD, down=True)
        self.press(12)                  # bottom-left -> 36... top row of window
        self.button(C.BTN_MOD, down=False)
        self.press(0)
        self.assertEqual(self.clip.notes[0].pitch, lane_for_pad(12))


# ------------------------------------------------------------------ lifecycle

class Lifecycle(SeqTest):

    def test_selecting_another_clip_rebinds(self):
        other = FakeClip(loop_start=0.0, loop_end=4.0)
        self.song.view.select(other)
        self.press(3)
        self.assertEqual(len(other.notes), 1)
        self.assertEqual(self.clip.notes, [])

    def test_the_old_clip_keeps_no_listeners(self):
        self.song.view.select(FakeClip())
        self.assertFalse(self.clip.notes_has_listener(self.seq._on_notes_changed))
        self.assertFalse(self.clip.playing_position_has_listener(self.seq._on_playhead))

    def test_a_deleted_clip_does_not_take_the_script_down(self):
        self.clip.dead = True
        self.song.view.select(None)     # must not raise
        self.assertIsNone(self.seq._clip)

    def test_an_audio_clip_is_not_bound(self):
        self.song.view.select(FakeClip(is_midi=False))
        self.assertIsNone(self.seq._clip)

    def test_a_pre_live_11_clip_is_refused_loudly(self):
        self.song.view.select(PreLive11Clip())
        self.assertIsNone(self.seq._clip)
        self.assertTrue(any('get_notes_extended' in line
                            for line in self.c_instance.log))

    def test_disconnect_releases_the_song_listeners(self):
        self.seq.disconnect()
        view = self.song.view
        self.assertFalse(view.detail_clip_has_listener(self.seq._on_selection_changed))
        self.assertFalse(view.selected_track_has_listener(self.seq._on_selection_changed))

    def test_disconnect_twice_does_not_raise(self):
        self.seq.disconnect()
        self.seq.disconnect()


# ----------------------------------------------------------------------- midi

class MidiPlumbing(SeqTest):

    def test_every_control_is_forwarded(self):
        MIDI_MAP.forwarded = []
        self.seq.build_midi_map('map')
        forwarded = set(MIDI_MAP.forwarded)
        for note in C.PAD_NOTES:
            self.assertIn(('note', C.PAD_CHANNEL, note), forwarded)
        for number in (C.BTN_LEFT, C.BTN_RIGHT, C.BTN_MOD, C.BTN_VIEW):
            self.assertIn(('note', C.BUTTON_CHANNEL, number), forwarded)
        self.assertIn(('cc', C.KNOB_CHANNEL, C.CC_LANE), forwarded)

    def test_unowned_midi_goes_back_to_the_framework(self):
        # Swallowing it is a documented silent failure in this repo.
        stray = (0x90, 60, 100)
        self.seq.receive_midi(stray)
        self.assertIn(stray, self.seq.forwarded_to_framework)

    def test_unmapped_midi_is_named_once(self):
        for _ in range(5):
            self.seq.receive_midi((0x90, 60, 100))
        lines = [line for line in self.c_instance.log if 'unmapped' in line]
        self.assertEqual(len(lines), 1)
        self.assertIn('60', lines[0])

    def test_a_broken_callback_is_logged_not_fatal(self):
        # An uncaught exception in a listener disables the whole script until
        # Live restarts, so every callback is wrapped.
        self.clip.get_notes_extended = lambda *a: 1 / 0
        self.clip._fire('notes')        # must not raise
        self.assertTrue(any('exception in notes listener' in line
                            for line in self.c_instance.log))

    def test_transport_button_toggles_playback(self):
        self.button(C.BTN_PLAY)
        self.assertTrue(self.song.is_playing)
        self.button(C.BTN_PLAY)
        self.assertFalse(self.song.is_playing)


# --------------------------------------------------------------------- config

class Configuration(unittest.TestCase):
    """Cheap guards on MIDI_Map.py, since a typo there is a Live restart."""

    def test_sixteen_pads(self):
        self.assertEqual(len(C.PAD_NOTES), 16)
        self.assertEqual(len(C.LED_NOTES), 16)
        self.assertEqual(len(set(C.PAD_NOTES)), 16)

    def test_four_lane_colours(self):
        self.assertEqual(len(C.LANE_COLORS), 4)

    def test_pads_and_buttons_do_not_collide(self):
        buttons = set(n for n in (C.BTN_PLAY, C.BTN_VIEW, C.BTN_MOD,
                                  C.BTN_LEFT, C.BTN_RIGHT) if n is not None)
        if C.BUTTON_CHANNEL == C.PAD_CHANNEL and not C.BUTTON_IS_CC:
            self.assertFalse((buttons & set(C.PAD_NOTES))
                             | (buttons & set(C.PAD_NOTES_B)))

    def test_every_value_is_a_legal_midi_byte(self):
        for name in ('COLOR_STEP_ON', 'COLOR_STEP_OFF', 'COLOR_PLAYHEAD',
                     'COLOR_PLAYHEAD_ON', 'COLOR_STEP_EMPTY',
                     'COLOR_STEP_DOWNBEAT', 'COLOR_NO_CLIP'):
            self.assertTrue(0 <= getattr(C, name) <= 127, name)
        for colour in C.LANE_COLORS:
            self.assertTrue(0 <= colour <= 127)
        for note in tuple(C.PAD_NOTES) + tuple(C.LED_NOTES):
            self.assertTrue(0 <= note <= 127)
        self.assertTrue(0 <= C.PAD_CHANNEL <= 15)
        self.assertTrue(0 <= C.LED_CHANNEL <= 15)

    def test_the_palette_only_uses_measured_colours(self):
        # Everything from 64 to 112 is one flat blue on this device, so a
        # colour up there is almost certainly a mistake (HARDWARE.md 3.2).
        for colour in ((C.COLOR_STEP_ON, C.COLOR_PLAYHEAD, C.COLOR_PLAYHEAD_ON)
                       + tuple(C.LANE_COLORS)):
            self.assertLessEqual(colour, 63, 'velocity %d is in the flat blue '
                                             'range' % colour)

    def test_knob_mode_is_one_of_the_two_schemes(self):
        self.assertIn(C.KNOB_MODE, ('centre', 'twos'))



class ButtonLeds(SeqTest):
    """The five buttons show state, when the device is set to accept feedback."""

    def test_play_button_lights_with_the_transport(self):
        self.seq.sent = []
        self.button(C.BTN_PLAY)                      # starts the transport
        self.assertTrue(self.song.is_playing)
        self.assertEqual(self.btn_led(C.BTN_PLAY), C.BTN_LED_ON)
        self.seq.sent = []
        self.button(C.BTN_PLAY)                      # stops it again
        self.assertEqual(self.btn_led(C.BTN_PLAY), C.BTN_LED_OFF)

    def test_view_button_lights_in_overview(self):
        self.seq.sent = []
        self.button(C.BTN_VIEW)
        self.assertEqual(self.seq._view, VIEW_OVERVIEW)
        self.assertEqual(self.btn_led(C.BTN_VIEW), C.BTN_LED_ON)
        self.seq.sent = []
        self.button(C.BTN_VIEW)
        self.assertEqual(self.btn_led(C.BTN_VIEW), C.BTN_LED_OFF)

    def test_modifier_lights_while_held(self):
        self.seq.sent = []
        self.button(C.BTN_MOD, True)
        self.assertEqual(self.btn_led(C.BTN_MOD), C.BTN_LED_ON)
        self.seq.sent = []
        self.button(C.BTN_MOD, False)
        self.assertEqual(self.btn_led(C.BTN_MOD), C.BTN_LED_OFF)

    def test_button_leds_are_diffed_not_resent(self):
        # _paint() runs on every playhead step. Without the cache each step would
        # rewrite all three buttons, which is the bulk-write the device's input
        # buffer does not survive.
        self.clip.play(0 * C.STEP)
        self.seq.sent = []
        for step in range(1, 8):
            self.clip.play(step * C.STEP)
        self.assertEqual(self.btn_writes(C.BTN_PLAY), [])
        self.assertEqual(self.btn_writes(C.BTN_VIEW), [])

    def test_the_paging_buttons_are_never_written(self):
        # Only three of the five carry state; the arrows have none to show.
        self.button(C.BTN_PLAY)
        self.button(C.BTN_VIEW)
        self.button(C.BTN_LEFT)
        self.button(C.BTN_RIGHT)
        self.assertEqual(self.btn_writes(C.BTN_LEFT), [])
        self.assertEqual(self.btn_writes(C.BTN_RIGHT), [])

    def test_all_leds_off_clears_the_buttons(self):
        self.button(C.BTN_VIEW)                      # light one
        self.seq.sent = []
        self.seq._all_leds_off()
        self.assertEqual(self.btn_led(C.BTN_VIEW), C.BTN_LED_OFF)

    def test_button_leds_can_be_switched_off(self):
        seqmod = SEQ_MODULE
        original = seqmod.BUTTON_LEDS
        try:
            seqmod.BUTTON_LEDS = False
            self.seq.sent = []
            self.button(C.BTN_VIEW)
            self.assertEqual(self.btn_writes(C.BTN_VIEW), [])
        finally:
            seqmod.BUTTON_LEDS = original


if __name__ == '__main__':
    unittest.main(verbosity=2 if '-v' in sys.argv else 1)
