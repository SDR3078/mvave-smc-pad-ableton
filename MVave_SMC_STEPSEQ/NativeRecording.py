"""Use Live's Session recorder. Never create or rebuild clip envelopes."""


class NativeRecording(object):
    def __init__(self, song, track, clip):
        if not song.is_playing or not clip.is_playing:
            raise RuntimeError('Launch the Session clip first')
        if getattr(clip, 'is_arrangement_clip', False):
            raise RuntimeError('Use a Session clip')
        if not getattr(track, 'can_be_armed', hasattr(track, 'arm')):
            raise RuntimeError('This track cannot be armed')
        if getattr(song, 'record_mode', False) or song.session_record:
            raise RuntimeError('Turn off existing Live recording before starting')
        self.song, self.track, self.clip = song, track, clip
        self.previous_automation_arm = song.session_automation_record
        self.arm_states = [(t, bool(t.arm)) for t in song.tracks
            if getattr(t, 'can_be_armed', hasattr(t, 'arm'))]
        self.parameters = []
        self.active = False
        try:
            for other, previous in self.arm_states:
                if other != track and other.arm:
                    other.arm = False
            track.arm = True
            song.session_automation_record = True
            song.session_record = True
            self.active = True
        except Exception:
            song.session_record = False
            song.session_automation_record = self.previous_automation_arm
            self._restore_arms()
            raise

    def turn(self, parameter, delta):
        if not parameter.is_enabled:
            return
        entry = next((entry for entry in self.parameters if entry[0] == parameter), None)
        if entry is None:
            if not callable(getattr(parameter, 'begin_gesture', None)):
                raise RuntimeError('This Live parameter does not expose begin_gesture')
            parameter.begin_gesture()
            entry = [parameter, parameter.value]
            self.parameters.append(entry)
        increment = 1 if parameter.is_quantized else (parameter.max - parameter.min) / 127.0
        entry[1] = max(parameter.min, min(parameter.max, entry[1] + delta * increment))
        parameter.value = entry[1]

    def _restore_arms(self):
        for track, previous in self.arm_states:
            try:
                track.arm = previous
            except Exception:
                pass  # The track may have been removed during the take.

    def stop(self):
        self.active = False
        # Disable recording first; cleanup must not leave a host recording latch.
        try:
            self.song.session_record = False
        finally:
            try:
                self.song.session_automation_record = self.previous_automation_arm
            finally:
                self._restore_arms()
        for parameter, value in self.parameters:
            try:
                parameter.end_gesture()
                parameter.re_enable_automation()
            except Exception:
                pass  # A removed device must not prevent other gestures closing.
