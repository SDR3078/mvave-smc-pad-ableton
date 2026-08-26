# `SMC_StepSeq` — the step sequencer

A third Remote Script for the SMC-PAD. The 16 pads become 16 steps of one drum
lane in the selected MIDI clip, with LED feedback and a playhead that chases
Live's own playback. A second view turns the grid into four lanes by four steps,
so a kick/clap/hat/open-hat groove is readable at a glance.

This is the design record the build brief asked for as `docs/decisions.md`,
renamed to match the rest of `docs/`. The brief itself is kept verbatim as
[STEPSEQ-BRIEF.md](STEPSEQ-BRIEF.md); where this file and the brief disagree,
this file is what got built and section 4 says why.

> **Status: written, self-tested, never run in Live.** The logic is exercised by
> `tools/stepseq_selftest.py` (60 checks, no controller and no DAW required).
> Nothing in it has touched the hardware, and several values in `consts.py` are
> still guesses — section 5 lists exactly which. Treating those as measured is
> the mistake this repo has already made four separate times
> ([FINDINGS.md](FINDINGS.md)).

---

## 1. What it does

| Control | Focus view | Overview |
|---|---|---|
| Pads | toggle a 16th note in the current lane | toggle a step at (lane row, beat column) |
| SHIFT + pad | select the lane, drum-rack layout | same, and scrolls the lane window to it |
| `<` `>` | page: steps 1–16 / 17–32 | page four steps at a time |
| SHIFT + `>` | switch view | switch view |
| stop button | switch view | switch view |
| play button | start/stop Live's transport | same |
| Knob CC 20 | scroll the current lane | scroll the 4-lane window |
| Knob CC 21 | paint velocity, 1–127 | same |
| Knob CC 22 | pattern length, 1–32 steps | same |
| Knob CC 23 | reserved — read and ignored | same |

Pad colours, from the measured palette ([HARDWARE.md 3.2](HARDWARE.md)):
teal a step that holds a note · amber the playhead · white the playhead sitting
on an active step · off everything else. In overview each lane row gets its own
colour — green, red-pink, blue, purple — chosen to avoid both playhead colours,
so a playhead column never reads as a lane.

## 2. The three properties everything else hangs off

**The clip is the only state.** The script stores no pattern. Steps are read
from and written to the bound MIDI clip through the Live API. Ctrl+Z undoes a
step edit, saving the set saves the pattern, a note drawn with the mouse lights
up on the pads, and Live's own playback provides sample-accurate timing — the
script never plays a note. None of that is implemented; all of it falls out of
not keeping a copy.

**One write path.** Both views funnel into `toggle_step(pitch, step_index)`. A
view is a coordinate mapping and a render function, nothing more.

**Listeners drive rendering, not the input handler.** Pressing a pad writes to
the clip and returns. The clip's notes listener fires and redraws. That is why a
pad press, a mouse edit and a Ctrl+Z produce identical LED updates, and it is
why nothing writes to the clip during a render — the listener would feed itself.

Three listeners: clip notes (redraw), clip playing position and status
(playhead), song view selected-track and detail-clip (re-bind).

## 3. How it renders

`_refresh()` reads the clip into a 16-slot grid, once per change. `_paint()`
overlays the playhead, diffs against a cache of what the device was last told,
and sends only the pads that changed. The playhead listener fires per audio
buffer and calls `_paint()` alone — no clip read, and no MIDI at all unless the
step index actually changed. At 140 BPM that is about nine repaints a second,
each one or two bytes triples.

The diff is not just tidiness. Sending all 128 notes back to back overruns this
device's MIDI input buffer and some pads silently never light
([HARDWARE.md 3.5](HARDWARE.md)) — the bug that first presented as a dead pad.

Two smaller decisions worth knowing:

- **Note times are floored into steps, not rounded.** `remove_notes_extended()`
  clears the half-open window `[t, t + STEP)`, so flooring is what makes "this
  pad is lit" and "pressing this pad clears it" agree about a note that sits
  slightly off the grid. Rounding to nearest would light a step whose window
  does not contain the note, and pressing it would appear to do nothing.
- **LEDs are always note-on.** This device ignores a real note-off entirely and
  silently, so velocity 0 is the only "off" it understands
  ([HARDWARE.md 3.3](HARDWARE.md)).

## 4. Where the brief met the measured hardware

The brief was written before [HARDWARE.md](HARDWARE.md) was consulted, and four
of its Phase 0 assumptions are already contradicted by measurements in this
repo. The architecture survived all four; the hardware constants did not.

**The knobs are probably unreachable, and it is not a software problem.** The
pads appear only on port 3 and the encoders only on ports 1 and 2, never both
([HARDWARE.md 1.1](HARDWARE.md)). A Remote Script gets exactly one input port.
Worse, encoder assignments are not per pad-preset — the `.spc` holds exactly 16
encoder records, two banks of eight ([HARDWARE.md 5.2](HARDWARE.md)) — so
putting the sequencer's CC 20–23 on the encoders spends one of the two KNOB BANK
banks globally, and both are already accounted for: bank 2 drives the device
macros, bank 1 is deliberately left free for Live's own MIDI mapping.

The sequencer works without any knob. Only paint velocity and pattern length
become unreachable, and both have mouse equivalents in Live. If the knobs turn
out to be worth having, `SMCStepSeq.handle_encoder_cc()` is the way in: a
sibling script on the encoder port can find the instance through the class-level
`_active_instances` list and forward, which is exactly what `MVave_SMC_KNOBS`
already does in the other direction to move the session box. That is a ten-line
addition to the encoder script, not a redesign of this one.

**There is no spare button to make SHIFT out of.** The device's own SHIFT key
transmits nothing at all — it is consumed by the firmware for its Shift+Pad
combinations ([HARDWARE.md 6.1](HARDWARE.md)). The five buttons above the grid
send notes 17–21 on channel 1, and they live in a different section of the
`.spc` from the pad banks, so they are very likely global rather than
per-preset. The brief's "spare button as SHIFT, CC 104 on channel 16" became the
record button, note 19, channel 1.

That in turn is why the script owns the play button. Claiming a port with a
Control Surface disables Track, Sync and Remote on it
([HARDWARE.md 1.4](HARDWARE.md)), so a button the script does not handle is a
dead button while this preset is live. Five buttons, five jobs.

**There is no dim.** The velocity byte sent to a pad is a palette index, not a
brightness, and the palette is absolute — it overrides the colour the pad is
configured with in the editor ([HARDWARE.md 3.1](HARDWARE.md)). "Step off = dim"
is not available; off is off. `COLOR_STEP_EMPTY` and `COLOR_STEP_DOWNBEAT` exist
for marking in-loop empty steps and default to 0, because every colour on this
device is full brightness and a lit empty grid is loud. Try them once you can
see the pads: quarter-note markers make 16 steps countable at a glance, which is
what a dim white does on a Push.

**Relative encoders here are centre-64, not two's complement.** The brief
specified `delta = v if v < 64 else v - 128`. The two encoders switched to
relative in the M-Vave editor were measured as 63 = one step back, 65 = one step
forward ([HARDWARE.md 4.4](HARDWARE.md)). The two schemes are mutually
ambiguous — 63 means +63 under one and −1 under the other — so this is a setting
(`KNOB_MODE`) rather than something that can be detected. It defaults to the
measured scheme.

**One more, not a contradiction but a trap.** The brief calls this "preset 3".
The `.spc` bank this repo already documents as **bank 3 is the clip launcher** —
notes 1–16, hand-edited, the bank port 3 plays back
([HARDWARE.md 5.2](HARDWARE.md)). The brief's preset numbering and the file's
bank numbering are not known to line up. Confirm which bank you are editing
before you program anything, or the first casualty is the clip launcher.

## 5. Phase 0 — what is settled and what is not

Already answered by [HARDWARE.md](HARDWARE.md), no experiment needed:

| Question | Answer |
|---|---|
| Do pads self-light on press? | **No.** Four rounds, ~78 strikes, no LED movement, and a host-set colour survives being struck (3.4). No re-render after release is needed. |
| Does velocity select the LED colour? | **Yes**, as an absolute palette index. The usable range is all below 64; 64–112 is one flat blue (3.1, 3.2). |
| How does a pad turn off? | **Note-on velocity 0.** A real note-off is ignored, silently (3.3). |
| Note-off form the device sends | **Note-on velocity 0**, not `0x80` (2.2). Both are accepted anyway. |
| Which OUT port lights the pads? | Port 3, `MIDIOUT3`. The other two outputs were never tested (1.1). |
| Left/right button numbers | Notes **20 and 21**, channel 1 — the `<` `>` buttons (2.4). |

Still open. Every one is a one-line edit in `SMC_StepSeq/consts.py`:

| Question | Assumed in `consts.py` | Why it matters |
|---|---|---|
| **Which port does the sequencer preset transmit on?** | port 3 | Gates the install — see section 6. Testable in a minute, and it also settles the `.spc` flag-byte hypothesis this repo has been carrying as a known unknown (5.6). |
| Do the pads send channel 16, notes 0–15, reading order? | yes | `PAD_CHANNEL`, `PAD_NOTES`. Note the clip-launcher bank uses **1–16**, and the M-Vave editor numbers pads bottom-up — its PAD1 is the bottom-left pad (5.3). |
| **Does a pad light only from a note matching its own note and channel?** | yes | Decides whether this script and `MVave_SMC_PAD` can share port 3 without their LEDs fighting. `LED_CHANNEL`. |
| Do the five buttons still send notes 17–21 on channel 1 in this preset? | yes | `BUTTON_CHANNEL`, `BTN_*`. They are a separate `.spc` section from the pad banks, so probably global — but "probably" is doing work there. |
| What does PAD BANK do in a custom preset? | nothing the script uses | If it silently switches to a second note set, fill in `PAD_NOTES_B` and stray presses stay harmless instead of going dead. |
| Do the encoders reach this script at all? | no | Section 4. If they do, confirm `KNOB_MODE` and the CC numbers. |
| Which velocities are actually teal and amber? | 20 and 15 | Named by eye by one observer (3.2). Swap them for whatever reads best on your unit. |

The measurement tool is already here: `tools/mvave_probe.py --listen --port MIDIIN3`
answers most of the first column, and `--colours --note 1` walks the palette.
[PROBE.md](PROBE.md) has the modes. Note the exclusivity constraint — Live must
not be holding the port.

## 6. Installing

Copy `SMC_StepSeq/` into Live's Remote Scripts directory alongside the other two
(see [INSTALL.md](INSTALL.md) for the path), restart Live, and add a Control
Surface slot for `SMC_StepSeq`. Live 11 or newer: the clip API this uses
(`get_notes_extended`, `add_new_notes`, `remove_notes_extended`) does not exist
before that, and the script says so in `Log.txt` rather than rendering an empty
grid forever.

**Which port to give it depends on a Phase 0 answer, and there are two shapes.**

*If the sequencer preset transmits on port 3* — the same port as the clip
launcher — then two Control Surface slots want one port, and whether that works
comes down to the LED channel-matching question above. The design is built for
it: the sequencer speaks channel 16 and `MVave_SMC_PAD` speaks channel 1, so
neither reads the other's input, and if a pad only lights from a note matching
its own configured note and channel, neither sees the other's output either.
Switching presets on the device then switches modes with nothing to change in
Live, which is the whole point. If Live refuses to share the port, the fallback
is swapping which script occupies the slot — workable, but no longer a
one-button mode switch.

*If it transmits on port 1* — which the `.spc` flag-byte hypothesis
([HARDWARE.md 5.6](HARDWARE.md)) predicts for a bank whose flag byte is `0x00` —
then give the sequencer port 1 in and out, move `MVave_SMC_KNOBS` to port 2, and
the encoders arrive on the same port as the pads, so the knobs work with no
sibling-script forwarding at all. This is the better outcome and it costs one
minute to check.

Either way, on the port's MIDI Ports rows set **Track = Off**. Forwarded
channel-16 notes are consumed by the script regardless, but this guarantees a
pad press can never play an instrument.

Live's `Log.txt` is the only debugger — the script logs a line on load naming
the channels and notes it is listening for, and logs any message it receives
that `consts.py` does not describe, exactly once per signature. That last one is
the fastest answer to "what is this thing actually sending?".

## 7. The self-test

```
python3 tools/stepseq_selftest.py -v
```

Runs the script against a fake Live on any machine, no controller and no DAW.
It exists because Live has no hot reload: every change costs a full restart, and
an exception inside a MIDI callback disables the script silently — the
controller just stops responding and the only evidence is a traceback in
`Log.txt`. Grid arithmetic is a punishing thing to debug through that loop.

It covers the coordinate maps, the step bucketing, the write path, LED bytes and
diffing, playhead gating, page clamping, re-binding, clip deletion, and the
consts file's own sanity. It cannot cover the hardware — note numbers, channels,
the palette. That is section 5, on the device.

## 8. Deliberately not built

From the brief's own out-of-scope list: per-step velocity editing, aftertouch
ratchets, swing and nudge, auto-creating a clip when none is selected, reading
drum-rack pad names, note repeat, melodic and scale modes.

Also skipped: **auto-following the playhead's page during playback**, which the
brief listed as a nice-to-have that defaults to off. A feature that is off by
default is a feature nobody has tried; it can be added in about six lines once
the rest is confirmed working on hardware.
