# Encoder half of the M-Vave SMC-PAD setup.
#
# The pads and the encoders arrive on DIFFERENT MIDI ports, and a Remote Script
# gets exactly one input port, so this is a second script in a second Control
# Surface slot:
#
#   slot 1   MVave_SMC_PAD     in MIDIIN3 / out MIDIOUT3   pads, buttons, LEDs
#   slot 2   MVave_SMC_KNOBS   in SMC-PAD (port 1)         the 8 encoders
#
# BOTH knob banks are used: on the launcher preset that is 14 macros plus two
# navigation encoders; on the sequencer preset, 16 macros and no navigation.
#
#   bank 1, knobs 7 8 5 6 3 4 1 2   ->  macros 1-8
#   bank 2, knobs 7 8 5 6 3 4       ->  macros 9-14
#   bank 2, knobs 1 2               ->  session box X and Y
#
# The macros follow the selection -- Live's "blue hand" -- rather than being
# statically MIDI-mapped. Click a different track and the same knobs control that
# device instead, which is the entire point of doing this in a script.
#
# Why the parameters are driven directly rather than through DeviceComponent's
# parameter controls: that mechanism addresses ONE BANK OF EIGHT at a time and
# pages between banks. Fourteen simultaneous macros do not fit it. Driving
# device.parameters directly also means decoding the relative encoders here,
# exactly as the navigation knobs already do, instead of depending on a
# Live.MidiMap.MapMode constant that cannot be verified off-machine.
#
# This script deliberately builds NO session box of its own. Live's red box
# belongs to whichever script called set_highlighting_session_component, so a
# second box would either fight the first or trigger the pad template's
# combination mode. Instead it reaches the pad script's session through the
# class-level _active_instances list and moves the real box.
from __future__ import with_statement

import traceback

import Live
from _Framework.ControlSurface import ControlSurface
from _Framework.DeviceComponent import DeviceComponent

# Measured 2026-08-31 with tools/mvave_probe.py --knobs, one encoder at a time.
# Every encoder on the device is RELATIVE, both banks, centred on 64:
# 65 is one click clockwise, 63 one click back.
CHANNEL = 0                                     # MIDI channel 1
CENTRE = 64

# Navigation -- bank 2, knobs 1 and 2 (the BOTTOM pair; the device numbers its
# encoders bottom-up, so encoder 1 is bottom-left and encoder 7 is top-left).
CC_TRACK = 17                                   # box across tracks
CC_SCENE = 18                                   # box through scenes
NAV_CCS = (CC_TRACK, CC_SCENE)

# CC -> macro number, 1-based. Macro N is device.parameters[N]; index 0 is the
# device on/off switch, so the numbering lines up with no offset arithmetic.
#
# Re-measured 2026-08-31 after the device was renumbered: CC number now equals
# macro number for all fourteen, so this table is the identity function. That is
# by design, not luck -- the CCs were chosen to make it so. It survives only as
# long as the device keeps that numbering, which is why it stays an explicit map
# rather than becoming arithmetic: the next editor change can break the identity
# without breaking the file.
#
# The physical layout is 2 wide by 4 tall, numbered BOTTOM-UP. Reading the panel
# top-left to bottom-right is therefore encoders 7,8,5,6,3,4,1,2, which is why
# the macros run in that order rather than 1..8:
#
#     enc 7  enc 8        macro 1  macro 2     <- top
#     enc 5  enc 6        macro 3  macro 4
#     enc 3  enc 4        macro 5  macro 6
#     enc 1  enc 2        macro 7  macro 8     <- bottom   (bank 2: nav)
# Encoders are PER-PRESET, so the two presets send different CCs from the same
# knobs -- and they were numbered so that no CC means two things. That is what
# lets one flat table serve both presets with no mode detection:
#
#   CC 1-14   macros 1-14      both presets, identical
#   CC 15-16  macros 15-16     sequencer preset only (bank 2, bottom pair)
#   CC 17-18  session box X/Y  launcher preset only  (bank 2, bottom pair)
#
# The bottom pair is the only difference. The launcher needs grid navigation; the
# sequencer has no session box to move -- it pages with the arrow buttons -- so
# there those two knobs become the last two macros of a 16-macro rack instead.
MACRO_BY_CC = {
    # bank 1: encoders 7, 8, 5, 6, 3, 4, 1, 2  ->  macros 1-8
    1: 1,   2: 2,   3: 3,   4: 4,   5: 5,   6: 6,   7: 7,   8: 8,
    # bank 2: encoders 7, 8, 5, 6, 3, 4  ->  macros 9-14
    9: 9,   10: 10, 11: 11, 12: 12, 13: 13, 14: 14,
    # bank 2 bottom pair, sequencer preset only  ->  macros 15-16
    15: 15, 16: 16,
}

# One click moves this fraction of a parameter's range. A rack macro runs 0-127,
# so its range is 127 and this gives exactly one unit per click; a continuous
# parameter with a different range scales proportionally rather than jumping.
# (128 was the obvious-looking number and is off by one: it moves 0.992 per
# click, so macro values never land on integers and one click per sweep is
# invisible.)
STEPS_PER_SWEEP = 127.0


def _clamp(value, ceiling):
    return max(0, min(value, max(0, ceiling)))


class MVave_SMC_KNOBS(ControlSurface):
    __doc__ = " Encoder half of the M-Vave SMC-PAD: session box + up to 16 device macros "

    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        self._logged = set()
        self._first_nav_logged = False
        self._first_macro_logged = False
        self._device_logged = False
        self._device = None
        self._target_device = None
        with self.component_guard():
            self._setup_device_control()
        self.log_message('MVave_SMC_KNOBS: loaded. CC %d/%d navigate; %d macro CCs %s.'
                         % (CC_TRACK, CC_SCENE, len(MACRO_BY_CC),
                            ','.join(str(c) for c in sorted(MACRO_BY_CC))))

    # ----------------------------------------------------------------- device

    def _setup_device_control(self):
        # The component exists only to keep Live's blue hand pointed at the same
        # device these knobs write to. set_parameter_controls is deliberately
        # NOT called: it addresses one bank of eight, and some _Framework
        # versions assert on the count, which would take the script down in
        # __init__ rather than merely disabling a feature.
        self._device = DeviceComponent()
        self._device.name = 'Device_Component'
        self.set_device_component(self._device)

    def _on_selected_track_changed(self):
        try:
            self._follow_selected_track()
        except Exception:
            # Live calls this on every track click. Letting it raise would take
            # the script down for the rest of the session.
            self._log_exception('selected track changed')

    def _follow_selected_track(self):
        # Follow the selection: the same knobs, whatever track you click on.
        ControlSurface._on_selected_track_changed(self)
        track = self.song().view.selected_track
        device_to_select = track.view.selected_device
        if device_to_select is None and len(track.devices) > 0:
            device_to_select = track.devices[0]
        if device_to_select is not None:
            self.song().view.select_device(device_to_select)
        self._target_device = device_to_select
        if self._device is not None:
            self._device.set_device(device_to_select)
        if not self._device_logged:
            # Once only. If the macros are dead, this line separates "no device
            # was ever assigned" from a fault further down.
            self._device_logged = True
            self.log_message('MVave_SMC_KNOBS: device -> %s'
                             % (device_to_select.name if device_to_select else 'None'))

    def _current_device(self):
        """The device to write to, resolved at write time rather than cached.

        _on_selected_track_changed is the only hook this script has, and it
        fires on a TRACK change only. A cached target therefore goes stale the
        moment you click a different device on the same track: Live's blue hand
        moves, because DeviceComponent has its own appointed-device listener,
        while the cache does not -- so the knobs quietly edit the device you
        just navigated away from, with nothing to show for it. Delete the
        cached device and the reference dangles, and the next click raises
        inside a MIDI callback, which takes the whole script down.

        DeviceComponent already follows the appointed device, so ask it. The
        cached value survives only as a fallback for a _Framework version whose
        DeviceComponent has no device() getter.
        """
        component = self._device
        getter = getattr(component, 'device', None) if component is not None else None
        if callable(getter):
            return getter()
        return self._target_device

    def _adjust_macro(self, macro, delta):
        device = self._current_device()
        if device is None:
            self._log_once('no device selected yet -- click a track to bind one')
            return
        params = device.parameters
        if macro >= len(params):
            # Not an error: a device with fewer macros than knobs is normal.
            # Logged once per device+macro so a small rack cannot flood the log.
            self._log_once('"%s" exposes %d parameter(s); the macro-%d knob does nothing'
                           % (device.name, max(0, len(params) - 1), macro))
            return
        param = params[macro]
        if not param.is_enabled:
            return
        if param.is_quantized:
            new_value = param.value + delta
        else:
            new_value = param.value + delta * (param.max - param.min) / STEPS_PER_SWEEP
        # Clamped here: writing outside a parameter's range raises, and an
        # exception inside a MIDI callback disables the whole script silently.
        param.value = max(param.min, min(param.max, new_value))

    # ------------------------------------------------------------------- midi

    def build_midi_map(self, midi_map_handle):
        ControlSurface.build_midi_map(self, midi_map_handle)
        script_handle = self._c_instance.handle()
        for cc in tuple(NAV_CCS) + tuple(sorted(MACRO_BY_CC)):
            Live.MidiMap.forward_midi_cc(script_handle, midi_map_handle, CHANNEL, cc)

    def receive_midi(self, midi_bytes):
        try:
            if len(midi_bytes) == 3 and (midi_bytes[0] & 0xF0) == 0xB0:
                cc, value = midi_bytes[1], midi_bytes[2]
                if cc in NAV_CCS:
                    self._navigate(cc, value)
                    return
                if cc in MACRO_BY_CC:
                    self._macro(cc, value)
                    return
        except Exception:
            # An uncaught exception here disables the entire script until Live
            # restarts -- all fourteen macros AND both navigation encoders --
            # with nothing in the UI to say so. Clamping alone was the previous
            # defence, which only covers the failures we thought of.
            self._log_exception('receive_midi')
            return
        # Anything unclaimed belongs to the framework. Swallowing it here is the
        # classic silent failure in this codebase, so it is forwarded explicitly.
        ControlSurface.receive_midi(self, midi_bytes)

    def _navigate(self, cc, value):
        if not self._first_nav_logged:
            # One line proving the pipe works, then silence -- a knob produces
            # hundreds of messages and Log.txt is not the place for them.
            self._first_nav_logged = True
            self.log_message('MVave_SMC_KNOBS: first nav CC -- %d value %d' % (cc, value))
        delta = value - CENTRE
        if delta == 0:
            return
        if cc == CC_TRACK:
            self._bank(delta, 0)
        elif cc == CC_SCENE:
            self._bank(0, delta)

    def _macro(self, cc, value):
        if not self._first_macro_logged:
            self._first_macro_logged = True
            self.log_message('MVave_SMC_KNOBS: first macro CC -- %d value %d -> macro %d'
                             % (cc, value, MACRO_BY_CC[cc]))
        delta = value - CENTRE
        if delta:
            self._adjust_macro(MACRO_BY_CC[cc], delta)

    # ---------------------------------------------------------------- session

    def _pad_session(self):
        # Resolved on every turn rather than cached at load: the two Control
        # Surface slots load in an order we do not control, so the pad script
        # may not exist yet when this one starts. After the first import this
        # is just a sys.modules lookup, so the cost is nil.
        try:
            from MVave_SMC_PAD.MVave_SMC_PAD import MVave_SMC_PAD
        except Exception as exc:
            self._log_once('cannot import MVave_SMC_PAD (%s)' % exc)
            return None
        instances = getattr(MVave_SMC_PAD, '_active_instances', None) or []
        if not instances:
            self._log_once('MVave_SMC_PAD is not loaded -- is it in a Control Surface slot?')
            return None
        return getattr(instances[0], '_session', None)

    def _log_once(self, message):
        # Keyed on the message rather than a single flag, so a later distinct
        # problem is not hidden by an earlier one.
        if message not in self._logged:
            self._logged.add(message)
            self.log_message('MVave_SMC_KNOBS: ' + message)

    def _log_exception(self, where):
        # Through _log_once, so a fault that repeats on every one of the
        # hundreds of messages a single knob turn produces is written once.
        self._log_once('exception in %s\n%s' % (where, traceback.format_exc()))

    def _bank(self, d_track, d_scene):
        session = self._pad_session()
        if session is None:
            return
        song = self.song()
        try:
            track_count = len(song.visible_tracks)
        except AttributeError:
            track_count = len(song.tracks)
        scene_count = len(song.scenes)

        track_offset = self._offset(session, 'track_offset', '_track_offset')
        scene_offset = self._offset(session, 'scene_offset', '_scene_offset')
        if track_offset is None or scene_offset is None:
            self._log_once('could not read the session offsets')
            return

        # Clamped here rather than left to set_offsets, which asserts on a
        # negative offset -- an assert inside a MIDI callback takes the script
        # down mid-jam.
        new_track = _clamp(track_offset + d_track, track_count - session.width())
        new_scene = _clamp(scene_offset + d_scene, scene_count - session.height())
        if (new_track, new_scene) != (track_offset, scene_offset):
            session.set_offsets(new_track, new_scene)

    def _offset(self, session, method_name, attr_name):
        # _Framework exposes these as methods in most versions and as bare
        # attributes in others, and it is not on the machine this was written
        # on, so try both rather than guess.
        method = getattr(session, method_name, None)
        if callable(method):
            return method()
        if method is not None:
            # This version spells it as a plain attribute under the same name.
            # Calling it would raise TypeError inside a MIDI callback, which is
            # the exact failure the two-spellings dance exists to avoid.
            return method
        return getattr(session, attr_name, None)
