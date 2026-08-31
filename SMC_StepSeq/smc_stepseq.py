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
#   One write path. Both views funnel into toggle_step(). A view is a
#   coordinate mapping and a render function, nothing more.
#
#   Listeners drive rendering, not the input handler. Pressing a pad writes to
#   the clip and returns; the clip's notes listener fires and redraws. That is
#   why a mouse edit and a pad press produce identical LED updates, and it is
#   why nothing here writes to the clip during a render -- the listener would
#   feed itself.
#
# Every hardware number is in consts.py. There are none in this file.

from __future__ import with_statement

import math
import traceback

import Live
from _Framework.ControlSurface import ControlSurface

from .consts import *


VIEW_FOCUS = 0
VIEW_OVERVIEW = 1

KNOB_CCS = (CC_LANE, CC_VELOCITY, CC_LENGTH, CC_SPARE)


def _clamp(value, low, high):
    return max(low, min(value, high))


def decode_relative(value, mode):
    """One encoder click -> a signed number of steps.

    The two schemes are mutually ambiguous -- a value of 63 is +63 under 'twos'
    and -1 under 'centre' -- so which one is in use has to be configured rather
    than detected. See KNOB_MODE in consts.py.
    """
    if mode == 'twos':
        return value if value < 64 else value - 128
    return value - 64


def lane_for_pad(pad_index, base=LANE_SELECT_BASE):
    """SHIFT + pad -> a drum-rack pitch.

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


class SMCStepSeq(ControlSurface):
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
        self._clip = None
        self._view = VIEW_FOCUS
        self._lane = DEFAULT_LANE
        self._bank = 0
        self._lane_window = DEFAULT_LANE
        self._page = 0
        self._shift = False
        self._follow = FOLLOW_PLAYHEAD
        self._lane_base = LANE_SELECT_BASE
        self._paint_velocity = PAINT_VELOCITY
        self._grid = [COLOR_STEP_OFF] * 16      # what the clip says
        self._on = [False] * 16                 # which of those hold a note
        self._led = [None] * 16                 # what the device was last told
        self._playhead = None
        self._unhandled = set()
        self._pads = {}
        for index, note in enumerate(PAD_NOTES):
            self._pads[note] = index
        for index, note in enumerate(PAD_NOTES_B):
            self._pads[note] = index
        self._buttons = tuple(n for n in (BTN_PLAY, BTN_VIEW, BTN_SHIFT,
                                          BTN_LEFT, BTN_RIGHT) if n is not None)

        ControlSurface.__init__(self, c_instance)
        with self.component_guard():
            self._attach_song_listeners()
        self._ready = True
        if self not in SMCStepSeq._active_instances:
            SMCStepSeq._active_instances.append(self)
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
        if self in SMCStepSeq._active_instances:
            SMCStepSeq._active_instances.remove(self)
        self._ready = False
        ControlSurface.disconnect(self)

    def refresh_state(self):
        # Called when Live enables the surface. The device may have been
        # repowered or switched presets since the last render, so the LED cache
        # is worthless -- drop it and repaint everything.
        ControlSurface.refresh_state(self)
        if not self._ready:
            return
        self._led = [None] * 16
        self._render()

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
        except Exception:
            pass

    @_guarded('rebind')
    def _rebind(self):
        self._detach_clip()
        clip = None
        try:
            candidate = self.song().view.detail_clip
            if candidate is not None and candidate.is_midi_clip:
                clip = candidate
        except Exception:
            clip = None

        if clip is not None and not hasattr(clip, 'get_notes_extended'):
            # Live 10 and older. Announce it rather than rendering an empty
            # grid forever and leaving the user to guess.
            self._log('this Live has no get_notes_extended() -- Live 11 or '
                      'newer is required. Running with no clip bound.')
            clip = None

        if clip is not None:
            clip.add_notes_listener(self._on_notes_changed)
            clip.add_playing_position_listener(self._on_playhead)
            clip.add_playing_status_listener(self._on_playhead)
        self._clip = clip
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
        time = clip.loop_start + step_index * STEP
        if time >= clip.loop_end - 1e-9:
            return                          # v1 edits inside the loop only
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
            return
        if self._shift:
            self._select_lane(lane_for_pad(index, self._lane_base))
            return
        # Push-style: how hard you hit the pad becomes the step's velocity.
        # None when the caller has none to offer -- the self-test, and the
        # sibling-script entry point -- in which case the knob/default stands.
        strike = velocity if (USE_STRIKE_VELOCITY and velocity) else None
        if self._view == VIEW_FOCUS:
            self.toggle_step(self._lane, self._bank * 16 + index, strike)
        else:
            row, col = divmod(index, 4)
            self.toggle_step(self._lane_window + row, self._page * 4 + col, strike)

    def _on_button(self, number, pressed):
        if number == BTN_SHIFT:
            self._shift = pressed
            return
        if not pressed:
            return
        if number == BTN_VIEW:
            self._toggle_view()
        elif number == BTN_PLAY:
            self._toggle_transport()
        elif number == BTN_LEFT:
            # Held SHIFT turns the arrows into a lane-bank control, because
            # SHIFT + pad only reaches the 16 pitches from _lane_base and a drum
            # rack has more rows than that.
            self._lane_base_by(-16) if self._shift else self._page_by(-1)
        elif number == BTN_RIGHT:
            self._lane_base_by(16) if self._shift else self._page_by(1)

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
            self._set_length(self._step_count() + delta)
        elif cc == CC_SPARE:
            pass                            # reserved: nudge/swing later

    def _select_lane(self, pitch):
        self._lane = pitch
        if self._view == VIEW_OVERVIEW:
            # Otherwise the press has no visible effect: put the chosen lane on
            # the top row of the window.
            self._lane_window = _clamp(pitch, 0, 124)
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
        """Move the SHIFT + pad lane picker up or down a bank of 16 pitches."""
        self._lane_base = _clamp(self._lane_base + delta, 0, 112)
        self._render()

    def _page_by(self, delta):
        # Manual paging means "stop chasing the playhead" -- otherwise the next
        # buffer would yank the view back and the button would look broken.
        self._follow = False
        if self._view == VIEW_FOCUS:
            self._bank = self._bank + delta
        else:
            self._page = self._page + delta
        self._clamp_pages()
        self._render()

    def _toggle_transport(self):
        song = self.song()
        if song.is_playing:
            song.stop_playing()
        else:
            song.start_playing()

    def _set_length(self, steps):
        clip = self._clip
        if clip is None:
            return
        end = clip.loop_start + _clamp(steps, 1, STEPS_MAX) * STEP
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
        length = clip.loop_end - clip.loop_start
        return _clamp(int(round(length / STEP)), 0, STEPS_MAX)

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
        if clip is not None and clip.is_playing:
            step = step_at(clip.playing_position, clip.loop_start)
            if not 0 <= step < self._step_count():
                step = None
        if step == self._playhead:
            # This listener fires per audio buffer. Only a step change is worth
            # any work, and _paint() below reads no clip data at all.
            return
        self._playhead = step
        if step is None:
            # Stopping restores following, so a manual page is temporary rather
            # than sticky and there is no mode to get stuck in.
            self._follow = FOLLOW_PLAYHEAD
        elif self._follow and self._scroll_to(step):
            self._render()      # the window moved, so the whole grid is stale
            return
        self._paint()

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

    def _refresh_focus(self, clip):
        first = self._bank * 16
        total = self._step_count()
        for index in range(16):
            if first + index < total:
                self._grid[index] = self._empty_color(first + index)
        notes = clip.get_notes_extended(self._lane, 1,
                                        clip.loop_start + first * STEP,
                                        16 * STEP)
        for note in notes:
            index = step_at(note.start_time, clip.loop_start) - first
            if 0 <= index < 16:
                self._grid[index] = COLOR_STEP_ON
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
            if 0 <= row < 4 and 0 <= col < 4:
                self._grid[row * 4 + col] = LANE_COLORS[row]
                self._on[row * 4 + col] = True

    def _paint(self):
        """Overlay the playhead on the grid and send only what changed."""
        colors = list(self._grid)
        if self._playhead is not None:
            for index in self._pads_for_step(self._playhead):
                colors[index] = (COLOR_PLAYHEAD_ON if self._on[index]
                                 else COLOR_PLAYHEAD)
        for index, color in enumerate(colors):
            if self._led[index] != color:
                self._led[index] = color
                self._send_led(index, color)

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

    # ---------------------------------------------------------------- logging

    def _log(self, message):
        self.log_message(LOG_PREFIX + message)

    def _log_exception(self, where):
        self._log('exception in %s\n%s' % (where, traceback.format_exc()))

    def _log_unhandled(self, status, data1, data2):
        # Phase 0's real payload: anything the device sends that consts.py does
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
