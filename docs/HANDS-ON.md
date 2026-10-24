# SMC-PAD + Ableton: hands-on reference

Current working build: **2026-10-15**. Ableton Live 12.4.6 Suite, Windows.
The user has confirmed probability, drum activity, macro locks, mutes and native
recording, and reports smooth, glitch-free jamming in their sessions.

## Five performance essentials

- **Step sequencing:** tap pads to build a drum's sixteenth-note pattern.
- **Parameter locks:** hold active steps and turn a macro to shape those hits.
- **On-the-fly mutes:** mute drums without deleting their patterns or locks.
- **Real-time record mode:** capture macro gestures with Live's Session recorder.
- **Eight-knob macro control:** select a drum and control its Instrument Rack.

Also included: four probability levels, cyan pattern-activity indicators,
pinned Drum Rack tracks, drum-bank navigation and automatic pattern following.

## Current files and installation

Download this contribution and copy the two complete folders below into your
Ableton User Library `Remote Scripts` directory. See [INSTALL.md](INSTALL.md).

| Folder | Required files |
|---|---|
| MVave_SMC_STEPSEQ | __init__.py, MIDI_Map.py, MVave_SMC_STEPSEQ.py, ParameterLocks.py, NativeRecording.py |
| MVave_SMC_KNOBS | __init__.py, MVave_SMC_KNOBS.py |

Close Live before installing and restart after updates. Keep a backup of your installed scripts before updating.
See [CHANGELOG.md](../CHANGELOG.md) for release history.

## Controller setup and recovery

Import `reference/sequencer.spc` in MidiSuite, choose **Preset 2**, then Save to
the controller. Use **pad bank 3**, **knob bank 1**, **Transpose 0**.

- Hardware **SHIFT + PAD2** selects preset slot 2. PAD2 is the **bottom row,
  second pad from the left**. Release SHIFT before playing.
- Top-left physical pad is **PAD13** in MidiSuite: **MCP type, note 101**.
- Pads transmit notes 101-116 on channel 1; transport buttons use 117-121.
- Relative knobs send 63 left and 65 right.

Hardware SHIFT changes controller settings; **Record** selects drums in our
script. SHIFT + NOTE REPEAT enters hardware repeat-settings mode. Unexpected
white/yellow layouts or unresponsive steps: check preset, bank and Transpose 0.
If needed, reimport the sequencer preset and Save. Close MidiSuite before Live.
Restart Live on the correct preset to refresh all LEDs.

## Live setup

Settings > Tempo & MIDI:

| Control Surface | Input | Output |
|---|---|---|
| MVave_SMC_STEPSEQ | SMC-PAD (Port 3) | SMC-PAD (Port 3) |
| MVave_SMC_KNOBS | SMC-PAD (no port suffix) | None |

For this dedicated setup, leave input Track, Sync and Remote off for the SMC-PAD
ports. LED feedback uses the Control Surface output. No Ctrl+M mapping is needed.

Use one Drum Rack per track and a looping **Session MIDI clip**. Launch the clip
with its Session triangle; global transport alone may not launch it. The
controller pins its drum track when you click elsewhere. Arrows select another
Drum Rack track without launching/stopping clips. On a track switch it prefers
the playing MIDI clip, then the remembered clip, then the first MIDI clip.

## All performance controls

| Gesture | Action |
|---|---|
| Tap a pad | Toggle a sixteenth-note step on release |
| Hold active step(s) + knob | Write a macro parameter lock on those steps |
| Hold active step(s) + < / > | Lower/raise note probability; keep holding for repeated presses |
| Hold Record + pad | Select a drum and its Instrument Rack macros |
| Hold Pause/Stop + pad | Mute/unmute that drum, preserving notes and locks |
| Hold Record or Pause/Stop | Show drum state with cyan pattern-activity pulses |
| Turn an unheld knob | Adjust the macro; step-locked macros support live base edits |
| Play | Start/stop transport; stopping also ends native capture |
| Hold Record + press Play | Toggle native macro recording while playback continues |
| < / > alone | Switch Drum Rack tracks |
| Hold Record + < / > | Change the bank of 16 drum pitches |
| Hold Pause/Stop + < / > | Page the pattern; release to see steps |

Steps run **top-left first**, across/down. Drum selection/mutes run **bottom-left
first**, across/up, matching Live's rack. Initial pitches: 36-51. One/two/four
bars in 4/4 contain 16/32/64 steps. Longer patterns follow playback automatically;
manual paging resumes following on loop wrap or stop. A one-bar loop has one page.

## Probability and activity

| Trigger probability | LED palette value |
|---|---|
| 100% - new-step default | 64 |
| 75% | 9 |
| 50% | 21 |
| 25% | 7 |

Hold one or more active steps and tap Left/Right to lower/raise chance. Keep
holding for repeated arrow presses. Levels stop at 25%/100%; release keeps the
notes. Live stores chance in the clip and makes the random decisions. The LEDs
use fixed palette colours, not adjustable brightness. External chance values
display the nearest level; viewing does not change them.

In Record and Pause/Stop views, cyan pulses mark programmed hits for the first
half of each step. Between pulses: green = populated/unmuted, red-pink = muted,
white = selected in Record view. Populated but unprogrammed drums remain steady;
empty slots stay dark. Activity follows **the bound clip's pattern**, not detected
audio: muted drums and probability-skipped hits still pulse. Disabled clip notes
do not. Other clips, MIDI effects and live input are not represented.

The step-view playhead remains amber on empty steps and white on active steps;
it shows note presence, not confirmation that a probability-based hit played.

## Eight macros per drum, including stock kits

Click a drum pad to expose its instrument. If it contains only Simpler, click
**Simpler's title bar** and press **Ctrl+G** to wrap it in an Instrument Rack
inside that pad. If a suitable Instrument Rack already exists, use its macros.

Show that rack's Macro Controls. Right-click useful parameters and map them to
Macro 1-8. Use the rack's Map mode to limit ranges. A consistent starting layout
is Pitch, Decay, Filter Frequency and Resonance. Select the drum again using
Record + pad, then turn the hardware knobs.

| Knob pair, top to bottom | Macro pair |
|---|---|
| Hardware 7 / 8 | 1 / 2 |
| Hardware 5 / 6 | 3 / 4 |
| Hardware 3 / 4 | 5 / 6 |
| Hardware 1 / 2 | 7 / 8 |

Use knob bank 1. The first direct Instrument Rack across the pad's chains is
the macro target. Plain instrument pads still sequence/mute but need that rack
for macros. Save the whole Drum Rack preset to reuse your mappings.

## Parameter locks and real-time recording

**Step locks:** hold existing steps and turn a knob. A macro value is written
as stepped clip automation for those steps. Release keeps the notes. Turn an
unheld knob to adjust the base while locks keep their saved absolute values.
Remove locks by editing envelopes in Live; there is no hardware clear-lock command.

**Real-time macro recording:**

1. Duplicate a Session clip, launch it, and select a drum with Record + pad.
2. Hold Record and press Play, then release both to start native recording.
3. Turn the eight macros to record your performance as Session automation.
4. Record + Play again ends capture while playback continues.
5. Play alone stops playback and ends capture.

The drum track arms automatically; other tracks are temporarily disarmed. Their
previous arm states and the prior Automation Arm setting return afterward.
Existing Live recording must be off before starting. Record stays lit during
capture. No script scale/step snapping is applied; quantized synth parameters
still move in their own increments.

After capture, an unheld knob temporarily overrides its recorded curve. The
unchanged curve resumes about 0.3 seconds after knob inactivity; the grey
automation indicator returns to red. Step-locked macros use base editing instead.

## Bass workflow, saving and limits

Inside a Drum Rack pad, an Instrument Rack contains **Sting 2 followed by Analog**.
Sting 2 is the **smiley-face device** and generates bass notes. Analog makes the
sound; the controller shapes it through the rack macros.

Current bass macros: 1 OSC1 Semi, 2 Filter Cutoff, 3 Resonance,
4 Filter Envelope Amount, 5 Filter Envelope Decay, 6 Amp Envelope Decay.
Macros 7-8 are available for extras such as glide or Saturator drive.

Save the **Live Set** for notes, chance, automation and mute states; a **Drum Rack
preset** for instruments/mappings; the **hardware preset** separately in MidiSuite.

The continuous-curve/step-lock distinction is session-only. After restart, avoid
ordinary base edits on free curves: adopting an envelope can sample it at step
resolution. A held-step edit can also convert a free curve to steps. Recording
can replace existing automation/locks on touched parameters. Use separate clips
for free curves and lock experiments.

Loop-bound changes, external envelope edits and undo can stale lock metadata;
restart before further lock edits in those cases. Only the first Drum Rack per
track is supported. Old custom recording, scale-snapping and record-latch paths
remain archived. The former four-lane overview is internal, not a Pause binding.

## Verification

From the main source folder:

    python -m unittest discover -s tools -p "*selftest.py"

**185 offline tests pass.** API stubs cover sequencing, locks, recording, drum
modes, probability and activity. The user's real controller sessions additionally
confirmed probability, repeated held-step edits, indicators and smooth operation.

Based on SDR3078/mvave-smc-pad-ableton with local extensions. Upstream licence
and attribution notes remain in the source README.
