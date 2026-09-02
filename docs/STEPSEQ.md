# `MVave_SMC_STEPSEQ` — the step sequencer

A third Remote Script for the SMC-PAD. The 16 pads become 16 steps of one drum
lane in the selected MIDI clip, with LED feedback and a playhead that chases
Live's own playback. A second view turns the grid into four lanes by four steps,
so a kick/clap/hat/open-hat groove is readable at a glance.

This is the design record the build brief asked for as `docs/decisions.md`,
renamed to match the rest of `docs/`. The brief itself is kept verbatim as
[STEPSEQ-BRIEF.md](STEPSEQ-BRIEF.md); where this file and the brief disagree,
this file is what got built and section 4 says why.

> **Status: running in Live on real hardware** (2026-08-31). Every value in
> `MIDI_Map.py` is measured rather than assumed — section 5 has the table and
> [HARDWARE.md](HARDWARE.md) has the method. The logic is also exercised by
> `tools/stepseq_selftest.py` (92 checks, no controller and no DAW required),
> which is what makes a change safe to attempt without a Live restart.
>
> Two things the first real session changed: the visible window now follows the
> playhead, and the lane picker banks past its first sixteen pitches. Both were
> found in minutes of use and neither was visible from the self-test — a
> reminder of what running it actually buys you.

---

## 1. What it does

| Control | Focus view | Overview |
|---|---|---|
| Pads | toggle a 16th note in the current lane | toggle a step at (lane row, beat column) |
| MOD + pad | select the lane, drum-rack layout | same, and scrolls the lane window to it |
| `<` `>` | page through the steps by 16 | page four steps at a time |
| MOD + `<` `>` | **bank the lane picker by 16 pitches** | same |
| stop button | switch view | switch view |
| play button | start/stop Live's transport | same |

**Three of the five buttons show state on their own LEDs** — play lit while the
transport runs, the view button lit while you are in overview, the modifier lit
while held. The arrows have no state to show and are never written.

This needs the buttons' **feedback option turned ON in the M-Vave editor**. With
it off the button lights from its own press and ignores the host, so the script's
writes do nothing; with it on the button is dark unless something lights it, which
is what this is for. `BUTTON_LEDS = False` in `MIDI_Map.py` turns it off again.

Whether the button LEDs take the pad palette or are simply on/off is unmeasured —
`BTN_LED_ON` is a velocity either way, so pick from the palette in
[HARDWARE.md](HARDWARE.md) 3.2 if they turn out to be colour capable.
| Knob CC 20–23 | **unreachable on this hardware — see below** | same |

**The window follows the playhead.** The sixteen pads show the sixteen steps
being played, so a 16, 32 or 64-step loop needs no paging at all.

Paging by hand stops the chase for a moment, because otherwise the next audio
buffer yanks the view straight back and the arrow looks broken. It comes back on
its own — **paging away is a peek at the current cycle, not a mode**:

| What you do | What happens |
|---|---|
| press `<` or `>` while playing | the view stays where you put it |
| the loop comes round again | the chase resumes and the view snaps to the playhead |
| page back onto the playing page | resumes immediately, without waiting |
| stop the transport | resumes |

So you can page away to edit steps 17–32 while 1–16 play, and at the top of the
next loop the view returns to the music by itself. You never have to remember to
re-arm it, and the wait is bounded by one cycle.

`FOLLOW_RESUMES_ON_WRAP = False` makes a manual page stick until you page back or
stop; `FOLLOW_PLAYHEAD = False` turns the whole thing off.

**MOD is the record button** (`BTN_MOD`, note 119), held down. It is deliberately
not called SHIFT: the device has a key physically labelled SHIFT which does
something else entirely and transmits nothing at all
([HARDWARE.md](HARDWARE.md) 6.1), so using that word for this button would put
two unrelated things under one name in a codebase about this exact device.

**The lane picker banks.** MOD + pad reaches sixteen pitches starting at
`LANE_SELECT_BASE`, which is one bank of a drum rack. MOD + an arrow moves that
base by 16, so all 128 pitches are reachable. The two end stops land on 0 and
112 rather than on the `LANE_SELECT_BASE + 16k` series, and stepping back off a
stop returns to the series — the picker tracks a bank index, not the base, so a
trip to either end does not strand it.

**The encoder CCs are not wired.** Both knob banks are spent on device macros for
the other script ([HARDWARE.md 4.1](HARDWARE.md)) and there is no third bank, so
the sequencer's four CCs have nowhere to live. Paint velocity and pattern length
are only settable in `MIDI_Map.py` or with the mouse. The handlers remain, so
they work the moment a bank frees up.

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
Encoder assignments *are* per preset — the two files in `reference/` differ at
exactly encoder records 8 and 9 ([HARDWARE.md 4.1](HARDWARE.md)) — so this preset
could carry its own CC 20–23 without costing the launcher anything. What it
cannot do is get them to this script: the encoders never appear on port 3, and a
Remote Script gets one input port. The way in is a forward from the encoder
script, not a different assignment.

The sequencer works without any knob. Only paint velocity and pattern length
become unreachable, and both have mouse equivalents in Live. If the knobs turn
out to be worth having, `MVave_SMC_STEPSEQ.handle_encoder_cc()` is the way in: a
sibling script on the encoder port can find the instance through the class-level
`_active_instances` list and forward, which is exactly what `MVave_SMC_KNOBS`
already does in the other direction to move the session box. That is a ten-line
addition to the encoder script, not a redesign of this one.

**There is no spare button to make SHIFT out of.** The device's own SHIFT key
transmits nothing at all — it is consumed by the firmware for its Shift+Pad
combinations ([HARDWARE.md 6.1](HARDWARE.md)). The five buttons above the grid
are **per-preset**, and on this preset they send notes **117–121** on channel 1.
Decoding the two exported presets settles it: the five button records read
20, 21, 17, 18, 19 in `launchpad.spc` and 120, 121, 117, 118, 119 in
`sequencer.spc`. The brief's "spare button as SHIFT, CC 104 on channel 16"
became the record button — note **119**, channel 1.

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

## 5. Phase 0 — closed

Everything the script assumed about the hardware has now been measured. Dates and
method are in [HARDWARE.md](HARDWARE.md); this is what the sequencer depends on.

| Question | Answer |
|---|---|
| Which port does the sequencer preset use? | **Port 3.** MCP-typed banks come out of port 3 — see [HARDWARE.md 5.6](HARDWARE.md), where the flag-byte-as-port-selector explanation is superseded and the confirming experiment is still unrun. |
| What do the pads send? | **Notes 101–116, channel 1, fixed velocity 127.** A purpose-built port-3 bank. |
| How are the LEDs addressed? | **The same notes the pads send**, on the same channel, out of `MIDIOUT3`. |
| Can the two scripts share port 3? | **Yes.** Note range is the only separator — the clip launcher is 1–16, this is 101–116. Channel cannot separate them; both are channel 1. |
| Do the five buttons work in this preset? | **Yes** — notes **117–121**, channel 1. They are per-preset, not global: the launcher's bank sends 17–21, this one sends 117–121. |
| Do pads self-light on press? | **No.** Four rounds, ~78 strikes, no LED movement, and a host-set colour survives being struck. |
| Does velocity select the LED colour? | **Yes**, an absolute palette index. Everything usable is below 64; 64–112 is one flat blue. |
| How does a pad turn off? | **Note-on velocity 0.** A real note-off is ignored, silently. |
| Do the encoders reach this script? | **No, and they cannot.** Both knob banks are spent on the other script's device macros and there is no third bank. |

**The one trade you cannot configure around**, and *why* — corrected 2026-08-31:
this is not a device quirk but a consequence of the assignment type. **MCP
assignments go to port 3, are fixed-velocity, and light. Plain MIDI assignments go
to ports 1/2, are velocity-sensitive, and do not light.** MCU is a control
protocol — on/off buttons, host-driven LEDs; MIDI notes are performance data —
velocity, and no feedback path in the protocol at all. See
[HARDWARE.md](HARDWARE.md) 5.6, where the confirming experiment is written up but
not yet run.

Concretely: only port-3 banks light their
pads, and only port-3 banks are fixed-velocity. Banks on ports 1 and 2 are
velocity-sensitive but could not be lit on any port, note range or channel tried.
So a lit grid and per-step strike velocity are mutually exclusive on this device.
`USE_STRIKE_VELOCITY` stays on and inert, correct the moment a device can do both.

Still genuinely unknown, and neither blocks anything:

| Question | Status |
|---|---|
| What does PAD BANK do in this preset? | Untested. If it silently switches to a second note set, fill in `PAD_NOTES_B` so stray presses stay harmless rather than going dead. |
| Which velocities are actually teal and amber? | 20 and 15, named by eye by one observer. Swap them for whatever reads best on your unit. |

The measurement tool is here if you need to redo any of it:
`tools/mvave_probe.py --listen --port "SMC-PAD"` shows what every control sends
with its port and channel, `--knobs` maps the encoders one at a time, and
`--colours --note 1` walks the palette. [PROBE.md](PROBE.md) has the modes. Live
must not be holding the port — Windows MIDI ports are exclusive.

## 6. Installing

Copy `MVave_SMC_STEPSEQ/` into Live's Remote Scripts directory alongside the other two
(see [INSTALL.md](INSTALL.md) for the path), restart Live, and add a Control
Surface slot for `MVave_SMC_STEPSEQ`. Live 11 or newer: the clip API this uses
(`get_notes_extended`, `add_new_notes`, `remove_notes_extended`) does not exist
before that, and the script says so in `Log.txt` rather than rendering an empty
grid forever.

**First, build the preset.** The sequencer needs its own port-3 pad bank, because
the note range is the only thing that separates it from the clip launcher. In the
M-Vave editor, take a bank you do not use and give it:

- the same **port-3 setting** the clip-launcher bank has — in the `.spc` this is
  the flag byte `0x04`; the editor presents it as a mode or routing option
- **notes 101–116**, channel 1, in screen reading order

The editor numbers pads **bottom-up** — its PAD1 is the bottom-left pad — so its
PAD13–16 carry the first four notes. Confirm with
`run_probe.bat --listen --port "SMC-PAD"` before going further: you want notes
101–116 on `MIDIIN3`, channel 1, and buttons 117–121 alongside them.

**Then the Control Surface slot:**

| | |
|---|---|
| Control Surface | `MVave_SMC_STEPSEQ` |
| Input | `MIDIIN3 (SMC-PAD)` |
| Output | `MIDIOUT3 (SMC-PAD)` |

Both scripts sit on the same port and coexist because their note ranges do not
overlap: 1–16 for the clip launcher, 101–116 here. Switching the pad preset on
the device switches which one you are driving, with nothing to change in Live.

**One consequence to expect.** Both scripts render LEDs on Live-side events —
clip changes, playhead, track selection — regardless of which preset is active,
so with both loaded they will draw over each other. The fix is available and not
yet built: each script can watch for the other's note range and stand down from
drawing when it sees it, which turns the preset switch into a real mode switch.
Until then, load one at a time if the flicker bothers you.

On the port's MIDI Ports row set **Track = Off**. Notes 101–116 are real pitches
near the top of the keyboard, and with Track on and a track armed, every step you
toggle also plays a note through that instrument.

Live's `Log.txt` is the only debugger — the script logs a line on load naming
the channels and notes it is listening for, and logs any message it receives
that `MIDI_Map.py` does not describe, exactly once per signature. That last one is
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
map file's own sanity. It cannot cover the hardware — note numbers, channels,
the palette. That is section 5, on the device.

## 8. Deliberately not built

From the brief's own out-of-scope list: per-step velocity editing, aftertouch
ratchets, swing and nudge, auto-creating a clip when none is selected, reading
drum-rack pad names, note repeat, melodic and scale modes.

**Auto-following the playhead was built after all** (2026-08-31). The brief had
it as a nice-to-have defaulting to off, and this section previously argued that a
feature off by default is a feature nobody has tried. Running the sequencer in
Live for the first time settled it immediately: with a 32-step loop and a 16-pad
grid, manual paging is the whole interaction, and following makes loop length
stop mattering. It defaults to **on**.

Per-step velocity is also implemented (`USE_STRIKE_VELOCITY`) but **inert on this
hardware**: only port-3 banks light their pads, and only they are fixed-velocity.
See [HARDWARE.md](HARDWARE.md) — the trade is a property of the device.

---

## 9. To do

### Every step is written at velocity 127

The pads send a fixed 127 — MCP-typed banks are the only ones that light, and
they are not velocity-sensitive (section 5). `USE_STRIKE_VELOCITY` is on, so that
127 wins and `PAINT_VELOCITY` is never reached. A whole pattern therefore comes
out at full scale: no ghost notes, no dynamics.

The knob designed to fix this is `CC_VELOCITY`, and there is no encoder left to
send it. All sixteen are device macros on both presets — the launcher spends its
bottom pair on session navigation, the sequencer on macros 15 and 16.

Three ways out, cheapest first:

1. **`USE_STRIKE_VELOCITY = False`.** Steps then take `PAINT_VELOCITY`, a number
   you can edit. Still uniform, but not full scale, and it is one line.
2. **Draw the dynamics in Live afterwards** — which is what you would do for
   ghost notes regardless.
3. **Spend two macros.** Reassign two encoders on the sequencer preset to
   `CC_LANE` and `CC_VELOCITY` and both become live controls. The handlers are
   already written; only the device assignment is missing.

This matters more than a missing convenience. Flat velocity is exactly what made
an earlier track in this project measure as dynamically dead, and velocity is the
only dynamics lever available when the control API cannot write automation
envelopes.

### Constants describing controls that cannot exist

`CC_LANE` (20), `CC_VELOCITY` (21), `CC_LENGTH` (22) and `CC_SPARE` (23) are
unreachable for the same reason. Two of them are covered otherwise — lane
selection by holding the modifier and pressing a pad, paging by the window
following the playhead — so only velocity and pattern length are real losses.

### Confirm the MCP-vs-MIDI experiment

[HARDWARE.md](HARDWARE.md) 5.6 carries the leading explanation for why port,
velocity and LEDs move together, with the single-variable experiment written out
and not yet run.
