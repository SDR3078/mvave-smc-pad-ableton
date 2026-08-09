# Encoder half of the M-Vave SMC-PAD setup.
#
# The pads and the encoders arrive on DIFFERENT MIDI ports, and a Remote Script
# gets exactly one input port, so this is a second script in a second Control
# Surface slot:
#
#   slot 1   MVave_SMC_PAD     in MIDIIN3 / out MIDIOUT3   pads, buttons, LEDs
#   slot 2   MVave_SMC_KNOBS   in SMC-PAD (port 1)         the 8 encoders
#
# Everything here is on KNOB BANK 2. Bank 1 (CC 1-8) is deliberately untouched,
# so it stays free for Live's own MIDI mapping on port 2.
#
#   encoder 7, 8   CC 38, 39   relative   move the session box (X and Y)
#   encoder 1-6    CC 44,45,42,43,40,41   absolute   macros 1-6
#
# The macros follow the selection -- Live's "blue hand" -- rather than being
# statically MIDI-mapped. Click a different track and the same six knobs control
# that device instead, which is the entire point of doing this in a script.
#
# This script deliberately builds NO session box of its own. Live's red box
# belongs to whichever script called set_highlighting_session_component, so a
# second box would either fight the first or trigger the pad template's
# combination mode. Instead it reaches the pad script's session through the
# class-level _active_instances list and moves the real box.
from __future__ import with_statement

import Live
from _Framework.ControlSurface import ControlSurface
from _Framework.DeviceComponent import DeviceComponent
from _Framework.InputControlElement import *
from _Framework.SliderElement import SliderElement

# Measured 2026-08-03 with tools/pc/mvave_probe.py --knobs, one encoder at a
# time. The CC numbers do NOT follow the printed encoder numbers -- bank 2
# descends in pairs as the labels ascend -- so this tuple is in ENCODER order,
# not numeric order. Listing 40..45 instead would scatter the macros across the
# panel. Flip it to (40, 41, 42, 43, 44, 45) to put macro 1 at the top of the
# six rather than at the bottom.
CHANNEL = 0                                     # MIDI channel 1
MACRO_CCS = (44, 45, 42, 43, 40, 41)            # encoders 1-6 -> macros 1-6

# Some _Framework versions assert exactly 8 parameter controls, and an assert
# inside __init__ takes the whole script down rather than just the macros. Two
# encoders are spent on navigation, so pad the tuple with CCs the device never
# sends -- macros 7 and 8 simply stay unreachable, which is the intent anyway.
PAD_CCS = (118, 119)                            # undefined in the MIDI spec

# Relative encoders, centred on 64: 65 is one step clockwise, 63 one step back.
CC_TRACK = 38                                   # encoder 7: box across tracks
CC_SCENE = 39                                   # encoder 8: box through scenes
CENTRE = 64
NAV_CCS = (CC_TRACK, CC_SCENE)


def _clamp(value, ceiling):
    return max(0, min(value, max(0, ceiling)))


class MVave_SMC_KNOBS(ControlSurface):
    __doc__ = " Encoder half of the M-Vave SMC-PAD: session box + device macros "

    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        self._first_nav_logged = False
        self._problem_logged = False
        self._device_logged = False
        self._device = None
        with self.component_guard():
            self._setup_device_control()
        self.log_message('MVave_SMC_KNOBS: loaded. CC %d/%d navigate, CC %s = macros 1-6.'
                         % (CC_TRACK, CC_SCENE, ','.join(str(c) for c in MACRO_CCS)))

    # ----------------------------------------------------------------- device

    def _setup_device_control(self):
        controls = []
        for index, cc in enumerate(MACRO_CCS + PAD_CCS):
            slider = SliderElement(MIDI_CC_TYPE, CHANNEL, cc)
            slider.name = 'Macro_%d_CC_%d' % (index + 1, cc)
            controls.append(slider)
        self._device = DeviceComponent()
        self._device.name = 'Device_Component'
        self._device.set_parameter_controls(tuple(controls))
        self.set_device_component(self._device)

    def _on_selected_track_changed(self):
        # Follow the selection: same six knobs, whatever track you click on.
        # Lifted from the pad template's own implementation, which is known to
        # work against this vintage of _Framework.
        ControlSurface._on_selected_track_changed(self)
        track = self.song().view.selected_track
        device_to_select = track.view.selected_device
        if device_to_select is None and len(track.devices) > 0:
            device_to_select = track.devices[0]
        if device_to_select is not None:
            self.song().view.select_device(device_to_select)
        self._device_component.set_device(device_to_select)
        if not self._device_logged:
            # Once only. Tells us whether the blue hand ever gets a target --
            # if the macros are dead, this line says whether the cause is
            # "no device assigned" or something further down.
            self._device_logged = True
            self.log_message('MVave_SMC_KNOBS: device component -> %s'
                             % (device_to_select.name if device_to_select else 'None'))

    # ------------------------------------------------------------------- midi

    def build_midi_map(self, midi_map_handle):
        # Super first: that installs the device component's parameter controls.
        ControlSurface.build_midi_map(self, midi_map_handle)
        script_handle = self._c_instance.handle()
        for cc in NAV_CCS:
            Live.MidiMap.forward_midi_cc(script_handle, midi_map_handle, CHANNEL, cc)

    def receive_midi(self, midi_bytes):
        if (len(midi_bytes) == 3 and (midi_bytes[0] & 0xF0) == 0xB0
                and midi_bytes[1] in NAV_CCS):
            self._navigate(midi_bytes[1], midi_bytes[2])
            return
        # Everything else belongs to the framework. Swallowing it here would
        # silently break the macros, since ControlSurface is what dispatches to
        # the device component's controls.
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

    # ---------------------------------------------------------------- session

    def _pad_session(self):
        # Resolved on every turn rather than cached at load: the two Control
        # Surface slots load in an order we do not control, so the pad script
        # may not exist yet when this one starts. After the first import this
        # is just a sys.modules lookup, so the cost is nil.
        try:
            from MVave_SMC_PAD.MVave_SMC_PAD import MVave_SMC_PAD
        except Exception as exc:
            self._log_problem('cannot import MVave_SMC_PAD (%s)' % exc)
            return None
        instances = getattr(MVave_SMC_PAD, '_active_instances', None) or []
        if not instances:
            self._log_problem('MVave_SMC_PAD is not loaded -- is it in a Control Surface slot?')
            return None
        return getattr(instances[0], '_session', None)

    def _log_problem(self, message):
        if not self._problem_logged:
            self._problem_logged = True
            self.log_message('MVave_SMC_KNOBS: ' + message)

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
            self._log_problem('could not read the session offsets')
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
        if method is not None:
            return method()
        return getattr(session, attr_name, None)
