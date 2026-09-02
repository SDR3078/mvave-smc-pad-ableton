# `mvave_probe.py` — the MIDI probe

A standalone measurement tool for the M-Vave SMC-PAD. It opens the controller's
MIDI ports directly, sends and logs raw messages, and prints tables you can read.

It needs no Remote Script, it does not import anything from Live, and it never
touches an Ableton set. It is a MIDI monitor and a MIDI generator with a few
purpose-built interactive procedures on top.

## Why it exists

The SMC-PAD is undocumented in every way that matters to a Remote Script. The
manual names its modes and its Shift combos and stops there. It does not say
which notes the pads send, on which of the three port pairs, whether the LEDs can
be driven from the host, what velocity means when you send one back, which CC
each encoder emits, or what the VELOCITY 1–4 settings change. Every one of those
facts had to be measured, and the whole Remote Script rests on them — the note
map is in `MIDI_Map.py`, the clip colours are velocity numbers, the encoder CCs
are hard-coded in the knob script.

The probe is what produced those numbers, so it ships with the repo:

- To re-measure a different unit. Firmware revisions and `.spc` presets change
  the note map; if the pads do nothing, measure before you debug.
- To measure a different controller. Six of the eight modes are generic MIDI
  procedures with no SMC-PAD knowledge in them at all. See
  [Adapting it](#adapting-it-to-another-controller).

Everything the probe prints is an observation. Nothing in it assumes a protocol
from a port's name — which is exactly the mistake that cost this project the most
time.

## Setup

The probe runs on the machine the controller is plugged into.

### Windows

```bat
run_probe.bat --list
```

`run_probe.bat` is self-contained. On first run it creates `venv-midi` next to
itself, upgrades pip, installs `requirements-midi.txt`, verifies that
`import mido, rtmidi` works, and saves a copy of the requirements file as
`venv-midi\.deps-ok`. Later runs compare that copy against the current
requirements file and reinstall only when it has changed — so bumping a pin
takes effect on the next run instead of being silently ignored. Delete
`venv-midi\.deps-ok` to force a reinstall, or `venv-midi\` to start over. All arguments are passed through unchanged,
so every command below works with `run_probe.bat` substituted for
`python mvave_probe.py`.

The venv is deliberately separate from any other virtualenv in the project, so
installing the probe cannot disturb a rig that already works.

Requirements and failure modes:

| Symptom | Cause |
|---|---|
| `Could not create the virtual environment` | No real Python on `PATH`. Check `python --version`; the Microsoft Store stub is not enough. |
| `Could not enter ... (UNC path?)` | The script was launched from a `\\server\share` path. Map it to a drive letter first. |
| `Dependency install failed` | No network access for pip. |

On a non-zero exit the batch file prints the exit code and pauses, so it is safe
to double-click.

### Everything else (Linux, macOS)

There is no wrapper; run the script with any Python 3 that has the dependencies.

```bash
python3 -m venv venv-midi
./venv-midi/bin/pip install -r tools/requirements-midi.txt
./venv-midi/bin/python tools/mvave_probe.py --list
```

Dependencies, pinned in `requirements-midi.txt`:

| Package | Version | Role |
|---|---|---|
| `mido` | 1.3.2 | message objects and port API |
| `python-rtmidi` | 1.5.8 | the backend that actually talks to the OS |

`mido` selects `python-rtmidi` automatically; there is nothing to configure.
`python-rtmidi` ships binary wheels for common platforms — if pip falls back to a
source build you will need a C++ toolchain plus ALSA headers on Linux.

The probe writes nothing outside its own directory. To remove it, delete
`venv-midi/`.

## The exclusivity constraint — read this first

**On Windows a MIDI port has exactly one owner.** If Ableton Live holds a port,
the probe cannot open it, and you get an access-denied style error rather than
silence. This is the single most common reason a probe run "doesn't work".

Before probing a port, make Live release it:

- Close Live entirely, or
- Preferences → Link, Tempo & MIDI → untick the port's Track/Sync/Remote boxes
  and set any Control Surface using it to `None`.

Simply stopping playback is not enough. A Control Surface slot holds its ports
open for as long as Live is running.

`--listen` degrades gracefully here: it opens whichever of the matched ports it
can, prints `! could not open <port> -- in use by Live?` for the rest, and only
gives up if it could open none. Every other mode opens a single port and fails
outright.

On Linux (ALSA) and macOS (CoreMIDI) ports are multi-client and this constraint
does not apply — you can probe alongside a running DAW.

## Port naming

You never type a full port name. `--port` takes a **substring**, matched
case-insensitively against the names from `--list`.

For every mode except `--listen`, the substring must resolve to **exactly one**
port. Zero matches and multiple matches are both hard errors, and the tool prints
the candidates rather than picking one:

```
'SMC-PAD' matches 3 input ports -- be more specific:
  SMC-PAD 0
  MIDIIN2 (SMC-PAD) 1
  MIDIIN3 (SMC-PAD) 2
```

This matters on Windows, where all three port pairs of one device share a stem.
`SMC-PAD` is a substring of all three names; `"SMC-PAD 0"` — with the trailing
index, quoted — is the one that resolves. A tool that guessed here would silently
measure the wrong port and every number after that would be wrong.

`--listen` is the deliberate exception. It uses a separate resolver that returns
**every** match and watches all of them at once. When you do not yet know which
port a control lives on, watching all of them is the entire question, so
ambiguity is the feature rather than the error. `--listen --port SMC-PAD` opens
all three inputs and labels every logged line with the port it arrived on.

An input mode matched against output ports (or vice versa) simply finds nothing —
the two lists are searched independently, and the error message says which kind
it was looking for.

---

# The modes

Exactly one mode flag is required; they are mutually exclusive.

## `--list` — what ports exist?

**Answers:** what is plugged in, and what are the port names I have to feed the
other modes?

```bat
run_probe.bat --list
```

```
MIDI INPUTS  (what the SMC-PAD sends us)
    SMC-PAD 0
    MIDIIN2 (SMC-PAD) 1
    MIDIIN3 (SMC-PAD) 2

MIDI OUTPUTS  (what we can send to the SMC-PAD)
    SMC-PAD 1
    MIDIOUT2 (SMC-PAD) 2
    MIDIOUT3 (SMC-PAD) 3

The DAW manual calls these Port 2 (generic) and Port 3 (Mackie/DAW);
on Windows they usually show up as MIDIIN2/MIDIIN3 or similar.
```

**Reading it:** the SMC-PAD exposes three port pairs. Names differ per OS and per
driver, so copy what you see; do not copy the names above. This is the only mode
that ignores `--port`.

A port pair being present tells you nothing about what it carries. That is the
next mode's job.

## `--listen` — what does the device send?

**Answers:** which notes, CCs and channels does each control emit, on which port,
and with what values?

```bat
run_probe.bat --listen --port MIDIIN3
run_probe.bat --listen --port SMC-PAD --seconds 120
```

The second form watches all three inputs at once — the right first move on an
unknown device.

It logs live, then summarises:

```
Listening on 1 port(s) for 60 seconds:
    MIDIIN3 (SMC-PAD) 2

Press the pads and buttons, and turn every knob both ways.
Ctrl+C to stop early.

     3.21s  MIDIIN3 (SMC-PAD) 2    note_on channel=0 note=1 velocity=127 time=0
     3.34s  MIDIIN3 (SMC-PAD) 2    note_on channel=0 note=1 velocity=0 time=0

--- summary: 21 distinct controls ---
  port                   type           ch  num    count  values seen
  MIDIIN3 (SMC-PAD) 2    note_on        1   1          8  0, 127
  MIDIIN3 (SMC-PAD) 2    note_on        1   2          4  0, 127

MIDI channels seen: 1
```

Ctrl+C ends the run early and still prints the summary.

**Reading it:**

- The summary is keyed by (port, message type, channel, note-or-CC number). One row is one
  physical control — press each pad a few times and count the rows.
- `values seen` lists up to 10 distinct values; past that it collapses to
  `... (N distinct, range LO-HI)`.
- A pad that reports `0, 127` is a button, not a velocity-sensitive pad: 127 on
  press, note-on velocity **0** on release. Note that it is not sending a real
  note-off.
- If any `control_change` rows appeared, the tool prints an encoder-encoding
  hint: a couple of distinct values (1 and 127, or 65 and 63) means the encoder is
  **relative** and each tick reports a direction; a wide spread across 0–127
  means **absolute** and it reports a position.
- A control that produces no row sent nothing. That is a real result — on this
  device SHIFT sends nothing on any port, because the firmware consumes it for
  the Shift+Pad combos.

Aftertouch and polyphonic aftertouch are filtered out of both the log and the
summary. They flood the output and say nothing about layout.

**Limit:** a flat listen run is a poor way to map *many* controls, because
nothing is confirmed while you are doing it. Use `--knobs` for encoders. See
[Design notes](#design-notes).

## `--light` — can the host light the pads at all?

**Answers:** does this device respond to incoming MIDI on its LEDs, yes or no?

```bat
run_probe.bat --light --port MIDIOUT3
run_probe.bat --light --port MIDIOUT3 --lo 0 --hi 31 --velocity 5 --hold 5
```

```
Sending note-on to notes 0-127, velocity 127, channel 1 on 'MIDIOUT3 (SMC-PAD) 3'.
WATCH THE PADS. Holding for 3s, then clearing.

Cleared. Did anything light up?
```

It blasts note-on to every note in `--lo`..`--hi`, holds for `--hold` seconds,
then extinguishes the same range. A blunt instrument, and the right first test:
it answers the gating question in ten seconds without needing to know the note
map.

**Reading it:** anything lighting up means the LEDs are host-drivable and the
project is viable. Nothing lighting up means either the wrong port, the wrong
channel (`--channel`), or a device that does not accept LED MIDI.

**Two traps, both hit during the original measurement:**

1. **"All pads lit" is not "the host can set colours."** They may have lit in the
   colour already configured on the device. Distinguishing local colour from host
   colour requires `--colours`.
2. **A pad that stays dark may not be dead — and this is why the sends are
   paced.** The original `--light` sent up to 128 note-ons back to back with no
   throttle, overran the device's MIDI input buffer, and reported 15 of 16 pads
   on a grid where all 16 work; the sixteenth lit fine when addressed alone.
   Every bulk send now goes through `_paced()`, which leaves `SEND_GAP` (2 ms)
   between messages — well under a human's notice, and enough for this device.
   Keep that pacing if you port the send path elsewhere. Confirm a suspect pad
   with a single-note test (`--light --lo N --hi N`) before designing around it.

## `--sweep` — which notes address the pads?

**Answers:** given that *something* lights, which note numbers actually map to
the grid?

```bat
run_probe.bat --sweep --port MIDIOUT3
run_probe.bat --sweep --port MIDIOUT3 --step 8 --hold 1.5 --lo 0 --hi 63
```

```
Sweeping notes 0-127 in blocks of 16 on 'MIDIOUT3 (SMC-PAD) 3', 3.0s per block.

  notes   0- 15 ...
  notes  16- 31 ...
  notes  32- 47 ...

Which block lit the pads?
```

Each block is lit, held for `--hold`, cleared, then a fixed 0.15 s gap before the
next. Ctrl+C clears the whole `--lo`..`--hi` range on the way out, so an
interrupted sweep does not leave the grid lit.

**Reading it:** watch which printed block coincides with the grid lighting, then
re-run with `--lo`/`--hi` narrowed to that block and `--step 1` to isolate
individual notes. Two passes usually pin the range exactly.

Do not assume the answer from the port's name. This device's DAW port sends and
accepts notes 1–16 for the grid and 17–21 for the buttons — not Mackie Control's
numbering, despite being the Mackie port.

## `--colours` — what does velocity mean on an LED?

**Answers:** is the velocity byte a brightness, or an index into a colour
palette? And if it is a palette, what is the table?

```bat
run_probe.bat --colours --port MIDIOUT3 --note 1
run_probe.bat --colours --port MIDIOUT3 --note 1 --velocities all
run_probe.bat --colours --port MIDIOUT3 --note 1 --velocities 5,14,15,21,24,40
```

The mode walks one note through a list of velocities, **stopping at every step**
for you to type what you see:

```
Note 1 on 'MIDIOUT3 (SMC-PAD) 3' -- 21 steps.
Look at the pad, type the colour, press Enter.
Enter on its own records nothing. Type 'q' to stop early.

  velocity   1  colour? pastel orange
  velocity   2  colour? pastel orange
  velocity   3  colour? yellow-white
```

Then two tables — the raw log, and the one that matters:

```
--- velocity -> colour ---
    1  pastel orange
    2  pastel orange
    3  yellow-white

--- grouped ---
  1-2       pastel orange
  3         yellow-white
```

Enter on its own records `?` for that step and moves on. `q` stops early and
still prints what was collected. The pad is extinguished on exit however you
leave.

**Reading it:** the grouped table collapses runs of identical answers into
velocity **ranges**, which is the usable form — what a Remote Script needs is
"which velocity range gives which colour", not 127 individual readings. If the
colours change hue as the number climbs, velocity is a palette index and the
device supports a real colour grid. If they only get brighter, it is a
brightness.

This is also the test that separates host-set colour from device-configured
colour: a pad configured pure green in the `.spc` that nevertheless shows pink,
blue and orange here proves the host owns the colour.

`--velocities` accepts three forms:

| Value | Steps |
|---|---|
| `coarse` (default) | 21 steps: 1–8, 12, 16, 20, 24, 32, 40, 48, 60, 64, 80, 96, 112, 127 |
| `all` | every velocity 1–127 |
| `5,14,21,40` | exactly those, in that order |

Start with `coarse`; it reveals the shape of the palette in about a minute. Use
`all` only to pin down a boundary `coarse` has bracketed.

## `--clear` — turn everything off

**Answers:** nothing. It cleans up after a run that left the grid lit.

```bat
run_probe.bat --clear --port MIDIOUT3
```

```
Sent note-on/velocity-0 to notes 0-127 on 'MIDIOUT3 (SMC-PAD) 3'.
```

It always covers the full range 0–127 and **ignores `--lo`/`--hi`**. It does
respect `--channel`, so clear on the same channel you lit.

**How it clears is load-bearing.** Everything the probe extinguishes uses
**note-on with velocity 0**, never a real note-off (`0x80`). The SMC-PAD reports
its own pad releases that way and appears to ignore `0x80` entirely — clear with
a proper note-off and every pad stays stuck lit. Convenient for the Remote
Script: `_Framework` lights note-type buttons via `send_value()`, which emits
note-on with the value as velocity, so the template already speaks this dialect.

## `--curves` — what do the VELOCITY 1–4 settings do?

**Answers:** does the device's Shift+Pad 9–12 velocity-curve setting change the
velocity bytes the pads transmit, or the LED behaviour, or neither?

```bat
run_probe.bat --curves --port "SMC-PAD 0" --port2 MIDIIN3
```

`--port2` is optional and unique to this mode. It opens a **second input** and
samples both simultaneously, because the whole question is whether the playing
port and the DAW port behave differently. Both must resolve to exactly one input
port each, and resolving to the same port is an error.

The run is interactive, four settings deep:

```
Measuring VELOCITY 1-4 on:
   SMC-PAD 0
   MIDIIN3 (SMC-PAD) 2

--- VELOCITY 1 ---
  Select it: hold SHIFT, press PAD 9, release. Then Enter here.
  Now hit ONE pad about 10 times, softest to hardest. Enter when done.
  What did the pad's own LED do while you played?
```

Setting *n* is selected with Shift + Pad *8+n*, so pads 9, 10, 11 and 12. After
you confirm the selection the input buffers are flushed, because the Shift combo
itself may emit traffic and it would otherwise land in the sample and skew the
numbers. Only `note_on` messages with velocity > 0 are counted.

Output:

```
=== VELOCITY setting -> transmitted velocity ===
setting  port                      hits   min   max  distinct values
1        SMC-PAD 0                    0     -     -  nothing received
1        MIDIIN3 (SMC-PAD) 2         10   127   127  127
2        SMC-PAD 0                    0     -     -  nothing received
2        MIDIIN3 (SMC-PAD) 2         11   127   127  127

=== LED behaviour while playing ===
  VELOCITY 1: no change
  VELOCITY 2: no change

If every setting gives the same min/max/spread, the curves do nothing
on that port -- most likely because the pads carry a fixed velocity
byte in the .spc, which would override any curve.
```

**Reading it:** compare min/max/spread down the four settings for one port. A
working curve shows different distributions per setting. Identical numbers mean
the curve is not reaching that port. On the measured unit every setting
transmitted a flat 127 on the DAW port — the per-pad velocity byte in the active
`.spc` bank is a fixed `0x7f` and overrides any curve — and the LED column stayed
empty, which is what licenses the Remote Script to skip re-asserting colour after
a press.

The free-text LED column is recorded verbatim and reprinted at the end. Ctrl+C or
EOF at any prompt stops the run and prints what was gathered so far.

Note that this mode opens its ports without the fallback `--listen` has: if Live
holds either port, it fails immediately. Release both first.

## `--knobs` — which CC does each encoder send?

**Answers:** the full encoder map — CC number per encoder per bank, relative or
absolute, plus which encoders are silent and which collide.

```bat
run_probe.bat --knobs --port "SMC-PAD 0"
run_probe.bat --knobs --port "SMC-PAD 0" --banks 1 --count 8
```

`--banks` (default 2) is how many bank-switch positions to walk; `--count`
(default 8) is encoders per bank. It prompts once per bank and once per encoder:

```
Mapping 8 encoder(s) across 2 bank(s) on 'SMC-PAD 0'.
Enter alone records nothing and moves on. 'q' stops and prints what we have.

=== knob bank 1 -- press KNOB BANK until you are on it, then Enter.
   encoder 1: turn it a few clicks each way, then Enter.
      ch 1  CC 7    relative   26 msgs  [63, 65]
   encoder 2: turn it a few clicks each way, then Enter.
      ch 1  CC 8    relative   19 msgs  [63, 65]
```

The verdict for each knob is printed **while you are still holding it**. The
input buffer is flushed before each encoder prompt, so one knob's messages cannot
bleed into the next knob's reading — including the traffic from the bank switch
itself, which is discarded by the first encoder's flush. An
encoder that emits more than one CC gets one line per CC, ordered by message
count descending. `q` at either prompt stops and prints the partial map.

The final report:

```
=== encoder map ===
  bank  encoder  ch  CC    mode         msgs  values
  1     1        1   7     relative       26  63, 65
  1     2        1   8     relative       19  63, 65
  2     3        1   10    relative        9  63, 65
  2     7        1   9     relative       14  63, 65
  2     8        1   10    relative       11  63, 65

Sent nothing: bank 1 enc 4
CLASH: bank 2 ch 1 CC 10 came from encoders 3, 8
```

**Reading it:**

| `mode` | Criterion | Meaning |
|---|---|---|
| `relative` | values ⊆ {63, 64, 65}, or ⊆ {1, 127}, or ⊆ {1, 64, 127} | each message is a **step**: direction, not position |
| `relative?` | 3 or fewer distinct values, none of the patterns above | probably relative — turn it further and re-run to be sure |
| `absolute` | more than 3 distinct values | each message is a **position** on 0–127 |
| `-` | nothing received | silent |

The distinction decides how a control can be used. An absolute CC carries a value
and maps cleanly onto a continuous parameter like volume or cutoff. A relative CC
carries a step and is the only correct choice for anything whose state can also
be changed elsewhere — a session-box position moved by the arrow keys and the
mouse will desync an absolute knob's internal counter immediately, and the box
will teleport the next time you touch it.

`Sent nothing:` names every encoder that produced no CC. `CLASH:` names every
case where two encoders in the same bank produced the same CC **on the same
channel** — two encoders sharing a CC number across different channels are
distinguishable, so they are not a clash. Both are printed
by bank and encoder number, so you know which physical knob to go back to.

Two results worth expecting: bank switching is usually a whole-bank operation, so
an encoder that looks dead may just be on the other bank — check the bank before
debugging a knob. And the CC numbers need not follow the printed encoder numbers.
On this device bank 2 descends in pairs as the labels ascend; wire macros in
numeric CC order and they scatter across the panel.

---

# Flags

Exactly one mode flag is required and they are mutually exclusive:
`--list`, `--listen`, `--light`, `--sweep`, `--colours`, `--clear`, `--curves`,
`--knobs`.

| Flag | Type | Default | Used by | Meaning |
|---|---|---|---|---|
| `--port` | string | none | all but `--list` | Substring of the MIDI port name. Must resolve to exactly one port, except under `--listen`, which takes every match. Omitting it prints the available ports and exits. |
| `--port2` | string | none | `--curves` | A second input port to watch simultaneously. Must resolve to exactly one port, and not the same one as `--port`. |
| `--channel` | int | `1` | `--light`, `--sweep`, `--colours`, `--clear` | MIDI channel, 1–16 on the command line, sent as 0–15 on the wire. |
| `--lo` | int | `0` | `--light`, `--sweep` | Lowest note to touch. |
| `--hi` | int | `127` | `--light`, `--sweep` | Highest note to touch. |
| `--velocity` | int | `127` | `--light`, `--sweep` | Velocity of the lighting note-ons. |
| `--hold` | float | `3.0` | `--light`, `--sweep` | Seconds to hold each step lit. |
| `--step` | int | `16` | `--sweep` | Notes per block. |
| `--seconds` | int | `60` | `--listen` | How long the listen runs before summarising. |
| `--banks` | int | `2` | `--knobs` | Knob banks to walk. |
| `--count` | int | `8` | `--knobs` | Encoders per bank. |
| `--note` | int | `0` | `--colours` | Which note to walk through the velocity list. |
| `--velocities` | list | `coarse` | `--colours` | `coarse`, `all`, or a comma-separated list. See the [`--colours`](#--colours--what-does-velocity-mean-on-an-led) table. |

`--clear` ignores `--lo`/`--hi` and always covers 0–127. Input modes (`--listen`,
`--curves`, `--knobs`) ignore `--channel` — they record whatever channel arrives.
`--listen` and `--knobs` also *report* it, since a summary that omits the channel
agrees equally well with two mutually exclusive theories; `--curves` keeps only
velocities and cannot.

Numeric flags are range-checked before any port is opened: `--channel` takes
1–16, `--lo`/`--hi`/`--velocity`/`--note` take 0–127, `--step` 1–128, `--seconds`
1–86400, `--banks` 1–16, `--count` 1–64, `--hold` 0–3600 seconds (rejecting `nan`
and `inf`), and `--velocities` rejects anything outside 0–127. `--lo` must also
not exceed `--hi`, which is legal individually but sends nothing. A bad value is an argparse error, not a traceback from
inside a run you have already started answering prompts for.

---

# Design notes

Two choices in this script are the difference between a measurement that works
and one that lies.

## 1. `--colours` and `--knobs` stop at every step, on purpose

Both could have been written as timed sweeps: fire a sequence, wait, collect at
the end. Both are interactive instead, and each step blocks until you press
Enter.

The reason is that a timed sweep outsources the hard part to human memory. For
`--colours` it asks you to watch 21 colours go past and then recall the sequence
— the thing humans are worst at. For `--knobs` it asks you to turn sixteen
controls in a prescribed order, correctly, with no feedback.

This is not a theoretical concern. The first attempt at the encoder map was
exactly that: one 180-second `--listen` run with a written turn order. It came
back with 14 of 16 encoders, two CCs missing entirely and one mode misreported as
relative — and there was no way to tell *which* step went wrong, because nothing
had been confirmed as it happened. The same physical procedure, rewritten with a
checkpoint at every knob, produced a clean 16 of 16 with the clash and the silent
knob named.

**When a measurement asks a human to sequence many steps correctly, put a
checkpoint at every step, not at the end.** The interactive version is slower to
run and vastly faster to trust.

Both modes therefore accept `q` to stop early and print what was gathered, and
both treat a bare Enter as "nothing here, move on" rather than an error — a
partial map you can trust beats a full one you cannot.

## 2. `--knobs` reports per knob, and names what went wrong

Each encoder's verdict — CC, mode, message count, values — prints immediately
after that encoder, while your hand is still on it. A knob that sends nothing, or
sends the same CC as its neighbour, is visible on the spot and can be re-tested
in five seconds, rather than surfacing as a hole in a table twenty minutes later
when you no longer know which knob it was.

The end-of-run report then makes both failure classes explicit by name rather
than leaving them to be spotted:

```
Sent nothing: bank 1 enc 4
CLASH: bank 2 ch 1 CC 10 came from encoders 3, 8
```

A silent knob and a duplicated CC are the two mistakes that produce a plausible
map — one that is complete-looking, wrong, and only fails much later inside a
Remote Script where the cause is invisible. Naming them at measurement time is
the cheapest place to catch them.

---

# Adapting it to another controller

Most of the script is generic. `--list`, `--listen`, `--light`, `--sweep`,
`--colours` and `--clear` contain no SMC-PAD knowledge beyond default values and
some prompt wording.

## A procedure for an unknown device

1. `--list` — get the port names.
2. `--listen --port <device stem>` — watch every port at once and touch every
   control. This gives you the note/CC map, the channel, the release convention
   and which port carries what.
3. `--light --port <output>` — does anything light? Try `--channel` variations if
   not.
4. `--sweep --port <output>` — narrow to the note range, then re-run with
   `--step 1` over that range.
5. `--colours --port <output> --note <a pad you found>` — palette or brightness,
   and the velocity→colour table.
6. `--knobs --port <input> --banks N --count M` — the encoder map.
7. `--clear --port <output>` — tidy up.

## What to change in the source

| Location | Assumption | When to change it |
|---|---|---|
| `DEFAULT_CHANNEL` | Device is on MIDI channel 1 | Use `--channel` per run, or change the constant if your device lives elsewhere permanently. |
| `_off()` | LEDs are extinguished with note-on velocity 0 | If your device honours a real note-off (`0x80`), send that instead. Test both: on the SMC-PAD, note-off leaves every pad stuck lit. |
| `cmd_light` / `cmd_sweep` / `cmd_colours` | LEDs are addressed by **note-on, velocity = colour** | Devices that use SysEx or CC for LED colour need these rewritten. The message construction is one `mido.Message(...)` call in each function. |
| `_classify()` | Relative encoders use 63/64/65 or 1/64/127 | Other relative encodings exist (binary offset, signed bit, 2's complement with different centres). Add your device's values to the sets, or read the raw numbers from `--listen` and classify by eye. |
| `cmd_curves` prompts | Velocity curves are selected with Shift + Pad 9–12 | This is the one genuinely device-specific mode. Change the prompt strings, or ignore the mode entirely. The measurement logic — flush, sample, tabulate per setting — transfers to any four-way hardware setting. |
| `cmd_knobs` prompts | There is a KNOB BANK button that shifts all encoders at once | Reword the prompt; set `--banks 1` for a device with no banks. |
| `cmd_list` closing text | Names Port 2/Port 3 of this device | Cosmetic. |

## Things that transfer regardless of device

- **Never infer a protocol from a port's name.** This device's "Mackie" port sends
  notes 1–16, not Mackie Control's numbering. Measure it.
- **Test the assumption everything else depends on, first.** This whole project
  rested on "can the pads be coloured by incoming MIDI", and plans were built on
  top of that for a long time while it was unverified. A ten-minute `--light` run
  answered it.
- **Distinguish "it lit" from "the host set the colour."** They are different
  claims and need different tests — `--light` answers the first, `--colours`
  answers the second.
- **A dark pad may be a dropped message.** Bulk note-ons can overrun a device's
  MIDI buffer. Re-test a suspect control on its own before believing it is dead.
