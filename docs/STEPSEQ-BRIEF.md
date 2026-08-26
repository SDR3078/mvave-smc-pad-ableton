# SMC-PAD Step Sequencer — Build Brief for Claude Code

**Goal:** Build an Ableton Live MIDI Remote Script (Python) that turns the M-Vave SMC-PAD's third preset into a Push-style step sequencer. The design phase is done. This document is the spec — implement it, don't redesign it.

---

## 1. Context

- **Ableton Live 11+ (Windows gaming PC).** The Remote Script runs inside Live on Windows. The clip API used here (`get_notes_extended`, `add_new_notes`, `remove_notes_extended`) requires Live 11 or newer.
- **Development happens on the Linux devbox** (this Claude Code session). Deployment = sync the script folder to the Windows machine (git pull or SMB copy) and reload Live. There is no hot reload: Live re-imports Remote Scripts only on restart or when the control surface slot is toggled off/on in Preferences.
- **AbletonMCP is already installed as a separate control surface** on the same Live instance. It stays untouched. Live supports multiple control surfaces; this script is a new, independent one. Do not modify the AbletonMCP script folder.
- **The SMC-PAD already has two presets in use:** preset 1 = clip launching, preset 2 = finger drumming. This project adds **preset 3 = step sequencer**. Switching presets on the hardware (Shift + pad) *is* the mode switch — the script needs no mode button.
- The SMC-PAD is one USB device exposing **three virtual MIDI ports** (Windows shows them as `SMC-PAD`, `MIDIIN2 (SMC-PAD)`, `MIDIIN3 (SMC-PAD)`, plus matching OUTs). On the existing presets, port 1 carries knob CCs, port 2 carries pad notes, port 3 carries Mackie Control traffic. **Port routing is per-preset**, so Phase 0 must verify which port preset 3 actually transmits on.

## 2. Design decisions already made — do not relitigate

1. **Dedicated MIDI channel 16.** The sequencer preset sends everything (pads, knobs, buttons) on channel 16, which no other preset uses. The script consumes channel-16 traffic; it never reaches a track. Channel = the mode discriminator.
2. **The Live clip is the single source of truth.** The script holds no pattern data. Steps are read from and written to the bound MIDI clip via the Live API. Consequences that must hold: Ctrl+Z undoes step edits, saving the set saves patterns, editing notes with the mouse updates the pads, and Live's own playback provides sample-accurate timing (the script never plays notes).
3. **The script is (nearly) stateless.** Persistent state is exactly: `current_lane`, `current_bank` (page), `shift_held`, `bound_clip` reference, plus the view flag (focus/overview) and the LED cache described below. Nothing else.
4. **One write path.** Both views funnel through a single `toggle_step(pitch, step_index)` function. Views are only coordinate mappings plus render functions.
5. **Two views.**
   - **Focus view (default):** all 16 pads = 16 consecutive steps of the current lane, reading left→right, top→bottom. Bank/page selects steps 1–16 vs 17–32.
   - **Overview:** rows = 4 drum lanes (a scrollable window), columns = 4 steps per page. Shows the groove skeleton (e.g. kick/clap/hat/open-hat) at a glance.
6. **Three listeners drive everything:**
   - clip **notes listener** → re-render pads on any clip change (from pads *or* mouse edits),
   - clip **`playing_position` listener** → playhead chase (amber column/pad),
   - song.view **`selected_track` / `detail_clip` listeners** → re-bind when the user selects a different track/clip.
7. **LED language (colors are velocity values, exact map TBD in Phase 0):** step ON = teal, step OFF = off/dim, playhead = amber, playhead-on-active-step = bright/highlight. In overview, if the color experiment pans out, each lane row gets its own color.

## 3. Phase 0 — Hardware discovery (do this FIRST, interactively with me)

Budget RGB implementations vary, so these experiments gate the constants. Walk me through them one at a time; I'll be at the controller with a MIDI monitor (MIDI-OX or Live's own MIDI indicators). Record every answer in `consts.py` and in the TBD table below.

1. **Program preset 3 in CubeSuite** (M-Vave's config app) per Section 4, then verify with the monitor:
   - Which **USB port** does preset 3 transmit on? (Expected: the generic-MIDI port, but confirm.)
   - Pads send **Note On/Off, channel 16, notes 0–15**, in the programmed reading order (pad top-left = note 0 … bottom-right = note 15)? Note the actual note-off form (real Note Off vs Note On velocity 0).
   - What does the **PAD BANK** button do in a custom preset: (a) emit its own MIDI message, or (b) silently switch pads to a second note set (expect notes 16–31)? This decides the view-toggle wiring (Section 4).
   - Do the **left/right buttons** and one spare button emit assignable CCs? Which CC numbers did we assign?
   - Do knobs send on channel 16 with the assigned CCs, and in **relative CW mode** (one click right = value 1, one click left = value 127)?
2. **LED feedback experiments** (already known: the pads *do* light from incoming notes):
   - Does the pad light only when the incoming note matches **its own note+channel**, or any channel?
   - Does **incoming velocity select the LED color**? Sweep velocities (e.g. 1, 8, 16, 24 … 127) on one pad and record the observed color per value. Build the `COLOR` map from this.
   - Which **OUT port** must the script send on for LEDs to respond?
   - Do pads **self-light on press** (local LED control)? If yes, check CubeSuite for a "local off" option; if none, the script must re-render after every pad release so script state always wins.

### TBD table — fill during Phase 0

| Item | Expected | Measured |
|---|---|---|
| Preset 3 TX port | generic MIDI port | |
| Pad notes (bank A) | ch16, notes 0–15, reading order | |
| PAD BANK behavior | emits CC *or* switches to notes 16–31 | |
| Left/right button CCs | CC 102 / 103 | |
| Shift/spare button CC | CC 104 | |
| Knob CCs + mode | CC 20–27, relative CW | |
| LED input port + channel rule | same cable, ch16 only | |
| Velocity→color map | teal/amber/dim available | |
| Local LED on press | ideally off | |

## 4. CubeSuite preset 3 — proposed programming

Everything on **channel 16**:

- **Pads 1–16 (bank A):** Note 0–15, programmed in reading order (top-left = 0). This makes the script's math trivial: `step = note` in focus view.
- **Pads bank B** (if PAD BANK is a silent note-set switch): Note 16–31 → interpreted as steps 17–32 in focus view.
- **Knobs 1–4:** CC 20 (lane select / lane-window scroll), CC 21 (paint velocity), CC 22 (pattern length), CC 23 (reserved: nudge/swing later). Relative CW mode: left = 127, right = 1. Knobs 5–8: unassigned for now.
- **Left / Right buttons:** CC 102 / CC 103 (page/bank navigation).
- **One spare button as SHIFT:** CC 104, momentary (value >0 = held, 0 = released). The device's own Shift key is local (used for preset switching) and likely emits nothing — hence a dedicated CC.
- **View toggle:** Plan A — if PAD BANK emits a CC, that CC toggles focus/overview. Plan B — if PAD BANK just switches note sets, use SHIFT + Left/Right (or a second spare button) as the view toggle, and keep bank-B notes as steps 17–32.

## 5. Repo layout & deployment

```
smc-stepseq/
├── SMC_StepSeq/
│   ├── __init__.py          # create_instance(c_instance)
│   ├── smc_stepseq.py       # SMCStepSeq(ControlSurface)
│   └── consts.py            # channel, notes, CCs, COLOR map, STEP length
├── README.md                # install, port setup, usage cheatsheet
└── docs/decisions.md        # this brief + Phase 0 measurements
```

- **Install path (Windows):** `%USERPROFILE%\Documents\Ableton\User Library\Remote Scripts\SMC_StepSeq\` (Live 11+ scans the User Library).
- **Live Preferences → Link/Tempo/MIDI:** add Control Surface `SMC_StepSeq`; set Input *and* Output to the SMC-PAD port pair measured in Phase 0. On that port's MIDI Ports rows, switch **Track = Off** (belt and braces: forwarded channel-16 notes are consumed by the script anyway, but this guarantees pad presses never play an instrument). Leave the ports used by presets 1–2 exactly as they are.
- **Debugging:** `self.log_message(...)` writes to `%APPDATA%\Ableton\Live x.x.x\Preferences\Log.txt`. Tail it after every reload. Wrap `receive_midi` and all listener callbacks in try/except + log — an uncaught exception silently kills the script until reload.

## 6. Implementation spec

### 6.1 Lifecycle

```python
# __init__.py
from .smc_stepseq import SMCStepSeq
def create_instance(c_instance):
    return SMCStepSeq(c_instance)
```

`SMCStepSeq` extends `_Framework.ControlSurface.ControlSurface` (still shipped in Live 11/12; simpler than v2/v3 for a single-surface script). On `__init__`: log a hello, attach song-view listeners, attempt first clip bind, full render. On `disconnect()`: remove every listener (guard each with `*_has_listener`), send all-LEDs-off, then call super.

### 6.2 MIDI routing

```python
def build_midi_map(self, midi_map_handle):
    h = self._c_instance.handle()
    for note in range(0, 32):                       # pads bank A + B
        Live.MidiMap.forward_midi_note(h, midi_map_handle, CHANNEL, note)
    for cc in ALL_CCS:                              # knobs + buttons
        Live.MidiMap.forward_midi_cc(h, midi_map_handle, CHANNEL, cc)
```

`CHANNEL = 15` (0-indexed = MIDI channel 16). Forwarding routes these messages to `receive_midi(self, midi_bytes)` instead of the track. Parse there: status `0x9F` = note-on ch16 (`0x8F` or velocity-0 note-on = release), `0xBF` = CC ch16. Act on note-on for step toggles; on note-off, re-render (defeats local LED behavior if present). Relative CC decode: `delta = v if v < 64 else v - 128` (CW mode: 1 → +1, 127 → −1).

### 6.3 Clip binding

`_rebind()` runs on init and whenever `song.view.selected_track` or `song.view.detail_clip` changes:

1. Detach notes/position/status listeners from the old clip (guarded).
2. `clip = song.view.detail_clip`; bind only if `clip and clip.is_midi_clip`, else `bound_clip = None`.
3. Attach: `clip.add_notes_listener(self._render)`, `clip.add_playing_position_listener(self._on_playhead)`, `clip.add_playing_status_listener(self._on_playhead)`.
4. Full render. Unbound state: all pads off (or a single dim "no clip" indicator).

### 6.4 The one write path

```python
STEP = 0.25  # 1/16th note, in beats

def toggle_step(self, pitch, step_index):
    clip = self.bound_clip
    if clip is None: return
    t = clip.loop_start + step_index * STEP
    if t >= clip.loop_end: return                    # v1: stay inside the loop
    existing = clip.get_notes_extended(pitch, 1, t, STEP)
    if len(existing):
        clip.remove_notes_extended(pitch, 1, t, STEP)
    else:
        spec = Live.Clip.MidiNoteSpecification(
            pitch=pitch, start_time=t, duration=STEP,
            velocity=self.paint_velocity, mute=False)
        clip.add_new_notes((spec,))
    # no render here — the notes listener fires and renders
```

`paint_velocity` defaults to 100, adjustable via knob CC 21. Each add/remove is a native undo step. **Never write to the clip from inside `_render`** — the notes listener would loop.

### 6.5 Rendering & LEDs

- `_render()` computes the desired color for each of the 16 pads from clip contents + playhead + view, diffs against a 16-slot LED cache, and sends only the changed pads: `self._send_midi((0x90 | CHANNEL, pad_note, COLOR[state]))`. The diff keeps MIDI traffic tiny; no extra throttling needed for 16 pads.
- Reads for rendering: one `get_notes_extended` call per visible lane spanning the visible time window, then bucket note start times into steps (`round((n.start_time - loop_start) / STEP)`).
- `_on_playhead()`: `pos = clip.playing_position`; `cur = int((pos - clip.loop_start) / STEP)`. The listener fires very frequently — cache the last step and only re-render when the step index changes or playback stops (then clear the playhead).
- Steps beyond `clip.loop_end` render as OFF; the lane's base color marks in-loop empty steps if the color map allows a dim variant.

### 6.6 Views

State: `view ∈ {FOCUS, OVERVIEW}`, `current_lane` (a drum pitch, default 36), `current_bank` (0 or 1), `lane_window` (lowest pitch of the 4 overview rows, default 36), `overview_page` (0–7).

- **Focus:** pad *i* (note 0–15) → `toggle_step(current_lane, current_bank*16 + i)`. Bank-B notes 16–31 (if Plan B) → steps 17–32 directly. Left/Right buttons switch `current_bank`. Knob 20 scrolls `current_lane` (clamp to 0–127; practical range 36–51 for a drum rack). SHIFT + pad = jump-select lane: pads map to pitches 36–51 in **drum-rack orientation** (bottom-left = 36, ascending left→right then bottom→top) so it mirrors Live's drum rack on screen.
- **Overview:** pad at (row, col) with row 0 = top → `toggle_step(lane_window + row, overview_page*4 + col)`. Top row = lowest lane of the window (matches the agreed mock: kick/clap/hat/oh top→bottom). Left/Right buttons page beats (`overview_page`); optional auto-follow of the playhead page during playback (nice-to-have, off by default). Knob 20 scrolls `lane_window`. Per-lane row colors if the LED map supports it.
- Lanes are plain MIDI pitches — the script does not inspect the Drum Rack device. (Reading pad names off the rack is a stretch goal.)

### 6.7 Knobs & buttons summary

| Control | Focus view | Overview |
|---|---|---|
| Pads | toggle step of current lane | toggle step at (lane row, beat col) |
| SHIFT + pad | select lane (drum-rack layout) | select lane (same) |
| Left / Right | bank: steps 1–16 / 17–32 | page beats (4 steps per page) |
| Knob CC20 | scroll current lane | scroll 4-lane window |
| Knob CC21 | paint velocity (1–127) | same |
| Knob CC22 | pattern length: `clip.loop_end = loop_start + n*STEP`, n in 1–32 | same |
| Knob CC23 | reserved (nudge/swing later) | reserved |
| PAD BANK (or SHIFT+Left/Right) | switch to Overview | switch to Focus |

## 7. Live API notes & gotchas

- Imports available inside Live's interpreter: `import Live`, `from _Framework.ControlSurface import ControlSurface`. Python 3 since Live 11.
- `get_notes_extended(from_pitch, pitch_span, from_time, time_span)` returns MidiNote objects; `add_new_notes` takes an iterable of `Live.Clip.MidiNoteSpecification`; `remove_notes_extended` mirrors the getter. All Live 11+.
- Note times are in beats on the clip's own timeline; always offset by `clip.loop_start`.
- Guard every listener removal with the matching `*_has_listener` check; double-remove raises.
- Everything runs on Live's main thread — callbacks must be fast. The diffing LED cache plus step-change gating on `playing_position` is sufficient.
- No `time.sleep`, no threads, no blocking I/O anywhere in the script.

## 8. Milestones (implement in order; each ends with a checkpoint I run in Live)

1. **Skeleton:** script loads, logs hello, forwards ch16, logs every pad press, echoes the note back so the pressed pad lights. ✔ press pad 1 → log line + LED.
2. **Bind + read:** clip binding with re-bind listeners; focus view renders existing clip notes on the pads. ✔ mouse-drawn notes appear on pads; switching tracks re-renders.
3. **Write:** `toggle_step` + notes-listener re-render. ✔ pad toggles a 16th note at the right position; Ctrl+Z removes it and the LED follows.
4. **Playhead:** amber chase in focus view, cleared on stop. ✔ playing clip shows a moving pad.
5. **Navigation:** banks (steps 17–32), pattern-length knob, lane scroll + SHIFT-select. ✔ 2-bar pattern editable end to end.
6. **Overview:** 4×4 lane/step grid, paging, lane-window scroll, per-lane colors. ✔ kick/clap/hat/oh groove readable and editable at a glance.
7. **Polish:** README (install + port setup + control cheatsheet), all-LEDs-off on disconnect, defensive logging pass.

## 9. Definition of done

Preset 3 active → pads edit the selected MIDI clip as a step sequencer with LED feedback and playhead chase; presets 1–2 behave exactly as before; undo, save, and mouse editing stay fully native; nothing the script receives on channel 16 ever reaches an instrument; script survives track switching, clip deletion, and Live restart without errors in Log.txt.

## 10. Explicitly out of scope for v1 (stretch list — do not build now)

Per-step velocity editing (hold pad + turn knob), aftertouch → ratchets, swing/nudge, auto-creating a clip when none is selected, reading Drum Rack pad names, note repeat integration (hardware already provides it), melodic/scale mode.
