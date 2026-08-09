# M-Vave SMC-PAD — measured MIDI reference

Everything the SMC-PAD sends, everything it accepts, and the format of its
configuration file. All of it measured on real hardware, because there is no
usable public documentation for this device — the manufacturer's manuals name
the controls and stop there.

**How this was measured.** With `tools/mvave_probe.py`, run on the Windows PC the
controller is plugged into, talking straight to the MIDI ports with no Remote
Script and no DAW involved. Pads, LEDs and the velocity settings were measured
2026-08-02; the encoder map 2026-08-03. `tools/mvave_probe.py` is in this repo,
so any of it can be re-run.

**How to read the claims.** Anything stated flatly here was observed directly.
Anything that was inferred but never tested is marked **Hypothesis** and says so.
That distinction is load-bearing: several early wrong turns in this project came
from treating a plausible inference as a fact, and they are recorded below rather
than quietly fixed.

**Scope.** Windows. None of this has been checked on macOS or Linux; the port
names at minimum will differ there.

---

## 1. MIDI ports

### 1.1 Three port pairs

The SMC-PAD enumerates as three independent in/out pairs:

| # | Windows port name | Sends (device → host) | Accepts (host → device) |
|---|---|---|---|
| 1 | `SMC-PAD` | encoder CCs | not tested |
| 2 | `MIDIIN2` / `MIDIOUT2` | encoder CCs, identical to port 1 | not tested |
| 3 | `MIDIIN3` / `MIDIOUT3` | pad and button notes | pad LED colours |

"Port 1/2/3" throughout this document means the Windows enumeration above, in
that order. The manufacturer's material refers to a *generic* port and a
*Mackie/DAW* port without matching them to those names; port 3 is the DAW one.

All LED work here was done through `MIDIOUT3`. Whether the other two output ports
also light pads was never tested. Mackie mode was the interesting one to begin
with precisely because it was the only mode on this device that sends anything
*back* for lighting.

The split matters more than it looks. **The pads are on port 3 and the encoders
are on ports 1 and 2, and no port carries both.** An Ableton Remote Script gets
exactly one input port, so a single script physically cannot see the whole
controller. That is a hardware fact, not a software limitation, and it is why
this repo ships two scripts.

Two further measured details:

- The encoders appear on ports 1 and 2 **identically** — same CC numbers, same
  message counts. Port 2 is a mirror, not a second layer.
- Encoders never appear on port 3, and in pad preset bank 3 the pads never
  appear on port 1. (Port 1 was watched during the velocity-curve test and
  received nothing at all while pads were being struck.)

### 1.2 Windows MIDI ports are exclusive

Only one process may hold a given port. If Live has a port open, nothing else
can open it — you get an access-denied style error. Before running any probe,
either close Live or untick that port in **Preferences → Link, Tempo & MIDI**.
This is the single most common reason a probe run comes back empty.

`mvave_probe.py --listen` deliberately opens what it can and skips what it
cannot, so one port held by Live does not abort a run across the other two.

### 1.3 Port names collide — disambiguate with the index

`SMC-PAD` is a substring of all three Windows port names, so tools that resolve
port names by substring will match all of them. `mvave_probe.py` refuses rather
than guessing; pass the trailing index, e.g. `"SMC-PAD 0"`.

### 1.4 A Live Control Surface takes its port away from Ctrl+M

Assigning a port to a Control Surface slot in Live **disables Track, Sync and
Remote for that port**. Any MIDI mappings you had made through Ctrl+M on that
port stop working silently — nothing is reported, the knobs just go dead.

This was found the hard way: putting the encoder script on port 1 killed a set of
existing macro mappings that had been arriving there.

**Ports 1 and 2 being identical is what makes this survivable.** A script claims
one of them, and Live's Remote stays enabled on the other, so the same physical
encoders remain available to Ctrl+M. In this repo's layout, port 1 goes to the
script and port 2 is left unassigned with Remote on.

---

## 2. Pads and buttons (port 3)

### 2.1 Note map

Sixteen pads, MIDI channel 1, **notes 1–16 in reading order** — top-left is 1,
bottom-right is 16:

```
 1   2   3   4
 5   6   7   8
 9  10  11  12
13  14  15  16

buttons = 17 - 21
```

### 2.2 Press and release encoding

- Press: note-on, **velocity 127**, every time.
- Release: **note-on with velocity 0** — not a note-off (`0x80`).

The pads are not velocity-sensitive on this port. Every strike reports 127
regardless of how hard you hit it, so on port 3 the pads are buttons, which is
what a clip grid wants. (Section 5.2 explains why the velocity is fixed, and
section 6 covers the VELOCITY settings that do not change it.)

The note-on/velocity-0 idiom matters in both directions. The device uses it for
its own releases, and it is also the only thing it accepts for turning an LED
off — see section 3.3.

### 2.3 This is *not* Mackie/MCU numbering

Port 3 is the "DAW"/Mackie port, and that name tells you nothing about the
protocol on it. Real MCU would be arm 0–7, solo 8–15, mute 16–23, select 24–31,
transport 91–95. The SMC-PAD sends 1–16 and 17–21.

Assuming MCU numbering because of the port's name was one of the first wrong
calls in this project and cost real time. Measure the port; do not read its
label.

### 2.4 The five transport/function buttons

The five buttons above the grid send **notes 17–21** on port 3, with the same
press/release encoding as the pads.

The session log records that these buttons had already been configured on the
device to line up with the script's map before they were measured. It does not
establish whether 17–21 is a factory default or the result of that
configuration. **If you own one of these, measure your own buttons before
trusting 17–21.**

For what it is worth, the `.spc` configuration file's five SysEx-button records
carry id bytes 17, 18, 19, 20, 21 — the same range (section 5.1). The
relationship between those id bytes and the notes port 3 emits was never
established.

---

## 3. Pad LEDs

### 3.1 Velocity is a palette index, not a brightness

Send a note-on to note *n* on `MIDIOUT3` and pad *n* lights. The velocity byte
selects a **colour from a fixed palette**. It is not brightness, and it is not a
modifier on the pad's configured colour: a pad configured pure green
(`#00ff00`) in the `.spc` still displays pink, blue and orange when driven with
the right velocities. **The palette is absolute.**

The hue cycles roughly every 13–14 steps, with the wash/pastel-ness varying
between cycles.

### 3.2 The measured palette

Built with `mvave_probe.py --colours`, which lights one pad at one velocity, waits
for you to type what you see, and moves on. Colour names are therefore one
observer's description by eye, not measured chromaticity — treat them as
identification, not specification.

| Velocity | Colour |
|---|---|
| 0 | off |
| 1–2 | pastel orange |
| 3 | yellow-white |
| 4 | yellow |
| 5 | green |
| 6 | turquoise |
| 7 | light blue |
| 8 | cold white-blue |
| 9 | light blue |
| 10 | white-blue |
| 11 | light pink |
| 12 | pink |
| 13 | white |
| 14 | red-pink |
| 15 | orange |
| 16 | pastel pink-orange |
| 17 | yellow |
| 18 | pastel green |
| 19 | absinth green |
| 20 | turquoise |
| 21–23 | bright blue |
| 24 | light purple |
| 32 | yellow-white |
| 40 | white |
| 48 | blue-white |
| 60 | light yellow |
| 64–112 | blue (flat — no variation across the whole range) |
| 127 | green |

Values between the sampled points above 24 were not walked exhaustively.

**What this means in practice:**

- **Everything usable lives below ~64.** The entire top half of the velocity
  range is one flat blue. Half the byte is wasted.
- **There is no saturated red.** 14 (red-pink) is the closest the palette gets.
  Any design that needs a clear red/green distinction has to accept red-pink.
- Usable, well-separated anchors: **5 green · 14 red-pink · 15 orange ·
  21 bright blue · 24 light purple · 40 white · 0 off.**

If you are picking state colours, note that **14 and 15 are adjacent in the hue
cycle**, so red-pink and orange can be hard to tell apart under stage lighting.
Swapping one of them for 21 or 24 buys much more contrast.

### 3.3 Turning a pad off requires note-on velocity 0

Send note-on with velocity 0. **A real note-off (`0x80`) appears to be ignored
entirely.** Clear a grid with note-offs and every pad stays lit, with no error
and no clue as to why.

This is worth knowing before you write any LED code, because the failure mode is
"my clear function does nothing" and the obvious explanation (wrong note
numbers, wrong channel, wrong port) is the wrong one.

Convenient consequence for Ableton work: `_Framework` lights note-type buttons
through `send_value()`, which emits a note-on carrying the value as velocity. The
stock framework already speaks this dialect, including for value 0, so no
custom LED transport is needed.

`mvave_probe.py --clear` sends note-on/velocity-0 across notes 0–127 if you need
to recover a grid left lit by an aborted run.

### 3.4 The host owns the grid — measured, not assumed

Three separate things had to be true for a host to be able to drive the LEDs as a
state display, and each was tested on its own:

1. **Pads do not recolour themselves as you play.** Four rounds, roughly 78
   strikes, with no LED movement at all.
2. **A colour the host has set survives being struck.** A pad lit green stays
   green under your fingers. This is a genuinely different claim from (1) and
   needed its own test.
3. **The VELOCITY 1–4 setting does not affect colour.** Velocity 5 produced
   green on every setting tried.

Together these mean no re-assert-after-press logic is needed: set a pad's colour
once and it stays until you change it.

A caution that came out of this: **"all pads lit" is not the same as "the host
can set colours."** The first `--light` test lit the whole grid in the colour
each pad was already configured with in the `.spc`, which proves only on/off
feedback. Distinguishing that from a real colour grid needed the velocity sweep.

### 3.5 Do not blast 128 note-ons back to back

Sending note-on to all 128 notes in a tight loop **overruns the device's MIDI
input buffer** and some pads never light. In the original test this presented as
pad 16 being dead; addressed on its own, pad 16 lights fine.

If you are lighting the whole grid, pace it, or at minimum do not conclude a pad
is broken from a bulk write.

---

## 4. Encoders

### 4.1 Layout

Eight physical encoders, arriving on ports 1 and 2 only (never port 3). A
**KNOB BANK** button switches all eight at once between two banks, each bank
with its own CC set.

Measured with `mvave_probe.py --knobs`, which walks one encoder at a time and
reports after each, so a silent knob or a CC clash shows up while your hand is
still on it.

| Encoder | Bank 1 CC | Bank 1 mode | Bank 2 CC | Bank 2 mode |
|---|---|---|---|---|
| 1 | 1 | absolute | 44 | absolute |
| 2 | 2 | absolute | 45 | absolute |
| 3 | 3 | absolute | 42 | absolute |
| 4 | 4 | absolute | 43 | absolute |
| 5 | 5 | absolute | 40 | absolute |
| 6 | 6 | absolute | 41 | absolute |
| 7 | 7 | absolute | 38 | **relative** |
| 8 | 8 | absolute | 39 | **relative** |

### 4.2 Bank 2's CC numbers do not follow the printed encoder numbers

Bank 1 is well behaved: encoder *n* sends CC *n*. **Bank 2 is not.** The CC
numbers descend in pairs as the printed labels ascend — encoder 1 sends CC 44,
encoder 8 sends CC 38.

Wire your macros in numeric CC order (40, 41, 42, …) and they will scatter across
the panel in a pattern that looks random when you turn them. Always map bank 2 in
*encoder* order:

```
encoders 1..8  ->  CC 44, 45, 42, 43, 40, 41, 38, 39
```

That ordering is why `MVave_SMC_KNOBS.py` stores `MACRO_CCS = (44, 45, 42, 43,
40, 41)` rather than a sorted tuple.

### 4.3 A knob that seems dead is usually on the other bank

KNOB BANK switches all eight encoders together. Mappings made on bank 1 are
completely inert while bank 2 is selected, and vice versa. Check the bank before
debugging anything about an encoder.

### 4.4 Relative encoding

The encoders ship **absolute**: the firmware accumulates a position internally and
reports it, confirmed by walking a knob and watching the value climb (6 → 31).

Two of them — encoders 7 and 8, bank 2, CC 38 and 39 — were switched to
**relative** by hand in the M-Vave editor. Relative here is the standard
signed-bit-around-centre scheme:

| Value | Meaning |
|---|---|
| 63 | one step counter-clockwise (−1) |
| 64 | centre / no movement |
| 65 | one step clockwise (+1) |

Relative is a setting made in the M-Vave editor, not a fixed property of those two
encoders — the other six were simply left absolute.

**Why the mode matters.** An absolute CC carries a *value*, which maps cleanly
onto a continuous range like volume or filter cutoff, where nothing else moves
the target. A relative CC carries a *step*. If the thing you are driving is an
integer index that other inputs also move — Ableton's session box, moved by the
arrow keys and the mouse as well — an absolute encoder's internal counter desyncs
immediately and the target teleports the next time you touch the knob. There is
nothing to desync in a relative encoder.

If you are writing a `_Framework` script: `SliderElement` handles the absolute
case, and `EncoderElement` plus a map mode handles relative. Older templates
frequently only build the absolute kind, which is why the script in this repo
decodes CC 38/39 itself in `receive_midi` instead of going through the framework.

---

## 5. The `.spc` configuration file

`Ableton.spc` is what the M-Vave editor writes out. Binary, **no magic bytes, no
header, no version field**. It is three fixed-size record sections back to back.

### 5.1 How the segmentation was confirmed

The record sizes multiply out to exactly the file length:

```
5 x 23  +  16 x 6  +  128 x 26  =  115 + 96 + 3328  =  3539 bytes
```

3539 is the file size. Three independently guessed record sizes summing exactly
to the total, with no header and no slack, is strong enough evidence to work
from. **This is the technique worth stealing for the next undocumented binary
format**: guess record boundaries from repeating byte patterns, then check
whether the arithmetic closes.

### 5.2 Section layout

| Offset | Records | Size | Contents |
|---|---|---|---|
| `@0` | 5 | 23 B | buttons that send SysEx |
| `@115` | 16 | 6 B | continuous controls (encoders) |
| `@211` | 128 | 26 B | pads — 8 banks x 16 |

**Section 1 — SysEx buttons, `@0`, 5 x 23 B**

```
[type=05] [00] [id] [00] [7f] [len] [sysex, 16 B] [tail]
```

All five records hold MMC commands:

| id | MMC command |
|---|---|
| 17 | Deferred Play |
| 18 | Fast Forward |
| 19 | Rewind |
| 20 | Stop |
| 21 | Play |

`len` is the length of the SysEx message carried in the fixed 16-byte field.

**Section 2 — continuous controls, `@115`, 16 x 6 B**

```
[00] [type=02] [00] [cc] [00] [max]
```

Sixteen records for eight physical encoders — two banks of eight. The CC bytes
read `7, 8, 5, 6, 3, 4, 1, 2` then `38–45`.

Note that this is **not** printed-encoder order: the first eight records are bank
1, whose measured map is encoder *n* → CC *n*. Section 4.1's table, not the file's
record order, is what the device actually sends.

> **Hypothesis, untested.** If section-2 records are stored in the order
> (enc 7, enc 8, enc 5, enc 6, enc 3, enc 4, enc 1, enc 2) — the same
> non-obvious internal ordering the pads turn out to have, see 5.3 — then both
> banks' records line up with the measured CC map exactly. This was derived by
> laying the file next to the measured table, not verified against a second dump
> or a second unit.

**Section 3 — pads, `@211`, 128 x 26 B**

```
[flag] [type] [note] [chan] [vel] [r] [g] [b] [tail] [zeros...]
```

128 records = **8 banks x 16 pads**, one bank per Shift+Pad preset. Measured note
ranges per bank:

| Bank | Notes |
|---|---|
| 1 | 4–19 |
| 2 | 20–35 |
| 3 | **1–16** |
| 4 | 52–67 |
| 5 | 68–83 |
| 6 | 84–99 |
| 7 | 100–115 |
| 8 | 52–67 |

Bank 3 is the hand-edited one in this project's dump — `#00ff00` for every pad
and notes 1–16 — and it is the bank port 3 plays back.

### 5.3 The device numbers its pads bottom-up

**PAD1 is bottom-left. PAD13 is top-left.** Read bank 3's records in that
bottom-up order and they yield notes 1–16 in *reading* order from the top-left —
which is precisely what the probe measured on port 3, inversion and all,
sixteen out of sixteen.

This matters whenever you edit a bank in the M-Vave editor: the pad the editor
calls PAD1 is not the pad in the top-left corner.

### 5.4 Why the pads always transmit velocity 127

Every record in bank 3 carries `vel = 0x7f`. It is a **fixed velocity byte, not a
curve**, which is why every strike reports 127 and why the VELOCITY settings do
nothing to it (section 6.2).

### 5.5 Two traps in reading this format

**A `0x00` in the `type` byte does not mean "pad disabled."** Two bank-3 records
have `0x00` there where the rest have `0x09`. That was read as "these two pads
transmit nothing" and it produced a confident, wrong prediction that notes 1 and
6 would be silent. Both fire normally. Whatever that byte means, it is not an
enable flag — do not infer silence from it.

**The `.spc` and a Remote Script must be reasoned about as a pair.** An apparent
collision between the script's `PLAY=17 STOP=18 REC=19` and the pad note range
was called a bug; it was not, because the device had been configured to match the
map. Reading either artifact in isolation produces nonsense.

### 5.6 The flag byte

Bank 3's `flag` byte is `0x04`. All seven factory banks have `0x00`.

> **Hypothesis, untested.** The flag byte is an **output-port selector**. Two
> consistent observations support it: pads in bank 3 have `0x04` and appear on
> port 3, while the encoder records have `0x00` and appear on ports 1 and 2. That
> is two data points and no experiment. Testable in about a minute — switch the
> device to preset bank 1 and see which port receives the pad notes.

---

## 6. SHIFT and the Shift+Pad settings

### 6.1 SHIFT transmits nothing

Confirmed by listening on all three ports simultaneously. The SHIFT button is
consumed entirely by the firmware for its Shift+Pad combinations (preset select,
velocity, transpose, octave).

**There is no spare modifier button on this device.** Any host-side "hold X to
change what the other controls do" scheme has to spend one of the five
transport/function buttons on it.

### 6.2 VELOCITY 1–4 (Shift + Pad 9–12)

Undocumented — the manual names the setting and says nothing else. Measured with
`mvave_probe.py --curves`, which walks all four settings while watching two ports
at once.

**What was established:**

- All four settings transmit **velocity 127 on port 3**, every strike, no
  variation. The fixed `0x7f` velocity byte in the pad bank (section 5.4)
  overrides whatever the setting would otherwise do.
- None of the four settings changes LED colour.

**What was not established: what the settings actually do.** A velocity curve
would shape the *playing* port's output, and port 1 transmitted nothing at all
during the test. Measuring these properly means first working out why port 1 is
silent in this configuration — probably by switching to a different pad preset
bank, which ties back to the flag-byte hypothesis in 5.6.

For clip-launching purposes the setting is simply irrelevant.

---

## 7. Factory DAW mode, and why it cannot launch clips

In its factory DAW (Mackie) mode, the SMC-PAD spends the entire 4x4 grid on mixer
duties:

| Pads | Function |
|---|---|
| 1–4 | select track |
| 5–8 | arm |
| 9–12 | solo |
| 13–16 | mute |

with **PAD BANK** toggling between tracks 1–4 and tracks 5–8.

Mackie Control is a mixer and transport protocol. **It has no concept of a clip
grid at all**, so no amount of configuration on the device or in Live's stock
`MackieControl` script will get a pad to launch a clip. The limitation is in the
protocol, not the hardware.

What makes a clip launcher possible anyway: the firmware keeps sending pad notes
and keeps lighting pads from incoming MIDI regardless of what the host does with
them. Put a custom Remote Script in that Control Surface slot instead of
`MackieControl` and the same note stream means whatever you decide it means. The
device is unchanged and the change is fully reversible — switch the Control
Surface dropdown back and the factory behaviour returns.

---

## 8. Reproducing any of this

`tools/mvave_probe.py` runs on the machine the controller is plugged into. It
needs `mido` and `python-rtmidi` (see `tools/requirements-midi.txt`); on Windows,
`tools/run_probe.bat` builds a venv and runs it. It never touches the DAW.
Full usage is in [PROBE.md](PROBE.md); the modes exist as follows.

| Mode | What it does |
|---|---|
| `--list` | enumerate MIDI in/out ports |
| `--listen --port MIDIIN3` | log everything the device sends, with a per-control summary |
| `--light --port MIDIOUT3` | blunt test — light everything at once |
| `--sweep` | narrow down which notes address pads, a block at a time |
| `--colours --note 1` | step a pad through velocities, typing the colour you see; prints a grouped velocity→colour table |
| `--clear` | extinguish every pad |
| `--curves --port "SMC-PAD 0" --port2 "MIDIIN3"` | walk VELOCITY 1–4, capturing transmitted velocities on two ports at once |
| `--knobs --port "SMC-PAD 0"` | map every encoder to its CC, one knob at a time, reporting mode and flagging silent knobs and CC clashes |

Both `--colours` and `--knobs` are interactive and checkpoint every single step,
which is deliberate. A timed sweep asks a human to remember a sequence of colours
or to turn sixteen knobs in the right order and only reveals a mistake at the end.
The first attempt at the encoder map was one flat 180-second `--listen` run; it
came back 14 of 16, with two CCs missing and one wrongly classified, and no way to
tell which step had gone wrong. Step-by-step, it produced a clean 16 of 16.

---

## 9. Known unknowns

Collected so nobody re-derives them as facts:

1. **What VELOCITY 1–4 do.** Blocked on port 1 being silent in the pad preset
   bank used here (6.2).
2. **Whether the `.spc` flag byte selects the output port.** Two consistent
   observations, no experiment (5.6).
3. **Whether notes 17–21 for the five buttons are a factory default** or the
   result of prior configuration on the device (2.4).
4. **The full velocity→colour mapping above 24.** Sampled, not walked
   exhaustively (3.2).
5. **The meaning of the pad record's `type` byte** (`0x09` vs `0x00`). Known not
   to be an enable flag; nothing more (5.5).
6. **Any of this on macOS or Linux.** Not tested.
