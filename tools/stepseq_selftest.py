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

Live behaviours these fakes *assert* rather than check. A green run inherits
whichever of these is wrong, so they are listed rather than buried:

  * get_notes_extended/remove_notes_extended use the half-open window
    [from_time, from_time + span) -- CONFIRMED on Live 11.3.43, 2026-09-03, by
    hand: a note on step 5, then pressing the empty step 4, adds to step 4 and
    leaves step 5 alone. A closed window would have deleted the neighbour. The
    "a lit step is a step pressing clears" guarantee rests on this one.
  * add_new_notes fires the notes listener exactly once, synchronously -- still
    assumed; the suite would not notice a second fire.
  * MidiNoteSpecification accepts these keyword arguments -- de facto confirmed,
    since steps are written on real hardware.
  * a deleted LOM object raises on EVERY attribute access, methods included --
    STILL ASSUMED. FakeClip.__getattribute__ models it, and both the
    deleted-clip test and _detach_clip's block-level guard rest on it. No
    session has yet deleted a clip while the sequencer held it.
"""

import ast
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
        self.selected_track = FakeTrack()
        self.selected_device = None

    def select_device(self, device):
        self.selected_device = device

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


class FakeTrack(object):
    """Enough of a track for _follow_selected_track to walk it."""

    def __init__(self, devices=()):
        self.devices = list(devices)
        self.view = FakeTrackView(self.devices[0] if self.devices else None)


class FakeTrackView(object):
    def __init__(self, selected_device=None):
        self.selected_device = selected_device


class FakeSession(object):
    """The launcher's session box, as MVave_SMC_KNOBS._bank() reads it.

    Method-spelled, which is the spelling verified on Live 11.3.43; the
    attribute spelling is exercised separately through _fake_component.
    """

    def __init__(self, width=4, height=4):
        self._width, self._height = width, height
        self._track_offset = self._scene_offset = 0
        self.offsets = []

    def width(self):
        return self._width

    def height(self):
        return self._height

    def track_offset(self):
        return self._track_offset

    def scene_offset(self):
        return self._scene_offset

    def set_offsets(self, track_offset, scene_offset):
        # Live's own setter asserts on a negative offset, and an assert inside
        # a MIDI callback takes the script down mid-jam. Mirror that.
        assert track_offset >= 0, 'negative track offset %r' % track_offset
        assert scene_offset >= 0, 'negative scene offset %r' % scene_offset
        self._track_offset, self._scene_offset = track_offset, scene_offset
        self.offsets.append((track_offset, scene_offset))


class FakeSong(object):
    def __init__(self):
        self.view = FakeView()
        self.is_playing = False
        self.tracks = [FakeTrack() for _ in range(8)]
        self.visible_tracks = self.tracks
        self.scenes = [object() for _ in range(8)]

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

        def _on_selected_track_changed(self):
            pass

        def set_device_component(self, component):
            self._device_component = component

        def disconnect(self):
            pass

    cs_module = types.ModuleType('_Framework.ControlSurface')
    cs_module.ControlSurface = ControlSurface
    framework = types.ModuleType('_Framework')
    framework.ControlSurface = cs_module

    dc_module = types.ModuleType('_Framework.DeviceComponent')

    class DeviceComponent(object):
        """Only what MVave_SMC_KNOBS touches: a name, set_device, device()."""

        def __init__(self):
            self.name = None
            self._device = None

        def set_device(self, device):
            self._device = device

        def device(self):
            return self._device

    dc_module.DeviceComponent = DeviceComponent
    sys.modules['_Framework.DeviceComponent'] = dc_module

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

from MVave_SMC_KNOBS import MVave_SMC_KNOBS as _knobs_pkg                  # noqa: E402
KNOBS_MODULE = sys.modules['MVave_SMC_KNOBS.MVave_SMC_KNOBS']


# ------------------------------------------------- knob-script fixtures

class FakeParameter(object):
    """A device parameter that rejects an out-of-range write, as Live's does.

    Stored as a plain attribute this accepted writes the real
    Live.DeviceParameter setter raises on, so _adjust_macro's clamp could be
    deleted with the suite green -- and the exception that clamp exists to
    prevent disables the whole script from inside a MIDI callback.
    """

    def __init__(self, minimum, maximum, value=0.0, quantized=False):
        self.min, self.max = minimum, maximum
        self.is_quantized, self.is_enabled = quantized, True
        self._value = value

    def _get_value(self):
        return self._value

    def _set_value(self, new):
        if not (self.min <= new <= self.max):
            raise RuntimeError('value %r outside [%r, %r]' % (new, self.min, self.max))
        self._value = new

    value = property(_get_value, _set_value)


class FakeDevice(object):
    def __init__(self, parameters, name='Fake Rack'):
        self.parameters, self.name = parameters, name


def _fake_component(spelling, held):
    """A DeviceComponent that exposes its device in one of four ways.

    'method' and 'property' are the two _Framework spellings the script has to
    survive; 'private' is the fallback for a component with no public getter;
    'nothing' exposes none of them and must take the logged fallback.
    """
    if spelling == 'method':
        return type('M', (), {'device': lambda self: held})()
    if spelling == 'property':
        return type('P', (), {'device': property(lambda self: held)})()
    if spelling == 'private':
        obj = type('V', (), {})()
        obj._device = held
        return obj
    return type('N', (), {})()


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

    def test_a_sliver_of_a_final_step_does_not_bank_the_view(self):
        # A loop brace dragged off the grid leaves a last step holding a
        # fraction of a step's worth of in-loop time. Chasing it banks the view
        # there and back twice per cycle, tens of milliseconds apart, at
        # roughly double the LED traffic -- the burst this device's MIDI input
        # buffer does not survive (HARDWARE.md 3.5).
        self.clip.loop_end = self.clip.loop_start + 16 * C.STEP + C.STEP / 4.0
        self.seq.refresh_state()
        self.clip.play(16 * C.STEP)
        self.assertEqual(self.seq._bank, 0)

    def test_a_final_step_worth_following_is_followed(self):
        # The companion: a full step past the page boundary must still scroll,
        # or the gate has simply broken the follower.
        self.clip.loop_end = self.clip.loop_start + 18 * C.STEP
        self.seq.refresh_state()
        self.clip.play(16 * C.STEP)
        self.assertEqual(self.seq._bank, 1)

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

class LengthKnob(SeqTest):
    """The pattern-length encoder, on a loop longer than the grid can show."""

    def test_the_length_knob_never_truncates_a_loop_it_cannot_show(self):
        # _step_count() is the VIEW ceiling and stops at STEPS_MAX. Feeding it
        # back as if it were the CURRENT length turned one click into a
        # truncation on any longer loop -- 128 beats became 64, in either
        # direction, silently, dragging the clip's end marker in with it.
        self.clip.loop_start = 0.0
        self.clip.loop_end = 4.0 * C.STEPS_MAX * C.STEP      # four screens
        long_end = self.clip.loop_end
        self.seq.handle_encoder_cc(C.CC_LENGTH, 65)          # one click up
        self.assertGreaterEqual(self.clip.loop_end, long_end,
                                'the knob shortened a loop it cannot address')
        self.seq.handle_encoder_cc(C.CC_LENGTH, 63)          # one click down
        self.assertAlmostEqual(self.clip.loop_end, long_end - C.STEP)

    def test_the_length_knob_still_resizes_an_ordinary_loop(self):
        self.clip.loop_start = 0.0
        self.clip.loop_end = 4 * C.STEP
        self.seq.handle_encoder_cc(C.CC_LENGTH, 65)
        self.assertAlmostEqual(self.clip.loop_end, 5 * C.STEP)
        self.seq.handle_encoder_cc(C.CC_LENGTH, 63)
        self.assertAlmostEqual(self.clip.loop_end, 4 * C.STEP)


class LogFlooding(SeqTest):
    """The latches were pinned; the caps beside them were not.

    The existing tests fire the SAME signature repeatedly, which pins the
    latch. The cap exists for the opposite case, named in the code: "a fault
    whose message varies every time cannot fill Log.txt either." A per-audio-
    buffer fault with a varying message writes ~90 tracebacks a second and
    grows an unbounded set, burying the first copy -- which is also the only
    thing tearDown and the "no exception in any session" claim can read.
    """

    def test_the_exception_log_stops_at_the_cap(self):
        self.expect_logged_exception = True
        for index in range(40):
            try:
                raise RuntimeError('a fault whose message varies %d' % index)
            except RuntimeError:
                self.seq._log_exception('receive_midi')
        lines = [l for l in self.c_instance.log if 'exception in' in l]
        self.assertEqual(len(lines), 32, 'wrote %d lines' % len(lines))

    def test_the_unmapped_log_stops_at_the_cap(self):
        for status in range(0x90, 0x90 + 60):
            self.seq._log_unhandled(status, 1, 1)
        lines = [l for l in self.c_instance.log if 'unmapped' in l]
        self.assertEqual(len(lines), 48, 'wrote %d lines' % len(lines))

    def test_a_second_distinct_fault_in_one_place_is_still_heard(self):
        # The reason the signature carries the frame as well as `where`:
        # receive_midi covers pads, buttons and knobs, and the likeliest fault
        # in each is the same message.
        self.expect_logged_exception = True

        def one():
            raise RuntimeError('same message')

        def two():
            raise RuntimeError('same message')

        for raiser in (one, two):
            try:
                raiser()
            except RuntimeError:
                self.seq._log_exception('receive_midi')
        lines = [l for l in self.c_instance.log if 'exception in' in l]
        self.assertEqual(len(lines), 2, 'the second subsystem was dropped')


class RetiredClaims(unittest.TestCase):
    """Facts that were corrected once and must not come back anywhere else.

    Five review rounds found the same shape of defect over and over: a claim
    fixed in one file and left standing in another -- CC 38 corrected in a
    block and surviving in a table eight lines away; the flag-byte-as-port
    model retired in HARDWARE.md and still instructing in STEPSEQ.md; a
    pre-fix function body quoted in DEVELOPMENT.md as the pattern to copy.
    Six separate instances in the fifth round alone.

    Every one of them is a literal string that outlived its correction, so
    this is a grep, not a judgement. Add a row whenever a claim is retired;
    the cost is one line and it never rots the way prose does.
    """

    # (phrase, why it was retired). Case-insensitive, substring.
    RETIRED = (
        ('eight Shift+Pad presets',
         'those eight note ranges are PAD BANK positions of ONE preset file'),
        ('REC is -1 above',
         'never existed in MIDI_Map.py in any revision'),
        ('satisfied by padding',
         'the setter is not called at all, so nothing is padded'),
        ('All three scripts now call this body',
         'MVave_SMC_STEPSEQ has no such body -- it uses a guarded listener'),
        ('Dependency install failed',
         'run_probe.bat prints DOWNLOAD or IMPORTED, two separate labels'),
        ('set_scene_bank_buttons(None, None)',
         'commit 204acbe replaced it; quoting it reinstates a permanent unbind'),
        ('CC 118 and 119 are chosen',
         'present tense: the padding that used them is gone'),
        ('draw over each other',
         'the two port-3 scripts write disjoint note ranges (measured)'),
        ('load one at a time',
         'same -- both scripts stay loaded, the preset switch is the mode switch'),
        ('CC 38',
         'the encoders send CC 1-18; 38-45 was never measured on this unit'),
        ('take a bank you do not use',
         'the sequencer needs its own PRESET, not a spare bank'),
        ('one bank per Shift+Pad',
         'one bank per PAD BANK position; Shift+Pad loads a different file'),
        ('only the two navigation encoders',
         'all sixteen must be relative -- the macros are decoded as deltas too'),
        ('All five `Special*Component.py`',
         'there are six'),
    )

    # STEPSEQ-BRIEF.md is the original build brief, kept verbatim as history
    # and superseded by STEPSEQ.md. It is not held to these.
    EXEMPT = ('STEPSEQ-BRIEF.md',)

    def test_no_retired_claim_survives_anywhere_in_the_docs(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        documents = []
        for directory in (root, os.path.join(root, 'docs')):
            for name in sorted(os.listdir(directory)):
                if name.endswith('.md') and name not in self.EXEMPT:
                    documents.append(os.path.join(directory, name))
        self.assertTrue(documents, 'found no documents to check')

        survivors = []
        for path in documents:
            with open(path, encoding='utf-8') as handle:
                lines = handle.read().split('\n')
            for number, line in enumerate(lines, 1):
                for phrase, why in self.RETIRED:
                    if phrase.lower() in line.lower():
                        survivors.append('%s:%d  %r\n      retired because: %s'
                                         % (os.path.relpath(path, root),
                                            number, phrase, why))
        self.assertEqual(survivors, [],
                         'retired claims are back:\n    ' + '\n    '.join(survivors))


class SourceFiles(unittest.TestCase):
    """Every shipped .py must parse, at the floor the docs claim.

    The suite imports MVave_SMC_STEPSEQ and MVave_SMC_KNOBS and loads
    MVave_SMC_PAD/MIDI_Map.py by path -- and touches nothing else in
    MVave_SMC_PAD/. A syntax error in MVave_SMC_PAD.py or any Special*
    component was a green run here and a silently dead control surface in
    Live. Four review rounds ran this by hand; nothing ran it on demand.
    """

    def test_every_shipped_python_file_parses_at_the_stated_floor(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        checked = []
        for package in ('MVave_SMC_PAD', 'MVave_SMC_KNOBS',
                        'MVave_SMC_STEPSEQ', 'tools'):
            directory = os.path.join(root, package)
            for name in sorted(os.listdir(directory)):
                if not name.endswith('.py'):
                    continue
                path = os.path.join(directory, name)
                checked.append(path)
                with open(path, 'rb') as handle:
                    source = handle.read()
                try:
                    # Live 11 embeds Python 3.7. Syntax newer than that parses
                    # fine under the interpreter running this suite and fails
                    # only on the target, which is the whole point.
                    ast.parse(source, path, feature_version=(3, 7))
                except SyntaxError as exc:
                    self.fail('%s does not parse at Python 3.7: %s' % (path, exc))
        self.assertGreaterEqual(len(checked), 16,
                                'expected all four directories scanned, saw %d files'
                                % len(checked))


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

        # LED_NOTES too: it decides where _send_led writes on the MIDIOUT3 both
        # scripts share, and the map file records having held a fixed 1-16 LED
        # map once already. Without it, one constant makes the sequencer paint
        # its step colours onto the launcher's clip slots, suite still green.
        mine = set(C.PAD_NOTES) | set(C.PAD_NOTES_B) | set(C.LED_NOTES)
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
        # The buttons and knob CCs go straight to Live.MidiMap in
        # build_midi_map, which is unguarded -- an illegal number there takes
        # the surface down at load. None is the documented "unassigned" value;
        # a negative is not, and the adapting guide used to hand out -1.
        for name in ('BTN_PLAY', 'BTN_VIEW', 'BTN_MOD', 'BTN_LEFT', 'BTN_RIGHT'):
            value = getattr(C, name)
            self.assertTrue(value is None or 0 <= value <= 127,
                            '%s = %r -- use None, not a negative' % (name, value))
        for cc in SEQ_MODULE.KNOB_CCS:
            self.assertTrue(0 <= cc <= 127, 'CC %r' % (cc,))
        self.assertTrue(0 <= C.BUTTON_CHANNEL <= 15)
        self.assertTrue(0 <= C.KNOB_CHANNEL <= 15)

    def test_a_negative_button_never_reaches_the_midi_map(self):
        # -1 is the sentinel MVave_SMC_PAD/MIDI_Map.py uses and the adapting
        # guide once recommended here too. The LED path always skipped it; the
        # forwarding path did not, so it arrived as note -1.
        seqmod = SEQ_MODULE
        original = seqmod.BTN_PLAY
        try:
            seqmod.BTN_PLAY = -1
            seq = seqmod.MVave_SMC_STEPSEQ(FakeCInstance())
            MIDI_MAP.forwarded = []
            seq.build_midi_map('map')
            numbers = [n for kind, ch, n in MIDI_MAP.forwarded if kind == 'note']
            self.assertTrue(all(0 <= n <= 127 for n in numbers), numbers)
        finally:
            seqmod.BTN_PLAY = original

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


# ------------------------------------------------- the other two scripts

def _load_launcher_map():
    """MVave_SMC_PAD/MIDI_Map.py, by path -- its package __init__ imports Live."""
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        'pad_midi_map', os.path.join(root, 'MVave_SMC_PAD', 'MIDI_Map.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NOT_NOTES = frozenset((
    'BUTTONCHANNEL', 'SLIDERCHANNEL', 'MESSAGETYPE', 'PADCHANNEL',
    'TSB_X', 'TSB_Y', 'TRACK_OFFSET', 'SCENE_OFFSET', 'TEMPO_TOP', 'TEMPO_BOTTOM',
    # CC assignments, on SLIDERCHANNEL -- same number space, different message
    # type, so they can never collide with a note.
    'TEMPOCONTROL', 'MASTERVOLUME', 'CUELEVEL', 'CROSSFADER', 'TRACKVOL',
    'TRACKPAN', 'TRACKSENDA', 'TRACKSENDB', 'TRACKSENDC', 'PARAMCONTROL',
    # Drum-rack pitches Live translates TO; never transmitted.
    'DRUM_PADS'))


# NOT_NOTES exempts these from the COLLISION test, correctly -- a CC and a note
# live in different message spaces. They are still list indexes, so the RANGE
# test must cover them: MASTERVOLUME = 200 is an IndexError inside __init__,
# where Live disables the whole surface silently.
NOT_INDEXES = frozenset((
    'BUTTONCHANNEL', 'SLIDERCHANNEL', 'MESSAGETYPE', 'PADCHANNEL',
    'TSB_X', 'TSB_Y', 'TEMPO_TOP', 'TEMPO_BOTTOM'))


def _launcher_indexes(pad):
    """Every constant the launcher uses to index _note_map or _ctrl_map."""
    out = []
    for name in dir(pad):
        if not name.isupper() or name in NOT_INDEXES or name.startswith('CLIP_'):
            continue
        value = getattr(pad, name)
        if isinstance(value, int):
            out.append((name, value))
        elif isinstance(value, tuple):
            for item in value:
                if isinstance(item, int):
                    out.append((name, item))
                elif isinstance(item, tuple):
                    out.extend((name, i) for i in item if isinstance(i, int))
    return out


def _launcher_notes(pad):
    """Every note constant the launcher declares, as (name, value) pairs."""
    out = []
    for name in dir(pad):
        if not name.isupper() or name in NOT_NOTES or name.startswith('CLIP_'):
            continue
        value = getattr(pad, name)
        if isinstance(value, int):
            out.append((name, value))
        elif isinstance(value, tuple):
            for item in value:
                if isinstance(item, int):
                    out.append((name, item))
                elif isinstance(item, tuple):
                    out.extend((name, i) for i in item if isinstance(i, int))
    return out


class LauncherMap(unittest.TestCase):
    """MVave_SMC_PAD/MIDI_Map.py -- the file INSTALL.md tells users to edit.

    Six single-constant edits to it used to pass the only check that read this
    file and then raise inside MVave_SMC_PAD.__init__, where Live disables the
    whole control surface silently and the only evidence is a Log.txt traceback
    after a full restart. These assertions are the half of that a machine can
    catch in a second.
    """

    def setUp(self):
        self.pad = _load_launcher_map()

    def test_every_indexing_constant_is_a_legal_index(self):
        # Wider than the note test below: the CC constants are indexes too.
        for name, value in _launcher_indexes(self.pad):
            self.assertTrue(-1 <= value <= 127, '%s = %r' % (name, value))
        # The session offsets are asserted >= 0 by SpecialSessionComponent.
        for name in ('TRACK_OFFSET', 'SCENE_OFFSET'):
            self.assertGreaterEqual(getattr(self.pad, name), -1, name)

    def test_every_note_constant_is_a_legal_index(self):
        # -1 is the "unassigned" sentinel; 128+ is an IndexError at load and a
        # value below -1 silently binds the wrong note from the end of the list.
        for name, value in _launcher_notes(self.pad):
            self.assertTrue(-1 <= value <= 127, '%s = %r' % (name, value))

    def test_the_grid_dimensions_are_whole_numbers(self):
        # A float here is a TypeError inside range() at load.
        for name in ('TSB_X', 'TSB_Y'):
            self.assertIsInstance(getattr(self.pad, name), int, name)

    def test_clipnotemap_covers_the_declared_grid(self):
        p = self.pad
        self.assertGreaterEqual(len(p.CLIPNOTEMAP), p.TSB_Y)
        for row in p.CLIPNOTEMAP[:p.TSB_Y]:
            self.assertGreaterEqual(len(row), p.TSB_X)

    def test_the_indexed_tuples_are_long_enough(self):
        # _setup_session_control indexes SCENELAUNCH by range(TSB_X) and
        # TRACKSTOP by range(TSB_Y) -- the documented swap. Pinned as the code
        # is, not as it reads, so a non-square grid fails here and not in Live.
        p = self.pad
        self.assertGreaterEqual(len(p.SCENELAUNCH), p.TSB_X)
        self.assertGreaterEqual(len(p.TRACKSTOP), p.TSB_Y)
        # _scene_launch_buttons is built with range(TSB_X) and then indexed by
        # range(TSB_Y), so TSB_X < TSB_Y is an IndexError at load that the two
        # assertions above cannot see. The grid is square by assumption
        # (DEVELOPMENT.md) -- pin the assumption rather than the symptom.
        self.assertEqual(p.TSB_X, p.TSB_Y,
                         'a non-square grid raises IndexError in '
                         '_setup_session_control')
        for name in ('TRACKREC', 'TRACKSOLO', 'TRACKMUTE', 'TRACKSEL',
                     'TRACKVOL', 'TRACKPAN', 'TRACKSENDA', 'TRACKSENDB',
                     'TRACKSENDC', 'PARAMCONTROL', 'DEVICEBANK'):
            self.assertGreaterEqual(len(getattr(p, name)), 8, name)

    def test_the_clip_palette_stays_in_the_measured_range(self):
        # Same hardware palette as the sequencer's: everything above ~64 is one
        # flat blue, and above 127 is not a legal MIDI byte at all.
        for name in ('CLIP_PLAYING', 'CLIP_STOPPED', 'CLIP_RECORDING',
                     'CLIP_TRIGGERED_PLAY', 'CLIP_TRIGGERED_REC'):
            value = getattr(self.pad, name)
            self.assertTrue(0 <= value <= 63, '%s = %d' % (name, value))


class KnobScript(unittest.TestCase):
    """MVave_SMC_KNOBS had no test of any kind before this class."""

    def setUp(self):
        self.knobs = KNOBS_MODULE.MVave_SMC_KNOBS(FakeCInstance())
        self.expect_logged_exception = False

    def tearDown(self):
        # The same backstop SeqTest has, and for the same reason: receive_midi
        # swallows and logs, so a test that drives the script the way real MIDI
        # arrives can be green while every write raised and was discarded.
        if self.expect_logged_exception:
            return
        raised = [l for l in self.knobs._c_instance.log if 'exception in' in l]
        self.assertEqual(raised, [], 'a guarded callback raised: %s' % raised)

    def _with_session(self, width=4, height=4):
        session = FakeSession(width, height)
        self.knobs._pad_session = lambda: session
        return session

    def _turn(self, cc, value):
        self.knobs.receive_midi((0xB0 | KNOBS_MODULE.CHANNEL, cc, value))

    # ------------------------------------------------------- the MIDI path

    def test_a_navigation_click_moves_the_session_box(self):
        session = self._with_session()
        self._turn(KNOBS_MODULE.CC_TRACK, 65)
        self.assertEqual(session.offsets[-1], (1, 0))
        self._turn(KNOBS_MODULE.CC_SCENE, 65)
        self.assertEqual(session.offsets[-1], (1, 1))

    def test_the_session_box_never_banks_below_zero(self):
        # set_offsets asserts on a negative offset, and an assert inside a MIDI
        # callback takes the whole script down mid-jam.
        session = self._with_session()
        for _ in range(4):
            self._turn(KNOBS_MODULE.CC_TRACK, 63)
        self.assertEqual(session.track_offset(), 0)

    def test_every_cc_the_script_handles_is_forwarded(self):
        # Dropping this loop leaves Live forwarding nothing: all sixteen macros
        # and both navigation encoders go dead, with no UI evidence at all.
        MIDI_MAP.forwarded = []
        self.knobs.build_midi_map('map')
        forwarded = set(MIDI_MAP.forwarded)
        for cc in (tuple(KNOBS_MODULE.NAV_CCS)
                   + tuple(sorted(KNOBS_MODULE.MACRO_BY_CC))):
            self.assertIn(('cc', KNOBS_MODULE.CHANNEL, cc), forwarded)

    def test_unowned_midi_goes_back_to_the_framework(self):
        # Swallowing it is the documented silent failure in this codebase.
        stray = (0x90, 60, 100)
        self.knobs.receive_midi(stray)
        self.assertIn(stray, self.knobs.forwarded_to_framework)

    def test_a_macro_cc_reaches_the_device(self):
        param = FakeParameter(0.0, 127.0)
        self.knobs._device.set_device(FakeDevice([FakeParameter(0.0, 1.0), param]))
        self._turn(sorted(KNOBS_MODULE.MACRO_BY_CC)[0], 65)
        self.assertEqual(param.value, 1.0)

    def test_a_raising_device_is_logged_not_propagated(self):
        # And tearDown must SEE it -- the point of the opt-out.
        self.expect_logged_exception = True

        class Exploding(object):
            name = 'Exploding Rack'

            @property
            def parameters(self):
                raise RuntimeError('device went away')

        self.knobs._device.set_device(Exploding())
        self._turn(sorted(KNOBS_MODULE.MACRO_BY_CC)[0], 65)
        self.assertTrue(any('exception in receive_midi' in l
                            for l in self.knobs._c_instance.log))

    # ------------------------------------------------------- the guards

    def test_a_macro_never_writes_outside_the_parameter_range(self):
        # Live's setter raises on an out-of-range write, and an exception in a
        # MIDI callback disables the script silently.
        param = FakeParameter(0.0, 127.0, value=127.0)
        self.knobs._device.set_device(FakeDevice([FakeParameter(0.0, 1.0), param]))
        self.knobs._adjust_macro(1, 1)
        self.assertEqual(param.value, 127.0)

    def test_a_disabled_parameter_is_left_alone(self):
        param = FakeParameter(0.0, 127.0)
        param.is_enabled = False
        self.knobs._device.set_device(FakeDevice([FakeParameter(0.0, 1.0), param]))
        self.knobs._adjust_macro(1, 1)
        self.assertEqual(param.value, 0.0)

    def test_a_rack_with_fewer_macros_than_knobs_is_not_an_error(self):
        self.knobs._device.set_device(FakeDevice([FakeParameter(0.0, 1.0)]))
        self.knobs._adjust_macro(9, 1)
        self.assertTrue(any('does nothing' in l
                            for l in self.knobs._c_instance.log))

    def test_two_identically_named_devices_are_both_reported(self):
        # Live names every rack "Audio Effect Rack", so a latch keyed on the
        # finished message reported the first and silently dropped the second
        # -- while the troubleshooting step reads "no line, so not this cause".
        devices = [FakeDevice([FakeParameter(0.0, 1.0)], name='Audio Effect Rack')
                   for _ in range(2)]
        for device in devices:
            self.knobs._device.set_device(device)
            self.knobs._adjust_macro(9, 1)
        lines = [l for l in self.knobs._c_instance.log if 'does nothing' in l]
        self.assertEqual(len(lines), 2, lines)

    def test_the_once_latch_is_capped(self):
        for index in range(40):
            self.knobs._log_once('a message that varies %d' % index)
        lines = [l for l in self.knobs._c_instance.log if 'that varies' in l]
        self.assertEqual(len(lines), 32, 'wrote %d lines' % len(lines))

    def test_the_two_navigation_ccs_are_distinct(self):
        # NAV_CCS is a tuple and set() collapses a duplicate silently; then
        # _navigate's "if cc == CC_TRACK" claims both, the scene encoder banks
        # tracks, and the box's Y axis becomes unreachable. No log line.
        self.assertNotEqual(KNOBS_MODULE.CC_TRACK, KNOBS_MODULE.CC_SCENE)

    def test_the_macro_map_is_self_consistent(self):
        K = KNOBS_MODULE
        self.assertFalse(set(K.MACRO_BY_CC) & set(K.NAV_CCS),
                         'a macro CC collides with a navigation CC')
        for cc, macro in K.MACRO_BY_CC.items():
            self.assertTrue(0 <= cc <= 127, 'CC %r' % (cc,))
            self.assertTrue(1 <= macro <= 127,
                            'macro %r -- index 0 is the device on/off switch' % (macro,))
        values = list(K.MACRO_BY_CC.values())
        self.assertEqual(len(set(values)), len(values), 'two CCs drive one macro')

    def test_one_click_moves_a_rack_macro_by_exactly_one(self):
        # The documented guarantee (INSTALL.md): a rack macro runs 0-127, a
        # range of 127, so one click is one unit. STEPS_PER_SWEEP = 128.0 was
        # shipped once and moves 0.992, which never lands on an integer.
        param = FakeParameter(0.0, 127.0)
        # Bound through the component, not the cache: _adjust_macro resolves the
        # device at write time, which is the whole point of _current_device().
        self.knobs._device.set_device(
            FakeDevice([FakeParameter(0.0, 1.0), param]))
        self.knobs._adjust_macro(1, 1)
        self.assertEqual(param.value, 1.0)

    def test_the_device_lookup_engages_on_every_spelling(self):
        # getattr(component, 'device', None) cannot tell an absent attribute
        # from a getter answering None, which made this fall back to the stale
        # cache on a fresh start. A sentinel distinguishes them.
        live_device, stale = FakeDevice([]), FakeDevice([])
        for spelling in ('method', 'property', 'private'):
            for held in (live_device, None):
                self.knobs._device = _fake_component(spelling, held)
                self.knobs._target_device = stale
                self.assertIs(self.knobs._current_device(), held,
                              '%s spelling, held=%r' % (spelling, held))

    def test_an_absent_getter_falls_back_and_says_so(self):
        self.knobs._device = _fake_component('nothing', None)
        stale = FakeDevice([])
        self.knobs._target_device = stale
        self.assertIs(self.knobs._current_device(), stale)
        self.assertTrue(any('no device getter' in line
                            for line in self.knobs._c_instance.log))

    def test_both_scripts_decode_a_click_the_same_way(self):
        # One measured hardware fact, two copies -- KNOBS hard-codes CENTRE and
        # the sequencer exposes KNOB_MODE. If they ever disagree, the same byte
        # moves the session box and the step lane in opposite directions.
        #
        # BOTH modes, not just the shipped one: comparing the two scripts under
        # 'centre' alone never executed the 'twos' branch at all, so the whole
        # convention a stranger with a 1/127 encoder depends on -- added by the
        # previous review round -- shipped untested.
        self.assertEqual(KNOBS_MODULE.ENCODER_MODE, C.KNOB_MODE)
        for mode in ('centre', 'twos'):
            for value in (0, 1, 2, 63, 64, 65, 126, 127):
                self.assertEqual(KNOBS_MODULE.decode_relative(value, mode),
                                 decode_relative(value, mode),
                                 'mode %s, value %d' % (mode, value))
        # And the two conventions must not be silently interchangeable.
        self.assertNotEqual(KNOBS_MODULE.decode_relative(127, 'centre'),
                            KNOBS_MODULE.decode_relative(127, 'twos'))


if __name__ == '__main__':
    unittest.main(verbosity=2 if '-v' in sys.argv else 1)
