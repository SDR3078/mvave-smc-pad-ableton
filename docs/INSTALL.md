# Installing the M-Vave SMC-PAD Remote Scripts

Two Remote Scripts that turn the SMC-PAD into a Session-view clip launcher with
pad LED feedback, plus device macros and session-box navigation on the encoders.

The pads and the encoders arrive on **different MIDI ports**, and a Remote Script
gets exactly one input port. That is why there are two scripts and two Control
Surface slots — `MVave_SMC_PAD` (pads, buttons, LEDs) and `MVave_SMC_KNOBS`
(encoders). The knob script reaches into the pad script's session component to
move the red box, so **both must be installed and both slots filled**.

---

## Requirements

| | |
|---|---|
| Ableton Live | Any version that ships the classic `_Framework` MIDI Remote Scripts API. **Verified on Live 11.3.43 (Windows)** — see DEVELOPMENT.md §"Verified on hardware". Live 12 is expected to work but is unverified. The step sequencer additionally needs Live 11+ for `get_notes_extended`. |
| Hardware | M-Vave SMC-PAD, connected by USB. |
| OS | Windows or macOS. **Everything here was built and tested on Windows only.** The macOS paths below are Live's standard locations, but they have not been verified with these scripts. |
| Python | None needed. Live runs the scripts with its own interpreter. (The optional probe tool in `tools/` needs Python — see [Finding out what your unit sends](#finding-out-what-your-unit-sends).) |

Two known `_Framework` differences across Live versions are already handled in
the code: missing `ClipSlotComponent` colour setters degrade to plain clip
launching with a warning in the log, and the `set_parameter_controls` assert
that demands exactly 8 controls is sidestepped entirely — the pad script calls
that setter only when all eight slots are assigned (they are not, so it never
does), and the knob script writes `device.parameters[...]` directly and never
calls it at all.

### What the scripts expect the device to send

`MIDI_Map.py` and `MVave_SMC_KNOBS.py` assume this, all on MIDI channel 1:

| Control | Sends |
|---|---|
| 16 pads | notes **1–16**, reading order — top-left is 1, bottom-right is 16 — on the **third** port pair (the DAW port), velocity 127 on press and note-on velocity 0 on release |
| Buttons | note **17** play, **18** stop, **19** record, **20** left arrow, **21** right arrow |
| Encoders, knob bank 1 | CC **7, 8, 5, 6, 3, 4, 1, 2** across encoders 1–8 — the CC numbers do not follow the printed encoder numbers on this bank |
| Encoders, knob bank 2 | CC **17, 18, 13, 14, 11, 12, 9, 10** across encoders 1–8 (the sequencer preset sends 15, 16 for the bottom pair instead) |
| All sixteen | **relative**, centred on 64: 63 is one step back, 65 one step forward |

This was measured on one unit whose pad bank and transport buttons had been
configured by hand in the M-Vave editor, and every one of whose sixteen encoder
assignments had been switched there from absolute to relative. **A factory unit
will not match**, and neither will this one after any further editor change — the
encoder numbering has already moved once between measurements. Re-measure with
`run_probe.bat --knobs` rather than trusting the table above.
On the measured unit, the eight **PAD BANK** positions of one preset transmitted
note ranges 1) 4–19, 2) 20–35, 3) 1–16 (the hand-edited one), 4) 52–67,
5) 68–83, 6) 84–99, 7) 100–115, 8) 52–67. **PAD BANK** cycles those eight banks
*within* the loaded preset; **Shift+Pad** loads a different preset file
altogether. The two are easy to confuse and the consequences differ — see
[HARDWARE.md](HARDWARE.md) §5.

**You need M-Vave's editor to do any of this.** The configuration lives on the
device, not in these scripts, and the editor is the only thing that writes it.

For the SMC-PAD that editor is **MidiSuite**, from
[m-vave.com/appdownload](https://www.m-vave.com/appdownload) — desktop builds
for **Windows and macOS**, which connect to the unit over the USB data cable,
plus iOS and Android versions. Checked 2026-09-06: the SMC-PAD is listed among
MidiSuite's supported devices.

> **Not CubeSuite.** M-Vave ships a second editor of that name for a different
> part of their range (LooperPro, SMK25, VMK25 and so on) and the SMC-PAD is
> **not** in its device list. `docs/STEPSEQ-BRIEF.md`, the original build brief
> kept verbatim as history, names CubeSuite — it predates the device being
> identified and is wrong on this point. MidiSuite is the one.

Nothing in this repository ships, mirrors or depends on the editor, and none of
what follows has been tested against any particular version of it.

**The two presets in `reference/` are this project's configuration, exported.**
`launchpad.spc` is the clip-launcher preset and `sequencer.spc` the
step-sequencer one. If your build of MidiSuite can load a `.spc`, load each into
its own preset slot and write it to the device — by far the shortest route. If
it cannot, configure by hand from the table above; `docs/HARDWARE.md` §5 decodes
the format byte by byte, so the files remain the authoritative answer to what
every number should be.

Configuring by hand, two gotchas make it silently wrong:

- **The editor numbers pads bottom-up**, so its PAD1 is the bottom-left pad and
  PAD13–16 carry the first four notes (HARDWARE.md 5.3).
- **The five buttons are one set per preset**, not per pad bank (HARDWARE.md
  2.4) — so they cannot be given different jobs in different PAD BANK positions.

> **Which preset slot?** It makes no difference to the scripts: the *note
> ranges* are what tell the two apart, not the slot. What matters is that the
> two presets sit in **different** slots so you can switch between them. Hold
> **Shift** and press a pad to load a slot — that is the "preset switch" the
> rest of these docs and [STEPSEQ.md](STEPSEQ.md) mean by the mode switch.
> Write down which pad you used for which preset; nothing on the device tells
> you afterwards.

**Confirm it took** before going anywhere near Live: run
`run_probe.bat --listen` (see [PROBE.md](PROBE.md) for setup) and press the
pads. The launcher preset sends notes 1–16, the sequencer preset 101–116. A
factory unit sends neither, which is exactly the "appears to do nothing" state
the README warns about.

So before you start, either configure the device in the M-Vave editor to match
the table, or change the numbers in `MIDI_Map.py` to match your device — see
[Customising](#customising). **All sixteen encoders must be relative**
whichever way you go — the macro knobs are decoded as deltas too
(`decode_relative` in `MVave_SMC_KNOBS.py`), so an absolute macro encoder applies
its position as an increment and slams the macro to a limit on the first turn.
For the two navigation encoders the reason is sharper still: an absolute encoder
sends a position, and the session box is an index the arrows and the mouse also
move, so an absolute counter desyncs and the box teleports the next time you
touch the knob.

#### Finding out what your unit sends

`tools/mvave_probe.py` logs everything the device transmits and can light pads,
without installing a Remote Script:

```
run_probe.bat --list                            # enumerate ports
run_probe.bat --listen --port "MIDIIN3"         # log notes and CCs, with a summary
run_probe.bat --knobs  --port "SMC-PAD 0"       # map every encoder to its CC, one at a time
run_probe.bat --clear  --port "MIDIOUT3"        # extinguish every pad
```

The `.bat` is Windows-only and builds its own venv on first run. On macOS and
Linux there is no launcher — set the probe up once, then call it directly:

```
python3 -m venv venv-midi
./venv-midi/bin/pip install -r tools/requirements-midi.txt
./venv-midi/bin/python tools/mvave_probe.py --list
```

Full setup and every mode is in **[PROBE.md](PROBE.md)**. (Untested on macOS —
the commands are standard, the device behaviour is not verified there.)
Port names need the trailing index to disambiguate, because `SMC-PAD` is a
substring of all three Windows port names — use `"SMC-PAD 0"`.

**Windows MIDI ports are exclusive.** Close Live, or untick the port in
Preferences, before running the probe, or it cannot open the port.

---

## Installation

### 1. Copy both folders into Live's Remote Scripts directory

Copy the folders themselves — `MVave_SMC_PAD` and `MVave_SMC_KNOBS`, plus
`MVave_SMC_STEPSEQ` if you want the step sequencer — not their contents, and do not
nest them one level deeper. Live scans the direct subfolders of this directory,
and each subfolder must keep its `__init__.py`.
The result should look like `…/Remote Scripts/MVave_SMC_PAD/__init__.py`.

There are two possible destinations. Prefer the user location: the application
folder belongs to the installer, and a Live update can overwrite it.

**Windows**

| | Path |
|---|---|
| User | `%APPDATA%\Ableton\Live <version>\Preferences\User Remote Scripts\` |
| Application | `C:\ProgramData\Ableton\Live <version>\Resources\MIDI Remote Scripts\` |

**macOS** (standard Live locations, not verified with these scripts)

| | Path |
|---|---|
| User | `~/Music/Ableton/User Library/Remote Scripts/` |
| Application | `/Applications/Ableton Live <version>.app/Contents/App-Resources/MIDI Remote Scripts/` — right-click the app and choose Show Package Contents to get in |

`<version>` is the exact installed version and **varies per install** (`Live 12`,
`Live 12.1.5`, `Live 11.3.21`, …). Don't type it from memory; open the parent
folder and use whichever version folder is actually there. If you already have
another custom script installed, put these next to it.

### 2. Restart Live

Live scans the Remote Scripts directory **only at startup**. Until you restart,
the scripts will not appear in the Control Surface dropdown. The same applies
after any later edit to a `.py` file — an edit does nothing until Live is
restarted.

### 3. Fill the two Control Surface slots

Preferences → **Link, Tempo & MIDI** → the Control Surface table at the top. Slot
order does not matter; the numbering below is just for reference.

| Slot | Control Surface | Input | Output |
|---|---|---|---|
| 1 | `MVave_SMC_PAD` | `MIDIIN3 (SMC-PAD)` | `MIDIOUT3 (SMC-PAD)` |
| 2 | `MVave_SMC_KNOBS` | `SMC-PAD` (the first port) | `None` |

- The **output** on slot 1 is what lights the pads. Set it to `None` and clip
  launching still works, with no LED feedback at all.
- Slot 2 needs no output — the encoder script never transmits.
- Those are the Windows port names. On macOS the names will differ; identify the
  ports by function instead — the pads appear on the **third** port pair, and the
  encoders appear **identically on the first two pairs** and never on the third.

> **The step sequencer is a third, optional slot** on `MIDIIN3`/`MIDIOUT3` — the
> same ports as slot 1, deliberately. The note ranges (1–21 against 101–121) are
> what keep the two apart, so both can stay loaded and the pad preset switch is
> the mode switch. Setup is in [STEPSEQ.md](STEPSEQ.md) §6.
>
> Skip it entirely if you only want the clip launcher — nothing else here
> depends on it.

### 4. Leave the remaining port unassigned, with Remote on

Leave the second port pair (`MIDIIN2` on Windows) out of every Control Surface
slot, and tick **Remote** for it in the MIDI Ports list further down the same
preferences page.

This matters more than it looks. **A Control Surface takes its port away from
Ctrl+M** — Live disables Track/Sync/Remote for a port as soon as a script claims
it. Ports 1 and 2 carry identical encoder CCs, same messages, same counts. So the
script claims port 1 and port 2 stays open for Live's own MIDI mapping. Skip
this and Ctrl+M mapping from the encoders stops working entirely.

If you already had Ctrl+M mappings arriving on port 1, assigning the knob script
to that port kills them silently. Remake them on whichever of the two the
script is **not** using.

> **Check which port the script actually holds.** Ports 1 and 2 carry
> identical CCs, so either works for the script and the other is left for
> Ctrl+M — but the docs and your Live preferences can drift apart. The
> **last** `Midi Remote Scripts` block in `Log.txt` names the input each slot is
> on. Live appends one block per launch, so scroll to the *bottom* of the file:
> the block at the top is the first session ever recorded, and following it
> sends you to remake mappings onto the port the script currently holds — the
> exact failure §4 exists to prevent.

### 5. Both knob banks are in use

**KNOB BANK** switches all eight encoders at once, and each bank has its own CC
set. Both are now mapped, giving fourteen macros plus navigation:

| Bank | Knobs | Do |
|---|---|---|
| 1 | 7, 8, 5, 6, 3, 4, 1, 2 | macros **1–8** |
| 2 | 7, 8, 5, 6, 3, 4 | macros **9–14** |
| 2 | 1, 2 | session box across tracks / through scenes |

So there is no bank to select — press KNOB BANK for whichever half of the macros
you want. Note that bank 1 is **no longer free for Ctrl+M**: the script claims
CC 1–8, two of which (CC 1 and CC 7) are the mod wheel and channel volume. That
is harmless while the port belongs to a Control Surface, since Live disables
Remote on it, but it matters if you ever hand the port back.

---

## Verifying it worked

`Log.txt` lives at:

- **Windows:** `%APPDATA%\Ableton\Live <version>\Preferences\Log.txt`
- **macOS:** `~/Library/Preferences/Ableton/Live <version>/Log.txt` (standard
  location, not verified here)

Look for these lines, in this order:

```
MVave_SMC_KNOBS: loaded. CC 17/18 navigate; 16 macro CCs 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16.
MVave_SMC_KNOBS: device -> <device name>
MVave_SMC_KNOBS: first nav CC -- 17 value 65
MVave_SMC_KNOBS: first macro CC -- 1 value 65 -> macro 1
```

| Line | Proves | Appears when |
|---|---|---|
| `loaded.` | The knob script was found and constructed. | At startup. |
| `device -> …` | The macro knobs have a device to point at. | **Only once the selected track changes** — click a track before concluding the macros are broken. |
| `first nav CC -- 17 value 65` | MIDI is actually reaching the script. | The first time you turn encoder 1 or 2 on bank 2. Logged once only; a knob produces hundreds of messages. |
| `first macro CC -- …` | A macro knob is reaching the script and resolving to a macro number. | The first time you turn any macro encoder. Logged once only. |

The **pad script prints nothing on a clean load** — its only log lines are
warnings. Verify it by behaviour instead: pads under the red box should light
orange where a clip sits, green when one plays.

Lines that mean something went wrong:

- `MVave_SMC_KNOBS: cannot import MVave_SMC_PAD (…)` or
  `MVave_SMC_KNOBS: MVave_SMC_PAD is not loaded -- is it in a Control Surface slot?`
  — the cross-script lookup failed. Macros still work; navigation does not.
- `MVave_SMC_KNOBS: could not read the session offsets` — the pad script's
  session was found but this `_Framework` version exposes its offsets in a way
  the knob script doesn't recognise.
- `MVave_SMC_PAD: ClipSlotComponent has no <setter>()` — this `_Framework`
  version has no such colour setter. Clip launching is unaffected; that one
  colour state just won't light.
- A Python traceback naming either module — see
  [the script fails to load](#the-script-fails-to-load-or-never-appears-in-the-dropdown).

---

## The control layout you end up with

| Control | Does |
|---|---|
| 16 pads | Launch clips in a **4 × 4** session box: green playing, orange loaded-but-stopped, red-pink recording, bright blue queued, unlit empty |
| Button 17 | Play |
| Button 18 | Stop |
| Button 19 | Record |
| Arrow 20 / 21 | Select previous / next track |
| **Bank 1**, encoders 1–8 | Macros **1–8** of the **selected** device (Live's blue hand) |
| **Bank 2**, encoders 3–8 | Macros **9–14** of the same device |
| **Bank 2**, encoders 1–2 | Move the session box across tracks / through scenes |

On the sequencer preset, bank 2's bottom pair carries macros **15–16** instead of
the session box, which the sequencer has no use for.

The macros follow the selection: click a different track and the same knobs
control that track's device. That is the whole reason for doing it in a script
rather than with Ctrl+M, which can only ever point at one fixed parameter.

The SHIFT button transmits nothing on any port — the firmware consumes it for
the Shift+Pad combos. There is no spare modifier on this device.

---

## Troubleshooting

### Nothing happens at all — no clips launch, no LEDs

- **Live wasn't restarted after copying.** Scripts are picked up at startup only.
  Restart and check the dropdown lists both scripts.
- **Wrong port in the slot.** The pads are on the third port pair. If the slot
  input is the first or second pair, the script sees encoder CCs and no notes.
- **The device is on the wrong pad preset**, sending notes other than 1–16.
  Confirm with `run_probe.bat --listen` (close Live first — the port is
  exclusive), then fix it in the M-Vave editor or in `MIDI_Map.py`.
- **The folders landed one level too deep**, e.g.
  `Remote Scripts/mvave-smc-pad-ableton/MVave_SMC_PAD/`. Live only scans direct
  children.

### Pads work but the macro knobs do nothing

- **You are on the other knob bank.** KNOB BANK switches all eight encoders at
  once and the two banks carry different macros, so a knob you expect to move
  macro 3 moves macro 11 instead. Note that this makes a knob move the *wrong*
  thing, not nothing — see *One knob appears dead* below if it does nothing at
  all.
- **The device has fewer macros than the knob you turned.** Bank 2's top six are
  macros 9–14, which an eight-macro rack simply does not have. `Log.txt` names
  the device and the macro, once.
- **Slot 2 is empty or on the wrong port.** `MVave_SMC_KNOBS` needs the *first*
  port pair as input. Check for the `MVave_SMC_KNOBS: loaded.` line in `Log.txt`;
  no line means the script never constructed.
- **No device is selected yet** — see the next entry.
- **The selected track has no device.** The blue hand needs something to hold.

### The macros only start working after you click a track

Expected. `DeviceComponent` is only handed a device when the **selected track
changes**, so after a fresh load the knobs do nothing until you click a track.
Click any track once after starting Live. The `device -> …` line in
`Log.txt` appears at that same moment, which is why its absence at startup is
not a fault.

### Pads stay stuck lit

The device ignores real note-offs (`0x80`) — a pad is extinguished by a note-on
with **velocity 0**, not by a note-off. Live's `_Framework` sends the right thing
while the script is running, but the LEDs simply hold their last value if the
script goes away: Live closed while pads were lit, the slot set to `None`, or a
crash.

Fix, Windows: `run_probe.bat --clear --port "MIDIOUT3"` — with Live closed, since
Windows MIDI ports are exclusive. macOS/Linux:
`./venv-midi/bin/python tools/mvave_probe.py --clear --port <your output port>`,
and you do **not** need to close Live; CoreMIDI and ALSA ports are multi-client. Sending a note-off from anywhere will not clear them.

### One knob appears dead

**The wrong knob bank moves a _different_ macro, not nothing.** Both banks are
mapped now, so a knob that does nothing at all is a different fault: check the
device's macro count (a rack with eight macros has nothing for bank 2's top six
to drive — `Log.txt` names the device and the macro, once per pair, so a
six-knob shortfall is six lines), then `run_probe.bat --knobs`.
Historically, when one bank was unassigned, the wrong bank *was* the usual
cause.

If it is dead on bank 2 as well, its CC may not match the map — verify with
`run_probe.bat --knobs`, which reports each encoder separately and names silent
knobs and CC clashes.

### The session box jumps to one end when you turn bank 2's encoder 1 or 2

- **`ENCODER_MODE` is set to the wrong convention.** If the encoder is already
  relative in the editor and the box still slams to one end, it is sending the
  other relative convention: one click decodes as ±63. Set
  `ENCODER_MODE = 'twos'` in `MVave_SMC_KNOBS/MVave_SMC_KNOBS.py` (or back to
  `'centre'`) and restart Live. `run_probe.bat --knobs` names which one your
  unit sends.
- **Or the encoder is still absolute** — the original cause, below.

That encoder is still **absolute**. It transmits a position, not a step, so the
first message after the box has moved by any other means slams it to wherever the
knob's counter happens to be. Switch CC 17 and 18 to relative in the M-Vave
editor (63 = one back, 65 = one forward, centred on 64).

### Ctrl+M mappings stopped working after installing this

A Control Surface disables Track/Sync/Remote on the port it claims. Your
mappings were arriving on the port the knob script now owns. Remake them on the
other port — ports 1 and 2 carry identical CCs — and keep Remote ticked there.

### The script fails to load, or never appears in the dropdown

- Not restarted, or copied to a Remote Scripts directory belonging to a
  **different Live version** than the one you launched. Check the `<version>` in
  the path against the version you are running.
- A file missing from the copy. Both folders need every `.py` file, including
  `__init__.py`.
- A traceback in `Log.txt` naming the module tells you which line failed.
  Note that an exception inside `__init__` takes the **whole script** down, not
  just the feature that raised it — a script that loads partially is not a thing.
- After any fix, restart Live again.

### Clip colours are missing or wrong

If `Log.txt` has `ClipSlotComponent has no <setter>()`, that state is
unsupported in your Live version and nothing can be done from `MIDI_Map.py`.
Otherwise, the colours are palette indices, not RGB — see below.

---

## Customising

### `MVave_SMC_PAD/MIDI_Map.py`

Everything the pad script maps lives in this one file. `-1` means unassigned, and
Live must be restarted for any edit to take effect.

| Constant | Controls |
|---|---|
| `CLIPNOTEMAP` | The 4 × 4 grid of pad notes, row by row. Change these to match what your pads transmit. |
| `TSB_X`, `TSB_Y` | Session box width and height. Must match `CLIPNOTEMAP`'s dimensions. |
| `PLAY`, `STOP`, `REC` | Transport button notes (17, 18, 19). |
| `TRACKLEFT`, `TRACKRIGHT` | Arrow button notes (20, 21) — previous / next track. |
| `BUTTONCHANNEL`, `SLIDERCHANNEL` | MIDI channel, 0-based: `0` is channel 1. |
| `MESSAGETYPE` | `0` for notes, `1` for CCs. |
| `MODIFIER` | Disabled (`-1`). Set it to a button note and the two arrows bank the session box through **scenes** while it is held, at the cost of that button's normal role. Kept because it is a one-constant change if a second modifier is ever wanted. |
| Everything else | Standard slots from the generic-controller template this is built on — mixer, sends, scene launch, device banks. Nearly all `-1` here. |

### Pad LED colours

Also in `MIDI_Map.py`:

```python
CLIP_PLAYING = 5           # clip is playing
CLIP_STOPPED = 15          # slot holds a clip, not playing
CLIP_RECORDING = 14        # clip is recording
CLIP_TRIGGERED_PLAY = 21   # queued, waiting for the quantise point
CLIP_TRIGGERED_REC = 24    # queued to record
```

The velocity of a note-on sent **to** the SMC-PAD is a **palette index, not a
brightness**, and the palette is absolute — a pad configured pure green on the
device still shows pink, blue and orange when Live sets it. The hue cycles about
every 13–14 steps, and everything above roughly 64 is the same flat blue, so all
useful values are low. There is no saturated red; 14 is as close as it gets.

Usable anchors: **5** green · **14** red-pink · **15** orange · **21** bright
blue · **24** light purple · **40** white · **0** off.

14 and 15 are adjacent in the hue cycle. If red-pink and orange prove hard to
tell apart in use, move `CLIP_STOPPED` to 21 or 24 for much more contrast.

### `MVave_SMC_KNOBS/MVave_SMC_KNOBS.py`

The encoder CCs are constants at the top:

- `MACRO_BY_CC` — a dict mapping each of the sixteen CCs to a macro number
  (fourteen macro knobs on the launcher preset, plus 15–16 on the sequencer
  preset).
  Macro *N* is `device.parameters[N]`; index 0 is the device on/off switch, so the
  numbering needs no offset. Build it in **encoder order**, not numeric CC order,
  or the macros scatter across the panel.
- `STEPS_PER_SWEEP = 127.0` — one click moves this fraction of a parameter's
  range. A rack macro runs 0–127, a range of 127, so one click is one unit and a
  full sweep is 127 clicks.
- `CC_TRACK = 17`, `CC_SCENE = 18`, `CENTRE = 64` — the relative navigation
  encoders (bank 2's bottom pair, launcher preset). The two CCs must differ; a
  collision makes one axis of the session box unreachable.
- `ENCODER_MODE = 'centre'` — **which relative convention your encoders use.**
  `'centre'` is 63 back / 65 forward (what this unit sends); `'twos'` is 127
  back / 1 forward. The two are mutually ambiguous, so nothing can detect it —
  it is a setting. `run_probe.bat --knobs` reports which one it saw, in those
  words. Getting it wrong moves the session box 63 tracks per click, silently.

### One editing gotcha

Files in `MVave_SMC_PAD/` have **CRLF line endings**. Line-anchored patterns in
`sed` and friends silently no-op unless they account for the trailing `\r`.

---

## Uninstalling

1. In Live, Preferences → Link, Tempo & MIDI: set **every** Control Surface slot
   showing `MVave_SMC_PAD`, `MVave_SMC_KNOBS` or `MVave_SMC_STEPSEQ` back to
   `None`. If you installed the sequencer, that is three slots, and two of them
   are on the port you are about to hand back.
2. Delete the folders from the Remote Scripts directory you installed them to
   (three, if you installed the sequencer):

   ```
   <remote-scripts-dir>\MVave_SMC_PAD
   <remote-scripts-dir>\MVave_SMC_KNOBS
   <remote-scripts-dir>\MVave_SMC_STEPSEQ
   ```

3. If you had **Mackie Control** in a slot before this, put it back on
   `MIDIIN3 (SMC-PAD)` / `MIDIOUT3 (SMC-PAD)` to restore the factory DAW-mode pad
   layout — pads 1–4 select track, 5–8 arm, 9–12 solo, 13–16 mute, with PAD BANK
   toggling tracks 1–4 / 5–8.
4. If any pads were left lit, clear them with
   `run_probe.bat --clear --port "MIDIOUT3"` while Live is closed.
5. Anything you changed in the **M-Vave editor** lives in the device, not in
   these files, so none of the above reverses it. Reload a factory preset from
   the editor if you want the device back as it shipped.
