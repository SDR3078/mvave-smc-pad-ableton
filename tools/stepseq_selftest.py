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

UNVERIFIED, and worth knowing before you trust a green run: three Live
behaviours are *asserted* by these fakes rather than checked against Live, so
any test whose verdict depends on them inherits the assumption --

  * get_notes_extended/remove_notes_extended use the half-open window
    [from_time, from_time + span) and the pitch range [from_pitch, +span);
  * add_new_notes fires the notes listener exactly once, synchronously;
  * MidiNoteSpecification accepts these keyword arguments;
  * a deleted LOM object raises on EVERY attribute access, methods included --
    which is what FakeClip.__getattribute__ models, and what both the
    deleted-clip test and _detach_clip's block-level guard rest on.

The "a lit step is a step pressing clears" guarantee rests on the first of
them. If Live's window turned out to be closed at the end, pressing an empty
step next to a set one would delete the neighbour, and nothing here would say
so.
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
    # Class-level so __getattribute__ below can read it before __init__ runs.
    dead = False

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

    def __getattribute__(self, name):
        # A deleted Live object raises on ANY attribute access, not only on the
        # three note methods -- and that is precisely what _detach_clip's guards
        # and _rebind's try/except exist to survive. Modelling only the note
        # methods meant the deleted-clip test never reached a single dead
        # access: _detach_clip nulls _clip and then asks *_has_listener, which
        # answered normally, so the test passed without exercising anything.
        if name != 'dead' and not name.startswith('__'):
            if object.__getattribute__(self, 'dead'):
                raise RuntimeError('clip has been deleted')
        return object.__getattribute__(self, name)

    def _check(self):
        if self.dead:
            raise RuntimeError('clip has been deleted')

    def set_loop_start(self, value):
        """Drag the FRONT of the brace. Fires loop_start and nothing else."""
        self.loop_start = value
        self._fire('loop_start')

    def set_loop_end(self, value):
        """Drag the loop brace the way the mouse does: no note changes at all.

        Live fires the loop listeners here and nothing else; the notes listener
        stays silent, which is why the script needs its own loop listener.
        """
        self.loop_end = value
        self._fire('loop_end')

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

    def add_loop_start_listener(self, cb):
        self._add('loop_start', cb)

    def remove_loop_start_listener(self, cb):
        self._remove('loop_start', cb)

    def loop_start_has_listener(self, cb):
        return self._has('loop_start', cb)

    def add_loop_end_listener(self, cb):
        self._add('loop_end', cb)

    def remove_loop_end_listener(self, cb):
        self._remove('loop_end', cb)

    def loop_end_has_listener(self, cb):
        return self._has('loop_end', cb)

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
        self.expect_logged_exception = False

    def tearDown(self):
        # _guarded logs and swallows, so without this an exception in any
        # callback is indistinguishable from success across the whole suite --
        # a test could "pass" purely because the code under it raised early and
        # the assertion it would have failed was never reached.
        if self.expect_logged_exception:
            return
        raised = [line for line in self.c_instance.log if 'exception in' in line]
        self.assertEqual(raised, [], 'a guarded callback raised: %s' % raised)

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

    def test_a_note_past_the_loop_end_is_not_lit(self):
        # Live keeps notes that sit outside the loop brace -- shortening a
        # pattern is enough to leave some -- and the 16-step read window
        # reaches them. Lighting one would promise a step that toggle_step
        # refuses: a lit pad that does nothing when pressed, which is exactly
        # what the floor-not-round rule exists to prevent.
        self.clip.loop_end = 1.0                    # four steps
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 5 * C.STEP, C.STEP, 100))
        self.seq.sent = []
        self.seq.refresh_state()
        self.assertEqual(self.leds()[5], C.COLOR_STEP_OFF)

    def test_the_render_and_the_write_path_agree_on_the_last_step(self):
        # A loop length that is not a whole number of steps. [0, 4.3) contains
        # 18 steps, 0..17: step 17 starts at 4.25, inside the loop, so it must
        # both light AND accept a press. Step 18 starts at 4.5 and must do
        # neither. _step_count() rounding instead of ceiling made step 17 dark
        # and unwritable -- and half of all loop lengths lose their last step
        # that way, so this is the boundary the two gates have to share.
        self.clip.loop_end = 4.3
        self.button(C.BTN_RIGHT)                    # bank 1 -> steps 16-31
        self.press(1)                               # step 17, the last in loop
        self.assertEqual(len(self.clip.notes), 1)
        self.assertAlmostEqual(self.clip.notes[0].start_time, 17 * C.STEP)
        self.assertEqual(self.leds()[1], C.COLOR_STEP_ON)   # and it lights
        self.seq.toggle_step(C.DEFAULT_LANE, 18)    # starts at 4.5, outside
        self.assertEqual(len(self.clip.notes), 1)   # refused, nothing written

    def test_a_note_past_the_loop_end_is_not_lit_in_overview(self):
        # The same gate exists on both refresh paths and only the focus one was
        # covered, so the lit-pad-that-ignores-you defect was fully
        # reintroducible in overview with the suite green.
        self.clip.loop_end = 1.5                    # six steps: 0..5
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 6 * C.STEP, C.STEP, 100))
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 5 * C.STEP, C.STEP, 100))
        self.button(C.BTN_VIEW)                     # overview
        self.button(C.BTN_RIGHT)                    # page 1 -> steps 4-7
        self.button(C.BTN_RIGHT)                    # and again: page 1 is the last
        self.seq.sent = []
        self.seq.refresh_state()
        self.assertEqual(self.seq._page, 1)                 # _clamp_pages held it
        # Both directions. Gating on `total` renders step 5 and hides step 6;
        # gating on `total - 1` hides both, which is the off-by-one the focus
        # companion test is named for and could not see over here.
        self.assertEqual(self.leds()[1], C.LANE_COLORS[0])  # step 5, last in loop
        self.assertEqual(self.leds()[2], C.COLOR_STEP_OFF)  # step 6, past the loop

    def test_the_in_loop_gate_holds_when_empty_steps_are_marked(self):
        # COLOR_STEP_EMPTY ships as 0, the same byte as COLOR_STEP_OFF, so the
        # in-loop gate on the *empty* pass is unobservable under the default
        # palette -- deleting it is green. MIDI_Map.py explicitly invites
        # turning these markers on, at which point the gate starts mattering.
        seqmod = SEQ_MODULE
        original = seqmod.COLOR_STEP_EMPTY
        try:
            seqmod.COLOR_STEP_EMPTY = 40
            self.clip.loop_end = 1.0                # four steps: 0..3
            self.seq.sent = []
            self.seq.refresh_state()
            self.assertEqual(self.leds()[0], 40)                # in loop, marked
            self.assertEqual(self.leds()[4], C.COLOR_STEP_OFF)  # out of loop, dark
        finally:
            seqmod.COLOR_STEP_EMPTY = original

    def test_a_note_on_the_last_step_of_a_whole_loop_lights(self):
        # The ordinary case the off-by-one would break: one bar, note on the
        # final 16th. Gating the render on `total - 1` renders it dark while
        # toggle_step still erases it.
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 15 * C.STEP, C.STEP, 100))
        self.seq.sent = []
        self.seq.refresh_state()
        self.assertEqual(self.leds()[15], C.COLOR_STEP_ON)

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
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 20 * C.STEP, C.STEP, 100))
        self.clip._fire('notes')
        self.assertEqual(self.seq._bank, 0)
        self.seq.sent = []
        self.clip.play(20 * C.STEP)
        self.assertEqual(self.seq._bank, 1)
        # Assert the PADS, not just _bank. _bank is set inside _scroll_to before
        # anything is drawn, so a follow that moved the window and then skipped
        # the clip read -- _paint() instead of _render() -- would satisfy the
        # bank assertion while the device showed bank 0's notes under bank 1's
        # playhead. That is the shape of the bug this test exists for.
        self.assertEqual(self.leds()[4], C.COLOR_PLAYHEAD_ON)
        self.clip.play(50 * C.STEP)
        self.assertEqual(self.seq._bank, 3)
        self.assertEqual(self.leds()[2], C.COLOR_PLAYHEAD)

    def test_the_window_follows_the_playhead_in_overview(self):
        # The overview half of _scroll_to had no test at all: the only overview
        # playhead test played step 1 on page 0, so the branch never ran.
        self.clip.loop_end = self.clip.loop_start + 64 * C.STEP
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 6 * C.STEP, C.STEP, 100))
        self.button(C.BTN_VIEW)                 # overview
        self.seq.sent = []
        self.clip.play(6 * C.STEP)
        self.assertEqual(self.seq._page, 1)
        # The note matters: with an empty clip _paint() alone reproduces this
        # result, so the test could not tell a moved window from a re-read one.
        # COLOR_PLAYHEAD_ON is only reachable if the new page was read.
        self.assertEqual(self.leds()[2], C.COLOR_PLAYHEAD_ON)
        self.assertEqual([self.leds()[i] for i in (6, 10, 14)],
                         [C.COLOR_PLAYHEAD] * 3)

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

    def test_mod_pad_selects_a_lane(self):
        self.button(C.BTN_MOD, down=True)
        self.press(15)                  # bottom-right -> 39
        self.button(C.BTN_MOD, down=False)
        self.press(0)
        self.assertEqual(self.clip.notes[0].pitch, 39)

    def test_mod_pad_does_not_write_a_step(self):
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

    def test_length_knob_repaints_the_grid(self):
        # The fake does not fire loop listeners on a programmatic write, and a
        # real Live may not either -- so _set_length's own render is what covers
        # the knob path, separately from the mouse-drag listener.
        self.clip.loop_end = 4.0                # 16 steps (Navigation gives 32)
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 12 * C.STEP, C.STEP, 100))
        self.clip._fire('notes')
        self.assertEqual(self.leds()[12], C.COLOR_STEP_ON)
        self.seq.sent = []
        for _ in range(8):
            self.seq.receive_midi(cc(C.KNOB_CHANNEL, C.CC_LENGTH, 63))  # -> 8 steps
        self.assertEqual(self.leds()[12], C.COLOR_STEP_OFF)

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

    def test_mod_arrows_move_the_lane_picker_bank(self):
        # MOD + pad only reaches 16 pitches from _lane_base, and a drum rack
        # has more rows than that, so the arrows bank the picker while held.
        base = self.seq._lane_base
        self.button(C.BTN_MOD, True)
        self.button(C.BTN_RIGHT)
        self.assertEqual(self.seq._lane_base, base + 16)
        self.button(C.BTN_LEFT)
        self.button(C.BTN_LEFT)
        self.assertEqual(self.seq._lane_base, base - 16)
        self.button(C.BTN_MOD, False)

    def test_the_lane_base_starts_inside_the_range_the_picker_derives(self):
        # _lane_base is a DERIVED value -- every later write is
        # _clamp(LANE_SELECT_BASE + 16 * bank, 0, 112) -- so the constructor has
        # to apply the same clamp. Writing the raw constant left any
        # LANE_SELECT_BASE above 112 starting out of range, and MOD + pad then
        # selected pitches past 127, which toggle_step refuses in silence.
        seqmod = SEQ_MODULE
        original = seqmod.LANE_SELECT_BASE
        try:
            seqmod.LANE_SELECT_BASE = 120
            fresh = MVave_SMC_STEPSEQ(FakeCInstance())
            self.assertLessEqual(fresh._lane_base, 112)
            self.assertLessEqual(lane_for_pad(0, fresh._lane_base), 127)
        finally:
            seqmod.LANE_SELECT_BASE = original

    def test_the_lane_picker_reaches_every_pitch_and_keeps_its_series(self):
        # Two properties at once, because the two obvious implementations each
        # give up one of them. The end stops must reach pitch 0 and 112, since
        # MOD + pad is the only lane control this hardware can offer; and
        # stepping back off a stop must return to the original 16-pitch series
        # rather than stranding the picker on 0+16k with 36 unreachable.
        self.button(C.BTN_MOD, True)
        for _ in range(8):
            self.button(C.BTN_LEFT)             # walk into the bottom stop
        self.assertEqual(self.seq._lane_base, 0)            # pitches 0-15
        for _ in range(3):
            self.button(C.BTN_RIGHT)
        self.assertEqual(self.seq._lane_base, C.LANE_SELECT_BASE)   # back on series
        for _ in range(5):
            self.button(C.BTN_RIGHT)            # walk into the top stop
        self.assertEqual(self.seq._lane_base, 112)          # pitches 112-127
        self.button(C.BTN_MOD, False)

    def test_mod_arrows_do_not_page_steps(self):
        self.seq._bank = 0
        self.button(C.BTN_MOD, True)
        self.button(C.BTN_RIGHT)
        self.assertEqual(self.seq._bank, 0)
        self.button(C.BTN_MOD, False)

    def test_lane_picker_follows_its_bank(self):
        self.button(C.BTN_MOD, True)
        self.button(C.BTN_RIGHT)              # base += 16
        self.press(0)                         # MOD + pad 0
        self.button(C.BTN_MOD, False)
        self.assertEqual(self.seq._lane,
                         lane_for_pad(0, C.LANE_SELECT_BASE + 16))

    def test_mod_pad_scrolls_the_lane_window_into_view(self):
        self.button(C.BTN_MOD, down=True)
        self.press(12)                  # bottom-left -> 36... top row of window
        self.button(C.BTN_MOD, down=False)
        self.press(0)
        self.assertEqual(self.clip.notes[0].pitch, lane_for_pad(12))


class OffsetLoop(SeqTest):
    """Every core guarantee again, on a clip whose loop does not start at zero.

    Every other clip in this file is built `loop_start=0.0`, which made six of
    the seven places the script reads `loop_start` invisible: dropping it from
    `toggle_step`, `_step_count`, `_on_playhead`, `_set_length` or either read
    window left the suite green while the pads wrote and drew at the wrong beat.
    Dragging the front of the brace in is an entirely ordinary thing to do.
    """

    def setUp(self):
        SeqTest.setUp(self)
        self.clip = FakeClip(loop_start=1.0, loop_end=5.0)      # 16 steps
        self.song.view.select(self.clip)
        self.seq.sent = []

    def test_a_pad_writes_relative_to_the_loop_start(self):
        self.press(3)
        self.assertAlmostEqual(self.clip.notes[0].start_time, 1.0 + 3 * C.STEP)

    def test_the_step_count_is_relative_to_the_loop_start(self):
        self.assertEqual(self.seq._step_count(), 16)

    def test_a_note_lights_the_pad_its_own_offset_names(self):
        # Step 14 sits at beat 4.5 -- inside [1.0, 5.0) but OUTSIDE the [0, 4.0)
        # window a loop_start-blind read would use. A note near the start of the
        # loop falls in both windows and so cannot see that mutation at all.
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 1.0 + 14 * C.STEP, C.STEP, 100))
        self.seq.sent = []
        self.seq.refresh_state()
        self.assertEqual(self.leds()[14], C.COLOR_STEP_ON)

    def test_the_overview_read_window_is_relative_to_the_loop_start(self):
        # The overview read window has its own copy of the offset, and the
        # focus tests above cannot see it.
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 1.0 + 2 * C.STEP, C.STEP, 100))
        self.button(C.BTN_VIEW)                 # overview
        self.seq.sent = []
        self.seq.refresh_state()
        self.assertEqual(self.leds()[2], C.LANE_COLORS[0])

    def test_the_playhead_is_relative_to_the_loop_start(self):
        self.clip.play(1.0 + 2 * C.STEP)
        self.assertEqual(self.leds()[2], C.COLOR_PLAYHEAD)

    def test_the_length_knob_measures_from_the_loop_start(self):
        self.seq.receive_midi(cc(C.KNOB_CHANNEL, C.CC_LENGTH, 63))      # 16 -> 15
        self.assertAlmostEqual(self.clip.loop_end, 1.0 + 15 * C.STEP)


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
        # Live goes on calling our listeners for a moment after the clip dies,
        # and a dead LOM object raises on any attribute access. Every entry
        # point has to survive that, log it, and carry on.
        self.expect_logged_exception = True
        self.clip.dead = True
        self.seq._on_playhead()             # guarded listener
        self.seq._on_notes_changed()        # guarded listener
        self.seq.refresh_state()            # the entry point the guard is for
        self.press(0)                       # receive_midi -> toggle_step
        self.song.view.select(None)         # rebind away from the corpse
        self.assertIsNone(self.seq._clip)
        self.assertTrue(any('exception in' in line
                            for line in self.c_instance.log))

    def test_dragging_the_loop_brace_clamps_the_visible_page(self):
        # The brace moves with no note change, so the notes listener stays
        # silent and only a loop listener sees it. Without one the grid keeps
        # showing a page the loop no longer has, and every pad on it is
        # refused without writing -- so nothing repaints it either.
        self.clip.loop_end = self.clip.loop_start + 32 * C.STEP
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 20 * C.STEP, C.STEP, 100))
        self.clip._fire('notes')
        self.button(C.BTN_RIGHT)                        # look at steps 17-32
        self.assertEqual(self.seq._bank, 1)
        self.assertEqual(self.leds()[4], C.COLOR_STEP_ON)   # step 20 is lit
        self.seq.sent = []
        self.clip.set_loop_end(self.clip.loop_start + 16 * C.STEP)
        self.assertEqual(self.seq._bank, 0)
        # Asserting _bank alone was the exact flaw this suite calls out in the
        # old playhead test: _clamp_pages moves it before anything is drawn, so
        # dropping the _render() from _on_loop_changed stayed green while the
        # device kept showing a page the loop no longer has.
        self.assertEqual(self.leds()[4], C.COLOR_STEP_OFF)

    def test_dragging_the_front_of_the_loop_redraws(self):
        # loop_start moves both the step count and the absolute time every index
        # maps to, and it fires only the loop_start listener -- so dropping that
        # half of LOOP_PROPERTIES has to fail something.
        self.clip.notes.append(FakeNote(C.DEFAULT_LANE, 2 * C.STEP, C.STEP, 100))
        self.clip._fire('notes')
        self.assertEqual(self.leds()[2], C.COLOR_STEP_ON)
        self.seq.sent = []
        self.clip.set_loop_start(2 * C.STEP)            # loop is now [0.5, 4.0)
        self.assertEqual(self.leds()[0], C.COLOR_STEP_ON)   # the note is step 0 now

    def test_the_loop_listeners_are_released_with_the_clip(self):
        # assertTrue first: assertFalse alone is trivially satisfied by a
        # listener that was never attached, which is how half of
        # LOOP_PROPERTIES could be dropped with this test still green.
        self.assertTrue(self.clip.loop_end_has_listener(self.seq._on_loop_changed))
        self.assertTrue(self.clip.loop_start_has_listener(self.seq._on_loop_changed))
        self.song.view.select(FakeClip())
        self.assertFalse(self.clip.loop_end_has_listener(self.seq._on_loop_changed))
        self.assertFalse(self.clip.loop_start_has_listener(self.seq._on_loop_changed))

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
        self.expect_logged_exception = True
        self.clip.get_notes_extended = lambda *a: 1 / 0
        self.clip._fire('notes')        # must not raise
        self.assertTrue(any('exception in notes listener' in line
                            for line in self.c_instance.log))

    def test_the_exception_log_is_latched_but_still_hears_a_new_fault(self):
        # The latch is what stops a per-audio-buffer fault writing ~90
        # tracebacks a second and burying the first. Keyed too coarsely it
        # would silently swallow a second, different fault -- and since the
        # suite's whole backstop is tearDown reading 'exception in' lines,
        # that would blind the suite as well as Log.txt.
        self.expect_logged_exception = True
        self.clip.get_notes_extended = lambda *a: 1 / 0
        self.clip._fire('notes')
        self.clip._fire('notes')
        lines = [l for l in self.c_instance.log if 'exception in notes listener' in l]
        self.assertEqual(len(lines), 1)         # the repeat is latched

        def different(*a):
            raise RuntimeError('a different fault entirely')
        self.clip.get_notes_extended = different
        self.clip._fire('notes')
        lines = [l for l in self.c_instance.log if 'exception in notes listener' in l]
        self.assertEqual(len(lines), 2)         # but a new one is still heard

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

    def test_the_two_port_3_scripts_cannot_collide(self):
        # Both scripts sit on port 3 and both use channel 1, so the NOTE RANGE
        # is the only thing keeping them apart -- which is what the +100 offset
        # in MIDI_Map.py exists for. The check below this one compares the
        # sequencer only with itself, so it would happily pass with
        # PAD_NOTES = 1..16, a state this map file records having been in once,
        # in which every clip launch would also toggle a step.
        import importlib.util
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location(
            'pad_midi_map', os.path.join(root, 'MVave_SMC_PAD', 'MIDI_Map.py'))
        pad = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pad)

        # Sweep every note constant the launcher defines, not a hand-picked
        # six: enabling any of the ~42 currently at -1 is the realistic way a
        # collision gets introduced, and naming six left that path uncovered.
        not_notes = {'BUTTONCHANNEL', 'SLIDERCHANNEL', 'MESSAGETYPE', 'PADCHANNEL',
                     'TSB_X', 'TSB_Y', 'TRACK_OFFSET', 'SCENE_OFFSET',
                     'TEMPO_TOP', 'TEMPO_BOTTOM',
                     # CC assignments, on SLIDERCHANNEL -- they share a number
                     # space with notes but never a message type, so a CC of 101
                     # is not a collision and must not fail this test.
                     'TEMPOCONTROL', 'MASTERVOLUME', 'CUELEVEL', 'CROSSFADER',
                     'TRACKVOL', 'TRACKPAN', 'TRACKSENDA', 'TRACKSENDB',
                     'TRACKSENDC', 'PARAMCONTROL',
                     # Drum-rack pitches Live translates TO; never transmitted.
                     'DRUM_PADS'}
        launcher = set()
        for name in dir(pad):
            if not name.isupper() or name in not_notes or name.startswith('CLIP_'):
                continue
            value = getattr(pad, name)
            if isinstance(value, int):
                launcher.add(value)
            elif isinstance(value, tuple):
                for item in value:
                    if isinstance(item, int):
                        launcher.add(item)
                    elif isinstance(item, tuple):
                        launcher.update(i for i in item if isinstance(i, int))
        launcher.discard(-1)

        mine = set(C.PAD_NOTES) | set(C.PAD_NOTES_B)
        mine.update(n for n in (C.BTN_PLAY, C.BTN_VIEW, C.BTN_MOD,
                                C.BTN_LEFT, C.BTN_RIGHT) if n is not None)

        if C.PAD_CHANNEL == pad.BUTTONCHANNEL:
            self.assertEqual(mine & launcher, set(),
                             'sequencer and clip launcher share notes on one port')

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

    def test_refresh_state_repaints_the_button_leds(self):
        # refresh_state exists because the device may have been repowered or
        # switched presets, which leaves every LED dark. Dropping only the pad
        # cache left the button diff believing the play and view lights were
        # still lit, so they stayed dark until their state next changed.
        self.button(C.BTN_VIEW)                 # overview: the view LED is on
        self.seq.sent = []
        self.seq.refresh_state()
        self.assertEqual(self.btn_led(C.BTN_VIEW), C.BTN_LED_ON)

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
