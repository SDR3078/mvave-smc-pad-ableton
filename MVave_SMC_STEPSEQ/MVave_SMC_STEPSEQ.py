# Push-style step sequencer for the M-Vave SMC-PAD.
#
# The 16 pads edit the 16th notes of one drum lane in the selected MIDI clip,
# with LED feedback and a playhead that chases the clip. A second view turns the
# grid into four lanes by four steps, so a kick/clap/hat/open-hat groove is
# readable at a glance.
#
# Three properties hold everything else together:
#
#   The clip is the only state. The script stores no pattern. Steps are read
#   from and written to the bound MIDI clip through the Live API, which is what
#   makes Ctrl+Z undo a step edit, makes saving the set save the pattern, and
#   makes a note drawn with the mouse light up on the pads. Live's own playback
#   provides the timing -- this script never plays a note.
#
#   Step toggles and probability edits write only in response to user input.
#   Both views use the same edit paths.
#
#   Listeners drive rendering, not the input handler. Pressing a pad writes to
#   the clip and returns; the clip's notes listener fires and redraws. That is
#   why a mouse edit and a pad press produce identical LED updates, and it is
#   why nothing here writes to the clip during a render -- the listener would
#   feed itself.
#
# Every hardware number is in MIDI_Map.py. There are none in this file.

from __future__ import with_statement

import math
import time
import traceback

import Live
from _Framework.ControlSurface import ControlSurface

from .MIDI_Map import *
from .ParameterLocks import ParameterLocks
from .NativeRecording import NativeRecording


VIEW_FOCUS = 0
VIEW_OVERVIEW = 1

KNOB_CCS = (CC_LANE, CC_VELOCITY, CC_LENGTH, CC_SPARE)

# Clip properties whose change has to redraw the grid even though no note moved.
LOOP_PROPERTIES = ('loop_start', 'loop_end')

# How far the MOD + arrow lane picker can travel, as a bank index either side of
# LANE_SELECT_BASE. Derived so the clamped base reaches both 0 and 112 -- i.e.
# every pitch 0-127 is selectable -- whatever LANE_SELECT_BASE is set to.
# The extra index at each end exists to overshoot onto the 0 and 112 stops. When
# the series already lands on a stop -- any LANE_SELECT_BASE that is a multiple
# of 16 -- overshooting would derive the same base twice and the first arrow
# press off that stop would do nothing, so it is only added when needed.
LANE_BANK_MIN = -(LANE_SELECT_BASE // 16) - (1 if LANE_SELECT_BASE % 16 else 0)
LANE_BANK_MAX = ((112 - LANE_SELECT_BASE) // 16
                 + (1 if (112 - LANE_SELECT_BASE) % 16 else 0))


def _clamp(value, low, high):
    return max(low, min(value, high))


def decode_relative(value, mode):
    """One encoder click -> a signed number of steps.

    The two schemes are mutually ambiguous -- a value of 63 is +63 under 'twos'
    and -1 under 'centre' -- so which one is in use has to be configured rather
    than detected. See KNOB_MODE in MIDI_Map.py.
    """
    if mode == 'twos':
        return value if value < 64 else value - 128
    return value - 64


def lane_for_pad(pad_index, base=LANE_SELECT_BASE):
    """MOD + pad -> a drum-rack pitch.

    A Live drum rack ascends bottom-up: the lowest note sits bottom-left and the
    pitch climbs left to right, then upward. The pads are indexed top-left
    first, so the row is flipped and the layout on the controller matches the
    rack on screen.
    """
    row, col = divmod(pad_index, 4)
    return base + (3 - row) * 4 + col


def step_at(time, loop_start, step_length=STEP):
    """Which step index a time in clip beats falls in.

    Floor, not round. remove_notes_extended() clears the half-open window
    [t, t + STEP), so flooring is what makes "this pad is lit" and "pressing
    this pad clears it" agree about a note that is slightly off the grid: a note
    nudged to a 32nd lights the step whose window contains it, and that step
    erases it. Rounding to nearest would light a step whose window does not.
    """
    return int(math.floor((time - loop_start) / step_length + 1e-9))


def _guarded(where):
    """Keep an exception inside a Live callback from killing the script.

    An uncaught exception in a listener or in receive_midi disables the whole
    Remote Script until Live is restarted, and nothing in the UI says so -- the
    controller simply stops responding. Log.txt is the only place it can be
    seen, so every entry point Live can call is wrapped.
    """
    def decorate(method):
        def wrapper(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            except Exception:
                self._log_exception(where)
        wrapper.__name__ = method.__name__
        wrapper.__doc__ = method.__doc__
        return wrapper
    return decorate


class MVave_SMC_STEPSEQ(ControlSurface):
    __doc__ = " Push-style step sequencer for the M-Vave SMC-PAD "

    # Mirrors MVave_SMC_PAD's pattern, for the same reason: a sibling script
    # that owns a different port of this controller needs a way to find this
    # instance. See handle_encoder_cc().
    _active_instances = []

    def __init__(self, c_instance):
        # Plain attributes before ControlSurface.__init__, because Live can call
        # refresh_state() the moment it returns and it must not find a
        # half-built object. Nothing here touches the Live API.
        self._ready = False
        self._held_steps = {}
        self._activity_notes = {}
        self._activity_state = (None, False)
        self._lock_release_time = -1.0
        self._lock_hint_shown = False
        self._parameter_locks = ParameterLocks()
        self._native_recording = None
        self._continuous_envelopes = []
        self._continuous_previews = []
        self._preview_scheduled = False
        self._base_edits = []
        self._base_edit_scheduled = False
        self._clip = None
        self._controlled_track = None
        self._remembered_clips = []
        self._view = VIEW_FOCUS
        self._lane = DEFAULT_LANE
        self._bank = 0
        self._lane_window = DEFAULT_LANE
        self._page = 0
        self._mod = False
        self._mute_mode = False
        self._follow = FOLLOW_PLAYHEAD
        # Clamped exactly as _lane_base_by derives it at bank 0, so the two
        # cannot start out of step. Writing the raw constant here put every
        # LANE_SELECT_BASE above 112 outside the range the derivation below
        # guarantees, and MOD + pad then selected pitches past 127.
        self._lane_base = _clamp(LANE_SELECT_BASE, 0, 112)
        self._lane_bank = 0                     # MOD + arrow moves this, not the base
        self._paint_velocity = PAINT_VELOCITY
        self._btn_led = {}                      # what each button was last told
        self._grid = [COLOR_STEP_OFF] * 16      # what the clip says
        self._on = [False] * 16                 # which of those hold a note
        self._led = [None] * 16                 # what the device was last told
        self._playhead = None
        self._unhandled = set()
        self._exceptions_logged = set()
        self._logged_no_extended = False
        self._missing_listeners = []
        self._pads = {}
        for index, note in enumerate(PAD_NOTES):
            self._pads[note] = index
        for index, note in enumerate(PAD_NOTES_B):
            self._pads[note] = index
        self._buttons = tuple(n for n in (BTN_PLAY, BTN_VIEW, BTN_MOD,
                                          BTN_LEFT, BTN_RIGHT)
                                if n is not None and n >= 0)

        ControlSurface.__init__(self, c_instance)
        with self.component_guard():
            self._attach_song_listeners()
        self._ready = True
        if self not in MVave_SMC_STEPSEQ._active_instances:
            MVave_SMC_STEPSEQ._active_instances.append(self)
        # No explicit blank-the-grid pass here. The LED cache starts empty, so
        # the render below writes all sixteen pads once -- including the ones
        # that end up off, which clears whatever the previous preset or script
        # left lit. Blanking first would double that to 32 messages back to
        # back, which is the shape of write this device's input buffer does not
        # survive (HARDWARE.md 3.5).
        # Logged before the first bind, not after: if binding throws, this
        # line is the difference between "the script loaded and then something
        # went wrong" and no evidence at all that it ran.
        self._log('loaded. pads ch %d notes %s, buttons ch %d notes %s.'
                  % (PAD_CHANNEL + 1, _span(PAD_NOTES),
                     BUTTON_CHANNEL + 1, _span(self._buttons)))
        self._rebind()

    def disconnect(self):
        self._detach_song_listeners()
        self._detach_clip()
        self._all_leds_off()
        if self in MVave_SMC_STEPSEQ._active_instances:
            MVave_SMC_STEPSEQ._active_instances.remove(self)
        self._ready = False
        ControlSurface.disconnect(self)

    def refresh_state(self):
        # Called when Live enables the surface. The device may have been
        # repowered or switched presets since the last render, so the LED cache
        # is worthless -- drop it and repaint everything.
        ControlSurface.refresh_state(self)
        if not self._ready:
            return
        try:
            self._led = [None] * 16
            self._btn_led = {}      # the buttons went dark with the pads
            self._render()
        except Exception:
            # The only Live-called entry point that reads the clip without a
            # guard. If the bound clip died before Live re-enabled the surface,
            # the first attribute access raises straight into Live and takes
            # the script down until a restart.
            self._log_exception('refresh_state')

    # ------------------------------------------------------------------- midi

    def build_midi_map(self, midi_map_handle):
        # Forwarding sends these messages to receive_midi() instead of to a
        # track, which is what keeps a pad press from playing an instrument.
        ControlSurface.build_midi_map(self, midi_map_handle)
        handle = self._c_instance.handle()
        for note in self._pads:
            Live.MidiMap.forward_midi_note(handle, midi_map_handle,
                                           PAD_CHANNEL, note)
        for number in self._buttons:
            if BUTTON_IS_CC:
                Live.MidiMap.forward_midi_cc(handle, midi_map_handle,
                                             BUTTON_CHANNEL, number)
            else:
                Live.MidiMap.forward_midi_note(handle, midi_map_handle,
                                               BUTTON_CHANNEL, number)
        for cc in KNOB_CCS:
            Live.MidiMap.forward_midi_cc(handle, midi_map_handle,
                                         KNOB_CHANNEL, cc)

    def receive_midi(self, midi_bytes):
        try:
            if self._dispatch(midi_bytes):
                return
        except Exception:
            self._log_exception('receive_midi')
            return
        # Whatever this script does not own goes back to the framework.
        # Swallowing it is one of this repo's documented silent failures --
        # see FINDINGS.md, "Failures that are silent by construction".
        ControlSurface.receive_midi(self, midi_bytes)

    def _dispatch(self, midi_bytes):
        if len(midi_bytes) != 3:
            return False
        status, data1, data2 = midi_bytes[0], midi_bytes[1], midi_bytes[2]
        kind = status & 0xF0
        channel = status & 0x0F
        if LOG_MIDI:
            self._log('midi %02X %d %d' % (status, data1, data2))

        if kind == 0x90 or kind == 0x80:
            # This device releases with note-on velocity 0 rather than a real
            # note-off (HARDWARE.md 2.2). Both forms are accepted anyway.
            pressed = (kind == 0x90 and data2 > 0)
            if channel == PAD_CHANNEL and data1 in self._pads:
                # data2 is the strike velocity on a press, 0 on a release.
                self._on_pad(self._pads[data1], pressed, data2)
                return True
            if (not BUTTON_IS_CC and channel == BUTTON_CHANNEL
                    and data1 in self._buttons):
                self._on_button(data1, pressed)
                return True
        elif kind == 0xB0:
            if (BUTTON_IS_CC and channel == BUTTON_CHANNEL
                    and data1 in self._buttons):
                self._on_button(data1, data2 > 0)
                return True
            if channel == KNOB_CHANNEL and data1 in KNOB_CCS:
                self._on_cc(data1, data2)
                return True

        self._log_unhandled(status, data1, data2)
        return False

    def handle_encoder_cc(self, cc, value):
        """Entry point for a sibling script that owns the encoder port.

        The pads and the encoders arrive on different MIDI ports and a Remote
        Script gets exactly one input port (HARDWARE.md 1.1), so unless the
        sequencer preset can move the encoder CCs onto the pad port, the knobs
        can only reach this script second-hand. MVave_SMC_KNOBS already does the
        same trick in the other direction, reaching into
        MVave_SMC_PAD._active_instances to move the session box.

        Nothing in this repo calls this yet. It exists so that "the knobs turned
        out to be on the wrong port" is a ten-line addition to the encoder
        script rather than a redesign of this one.
        """
        try:
            self._on_cc(cc, value)
        except Exception:
            self._log_exception('handle_encoder_cc')

    # ---------------------------------------------------------------- binding

    def _attach_song_listeners(self):
        view = self.song().view
        if not view.selected_track_has_listener(self._on_selection_changed):
            view.add_selected_track_listener(self._on_selection_changed)
        if not view.detail_clip_has_listener(self._on_selection_changed):
            view.add_detail_clip_listener(self._on_selection_changed)

    def _detach_song_listeners(self):
        try:
            view = self.song().view
        except Exception:
            return
        if view.selected_track_has_listener(self._on_selection_changed):
            view.remove_selected_track_listener(self._on_selection_changed)
        if view.detail_clip_has_listener(self._on_selection_changed):
            view.remove_detail_clip_listener(self._on_selection_changed)

    @_guarded('selection listener')
    def _on_selection_changed(self):
        self._rebind()

    def _detach_clip(self):
        self._stop_native_recording(defer=True)
        self._base_edits = []
        self._held_steps.clear()
        clip = self._clip
        self._clip = None
        self._playhead = None
        if clip is None:
            return
        # Guarded as a block, not per call: if the clip was deleted rather than
        # deselected, the object is dead and the first attribute access raises.
        # Live drops a dead object's listeners itself, so there is nothing left
        # to clean up in that case.
        try:
            if clip.notes_has_listener(self._on_notes_changed):
                clip.remove_notes_listener(self._on_notes_changed)
            if clip.playing_position_has_listener(self._on_playhead):
                clip.remove_playing_position_listener(self._on_playhead)
            if clip.playing_status_has_listener(self._on_playhead):
                clip.remove_playing_status_listener(self._on_playhead)
            self._detach_loop_listeners(clip)
        except Exception:
            pass

    @_guarded('rebind')
    def _rebind(self):
        view = self.song().view
        if self._controlled_track is None and self._drum_rack(view.selected_track) is not None:
            self._controlled_track = view.selected_track
        target = self._controlled_track
        if target is not None and hasattr(target, 'clip_slots'):
            # A removed track must release its target instead of dangling.
            if target not in self.song().tracks:
                self._controlled_track = None
                target = None
        candidate = view.detail_clip
        clip = None
        if target is None:
            # Retain upstream generic-MIDI behavior until a Drum Rack is bound.
            if candidate is not None and candidate.is_midi_clip:
                clip = candidate
        else:
            clips = self._midi_clips(target)
            if view.selected_track == target and candidate in clips:
                clip = candidate
            elif self._clip in clips:
                clip = self._clip
            else:
                clip = self._preferred_clip(target, clips)
        if clip == self._clip:
            self._render()
            return
        self._detach_clip()
        if target is not None and clip is not None:
            self._remembered_clips = [(t, c) for t, c in self._remembered_clips if t != target]
            self._remembered_clips.append((target, clip))

        if clip is not None and not hasattr(clip, 'get_notes_extended'):
            # Live 10 and older. Announce it rather than rendering an empty
            # grid forever and leaving the user to guess.
            # Latched: _rebind() is reached from a listener registered on both
            # selected_track and detail_clip, so one click can call it twice.
            # On the Live 10 host this line exists to warn, clicking around --
            # the user's first response to "the pads do nothing" -- is exactly
            # what would bury it.
            if not self._logged_no_extended:
                self._logged_no_extended = True
                self._log('this Live has no get_notes_extended() -- Live 11 or '
                          'newer is required. Running with no clip bound.')
            clip = None

        if clip is not None:
            clip.add_notes_listener(self._on_notes_changed)
            clip.add_playing_position_listener(self._on_playhead)
            clip.add_playing_status_listener(self._on_playhead)
            self._attach_loop_listeners(clip)
        self._clip = clip
        self._clamp_pages()
        self._render()

    def _attach_loop_listeners(self, clip):
        """Watch the loop brace, so a mouse drag is not invisible.

        Dragging the brace changes no note, so the notes listener stays silent.
        Without this the grid keeps showing a page the loop no longer has, and
        every pad on it is refused by toggle_step without writing anything --
        which means the notes listener never fires either, and the stale page
        stays lit until some unrelated event happens to call _clamp_pages().

        Probed rather than assumed, the same way the pad script probes its
        clip-slot setters: on a Live whose Clip does not expose these, the cost
        is the stale grid described above, not a dead script.
        """
        for name in LOOP_PROPERTIES:
            adder = getattr(clip, 'add_%s_listener' % name, None)
            if adder is None:
                if name not in self._missing_listeners:
                    self._missing_listeners.append(name)
                    self._log('clip has no add_%s_listener() -- the grid will '
                              'not follow the loop brace' % name)
                continue
            adder(self._on_loop_changed)

    def _detach_loop_listeners(self, clip):
        for name in LOOP_PROPERTIES:
            has = getattr(clip, '%s_has_listener' % name, None)
            remover = getattr(clip, 'remove_%s_listener' % name, None)
            if has is None or remover is None:
                continue
            if has(self._on_loop_changed):
                remover(self._on_loop_changed)

    @_guarded('loop listener')
    def _on_loop_changed(self):
        # The brace moved: the visible page may now be past the end of the loop,
        # and the steps beyond it have to go dark.
        self._clamp_pages()
        self._render()

    # ------------------------------------------------------------ write path

    def toggle_step(self, pitch, step_index, velocity=None):
        """Add or remove one 16th note. The only place the clip is written.

        velocity is the strike force when the pads are velocity-sensitive;
        None falls back to the painted default.
        """
        clip = self._clip
        if clip is None or not 0 <= pitch <= 127:
            return
        if not 0 <= step_index < STEPS_MAX:
            return
        if step_index >= self._step_count():
            # v1 edits inside the loop only. Asking _step_count() rather than
            # comparing times is what keeps this in step with the render: both
            # sides now call the same step in or out of the loop, so "this pad
            # is lit" and "pressing this pad clears it" cannot disagree.
            return
        time = clip.loop_start + step_index * STEP
        existing = clip.get_notes_extended(pitch, 1, time, STEP)
        if len(existing):
            clip.remove_notes_extended(pitch, 1, time, STEP)
        else:
            spec = Live.Clip.MidiNoteSpecification(
                pitch=pitch, start_time=time, duration=STEP,
                velocity=(velocity or self._paint_velocity), mute=False)
            clip.add_new_notes((spec,))
        # Deliberately no render. The clip's notes listener fires on the change
        # and renders -- the same path a mouse edit or a Ctrl+Z takes, so all
        # three produce identical LEDs. Rendering here would double the work and
        # invite a write-render-write loop.

    # ------------------------------------------------------------------ input

    def _on_pad(self, index, pressed, velocity=None):
        if not pressed:
            held = self._held_steps.pop(index, None)
            if held is not None and held['edited']:
                self._lock_release_time = time.monotonic()
                self._log('lock pad released: step %d' % (held['step'] + 1))
            if held is not None and not held['edited'] and held['clip'] == self._clip:
                self.toggle_step(held['pitch'], held['step'], held['velocity'])
            return
        if self._mute_mode:
            self._toggle_drum_mute(lane_for_pad(index, self._lane_base))
            return
        if self._mod:
            self._select_lane(lane_for_pad(index, self._lane_base))
            return
        if self._view == VIEW_FOCUS:
            pitch, step = self._lane, self._bank * 16 + index
        else:
            row, col = divmod(index, 4)
            pitch, step = self._lane_window + row, self._page * 4 + col
        if self._clip is None or step >= self._step_count():
            return
        # Repeated note-ons must not erase an in-progress lock gesture.
        if index in self._held_steps:
            return
        self._held_steps[index] = dict(clip=self._clip, pitch=pitch, step=step,
            velocity=velocity if USE_STRIKE_VELOCITY else None, edited=False)

    def handle_macro_lock(self, parameter, delta):
        """Return True when this surface owns the knob gesture."""
        recording = self._native_recording
        if recording is not None:
            if not self.song().is_playing or not self.song().session_record:
                self._stop_native_recording()
            else:
                try:
                    for held in self._held_steps.values():
                        held['edited'] = True
                    recording.turn(parameter, delta)
                except Exception:
                    self._log_exception('native recording knob')
                    self._stop_native_recording()
                    self.show_message('SMC recording stopped; see Live Log.txt')
                return True
        if any(clip == self._clip and param == parameter for clip, param in self._continuous_envelopes):
            # Audition the manual value, then resume the unchanged curve when
            # the knob is idle. Never collapse continuous curves into steps.
            if not self._held_steps:
                if parameter.is_enabled:
                    parameter.value = self._parameter_locks._changed(parameter, parameter.value, delta)
                    entry = next((item for item in self._continuous_previews
                        if item['parameter'] == parameter), None)
                    if entry is None:
                        self._continuous_previews.append(dict(parameter=parameter, time=time.monotonic()))
                    else:
                        entry['time'] = time.monotonic()
                    if not self._preview_scheduled:
                        self._preview_scheduled = True
                        self.schedule_message(3, self._resume_continuous_previews)
                return True
            self._continuous_envelopes = [(c, p) for c, p in self._continuous_envelopes
                if not (c == self._clip and p == parameter)]
        held = list(self._held_steps.values())
        if held:
            # Consume even a failed lock gesture: never delete its note or
            # accidentally turn it into a global parameter change.
            first_edit = any(not item['edited'] for item in held)
            for item in held:
                item['edited'] = True
            try:
                clip = self._clip
                if clip is None:
                    return True
                # Only lock existing notes, and use the rack explicitly selected
                # by the user. Automatic per-drum rack binding comes later.
                steps = [h['step'] for h in held if h['clip'] == clip and
                    clip.get_notes_extended(h['pitch'], 1,
                        clip.loop_start + h['step'] * STEP, STEP)]
                if not steps:
                    self.show_message('SMC: hold an active step to add a lock')
                    return True
                self._parameter_locks.adjust(clip, parameter, steps, delta, STEP)
                if first_edit:
                    self._log('parameter lock started: %s steps %s' %
                              (parameter.name, [n + 1 for n in steps]))
                self.show_message('Lock %s: steps %s' % (parameter.name,
                    ', '.join(str(n + 1) for n in steps)))
            except Exception:
                self._log_exception('parameter lock')
                self.show_message('SMC lock failed; see Live Log.txt')
            return True
        # Knob and pad messages arrive through separate ports. Ignore the
        # short tail of a lock gesture instead of treating it as a base edit.
        if time.monotonic() - self._lock_release_time < 0.3:
            return True
        if self._clip is not None:
            getter = getattr(self._clip, 'automation_envelope', None)
            if getter is None:
                return False
            envelope = getter(parameter)
            if envelope is not None:
                for edit in self._base_edits:
                    if edit['clip'] == self._clip and edit['parameter'] == parameter:
                        edit['delta'] += delta
                        break
                else:
                    self._base_edits.append(dict(clip=self._clip, parameter=parameter, delta=delta))
                if not self._base_edit_scheduled:
                    self._base_edit_scheduled = True
                    self.schedule_message(2, self._flush_base_edits)
                return True
            return self._parameter_locks.adjust_base(self._clip, parameter, delta, STEP)
        return False

    def _flush_base_edits(self):
        self._base_edit_scheduled = False
        edits, self._base_edits = self._base_edits, []
        for edit in edits:
            if edit['clip'] != self._clip:
                continue
            try:
                self._parameter_locks.adjust_base(edit['clip'], edit['parameter'], edit['delta'], STEP)
            except Exception:
                self._log_exception('base macro edit')
                self.show_message('SMC base edit failed; see Live Log.txt')

    def _resume_continuous_previews(self):
        self._preview_scheduled = False
        keep = []
        for entry in self._continuous_previews:
            if time.monotonic() - entry['time'] < 0.25:
                keep.append(entry)
            else:
                try:
                    entry['parameter'].re_enable_automation()
                except Exception:
                    self._log_exception('resume continuous automation')
        self._continuous_previews = keep
        if keep:
            self._preview_scheduled = True
            self.schedule_message(1, self._resume_continuous_previews)

    def _toggle_native_recording(self):
        if self._native_recording is not None:
            self._stop_native_recording()
            self.show_message('Free REC OFF - playback continues')
            self._paint_buttons()
            return
        try:
            track = self._controlled_track or self.song().view.selected_track
            managed, device = self.drum_macro_target()
            if device is None or self._clip is None:
                raise RuntimeError('Select a drum Instrument Rack and Session clip')
            self._base_edits = []
            self._continuous_previews = []
            self._native_recording = NativeRecording(self.song(), track, self._clip)
            self._log('native Session automation recording ON')
            self.show_message('Free REC ON - turn macro knobs; Record + Play ends recording')
        except Exception as exc:
            self._log('native recording not started: %s' % exc)
            self.show_message('SMC: %s' % exc)
        self._paint_buttons()

    def _stop_native_recording(self, defer=False):
        recording, self._native_recording = self._native_recording, None
        if recording is None:
            return
        if defer:
            self.schedule_message(1, lambda: self._cleanup_native_recording(recording))
        else:
            self._cleanup_native_recording(recording)

    def _cleanup_native_recording(self, recording):
        try:
            recording.stop()
        except Exception:
            self._log_exception('stop native recording')
        for parameter, value in recording.parameters:
            if not any(c == recording.clip and p == parameter for c, p in self._continuous_envelopes):
                self._continuous_envelopes.append((recording.clip, parameter))
            self._parameter_locks._owned = [state for state in self._parameter_locks._owned
                if not (state['clip'] == recording.clip and state['parameter'] == parameter)]
        self._log('native Session automation recording OFF')

    def _on_button(self, number, pressed):
        if number == BTN_VIEW:
            self._mute_mode = pressed
            self._held_steps.clear()
            self._render()
            return
        if number == BTN_MOD:
            self._mod = pressed
            self._held_steps.clear()
            self._render()       # lights while held, clears on release
            return
        if not pressed:
            return
        if number == BTN_PLAY:
            self._log('Play press: Record modifier=%s native recording=%s' %
                (self._mod, self._native_recording is not None))
            if self._mod:
                self._toggle_native_recording()
            else:
                self._toggle_transport()
        elif number == BTN_LEFT:
            # Held MOD turns the arrows into a lane-bank control, because
            # MOD + pad only reaches the 16 pitches from _lane_base and a drum
            # rack has more rows than that.
            self._arrow(-1)
        elif number == BTN_RIGHT:
            self._arrow(1)

    def _on_cc(self, cc, value):
        delta = decode_relative(value, KNOB_MODE)
        if delta == 0:
            return
        if cc == CC_LANE:
            if self._view == VIEW_FOCUS:
                self._lane = _clamp(self._lane + delta, 0, 127)
            else:
                self._lane_window = _clamp(self._lane_window + delta, 0, 124)
            self._render()
        elif cc == CC_VELOCITY:
            self._paint_velocity = _clamp(self._paint_velocity + delta, 1, 127)
        elif cc == CC_LENGTH:
            self._set_length(self._loop_steps() + delta)
        elif cc == CC_SPARE:
            pass                            # reserved: nudge/swing later

    def _select_lane(self, pitch):
        self._stop_native_recording()
        self._held_steps.clear()
        self._lane = pitch
        self._follow_drum_rack()
        if self._view == VIEW_OVERVIEW:
            # Otherwise the press has no visible effect: put the chosen lane on
            # the top row of the window.
            self._lane_window = _clamp(pitch, 0, 124)
        self._render()

    def _drum_rack(self, track=None):
        def find(devices):
            for device in devices:
                if getattr(device, 'can_have_drum_pads', False):
                    return device
                if getattr(device, 'can_have_chains', False):
                    for chain in device.chains:
                        result = find(chain.devices)
                        if result is not None:
                            return result
            return None
        track = track if track is not None else (self._controlled_track or self.song().view.selected_track)
        return find(getattr(track, 'devices', ()))

    def _midi_clips(self, track):
        return [slot.clip for slot in getattr(track, 'clip_slots', ())
                if slot.has_clip and slot.clip.is_midi_clip]

    def _preferred_clip(self, track, clips):
        playing = next((clip for clip in clips if clip.is_playing), None)
        if playing is not None:
            return playing
        remembered = next((c for t, c in self._remembered_clips if t == track and c in clips), None)
        return remembered or (clips[0] if clips else None)

    def _arrow(self, direction):
        if self._held_steps and not self._mod and not self._mute_mode:
            self._adjust_probability(direction)
            return
        if self._mod:
            self._lane_base_by(direction * 16)
        elif self._mute_mode:
            self._page_by(direction)
        else:
            tracks = [track for track in self.song().tracks
                      if self._drum_rack(track) is not None]
            if not tracks:
                self._page_by(direction)
                return
            current = self._controlled_track
            index = tracks.index(current) if current in tracks else (-1 if direction > 0 else len(tracks))
            target = tracks[_clamp(index + direction, 0, len(tracks) - 1)]
            if target == current:
                return
            self._held_steps.clear()
            self._controlled_track = target
            self._lane = DEFAULT_LANE
            self._lane_base = LANE_SELECT_BASE
            self._lane_bank = 0
            self._bank = self._page = 0
            self._mute_mode = self._mod = False
            # Rebind without launching or stopping any clip.
            self._detach_clip()
            self.song().view.selected_track = target
            self._rebind()
            self._follow_drum_rack()
            self.show_message('SMC track: %s' % target.name)

    def _adjust_probability(self, direction):
        """Edit native note chance; preserve the Live note vector and note IDs."""
        held = list(self._held_steps.values())
        for item in held:
            # Consume even an empty/failed edit so release never toggles a step.
            item['edited'] = True
        clip = self._clip
        if clip is None:
            return
        changed = []
        try:
            for item in held:
                if item['clip'] != clip or not 0 <= item['step'] < self._step_count():
                    continue
                notes = clip.get_notes_extended(item['pitch'], 1,
                    clip.loop_start + item['step'] * STEP, STEP)
                if not notes:
                    continue
                for note in notes:
                    chance = float(note.probability)
                    if direction < 0:
                        choices = [p for p in PROBABILITY_LEVELS if p < chance - 1e-6]
                        note.probability = choices[-1] if choices else PROBABILITY_LEVELS[0]
                    else:
                        choices = [p for p in PROBABILITY_LEVELS if p > chance + 1e-6]
                        note.probability = choices[0] if choices else PROBABILITY_LEVELS[-1]
                # Pass the original MidiNoteVector, never a Python list/tuple.
                clip.apply_note_modifications(notes)
                changed.extend(int(round(note.probability * 100)) for note in notes)
            if changed:
                self.show_message('SMC probability: %s%%' %
                    '/'.join(str(p) for p in sorted(set(changed))))
            else:
                self.show_message('SMC: hold an active step to change probability')
        except Exception:
            self._log_exception('probability edit')
            self.show_message('SMC probability edit failed; see Live Log.txt')
        self._render()

    @staticmethod
    def _probability_color(chance):
        # External Chance values use the nearest display level; no clip write.
        index = min(range(len(PROBABILITY_LEVELS)),
                    key=lambda i: abs(PROBABILITY_LEVELS[i] - chance))
        return PROBABILITY_COLORS[index]

    def _drum_pad(self, pitch, rack=None):
        rack = self._drum_rack() if rack is None else rack
        if rack is None:
            return None
        return next((pad for pad in rack.drum_pads if pad.note == pitch), None)

    def drum_macro_target(self):
        """Managed Drum Rack tracks must never fall back to another drum."""
        rack = self._drum_rack()
        if rack is None:
            return False, None
        pad = self._drum_pad(self._lane, rack)
        if pad is None:
            return True, None
        for chain in pad.chains:
            for device in chain.devices:
                if getattr(device, 'class_name', '') == 'InstrumentGroupDevice':
                    return True, device
        return True, None

    def _follow_drum_rack(self):
        rack = self._drum_rack()
        if rack is None:
            return
        pad = self._drum_pad(self._lane, rack)
        if pad is None:
            return
        rack.view.selected_drum_pad = pad
        managed, device = self.drum_macro_target()
        if device is not None:
            if self.song().view.selected_track == (self._controlled_track or self.song().view.selected_track):
                self.song().view.select_device(device)
            self.show_message('SMC drum: %s' % pad.name)
        else:
            self.show_message('SMC: %s needs an Instrument Rack for macros' % pad.name)

    def _toggle_drum_mute(self, pitch):
        pad = self._drum_pad(pitch)
        if pad is None or not pad.chains:
            return
        pad.mute = not pad.mute
        self.show_message('%s: %s' % (pad.name, 'muted' if pad.mute else 'unmuted'))
        self._render()

    def _toggle_view(self):
        # Keep the musical position across the switch rather than jumping back
        # to the start: a focus bank is 16 steps, an overview page is 4.
        if self._view == VIEW_FOCUS:
            self._view = VIEW_OVERVIEW
            self._page = self._bank * 4
        else:
            self._view = VIEW_FOCUS
            self._bank = self._page // 4
        self._clamp_pages()
        self._render()

    def _lane_base_by(self, delta):
        """Move the MOD + pad lane picker up or down a bank of 16 pitches.

        The bank INDEX is the state and the base is derived from it, because
        the two obvious implementations each lose something. Clamping the base
        directly knocks it off the 16-pitch series it started on -- 36, 20, 4,
        then 0 -- and strands it on 0+16k, where the default drum-rack bank at
        36 is gone. Refusing an out-of-range move keeps the series but puts
        pitches 0-3 and 116-127 permanently out of reach, and MOD + pad is the
        only lane control this hardware can offer. Moving the index and
        clamping the derived base keeps both: the end stops are pitch 0 and
        112, and stepping back off either stop returns to the original series.
        """
        self._lane_bank = _clamp(self._lane_bank + delta // 16,
                                 LANE_BANK_MIN, LANE_BANK_MAX)
        self._lane_base = _clamp(LANE_SELECT_BASE + 16 * self._lane_bank, 0, 112)
        rack = self._drum_rack()
        if rack is not None:
            rack.view.drum_pads_scroll_position = self._lane_base // 4
        message = 'Drum bank: MIDI notes %d-%d' % (self._lane_base, self._lane_base + 15)
        self._log(message)
        if hasattr(self, 'show_message'):
            self.show_message(message)
        self._render()

    def _page_by(self, delta):
        # Manual paging stops the chase -- otherwise the next audio buffer yanks
        # the view back and the button looks broken.
        self._follow = False
        if self._view == VIEW_FOCUS:
            self._bank = self._bank + delta
        else:
            self._page = self._page + delta
        self._clamp_pages()
        # ...but page back onto the playhead and you have caught up with the
        # music, so resume. Without this the only way to re-arm following is to
        # stop the transport, which is the one thing you do not want to do while
        # playing -- paging away became a mode you could not leave.
        if self._playhead is not None and self._pads_for_step(self._playhead):
            self._follow = FOLLOW_PLAYHEAD
        first = self._bank * 16 if self._view == VIEW_FOCUS else self._page * 4
        width = 16 if self._view == VIEW_FOCUS else 4
        message = 'Steps %d-%d of %d; release Stop to see pattern' % (
            first + 1, min(first + width, self._step_count()), self._step_count())
        self._log(message)
        if hasattr(self, 'show_message'):
            self.show_message(message)
        self._render()

    def _toggle_transport(self):
        song = self.song()
        if song.is_playing:
            self._stop_native_recording()
            song.stop_playing()
        else:
            song.start_playing()
        self._paint_buttons()

    def _loop_steps(self):
        """The loop's true length in steps, unclamped.

        _step_count() is the VIEW ceiling and stops at STEPS_MAX. Feeding that
        back to _set_length as if it were the current length turned one click
        into a truncation on any loop longer than STEPS_MAX steps: a 128-beat
        loop became 64, in either direction, silently, dragging the clip's end
        marker in with it.
        """
        clip = self._clip
        if clip is None:
            return 0
        return max(0, step_at(clip.loop_end - 1e-9, clip.loop_start) + 1)

    def _set_length(self, steps):
        clip = self._clip
        if clip is None:
            return
        # Ceiling is the larger of the view limit and the loop's real length,
        # so the knob can shorten a long loop step by step but can never
        # shorten one merely because it is longer than the grid can show.
        end = clip.loop_start + _clamp(steps, 1, max(STEPS_MAX,
                                                     self._loop_steps())) * STEP
        try:
            # The end marker has to stay at or past the loop end at every
            # intermediate point, so growing moves the marker first and
            # shrinking moves the loop first.
            if end > clip.loop_end:
                if clip.end_marker < end:
                    clip.end_marker = end
                clip.loop_end = end
            else:
                clip.loop_end = end
                if clip.end_marker > end:
                    clip.end_marker = end
        except Exception:
            self._log_exception('set pattern length')
        self._clamp_pages()
        self._render()

    # --------------------------------------------------------------- geometry

    def _step_count(self):
        clip = self._clip
        if clip is None:
            return 0
        # Ceiling, expressed through the same floor the rest of the file uses.
        # round() disagrees with step_at() whenever the loop is not a whole
        # number of 16ths -- half of all lengths -- and because BOTH the render
        # gate and the write gate ask this function, they agreed with each other
        # and were wrong together: the last step went dark and refused to clear.
        return _clamp(step_at(clip.loop_end - 1e-9, clip.loop_start) + 1,
                      0, STEPS_MAX)

    def _clamp_pages(self):
        last = max(0, self._step_count() - 1)
        self._bank = _clamp(self._bank, 0, last // 16)
        self._page = _clamp(self._page, 0, last // 4)

    def _pads_for_step(self, step):
        """Which pads show a given step in the current view."""
        if self._view == VIEW_FOCUS:
            index = step - self._bank * 16
            return (index,) if 0 <= index < 16 else ()
        col = step - self._page * 4
        return (col, col + 4, col + 8, col + 12) if 0 <= col < 4 else ()

    def _empty_color(self, step):
        if COLOR_STEP_DOWNBEAT and step % 4 == 0:
            return COLOR_STEP_DOWNBEAT
        return COLOR_STEP_EMPTY

    # -------------------------------------------------------------- rendering

    @_guarded('notes listener')
    def _on_notes_changed(self):
        self._render()

    @_guarded('playhead listener')
    def _on_playhead(self):
        clip = self._clip
        step = None
        position = None
        if clip is not None and clip.is_playing:
            position = clip.playing_position
            step = step_at(position, clip.loop_start)
            if not 0 <= step < self._step_count():
                step = None
        activity_changed = self._update_activity_position(step, position)
        previous = self._playhead
        if step == previous:
            # Pulse off halfway through each step, even for consecutive hits.
            # No note queries or extra timers on this audio-buffer callback.
            if activity_changed:
                self._paint()
            return
        self._playhead = step
        if step is None:
            if self._native_recording is not None:
                self.schedule_message(1, self._finish_native_after_stop)
            # Stopping restores following, so a manual page is temporary rather
            # than sticky and there is no mode to get stuck in.
            self._follow = FOLLOW_PLAYHEAD
        else:
            if (FOLLOW_RESUMES_ON_WRAP and not self._follow
                    and previous is not None and step < previous):
                # The step number went backwards, so the loop came round again.
                # Resume: paging away is a peek at one cycle, not a mode. Without
                # this the view stays stranded until you page back or stop.
                self._follow = FOLLOW_PLAYHEAD
            if (self._follow and self._worth_following(step)
                    and self._scroll_to(step)):
                self._render()  # the window moved, so the whole grid is stale
                return
        self._paint()

    def _finish_native_after_stop(self):
        if not self.song().is_playing:
            self._stop_native_recording()
            self._paint_buttons()

    def _worth_following(self, step):
        """Is this step worth banking the whole view onto?

        A loop brace dragged off the grid leaves a final step with only a sliver
        of in-loop time. Chasing it banks the view there and back within a few
        tens of milliseconds, twice per cycle -- the burst of LED writes this
        device's input buffer does not survive (HARDWARE.md 3.5). The step is
        still lit, still writable and still reachable with the arrows; only the
        automatic scroll declines to jump for it.
        """
        clip = self._clip
        if clip is None:
            return False
        return (clip.loop_end - (clip.loop_start + step * STEP)) >= STEP / 2.0

    def _scroll_to(self, step):
        """Put `step` on the visible window. True if the window actually moved."""
        if self._view == VIEW_FOCUS:
            target = step // 16
            if target == self._bank:
                return False
            self._bank = target
        else:
            target = step // 4
            if target == self._page:
                return False
            self._page = target
        self._clamp_pages()
        return True

    def _render(self):
        self._refresh()
        self._paint()

    def _refresh(self):
        """Read the clip into the pad grid. The only place the clip is read."""
        self._refresh_activity()
        self._grid = [COLOR_STEP_OFF] * 16
        self._on = [False] * 16
        clip = self._clip
        if clip is None:
            if COLOR_NO_CLIP:
                self._grid[0] = COLOR_NO_CLIP
            return
        if self._view == VIEW_FOCUS:
            self._refresh_focus(clip)
        else:
            self._refresh_overview(clip)

    def _update_activity_position(self, step, position):
        state = (None, False)
        if (self._mute_mode or self._mod) and step is not None:
            phase = (position - self._clip.loop_start) / STEP - step
            state = (step, phase < DRUM_ACTIVITY_STEP_FRACTION)
        changed = state != self._activity_state
        self._activity_state = state
        return changed

    def _refresh_activity(self):
        """Cache visible drums' programmed steps; playback only consults cache."""
        self._activity_notes = {}
        self._activity_state = (None, False)
        clip = self._clip
        if clip is None or not (self._mute_mode or self._mod):
            return
        total = self._step_count()
        if total <= 0:
            return
        notes = clip.get_notes_extended(self._lane_base, 16,
            clip.loop_start, min(total * STEP, clip.loop_end - clip.loop_start))
        for note in notes:
            step = step_at(note.start_time, clip.loop_start)
            if 0 <= step < total and not note.mute:
                self._activity_notes.setdefault(step, set()).add(int(note.pitch))
        if clip.is_playing:
            position = clip.playing_position
            step = step_at(position, clip.loop_start)
            if 0 <= step < total:
                self._update_activity_position(step, position)

    def _refresh_focus(self, clip):
        first = self._bank * 16
        total = self._step_count()
        probabilities = {}
        for index in range(16):
            if first + index < total:
                self._grid[index] = self._empty_color(first + index)
        notes = clip.get_notes_extended(self._lane, 1,
                                        clip.loop_start + first * STEP,
                                        16 * STEP)
        for note in notes:
            index = step_at(note.start_time, clip.loop_start) - first
            # Gated on `total` as well as on the window: Live keeps notes that
            # sit past the loop brace, and the read window can reach them.
            # Lighting one would promise a step that toggle_step refuses.
            if 0 <= index < 16 and first + index < total:
                # Multiple notes in a step display the highest note chance.
                probabilities[index] = max(probabilities.get(index, 0.0),
                    float(getattr(note, 'probability', 1.0)))
                self._grid[index] = self._probability_color(probabilities[index])
                self._on[index] = True

    def _refresh_overview(self, clip):
        first = self._page * 4
        total = self._step_count()
        for row in range(4):
            for col in range(4):
                if first + col < total:
                    self._grid[row * 4 + col] = self._empty_color(first + col)
        # One read for all four lanes rather than four.
        notes = clip.get_notes_extended(self._lane_window, 4,
                                        clip.loop_start + first * STEP,
                                        4 * STEP)
        for note in notes:
            row = int(note.pitch) - self._lane_window
            col = step_at(note.start_time, clip.loop_start) - first
            if 0 <= row < 4 and 0 <= col < 4 and first + col < total:
                self._grid[row * 4 + col] = LANE_COLORS[row]
                self._on[row * 4 + col] = True

    def _paint(self):
        """Overlay the playhead on the grid and send only what changed."""
        colors = list(self._grid)
        if self._mute_mode or self._mod:
            rack = self._drum_rack()
            colors = [0] * 16
            for index in range(16):
                pitch = lane_for_pad(index, self._lane_base)
                pad = self._drum_pad(pitch, rack)
                if pad is not None and pad.chains:
                    colors[index] = 14 if pad.mute else 5
                    if self._mod and not self._mute_mode and pitch == self._lane:
                        colors[index] = 40
                    activity_step, pulse = self._activity_state
                    if pulse and pitch in self._activity_notes.get(activity_step, ()):
                        colors[index] = COLOR_DRUM_ACTIVITY
        elif self._playhead is not None:
            for index in self._pads_for_step(self._playhead):
                colors[index] = (COLOR_PLAYHEAD_ON if self._on[index]
                                 else COLOR_PLAYHEAD)
        for index, color in enumerate(colors):
            if self._led[index] != color:
                self._led[index] = color
                self._send_led(index, color)
        self._paint_buttons()

    def _paint_buttons(self):
        """Show state on the buttons: transport, view, and the held modifier.

        Driven from _paint() rather than from a song listener. _paint() runs on
        every playhead step, so the transport LED follows within one step of the
        transport moving, and every button press repaints directly. That avoids
        adding an is_playing listener whose attach/detach lifecycle would be one
        more thing to get right against an API this file cannot test against.
        The visible cost: starting the transport while no clip is playing leaves
        the play LED stale until the next press or selection change.
        """
        if not BUTTON_LEDS:
            return
        try:
            playing = bool(self.song().is_playing)
        except Exception:
            playing = False
        for note, on in ((BTN_PLAY, playing),
                         (BTN_VIEW, self._mute_mode),
                         (BTN_MOD, self._mod or self._native_recording is not None)):
            if note is None or note < 0:
                continue
            color = BTN_LED_ON if on else BTN_LED_OFF
            if self._btn_led.get(note) != color:
                self._btn_led[note] = color
                self._send_midi((0x90 | BUTTON_CHANNEL, note, color))

    def _send_led(self, index, color):
        # Note-on, always. This device ignores a real note-off entirely and
        # silently, so velocity 0 is the only "off" it understands
        # (HARDWARE.md 3.3). The diff in _paint() is what keeps this from
        # becoming a bulk write, which the device's input buffer does not
        # survive (HARDWARE.md 3.5).
        self._send_midi((0x90 | LED_CHANNEL, LED_NOTES[index], color))

    def _all_leds_off(self):
        for index in range(16):
            self._led[index] = COLOR_STEP_OFF
            self._send_led(index, COLOR_STEP_OFF)
        if BUTTON_LEDS:
            for note in (BTN_PLAY, BTN_VIEW, BTN_MOD):
                if note is not None and note >= 0:
                    self._btn_led[note] = BTN_LED_OFF
                    self._send_midi((0x90 | BUTTON_CHANNEL, note, BTN_LED_OFF))

    # ---------------------------------------------------------------- logging

    def _log(self, message):
        self.log_message(LOG_PREFIX + message)

    def _log_exception(self, where):
        # Latched, like _log_unhandled below, and for a sharper reason: _guarded
        # wraps _on_playhead, which fires per audio buffer. One persistent fault
        # there would write a full traceback ~90 times a second and bury the
        # first copy -- the only one still holding the original context.
        #
        # Keyed on the last line of the traceback (the exception type and
        # message) rather than on `where` alone, so a later, different fault in
        # the same place is still heard. Capped like _unhandled so a fault whose
        # message varies every time cannot fill Log.txt either.
        # Keyed on the deepest frame as well as the exception line, matching
        # MVave_SMC_KNOBS: `where` is coarse -- receive_midi covers pads,
        # buttons and knobs -- so a key without the frame silently discards
        # whichever subsystem failed second.
        text = traceback.format_exc()
        lines = text.strip().split('\n')
        frame = next((l.strip() for l in reversed(lines)
                      if l.strip().startswith('File "')), '')
        signature = (where, frame, lines[-1])
        if signature in self._exceptions_logged or len(self._exceptions_logged) >= 32:
            return
        self._exceptions_logged.add(signature)
        self._log('exception in %s\n%s' % (where, text))

    def _log_unhandled(self, status, data1, data2):
        # Phase 0's real payload: anything the device sends that MIDI_Map.py does
        # not describe, named exactly once. Capped so a mis-programmed preset
        # cannot fill Log.txt during a jam.
        signature = (status, data1)
        if signature in self._unhandled or len(self._unhandled) >= 48:
            return
        self._unhandled.add(signature)
        self._log('unmapped: status %02X data %d %d (channel %d)'
                  % (status, data1, data2, (status & 0x0F) + 1))


def _span(numbers):
    if not numbers:
        return 'none'
    numbers = sorted(numbers)
    if numbers == list(range(numbers[0], numbers[-1] + 1)):
        return '%d-%d' % (numbers[0], numbers[-1])
    return ','.join(str(n) for n in numbers)
