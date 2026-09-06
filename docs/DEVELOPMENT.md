# Development

How these scripts are built, why they are built that way, and what to change if
you want them to do something else — or if you are writing a Remote Script for a
different controller and want the parts of this that generalise.

For what the controller physically sends, see [HARDWARE.md](HARDWARE.md). For
setup, see [INSTALL.md](INSTALL.md).

---

## Contents

- [How Live loads a Remote Script](#how-live-loads-a-remote-script)
- [Package naming, and one hazard it creates](#package-naming-and-one-hazard-it-creates)
- [Origin and attribution](#origin-and-attribution)
- [Why there are two scripts](#why-there-are-two-scripts)
- [How the knob script reaches the pad script's session box](#how-the-knob-script-reaches-the-pad-scripts-session-box)
- [File-by-file walkthrough](#file-by-file-walkthrough)
- [The MIDI map indirection](#the-midi-map-indirection)
- [Clip-state colour feedback](#clip-state-colour-feedback)
- [The device macros and the blue hand](#the-device-macros-and-the-blue-hand)
- [`_Framework` gotchas that fail silently](#_framework-gotchas-that-fail-silently)
- [Changing the mapping](#changing-the-mapping)
- [Adapting this to a different controller](#adapting-this-to-a-different-controller)
- [Known rough edges](#known-rough-edges)

---

## How Live loads a Remote Script

A Remote Script is a Python package directory dropped into Live's MIDI Remote
Scripts folder. Live scans that folder at startup, lists each subdirectory by
folder name in the Control Surface dropdown, and for the one you select calls
`create_instance(c_instance)` in its `__init__.py`. Both packages here are the
minimal three lines:

```python
from .MVave_SMC_PAD import MVave_SMC_PAD

def create_instance(c_instance):
    return MVave_SMC_PAD(c_instance)
```

Three consequences worth internalising before you start:

- **The folder name is the product name.** Renaming the folder renames the entry
  in the dropdown and invalidates the saved preference.
- **Live restarts are the edit-compile-run loop.** There is no reload. Every
  change means restarting Live.
- **`Log.txt` is the only debugger.** `self.log_message()` from a `ControlSurface`
  writes to it. An exception thrown during `__init__` disables the script
  entirely, usually with nothing visible in the UI beyond the controller not
  working — which is why several patterns in this codebase exist purely to keep
  exceptions out of `__init__`. See
  [`_Framework` gotchas](#_framework-gotchas-that-fail-silently).

---

## Package naming, and one hazard it creates

Every Control Surface in this repo follows the same shape:

```
MVave_SMC_<ROLE>/                 <- Live shows this string in its dropdown
├── __init__.py                   <- create_instance()
├── MVave_SMC_<ROLE>.py           <- the module, named for the folder
│     class MVave_SMC_<ROLE>      <- the class, named for the module
└── MIDI_Map.py                   <- device numbers, when there are enough
                                     to justify a file; inline otherwise
```

| | Folder | Module | Class | Constants |
|---|---|---|---|---|
| `MVave_SMC_PAD` | ✓ | ✓ | ✓ | `MIDI_Map.py` |
| `MVave_SMC_KNOBS` | ✓ | ✓ | ✓ | inline (~6 of them) |
| `MVave_SMC_STEPSEQ` | ✓ | ✓ | ✓ | `MIDI_Map.py` |

The folder name is load-bearing — it is the string a user picks in Live, so
renaming a package means re-selecting it in Preferences.

**The hazard.** Package, module and class share one name, and `__init__.py` does
`from .MVave_SMC_<ROLE> import MVave_SMC_<ROLE>` — which binds the **class** over
the **module** in the package namespace. So this does not do what it looks like:

```python
import MVave_SMC_STEPSEQ.MVave_SMC_STEPSEQ as m   # m is the CLASS, not the module
m.SOME_FLAG = False                               # sets a class attribute; the
                                                  # module's global is untouched
```

It fails *silently* in the direction that matters: the assignment succeeds, and
the code reading the global never sees it. `sys.modules` is not shadowed, so
that is the reliable handle:

```python
m = sys.modules['MVave_SMC_STEPSEQ.MVave_SMC_STEPSEQ']
```

All three packages have this shadowing. Only the self-test ever imports a module
by its dotted path, so it is the only place that has to care — see `SEQ_MODULE`
in `tools/stepseq_selftest.py`.

## Origin and attribution

`MVave_SMC_PAD/` is a derivative of **Hanz Petrov's "Introduction to the
Framework Classes"** template — published on
[remotescripts.blogspot.com](http://remotescripts.blogspot.com/2010/03/introduction-to-framework-classes.html)
in four parts from March 2010, still online as of 2026-09-05, and carrying no
licence statement on either the articles or the Support Files page that hosts
the example scripts. That page also distributes decompiled Live 8.2.2
`_Framework`, APC40 and APC20 scripts, which is the likely origin of the
`Partial --== Decompile ==--` marker in `SpecialViewControllerComponent.py`.

The template is the long-standing tutorial skeleton for custom Live Remote
Scripts, structured as an APC40/APC20 emulation with a flat `MIDI_Map.py` of
note and CC constants. Its fingerprints are all over this code:
the class docstring still says *"Script for M-Vave SMC-PAD in APC emulation
mode"*, several files carry `# emacs-mode: -*- python-*-` and
`# local variables: tab-width: 4` headers and footers,
`SpecialViewControllerComponent.py` is labelled
`# Partial --== Decompile ==-- with fixes`, and `SpecialTransportComponent.py`
credits *"from OpenLabs module SpecialTransportComponent"* for its undo/redo
handlers.

`MVave_SMC_KNOBS/` and `MVave_SMC_STEPSEQ/` are original to this project.

| Area | Provenance |
|---|---|
| `ControlSurface` subclass shape, `_setup_*` method split | Template |
| Combination mode: `_active_instances`, `_combine_active_instances`, `_do_combine`, `_do_uncombine`, `_activate_combination_mode` | Template |
| `_load_MIDI_map()` — 128 `ButtonElement`s + 128 `SliderElement`s indexed by note/CC number | Template |
| `MIDI_Map.py` as a flat constants file, `-1` meaning unassigned | Template (values replaced) |
| `_on_selected_track_changed()` device-follow | Template |
| `_load_pad_translations()` / `set_pad_translations()` | Template |
| All six `Special*Component.py` files — channel strip, mixer, session, transport, view controller, zooming | Template (in turn partly decompiled from Ableton's own scripts, and partly borrowed from the OpenLabs scripts). `SpecialZoomingComponent.py` additionally carries this project's clamp fixes (commit `204acbe`) |
| `TSB_X` / `TSB_Y` session-box size constants | Unclear — see below |
| `_apply_clip_colours()` and the `CLIP_*` palette constants | **This project** |
| `_setup_modifier()` / `_modifier_value()` / `_set_session_banking()` and `MODIFIER` | **This project** |
| `self._missing_clip_setters` version-tolerance logging | **This project** |
| Every value in `MIDI_Map.py` (note map, 4×4 grid, palette indices, transport notes) | **This project** |
| `MVave_SMC_KNOBS/` — except `__init__.py`, which is the template's boilerplate with the names changed, footer included | **This project** |
| `MVave_SMC_STEPSEQ/` — except `__init__.py`, the same three-line boilerplate as the row above | **This project** |

**The copy in this repo passed through at least one hand between Petrov's
original and this project.** The `TSB_X`/`TSB_Y` indirection and comments written
in the first person — *"My guess is that altering the range here will allow you
to alter the range of mixer tracks"*, *"There are lot of things to explore that
you can use to add extra functionality to your scipt"* — are not this project's
and are not obviously Petrov's either. Treat them as third-party edits of unknown
provenance; do not assume a diff against the original template will be small or
clean.

The licence position follows from this: `MVave_SMC_PAD/` is inherited, not freely
chosen. See the Licence section of the [README](../README.md).

---

## Why there are two scripts

**A Remote Script gets exactly one MIDI input port, and this controller sends its
pads and its encoders on different ports.**

The SMC-PAD presents three port pairs. Measured behaviour: the pads and the five
buttons appear only on port 3 (the DAW port); the eight encoders appear on ports
1 and 2, identically, and never on port 3. No single script can see both halves.

So there are two packages in two Control Surface slots:

| Slot | Script | Input | Output | Owns |
|---|---|---|---|---|
| 1 | `MVave_SMC_PAD` | port 3 in | port 3 out | 16 pads, 5 buttons, all LED feedback |
| 2 | `MVave_SMC_KNOBS` | port 1 in | *none* | the 8 encoders |
| — | — | port 2 left unassigned | | remains available to Live's own MIDI mapping |

Two properties of Live's port handling shape this table:

- **Claiming a port with a Control Surface disables Track/Sync/Remote on it.**
  Assigning the knob script to port 1 silently kills any Ctrl+M mappings that were
  arriving there. Ports 1 and 2 carry identical CCs, so the script takes one and
  ordinary MIDI mapping survives on the other. If your controller has no such
  duplicate port, understand that a script and Ctrl+M cannot share.
- **The knob script needs no output.** It sends nothing to the device; leaving
  Output at None avoids a second script writing to a port the pad script's LED
  feedback might also want.

The split is not a design preference. If your controller puts everything on one
port, write one script.

---

## How the knob script reaches the pad script's session box

Bank 2's encoders 1 and 2 — the bottom pair — move Live's session box (the red
rectangle), one across tracks,
one through scenes. The obvious implementation, a `SessionComponent` inside
`MVave_SMC_KNOBS`, is wrong.

**Why no second `SessionComponent`:** Live's red box belongs to whichever script
last called `set_highlighting_session_component()`. The pad script calls it, at
the end of `MVave_SMC_PAD.__init__`, on the session that owns the 4×4 clip grid.
A second box would either fight that one for the highlight, or — because the pad
script's class-level `_active_instances` machinery implements the template's
APC-style combination mode, in which multiple sessions link side by side with
`TRACK_OFFSET = -1` auto-joining them — end up linked into a two-box arrangement
nobody asked for. Either way the pads and the encoders would be looking at
different regions of the set.

**What it does instead** — `MVave_SMC_KNOBS._pad_session()`:

```python
from MVave_SMC_PAD.MVave_SMC_PAD import MVave_SMC_PAD
instances = getattr(MVave_SMC_PAD, '_active_instances', None) or []
return getattr(instances[0], '_session', None)
```

It imports the pad script's class by absolute package path, reads the class-level
`_active_instances` list that `_do_combine()` populates in the pad script's
`__init__`, takes the live instance, and reaches its `_session`. Then
`_bank()` calls `set_offsets()` on that session — the same entry point the
template's own `SpecialZoomingComponent._scroll_*` methods use, so it is a
supported way to move the box rather than a poke at private state.

Both scripts run in the same Python interpreter inside Live, so this is an
ordinary intra-process import. There is no IPC.

**Why the lookup is lazy — resolved on every encoder turn, never cached:**

1. **Slot initialisation order is not controllable.** Live constructs the control
   surfaces in an order this code does not choose and should not assume. If the
   knob script is built first, `_active_instances` is empty at that moment. A
   reference captured in `__init__` would be `None` forever, and the encoders
   would be dead until the next Live restart happened to load them in the other
   order — a bug that appears and disappears for no visible reason.
2. **The pad script can be replaced without the knob script noticing.** Editing
   preferences causes Live to tear down and rebuild control surfaces.
   `_do_uncombine()` removes the old instance from `_active_instances` and the new
   one appends itself; the lazy lookup picks up the replacement automatically,
   where a cached reference would point at a disconnected object.
3. **It costs nothing.** After the first import, `from MVave_SMC_PAD...` is a
   `sys.modules` dictionary hit, and the rest is two `getattr`s on a
   one-element list.

Failures are reported once, not per message — `_log_once()` latches on the
`self._logged` set (keyed on the message, so a later distinct problem is not
hidden by an earlier one), because an encoder generates hundreds of messages and
a per-turn log line would bury `Log.txt`. `_navigate()` uses the same
one-shot-logging trick with `_first_nav_logged` for the positive case: one line
proving the pipe works, then silence.

**Clamping happens in the caller, not in the framework.** `_bank()` computes the
new offsets and clamps them with `_clamp()` before calling `set_offsets()`,
because `set_offsets` asserts on a negative offset and an assertion raised inside
a MIDI callback takes the script down mid-performance. Note the track count comes
from `song.visible_tracks` with a fallback to `song.tracks` for framework
versions that lack the former.

Two limitations of the current implementation, both visible in the code:

- `instances[0]` — with two pad-script instances loaded (real combination mode),
  the encoders always move the first one's box.
- The clamp ceiling is `len(song.visible_tracks) - session.width()`, while the pad
  script hands the session a mixer whose `tracks_to_use()` includes return tracks.
  If the framework's `SessionComponent` takes its track list from its mixer — some
  versions do — the encoder's ceiling would be lower than the box's real range, and
  it could not bank onto the return tracks. **Unverified**; `_Framework` was not
  available to read while this was written.

---

## File-by-file walkthrough

### `MVave_SMC_PAD/`

| File | What it is |
|---|---|
| `__init__.py` | `create_instance()`. Three lines. |
| `MVave_SMC_PAD.py` | The `ControlSurface` subclass. All wiring lives here. |
| `MIDI_Map.py` | Every note number, CC number, grid size and colour index. The only file most users need to edit. |
| `SpecialSessionComponent.py` | `SessionComponent` + combination-mode linking + "fire the highlighted slot" button. |
| `SpecialMixerComponent.py` | `MixerComponent` whose `tracks_to_use()` returns visible tracks **and** return tracks; creates `SpecialChannelStripComponent`s. |
| `SpecialChannelStripComponent.py` | Channel strip whose select button also folds/unfolds group tracks, after a 5-tick timer delay. |
| `SpecialTransportComponent.py` | Transport + record-quantisation toggle, undo/redo, a relative tempo encoder, and a `_tempo_value` override that reads `TEMPO_TOP`/`TEMPO_BOTTOM` from `MIDI_Map.py`. |
| `SpecialViewControllerComponent.py` | `DetailViewControllerComponent` — toggles Detail view, switches Clip/Device chain, scrolls the device chain. |
| `SpecialZoomingComponent.py` | `SessionZoomingComponent` with page-wise (not step-wise) scrolling: `_scroll_*` snap the box to width/height boundaries. **Inert as shipped** — `ZOOMUP/DOWN/LEFT/RIGHT` are all `-1`, so `set_nav_buttons` receives four `None`s and nothing can call them. |

**`MVave_SMC_PAD.__init__`** runs everything inside `with self.component_guard():`
— the framework's context manager for building components — in this order:
`_load_MIDI_map()`, `_setup_session_control()`, `_setup_mixer_control()`,
`_session.set_mixer(...)`, `_setup_device_and_transport_control()`,
`set_highlighting_session_component(self._session)`. Then, outside the guard,
`_load_pad_translations()` and `_do_combine()`.

**`_setup_session_control()`** builds the `SpecialSessionComponent` at
`TSB_X × TSB_Y`, assigns bank/select/stop buttons from the note map, then loops
scenes × tracks assigning each clip slot's launch button from `CLIPNOTEMAP` and
calling `_apply_clip_colours()`. It also builds the `SpecialZoomingComponent` and
calls `_setup_modifier()`.

**`_setup_mixer_control()`** is stock template: a hardcoded 8-strip mixer with
arm/solo/mute/select buttons and volume/pan/three sends per strip. Every one of
those constants is `-1` in this project's `MIDI_Map.py`, so the whole mixer is
built and wired to `None` — except `set_select_buttons(TRACKRIGHT, TRACKLEFT)`,
which is what makes buttons 20 and 21 select the previous/next track.

**`_setup_device_and_transport_control()`** builds three things: the
`DeviceComponent`, the `DetailViewControllerComponent`, and the
`SpecialTransportComponent`. Only the device component is stored on `self`; the
other two are local variables (`detail_view_toggler`, `transport`) and the script
keeps no reference to them. That is inherited from the template. If you need to
reassign their buttons at runtime, store them first.

Note the two guards:

```python
if None not in device_bank_buttons:
    self._device.set_bank_buttons(tuple(device_bank_buttons))
if None not in device_param_controls:
    self._device.set_parameter_controls(tuple(device_param_controls))
```

This is the template's answer to the eight-controls assertion described
[below](#2-set_parameter_controls-wants-exactly-8): rather than pad the tuple, it
declines to call the setter at all unless all eight slots are assigned. In this
project `DEVICEBANK` is all `-1`, so bank buttons are skipped, while
`PARAMCONTROL` is `(1..8)`, so `set_parameter_controls` *is* called — with
`SliderElement`s on CC 1–8 of the pad script's own port. The DAW port never sends
CCs, so the pad script's device component is inert in practice. It is left in
place because removing it means either setting `PARAMCONTROL` to `-1`s or editing
template code, and it does no harm.

**`_load_pad_translations()`** would call `set_pad_translations()` — the framework
call that tells Live "these 16 buttons are a drum rack" — but `DRUM_PADS` is all
`-1`, so the `if -1 not in DRUM_PADS` guard skips it. The pads are a clip grid
here, not a drum rack; the two uses are mutually exclusive because a translated
pad's note is swallowed before the session component sees it.

**`disconnect()`** removes the modifier's value listener, drops the maps, calls
`_do_uncombine()`, and chains to `ControlSurface.disconnect`. See
[Known rough edges](#known-rough-edges) for the inherited bug in `_do_uncombine`.

### `MVave_SMC_KNOBS/`

| File | What it is |
|---|---|
| `__init__.py` | `create_instance()`. |
| `MVave_SMC_KNOBS.py` | Everything: constants, the `ControlSurface` subclass, the relative-encoder decode, the cross-script session lookup — all of it in one file, no subcomponents. |

Its constants sit at the top of the file rather than in a separate map, because
there are only a handful:

```python
CHANNEL  = 0
CENTRE   = 64
CC_TRACK = 17            # bank 2, encoder 1
CC_SCENE = 18            # bank 2, encoder 2
MACRO_BY_CC = {          # CC -> macro number, 1-based
    1: 1,  2: 2,  3: 3,  4: 4,  5: 5,  6: 6,  7: 7,  8: 8,     # bank 1
    9: 9,  10: 10, 11: 11, 12: 12, 13: 13, 14: 14,             # bank 2
    15: 15, 16: 16,                    # bank 2 bottom pair, sequencer preset
}
STEPS_PER_SWEEP = 127.0  # one click = this fraction of a parameter's range
```

Macro *N* is `device.parameters[N]` — index 0 is the device on/off switch, so the
numbering needs no offset arithmetic.

**Build the map in encoder order, not numeric CC order.** On this device one bank
always runs ascending with the printed labels while the other descends in pairs,
and *which bank misbehaves has already swapped once* between measurements. Listing
CCs numerically compiles fine and scatters the macros across the panel in a
physical order that looks random under your hands. Measured one encoder at a time
with the probe tool; see [HARDWARE.md](HARDWARE.md) §4, and re-measure after any
change in the M-Vave editor rather than trusting a table.

The class has four responsibilities, in four small blocks:

1. `_setup_device_control()` — construct a `DeviceComponent` *purely* so Live's
   blue hand follows the same device the knobs write to, and register it with
   `set_device_component()`. `set_parameter_controls()` is deliberately never
   called; see gotcha 2.
2. `_on_selected_track_changed()` — point both that component and the script's own
   `_target_device` at the newly selected track's device.
3. `build_midi_map()` / `receive_midi()` / `_navigate()` / `_macro()` — forward and
   intercept all eighteen CCs, decoding the relative encoding by hand and writing
   `device.parameters[n]` directly.
4. `_pad_session()` / `_bank()` / `_probe_value()` — move the other script's session box.

**`_probe_value()` reads the session's getters defensively:**

```python
method = getattr(session, method_name, None)   # 'track_offset'
if callable(method):
    return method()
if method is not None:
    return method          # spelled as a plain attribute on this version
return getattr(session, attr_name, None)       # '_track_offset'
```

`_Framework` exposes these as methods in most versions and as bare attributes in
others. The same reasoning as `_apply_clip_colours` — probe, don't assume, because
the framework being probed is not on the machine the code was written on.

---

## The MIDI map indirection

The template's central trick, and the reason `MIDI_Map.py` can be pure constants:

```python
for note in range(128):
    button = ButtonElement(is_momentary, MESSAGETYPE, BUTTONCHANNEL, note)
    button.name = 'Note_' + str(note)
    self._note_map.append(button)
self._note_map.append(None)     # index -1
```

All 128 possible note buttons and all 128 possible CC sliders are constructed up
front, whether used or not. Wiring then reads `self._note_map[PLAY]` — the
constant *is* the index. And because a `None` is appended at the end,
`self._note_map[-1]` is `None`, so **`-1` in `MIDI_Map.py` means "unassigned"
with no branching anywhere**. Every `-1` in that file flows through to a setter
being handed `None`, which the framework's setters accept as "no button".

That is why `MIDI_Map.py` can be almost entirely `-1` and the script still starts.
It is also why a typo of `-2` instead of `-1` silently binds note 127 — the list is 129 long, so `[-1]` is the `None`, `[-2]` is `Note_127`, and the mistake double-binds a note that is already in use.

Two details:

- `MESSAGETYPE` selects notes (`0`) or CCs (`1`) for all buttons. If you set it to
  CCs, `BUTTONCHANNEL` and `SLIDERCHANNEL` must differ, and `_load_MIDI_map`
  fills `_ctrl_map` with 128 `None`s to avoid two elements fighting over the same
  message.
- All buttons are constructed with `is_momentary = True`. The SMC-PAD sends
  note-on velocity 127 on press and note-on velocity 0 on release, which is
  exactly the momentary contract.

---

## Clip-state colour feedback

The pads light because `_Framework`'s `ClipSlotComponent` calls `send_value()` on
its launch button when the slot's state changes, and `send_value()` on a
note-type `ButtonElement` emits a note-on with that value as the velocity. On this
controller the velocity of an incoming note-on is a **palette index, not a
brightness**, so the framework's "LED value" mechanism doubles as a colour
mechanism with no extra code. The values live in `MIDI_Map.py`:

| Constant | Value | Colour | State |
|---|---|---|---|
| `CLIP_PLAYING` | 5 | green | clip is playing |
| `CLIP_STOPPED` | 15 | orange | slot holds a clip, not playing |
| `CLIP_RECORDING` | 14 | red-pink | clip is recording |
| `CLIP_TRIGGERED_PLAY` | 21 | bright blue | queued, waiting for the quantise point |
| `CLIP_TRIGGERED_REC` | 24 | light purple | queued to record |

Empty slots are off (0) — that is the framework's default, not a constant here.
The palette is not linear and not a hue ramp you can compute: it cycles hue every
13–14 steps and everything above roughly 64 is the same flat blue, so all useful
values are low. There is no saturated red; 14 is as close as the palette gets.
14 and 15 are adjacent in the cycle, so if red-pink and orange prove hard to tell
apart in practice, move `CLIP_STOPPED` to 21 or 24 for more contrast.

Live owns the grid outright — measured, not assumed: the pads do not recolour
themselves when struck, and a colour Live has set survives being hit. So the
script needs no re-assert-after-press logic.

### Why the setters are called by name and guarded

```python
def _apply_clip_colours(self, clip_slot):
    for setter, value in (('set_started_value', CLIP_PLAYING),
                          ('set_stopped_value', CLIP_STOPPED),
                          ('set_recording_value', CLIP_RECORDING),
                          ('set_triggered_to_play_value', CLIP_TRIGGERED_PLAY),
                          ('set_triggered_to_record_value', CLIP_TRIGGERED_REC)):
        method = getattr(clip_slot, setter, None)
        if method is not None:
            method(value)
        elif setter not in self._missing_clip_setters:
            self._missing_clip_setters.append(setter)
            self.log_message('MVave_SMC_PAD: ClipSlotComponent has no %s()' % setter)
```

Three decisions, each with a reason:

- **By name via `getattr` rather than `clip_slot.set_started_value(...)`.**
  `ClipSlotComponent` has gained and lost these setters across Live versions —
  `set_triggered_to_play_value` and `set_triggered_to_record_value` in particular
  are not present in every vintage. A direct call would raise `AttributeError`.
- **Guarded rather than allowed to raise.** This runs inside
  `_setup_session_control()`, which runs inside `__init__`. An exception there does
  not cost you the colour; it costs you the entire script — no clip launching, no
  transport, nothing. Colour is a nicety, launching is the product. Degrade, don't
  die.
- **Logged once, via `self._missing_clip_setters`.** The loop runs for all 16 clip
  slots, so an unguarded log line would print the same message sixteen times per
  startup and make `Log.txt` useless for anything else.

This is the pattern to copy whenever you touch an API surface that varies by host
version: probe with `getattr`, degrade to the subset that exists, say so once.
`MVave_SMC_KNOBS._probe_value()` is the same idea applied to two different framework
spellings of the same value.

---

## The device macros and the blue hand

`DeviceComponent` is `_Framework`'s "controls whatever device is selected"
component. Registering it with `self.set_device_component(...)` is what makes Live
draw the **blue hand** on a device's title bar — the marker meaning "a control
surface is pointed here". The component maps its parameter controls onto the
current parameter bank of the device it holds; for an Instrument or Audio Effect
Rack, that bank is the eight macro knobs.

Both scripts create one. Each `ControlSurface` instance stores its own
`_device_component`, so they do not collide, but only the knob script's has
controls that the hardware actually feeds.

The point of doing this in a script rather than with Ctrl+M is that Ctrl+M binds a
knob to *one fixed parameter of one fixed device forever*. The blue hand follows
the selection: click a different track, and the same encoders now drive that
track's device. That is the entire justification for the knob script existing.

### It only gets a device when the selected track changes

```python
def _follow_selected_track(self):                 # wrapped by the guard above
    ControlSurface._on_selected_track_changed(self)
    track = self.song().view.selected_track
    device_to_select = track.view.selected_device
    if device_to_select is None and len(track.devices) > 0:
        device_to_select = track.devices[0]
    if device_to_select is not None:
        self.song().view.select_device(device_to_select)
    self._device_component.set_device(device_to_select)
```

All three scripts contain this failure mode and all three guard it — but not
with the same shape, so do not read one and assume the others.
`MVave_SMC_PAD` and `MVave_SMC_KNOBS` both override
`_on_selected_track_changed`, wrap the body in a `try`, and give the superclass
call its own inner `try` so that a framework failure cannot cancel the rebinding
below it. `MVave_SMC_STEPSEQ` has no such override at all — it reaches the
selection through a `selected_track` listener and guards that with the
`@_guarded` decorator. All three latch and cap what they log.

The shape above — lifted from the pad template, which is known to work against
this vintage of `_Framework` — is the *only* place `set_device()` is called. There is
no equivalent hook on load and none on "selected device changed within the same
track". So:

- **After a fresh Live start the encoders do nothing until you click a track.**
  That is expected behaviour, not a fault. `Log.txt` distinguishes the two: the
  script logs `device -> <name>` the first time this fires (once only,
  latched on `_device_logged`). No such line means the hook has never run; a line
  saying `-> None` means it ran and found nothing to control.
- Selecting a different device *inside* the current track does move the blue hand,
  because Live's own device-selection listener inside `DeviceComponent` handles
  that; what this override adds is the cross-track case.

If you want the macros live immediately at startup, you would need to call the
same body once after construction. That is not done here and has not been tested.

---

## `_Framework` gotchas that fail silently

These get their own section because **each one produces a script that loads
cleanly, logs nothing unusual, and half-works**. That is the worst failure mode
available in this environment: there is no debugger, no reload, and the only
symptom is a control that does nothing.

### 1. `receive_midi` must forward what it does not handle

```python
def receive_midi(self, midi_bytes):
    if (len(midi_bytes) == 3 and (midi_bytes[0] & 0xF0) == 0xB0
            and midi_bytes[1] in NAV_CCS):
        self._navigate(midi_bytes[1], midi_bytes[2])
        return
    ControlSurface.receive_midi(self, midi_bytes)      # <-- not optional
```

`ControlSurface.receive_midi` is what dispatches incoming messages to every
control element the framework built. Override it and return early for everything,
and you have intercepted the entire input stream — including messages other
components are relying on.

**The symptom is the trap.** Navigation works perfectly, because that is the
branch you wrote and tested. The macros quietly do nothing, because the messages
that used to reach them now stop at your `return`. Nothing is logged. Nothing
raises. The two features are unrelated in your head, so the last place you look is
the navigation code.

Related, and equally silent: `build_midi_map()` must call the superclass **first**,
because that is what installs the device component's parameter controls into the
map. Then, for each CC you want to handle yourself:

```python
Live.MidiMap.forward_midi_cc(script_handle, midi_map_handle, CHANNEL, cc)
```

Without that forwarding call, `receive_midi` never sees CC 17/18 at all — Live
routes mapped messages directly and only forwards what you explicitly ask for.
Symptom: the encoder does nothing, and your handler's log line never appears
because your handler never runs.

### 2. `set_parameter_controls` wants exactly 8

Some `_Framework` versions assert that exactly eight parameter controls are
passed to `set_parameter_controls()`. An earlier version of this script padded its
tuple to eight with CCs the device never transmits, purely to satisfy that assert.

**The current script sidesteps the whole question by never calling the setter.**
Fourteen simultaneous macros do not fit the mechanism anyway — parameter controls
address one bank of eight and page between banks — so the parameters are written
directly and `DeviceComponent` is kept only for the blue hand. If you do use the
setter, pad to eight.

The reason this is a real hazard and not a style question is the blast radius: the
call happens inside `__init__`, and an `AssertionError` in `__init__` means the
script never finishes constructing. You do not lose two macros; you lose the whole
control surface. In a build where assertions are stripped you might instead get an
index error later, or silently wrong behaviour.

When that earlier version padded, it used CC 118 and 119, because they are
undefined in the MIDI specification — 120–127 are channel mode messages and
would be a poor choice of filler. Neither number appears anywhere in the code
today; the padding went with the setter call.

The pad script solves the same problem the other way, by refusing to call the
setter at all unless every slot is assigned (`if None not in device_param_controls`).
Either is fine. Passing six is not.

### 3. `SliderElement` is absolute; relative needs `EncoderElement` plus a map mode

`_Framework` has two input element types for continuous controls:

| | Element | Carries | Right for |
|---|---|---|---|
| Absolute | `SliderElement(MIDI_CC_TYPE, ch, cc)` | a **value**, 0–127 | volume, cutoff, macros — continuous ranges nothing else moves |
| Relative | `EncoderElement(MIDI_CC_TYPE, ch, cc, map_mode)` | a **step**, ±n | the session box, and anything that is an integer index |

**The template only ever builds the absolute kind.** `_load_MIDI_map()` constructs
128 `SliderElement`s and nothing else, so a template-derived script has no path to
a relative control unless you add one. This is easy to miss because both types
"work" — an absolute element bound to something steppable produces plausible
motion right up until it desyncs.

Why the distinction matters for the session box specifically: the box position is
an integer index, the track count changes as you add tracks, and the arrows, the
mouse and other scripts all move it too. An absolute encoder maintains its own
counter in the controller's firmware, that counter desyncs from Live the moment
anything else moves the box, and the box then teleports the next time you touch the
knob. A relative CC carries a step, not a position, so there is nothing to desync.

Relative is a per-encoder setting in the M-Vave editor, on the device itself, not
in software — and on this unit **all sixteen assignments are now relative**, where
an earlier measurement had only two. That is worth internalising: the mode is not a
fixed property of a control, and a device reconfiguration can silently invalidate
an entire script's input handling. When the macros here stopped working, this was
why — absolute elements were reading 63/65 as "just under half", parking every
macro near 50%.

What the knob script does instead of using `EncoderElement`: it forwards every CC
it cares about (see gotcha 1) and decodes them all by hand. That avoids depending
on a `Live.MidiMap.MapMode` constant whose name varies by host version, and it is
the only option once you are writing parameters directly rather than through
element bindings.

```python
delta = value - CENTRE          # CENTRE = 64; 65 is +1, 63 is -1
```

**"Relative" is not one format.** This device sends 64-centred values (sometimes
called binary offset). `SpecialTransportComponent._tempo_encoder_value` in the pad
folder decodes a *different* relative convention — two's complement, where values
≥ 64 are negative — and `set_tempo_encoder()` asserts on
`Live.MidiMap.MapMode.relative_two_compliment`. Feeding 64-centred data to a
two's-complement decoder gives you an encoder that only moves one way. Measure
what your controller sends before choosing.

If you prefer to go through the framework rather than decode by hand, the
equivalent is an `EncoderElement` with the map mode matching your controller's
convention — `relative_binary_offset` for 64-centred data. That path is untried in
this project; the manual decode was chosen because it is three lines and needs no
assumption about which map modes this `_Framework` version supports.

### 4. Assertions inside MIDI callbacks

Not silent — fatal, and worth listing next to the silent ones because the cause is
the same habit. `SessionComponent.set_offsets()` asserts on a negative offset, so
`_bank()` clamps first:

```python
new_track = _clamp(track_offset + d_track, track_count - width)
```

An assertion raised from a MIDI callback takes the script down while you are
playing. Anywhere you compute an index from live input, clamp it at your end.

---

## Changing the mapping

Almost everything is in **`MVave_SMC_PAD/MIDI_Map.py`**. Encoder assignments are
the exception and live at the top of `MVave_SMC_KNOBS/MVave_SMC_KNOBS.py`.

The rules of that file: values are `0`–`127` or `-1` for unassigned; duplicate
assignments are permitted for buttons (the same `ButtonElement` object gets two
listeners and both fire); no floats; spaces, not tabs.

Current assignments:

| Constant | Value | Effect |
|---|---|---|
| `TSB_X`, `TSB_Y` | 4, 4 | session box is 4 tracks × 4 scenes |
| `CLIPNOTEMAP` | notes 1–16 | the 4×4 grid, reading order from top-left |
| `PLAY`, `STOP`, `REC` | 17, 18, 19 | transport |
| `TRACKLEFT`, `TRACKRIGHT` | 20, 21 | select previous / next track (via the mixer) |
| `SESSIONLEFT/RIGHT/UP/DOWN` | −1 | session box banking — handled by the encoders instead |
| `CLIP_*` | 5, 15, 14, 21, 24 | pad colours, see above |
| `PARAMCONTROL` | CC 1–8 | pad-script device params; inert, the DAW port sends no CCs |
| everything else | −1 | built and wired to `None` |

To move a control, change the number. To remove one, set it to `-1`. To resize the
grid, change `TSB_X`/`TSB_Y` **and** `CLIPNOTEMAP` together — but read
[Known rough edges](#known-rough-edges) first, because the current code assumes
`TSB_X == TSB_Y`.

### Re-enabling the modifier button

There is a complete, disabled implementation of a shift-style modifier in
`MVave_SMC_PAD.py`: `_setup_modifier()`, `_modifier_value()`, `_set_session_banking()`.
Held down, it swaps the two arrow buttons between the session component's two
banking roles:

```python
def _set_session_banking(self, scenes):
    forward = self._note_map[SESSIONRIGHT]
    back = self._note_map[SESSIONLEFT]
    if scenes:
        self._session.set_track_bank_buttons(None, None)
        self._session.set_scene_bank_buttons(forward, back)
    else:
        self._session.set_scene_bank_buttons(self._note_map[SESSIONDOWN],
                                             self._note_map[SESSIONUP])
        self._session.set_track_bank_buttons(forward, back)
```

In the `if scenes:` branch, passing `None` to unhook is the template's own idiom
for an unassigned button, so it is a supported value rather than a trick.

The `else:` branch **restores what the constructor set** rather than passing
`(None, None)`, and that distinction is the whole point: with `SESSIONDOWN`/`UP`
assigned, hardcoding `None` here unbound them permanently on the first modifier
press — they worked until you first held the modifier, then were dead for the
rest of the session. Commit `204acbe` fixed it. An earlier revision of this
document quoted the pre-fix body, so anyone re-enabling the modifier by copying
from here reinstated the bug.

It was the first working answer to "two arrows, three things to navigate", and it
cost the record button — nothing is shared with the transport component, because
sharing a button between a modifier and a transport role would mean guessing at
`_Framework` internals that could not be read from the machine this was written on.
The encoders made it unnecessary: two knobs give both axes at once, live, with no
mode to remember and nothing to look at. So it was disabled and `REC` went back to
note 19.

To bring it back, in `MIDI_Map.py`:

| Constant | Set to | Why |
|---|---|---|
| `MODIFIER` | `19` | the modifier note |
| `REC` | `-1` | otherwise the transport component also claims note 19 and every modifier press toggles record |
| `SESSIONLEFT`, `SESSIONRIGHT` | `20`, `21` | `_set_session_banking` reads *these*, not `TRACKLEFT/RIGHT`; leave them at `-1` and the modifier swaps `None` for `None` |
| `TRACKLEFT`, `TRACKRIGHT` | `-1` | otherwise notes 20/21 are bound twice and each press both selects a track and banks the box |

A third option was considered and not built: pressing **both arrows at once** to
toggle the mode. It costs no button, but the mode would be invisible on the device
and the chord has to fire on release, so every ordinary press pays a little latency
for a rare operation.

---

## Adapting this to a different controller

The parts of this project that generalise, roughly in the order you would do them.

**1. Measure the controller before you write anything.** `tools/mvave_probe.py`
talks straight to MIDI ports, needs no Remote Script and never touches Live. What
you need to know: which port sends what, the note or CC number of every control,
whether pressing sends note-off or note-on-velocity-0, whether the encoders are
absolute or relative and in which convention, and — if the device has LEDs —
whether the host can set them and what the values mean. See
[PROBE.md](PROBE.md).

Do this even if the device has a published MIDI implementation, and do the
foundational test first. This project rested entirely on "can the pads be coloured
by incoming MIDI", and that went unverified while plans were built on top of it; a
ten-minute test answered it. Related trap: *"all pads lit"* is not *"the host can
set colours"* — they may be lighting in a colour already configured on the device.
Distinguishing those needs a velocity sweep.

**2. Decide how many scripts you need.** One per input port you must read. If
everything arrives on one port, write one script and skip the cross-script
machinery entirely. If you do split, remember that only one script may own the
highlighted session box.

**3. Start from the constants, in all three places.** `MVave_SMC_PAD/MIDI_Map.py`
and `MVave_SMC_STEPSEQ/MIDI_Map.py` are files; the encoder script's live at the
top of `MVave_SMC_KNOBS.py` (`CC_TRACK`, `CC_SCENE`, `MACRO_BY_CC`, `CENTRE`,
`ENCODER_MODE`, `STEPS_PER_SWEEP`) because there are only a handful.

**The two map files spell "unassigned" differently, and it matters.** In
`MVave_SMC_PAD/MIDI_Map.py` it is `-1`: that map is a 129-element list whose
last entry is `None`, so an unassigned control costs nothing but a constructed
object. In `MVave_SMC_STEPSEQ/MIDI_Map.py` it is `None`, because those constants
go straight to `Live.MidiMap` from an unguarded `build_midi_map` — a negative
there is forwarded as a MIDI note number. Use the value the file you are editing
uses, and fill in what you do have. Resize the grid via `TSB_X`/`TSB_Y` and
`CLIPNOTEMAP`.

**4. Deal with LEDs on their own terms.** Note that there are two write paths,
not one: the launcher goes through the element layer (`send_value` on a
`ButtonElement`), while the sequencer builds its own status bytes in `_send_led`
and `_paint_buttons` and bypasses it entirely. The mechanism here — framework value ⇒
note-on velocity ⇒ palette index — is specific to controllers that light from
note-on. Devices that want SysEx, or a note-off to extinguish, need different
handling in the element layer. This one ignores `0x80` note-offs entirely and
clears with note-on velocity 0, which happens to be exactly what `send_value()`
emits, so the template's LED path worked unmodified. Check that before assuming.

**5. Keep the version-tolerance habits.** `getattr`-guarded setters, log-once
latches, clamping before calls that assert. The framework varies across Live
versions and you will be developing against exactly one of them.

**6. Expect the loop to be slow.** Restart Live for every change; `Log.txt` is your
only instrument. Write log lines that answer a specific diagnostic question — the
knob script's three lines each distinguish a different failure ("loaded at all",
"the blue hand ever got a target", "MIDI is arriving") — and latch them so they
print once.

---

## Known rough edges

Things a contributor should know before being surprised by them. Several are
inherited from the template and left alone deliberately.

**`_do_uncombine()` never runs its body.**

```python
if (self in MVave_SMC_PAD._active_instances) and MVave_SMC_PAD._active_instances.remove(self):
```

`list.remove()` returns `None`, so the condition is always falsy and
`self._session.unlink()` and `_combine_active_instances()` are never called. The
`remove()` itself *does* happen, as a side effect of evaluating the condition, so
`_active_instances` is still cleaned up correctly — which is why the knob script's
lookup behaves. Inherited from the template; fixing it would change combination-mode
teardown behaviour that nothing here exercises.

**`TSB_X` and `TSB_Y` are swapped in two places.** In `_setup_session_control()`:

```python
self._scene_launch_buttons = [self._note_map[SCENELAUNCH[index]] for index in range(TSB_X)]
self._track_stop_buttons  = [self._note_map[TRACKSTOP[index]] for index in range(TSB_Y)]
```

Scene launch buttons are one per *scene* and should be sized by `TSB_Y` (they are
later indexed with `scene_index`, which runs to `TSB_Y`); track stop buttons are one
per *track* and should be sized by `TSB_X`. With `TSB_X == TSB_Y == 4` and every
constant `-1` this is harmless. Set a non-square grid and you get an `IndexError`
during `__init__`, which kills the script. Fix both lines before resizing to a
rectangle.

**Unused locals and dead template code.** `is_momentary = True` is assigned and
never read in four methods. `disconnect()` sets `self._shift_button = None`, an
attribute never created in `__init__`. `SpecialTransportComponent.py` and
`SpecialViewControllerComponent.py` carry large commented-out shift-button
implementations. All inherited; left in place because they document what the
template offers and re-enabling them is uncommenting.

**Line endings differ between the two packages.** `MVave_SMC_PAD/` is CRLF
throughout (it came off a Windows machine with the template);
`MVave_SMC_KNOBS/`, `MVave_SMC_STEPSEQ/` and `tools/*.py` are LF, while
`tools/run_probe.bat` is CRLF — deliberately, because `cmd.exe` can fail to
resolve `goto :label` in a batch file saved with bare LF endings. `.gitattributes` sets `* -text` so git
stores both exactly as they are rather than producing a whole-file diff on every
checkout. Python reads both without complaint. **This bites shell tooling:** `sed`
patterns anchored on `$` silently no-op against CRLF lines. If a scripted edit
appears to do nothing, check the line endings first.

**The `PARAMCONTROL` CCs in the pad script are inert.** CC 1–8 on the DAW port,
which sends no CCs. Harmless, and see
[the walkthrough](#file-by-file-walkthrough) for why it is left alone.

**`scene.set_triggered_value(2)`** is set for every scene launch button, a template
value that on this controller's palette would be pastel orange. `SCENELAUNCH` is
all `-1`, so no scene launch buttons exist and the value is never sent.

### Verified on hardware — Live 11.3.43, 2026-09-03

Read out of `Log.txt` after a session with all three scripts loaded and a MIDI
clip selected in sequencer mode. Each of these was previously an assumption the
code guarded against; the guards stayed silent, which is what settles them. The
diagnostics quoted are the exact strings to grep for if a future Live disagrees.

- **The cross-script lookup works.** `_bank()` ran — the log carries
  `first nav CC` and no `cannot import MVave_SMC_PAD` or `is not loaded`. This
  was the one part of the design with no offline test.
- **`DeviceComponent` exposes `device` as a *method*.** `_current_device()` ran
  on the first macro turn and never logged
  `DeviceComponent exposes no device getter`, so the write-time resolution is
  live rather than falling back to the cached target.
- **`SessionComponent`'s offsets and `width()`/`height()` are readable**, via the
  method spelling — neither `could not read the session offsets` nor
  `could not read the session box size` has ever appeared.
- **`Clip` exposes `add_loop_start_listener` / `add_loop_end_listener`.** A clip
  was bound and `clip has no add_*_listener()` did not fire, so a mouse drag on
  the loop brace does redraw the grid.
- **All five `ClipSlotComponent` colour setters exist.**
  `ClipSlotComponent has no ...` has never appeared in any session.
- **`get_notes_extended`'s window is half-open**, `[t, t + STEP)`. Tested by
  hand: with a note on step 5, pressing the empty step 4 adds a note there and
  leaves step 5 alone. Had the window been closed, pad 4 would have deleted its
  neighbour instead — the one assumption in `tools/stepseq_selftest.py`'s fakes
  that the "a lit step is a step pressing clears" guarantee rests on.
- **No guarded callback has ever raised.** `exception in` appears nowhere in any
  session. (The sequencer has also never logged an `unmapped:` message, but that
  proves nothing about the device: `build_midi_map` forwards exactly the sets
  `_dispatch` claims, so under Live's forward-only routing the latch has nothing
  it *can* report. Use `tools/mvave_probe.py --listen` for "what is this thing
  actually sending".)

### Not verified

- **Whether `SessionComponent` takes its track list from its mixer** in this
  `_Framework` version, which decides whether the encoder's clamp ceiling matches
  the box's real range. The log cannot show this; it would present as the box
  refusing to bank onto the return tracks. See
  [the session handoff section](#how-the-knob-script-reaches-the-pad-scripts-session-box).
- **Whether a deleted LOM object raises on every attribute access.** The
  deleted-clip guards and the self-test's `FakeClip.__getattribute__` both assume
  it; no session has yet deleted a clip while the sequencer held it.
- Device-side questions (the `.spc` flag byte, what the VELOCITY 1–4 settings do)
  are recorded in [HARDWARE.md](HARDWARE.md) and [FINDINGS.md](FINDINGS.md);
  neither affects the scripts.
