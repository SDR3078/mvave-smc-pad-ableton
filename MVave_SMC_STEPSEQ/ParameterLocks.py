"""Session-clip envelope prototype. Live performs all lock playback."""


class ParameterLocks(object):
    def __init__(self):
        self._owned = []

    def _find(self, clip, parameter):
        for state in self._owned:
            if state['clip'] == clip and state['parameter'] == parameter:
                return state
        return None

    @staticmethod
    def _changed(parameter, value, delta):
        increment = 1 if parameter.is_quantized else (parameter.max - parameter.min) / 127.0
        return max(parameter.min, min(parameter.max, value + delta * increment))

    def _render(self, clip, envelope, state, step_length):
        # Write every cell from a stable snapshot. Never read back a curve while
        # editing it: Live may interpolate newly inserted boundary points.
        for step, value in enumerate(state['values']):
            time = state['start'] + step * step_length
            duration = min(step_length, state['end'] - time)
            if duration > 0:
                envelope.insert_step(time, duration, value)
        state['parameter'].re_enable_automation()

    def adjust(self, clip, parameter, steps, delta, step_length):
        if getattr(clip, 'is_arrangement_clip', False):
            raise RuntimeError('Parameter locks require a Session clip')
        envelope = clip.automation_envelope(parameter)
        state = self._find(clip, parameter)
        if state is not None and (state['start'] != clip.loop_start or
                state['end'] != clip.loop_end):
            raise RuntimeError('Loop changed; restart prototype before editing locks')
        if state is None or envelope is None:
            import math
            count = int(math.ceil((clip.loop_end - clip.loop_start) / step_length))
            base = parameter.value
            if envelope is None:
                values = [base] * count
                envelope = clip.create_automation_envelope(parameter)
            else:
                # Adopt existing automation at step resolution once, without
                # clearing the envelope. This prototype is for stepped macros.
                values = [envelope.value_at_time(clip.loop_start + n * step_length)
                          for n in range(count)]
                base = max(set(values), key=values.count)
            if state is not None:
                self._owned.remove(state)
            state = dict(clip=clip, parameter=parameter, base=base, locks=set(),
                values=values, start=clip.loop_start, end=clip.loop_end)
            state['locks'] = {n for n, v in enumerate(values) if abs(v - base) > 1e-6}
            self._owned.append(state)
        for step in sorted(set(steps)):
            if 0 <= step < len(state['values']):
                state['values'][step] = self._changed(parameter, state['values'][step], delta)
                state['locks'].add(step)
        self._render(clip, envelope, state, step_length)

    def adjust_base(self, clip, parameter, delta, step_length):
        state = self._find(clip, parameter)
        envelope = clip.automation_envelope(parameter)
        if envelope is None:
            if state is not None:
                self._owned.remove(state)
            return False
        if state is None:
            # Recover an existing stepped envelope after a Live restart. The
            # common value is its base; differing cells keep their saved locks.
            import math
            count = int(math.ceil((clip.loop_end - clip.loop_start) / step_length))
            values = [envelope.value_at_time(clip.loop_start + n * step_length)
                      for n in range(count)]
            if not values:
                return False
            base = max(set(values), key=values.count)
            state = dict(clip=clip, parameter=parameter, base=base,
                locks={n for n, v in enumerate(values) if abs(v - base) > 1e-6},
                values=values, start=clip.loop_start, end=clip.loop_end)
            self._owned.append(state)
        if state['start'] != clip.loop_start or state['end'] != clip.loop_end:
            raise RuntimeError('Loop changed; restart prototype before editing locks')
        updated = self._changed(parameter, state['base'], delta)
        if updated == state['base']:
            return True
        for step in range(len(state['values'])):
            if step not in state['locks']:
                state['values'][step] = updated
        state['base'] = updated
        # One segment per run of equal values, rather than a write per step.
        values = state['values']
        first = 0
        while first < len(values):
            end = first + 1
            while end < len(values) and values[end] == values[first]:
                end += 1
            time = state['start'] + first * step_length
            duration = min(state['end'], state['start'] + end * step_length) - time
            if duration > 0:
                envelope.insert_step(time, duration, values[first])
            first = end
        parameter.re_enable_automation()
        return True
