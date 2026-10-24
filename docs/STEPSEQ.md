# MVave_SMC_STEPSEQ - current working guide

Revision **2026-10-15**, tested by the user on Live 12.4.6 Suite.
The main source now includes probability and drum activity.

The complete controls, installation, stock-kit macro setup, recording workflow,
LED meanings and prototype limits are in the maintained
[hands-on reference](HANDS-ON.md).
See also [current local status](LOCAL-PROTOTYPE.md) and [CHANGELOG.md](../CHANGELOG.md).
STEPSEQ-BRIEF.md is a historical build brief. The earlier STEPSEQ design text is
preserved in [STEPSEQ-ORIGINAL.md](STEPSEQ-ORIGINAL.md).

## Controls

| Gesture | Result |
|---|---|
| Tap pad | Toggle a sixteenth-note step on release |
| Hold active step(s) + knob | Lock a macro on those steps |
| Hold active step(s) + Left/Right | Change chance: 25%, 50%, 75%, 100% |
| Record + pad | Select drum and its Instrument Rack macros |
| Pause/Stop + pad | Mute/unmute without deleting the pattern |
| Hold Record or Pause/Stop | Drum state with cyan programmed-hit pulses |
| Play | Toggle transport; stopping ends capture |
| Record + Play | Toggle native real-time macro capture |
| Left/Right alone | Switch Drum Rack tracks |
| Record + Left/Right | Change drum bank by 16 pitches |
| Pause/Stop + Left/Right | Page the pattern |

Step order is top-left across/down; drum order is bottom-left across/up.
Probability palette: 25% = 7, 50% = 21, 75% = 9, 100% = 64. Hold the pad while
pressing arrows repeatedly. New steps default to 100%. Live owns the chance.
The old four-lane overview remains internal for tests; Pause/Stop is mute mode.

## Architecture and checks

Clips own notes, chance and automation. Input handlers write; listeners redraw.
Probability edits return the original MidiNoteVector to apply_note_modifications
to preserve IDs and note data. The activity cache is rebuilt on render and read
by the existing playhead callback, with half-step cyan pulses and no new timers.
Only changed LED values are sent. Muted/probability-skipped notes still pulse;
disabled notes do not. No actual audio/MIDI output detection is claimed.

One Drum Rack per track is supported. The first direct Instrument Rack inside
the selected pad is its macro target. Plain pads still sequence/mute but need
that inner rack for macro control. Knob bank 1 gives eight controls in reading
order. Tracks are pinned; track arrows do not launch or stop clips.

Native recording uses Session Record and parameter gestures with temporary
arming, restoration and idle-time automation resume. Curve/lock metadata remains
session-only. The old custom recorder and scale/latch modes are archived.

Run `python -m unittest discover -s tools -p "*selftest.py"` from the source:
**185 tests pass**. Stubs cover sequencing, macros, recording, drum modes,
probability and activity. Hardware sessions additionally confirmed smooth jamming.
