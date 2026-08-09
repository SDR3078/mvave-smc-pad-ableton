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
| Ableton Live | Any version that ships the classic `_Framework` MIDI Remote Scripts API. Developed and tested against Live 12. |
| Hardware | M-Vave SMC-PAD, connected by USB. |
| OS | Windows or macOS. **Everything here was built and tested on Windows only.** The macOS paths below are Live's standard locations, but they have not been verified with these scripts. |
| Python | None needed. Live runs the scripts with its own interpreter. (The optional probe tool in `tools/` needs Python — see [Finding out what your unit sends](#finding-out-what-your-unit-sends).) |

Two known `_Framework` differences across Live versions are already handled in
the code: missing `ClipSlotComponent` colour setters degrade to plain clip
launching with a warning in the log, and the `set_parameter_controls` assert that
demands exactly 8 controls is satisfied by padding with CCs the device never
sends.

### What the scripts expect the device to send

`MIDI_Map.py` and `MVave_SMC_KNOBS.py` assume this, all on MIDI channel 1:

| Control | Sends |
|---|---|
| 16 pads | notes **1–16**, reading order — top-left is 1, bottom-right is 16 — on the **third** port pair (the DAW port), velocity 127 on press and note-on velocity 0 on release |
| Buttons | note **17** play, **18** stop, **19** record, **20** left arrow, **21** right arrow |
| Encoders 1–6, knob bank 2 | CC **44, 45, 42, 43, 40, 41** (that order — the CC numbers do not follow the printed encoder numbers), absolute |
| Encoders 7–8, knob bank 2 | CC **38, 39**, **relative**, centred on 64: 63 is one step back, 65 one step forward |

This was measured on one unit whose pad bank and transport buttons had been
configured by hand in the M-Vave editor, and whose two navigation encoders had
been switched there from absolute to relative. **A factory unit will not match.**
On the measured unit, the eight Shift+Pad presets transmitted note ranges
1) 4–19, 2) 20–35, 3) 1–16 (the hand-edited one), 4) 52–67, 5) 68–83, 6) 84–99,
7) 100–115, 8) 52–67.

So before you start, either configure the device in the M-Vave editor to match
the table, or change the numbers in `MIDI_Map.py` to match your device — see
[Customising](#customising). The two navigation encoders must be relative
whichever way you go; an absolute encoder sends a position, and the session box
is an index the arrows and the mouse also move, so an absolute counter desyncs
and the box teleports the next time you touch the knob.

#### Finding out what your unit sends

`tools/mvave_probe.py` logs everything the device transmits and can light pads,
without installing a Remote Script:

```
run_probe.bat --list                            # enumerate ports
run_probe.bat --listen --port "MIDIIN3"         # log notes and CCs, with a summary
run_probe.bat --knobs  --port "SMC-PAD 0"       # map every encoder to its CC, one at a time
run_probe.bat --clear  --port "MIDIOUT3"        # extinguish every pad
```

The `.bat` is Windows-only and builds its own venv on first run; on macOS run
`mvave_probe.py` directly against `mido` and `python-rtmidi` (untested).
Port names need the trailing index to disambiguate, because `SMC-PAD` is a
substring of all three Windows port names — use `"SMC-PAD 0"`.

**Windows MIDI ports are exclusive.** Close Live, or untick the port in
Preferences, before running the probe, or it cannot open the port.

---

## Installation

### 1. Copy both folders into Live's Remote Scripts directory

Copy the folders themselves — `MVave_SMC_PAD` and `MVave_SMC_KNOBS` — not their
contents, and do not nest them one level deeper. Live scans the direct
subfolders of this directory, and each subfolder must keep its `__init__.py`.
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
to that port kills them silently. Remake them on port 2.

### 5. Put the device on knob bank 2

Press **KNOB BANK** until the device is on bank 2. The button switches all eight
encoders at once and each bank has its own CC set — bank 1 sends CC 1–8, bank 2
sends CC 38–45. **The scripts only listen to bank 2.** Bank 1 is deliberately
left alone so its eight absolute encoders stay free for Ctrl+M on the port from
step 4.

On knob bank 1 every encoder in this setup does nothing. That is the expected
behaviour, not a fault.

---

## Verifying it worked

`Log.txt` lives at:

- **Windows:** `%APPDATA%\Ableton\Live <version>\Preferences\Log.txt`
- **macOS:** `~/Library/Preferences/Ableton/Live <version>/Log.txt` (standard
  location, not verified here)

Look for these lines, in this order:

```
MVave_SMC_KNOBS: loaded. CC 38/39 navigate, CC 44,45,42,43,40,41 = macros 1-6.
MVave_SMC_KNOBS: device component -> <device name>
MVave_SMC_KNOBS: first nav CC -- 38 value 65
```

| Line | Proves | Appears when |
|---|---|---|
| `loaded.` | The knob script was found and constructed. | At startup. |
| `device component -> …` | The macro knobs have a device to point at. | **Only once the selected track changes** — click a track before concluding the macros are broken. |
| `first nav CC -- 38 value 65` | MIDI is actually reaching the script. | The first time you turn encoder 7 or 8. Logged once only; a knob produces hundreds of messages. |

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
| **Bank 2**, encoders 1–6 | Macros 1–6 of the **selected** device (Live's blue hand) |
| **Bank 2**, encoder 7 | Move the session box across tracks |
| **Bank 2**, encoder 8 | Move the session box through scenes |
| **Bank 1**, encoders 1–8 | Nothing — deliberately unassigned, free for Ctrl+M |

The macros follow the selection: click a different track and the same six knobs
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

- **The device is on knob bank 1.** Bank 1 is unassigned by design. Press KNOB
  BANK.
- **Slot 2 is empty or on the wrong port.** `MVave_SMC_KNOBS` needs the *first*
  port pair as input. Check for the `MVave_SMC_KNOBS: loaded.` line in `Log.txt`;
  no line means the script never constructed.
- **No device is selected yet** — see the next entry.
- **The selected track has no device.** The blue hand needs something to hold.

### The macros only start working after you click a track

Expected. `DeviceComponent` is only handed a device when the **selected track
changes**, so after a fresh load the knobs do nothing until you click a track.
Click any track once after starting Live. The `device component -> …` line in
`Log.txt` appears at that same moment, which is why its absence at startup is
not a fault.

### Pads stay stuck lit

The device ignores real note-offs (`0x80`) — a pad is extinguished by a note-on
with **velocity 0**, not by a note-off. Live's `_Framework` sends the right thing
while the script is running, but the LEDs simply hold their last value if the
script goes away: Live closed while pads were lit, the slot set to `None`, or a
crash.

Fix: `run_probe.bat --clear --port "MIDIOUT3"` (with Live closed, since the port
is exclusive). Sending a note-off from anywhere will not clear them.

### One knob appears dead

Almost always **the wrong knob bank**. KNOB BANK switches all eight encoders at
once and each bank has its own CCs, so a mapping made on bank 1 looks completely
dead while bank 2 is selected, and vice versa. Check the bank before debugging
anything else about a knob.

If it is dead on bank 2 as well, its CC may not match the map — verify with
`run_probe.bat --knobs`, which reports each encoder separately and names silent
knobs and CC clashes.

### The session box jumps to one end when you turn encoder 7 or 8

That encoder is still **absolute**. It transmits a position, not a step, so the
first message after the box has moved by any other means slams it to wherever the
knob's counter happens to be. Switch CC 38 and 39 to relative in the M-Vave
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

- `MACRO_CCS = (44, 45, 42, 43, 40, 41)` — in **encoder order**, left to right,
  not numeric order. Listing them as 40…45 instead scatters the macros across the
  panel. Flip the tuple to put macro 1 at the top of the six rather than the
  bottom.
- `PAD_CCS = (118, 119)` — filler, so the tuple is 8 long for `_Framework`
  versions that assert on it. The device never sends these, so macros 7 and 8 are
  unreachable by design. Don't point them at a real CC unless you mean it.
- `CC_TRACK = 38`, `CC_SCENE = 39`, `CENTRE = 64` — the relative navigation
  encoders.

### One editing gotcha

Files in `MVave_SMC_PAD/` have **CRLF line endings**. Line-anchored patterns in
`sed` and friends silently no-op unless they account for the trailing `\r`.

---

## Uninstalling

1. In Live, Preferences → Link, Tempo & MIDI: set **both** Control Surface slots
   showing `MVave_SMC_PAD` and `MVave_SMC_KNOBS` back to `None`.
2. Delete both folders from the Remote Scripts directory you installed them to:

   ```
   <remote-scripts-dir>\MVave_SMC_PAD
   <remote-scripts-dir>\MVave_SMC_KNOBS
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
