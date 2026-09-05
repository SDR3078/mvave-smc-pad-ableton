# M-Vave SMC-PAD for Ableton Live

Ableton Live Remote Scripts that turn an **M-Vave SMC-PAD** into a Launchpad-style
clip launcher — pads fire clips, pad LEDs show clip state, and the encoders drive
the session box and the selected device's macros — and, on a second pad preset,
into a Push-style **step sequencer** that edits the selected MIDI clip.

Also here: a **complete measured MIDI reference** for the SMC-PAD, and the tool
used to measure it. The manufacturer publishes no MIDI implementation — both its
manuals are marketing copy — so as far as we know that reference does not exist
anywhere else.

---

## What you get

| Control | Does |
|---|---|
| 16 pads | Launch clips in Session view, coloured by clip state |
| Transport buttons | Play, stop, record |
| `<` `>` | Select previous / next track |
| Knob bank 1, all 8 encoders | Macros **1–8** of the **selected** device — Live's "blue hand" |
| Knob bank 2, encoders 3–8 | Macros **9–14** of the same device |
| Knob bank 2, encoders 1–2 | Move the session box across tracks and through scenes |

On the step-sequencer preset those bottom two encoders carry macros **15–16**
instead, since a sequencer has no session box to move.

Pad colours: green playing · orange loaded · red-pink recording · blue queued ·
off empty.

### And a step sequencer

`MVave_SMC_STEPSEQ/` is a separate script on a separate pad preset. The 16 pads become
16 steps of one drum lane in the selected MIDI clip, with a playhead that chases
Live's playback; a second view shows four lanes by four steps, for reading a
kick/clap/hat/open-hat groove at a glance.

The clip is the only state it keeps, so Ctrl+Z undoes a step, saving the set
saves the pattern, and a note drawn with the mouse lights up on the pads.

**Running on real hardware.** Every value in `MVave_SMC_STEPSEQ/MIDI_Map.py` is measured.
The 16 pads follow the playhead, so a 16, 32 or 64-step loop needs no paging.
**[docs/STEPSEQ.md](docs/STEPSEQ.md)** has the design, the install, and the list
of what still needs measuring.

## Why this exists

The SMC-PAD's factory DAW mode speaks Mackie Control. That gives you LED feedback
but **no clip launching** — MCU is a mixer and transport protocol with no concept
of a clip grid, and the factory layout spends all 16 pads on select/arm/solo/mute.
Live's stock `MackieControl` script will never fire a clip.

These scripts take over that Control Surface slot instead. The firmware still
sends pad notes and still lights pads from incoming MIDI; nothing requires Live
to interpret those notes as mute and solo. Fully reversible — put
`Mackie Control` back in the slot and you are where you started.

## Install

Copy `MVave_SMC_PAD/` and `MVave_SMC_KNOBS/` into Live's Remote Scripts
directory, restart Live, and configure two Control Surface slots. Full steps,
port assignment, verification and troubleshooting in
**[docs/INSTALL.md](docs/INSTALL.md)**. The step sequencer is a third, optional
script with its own setup in **[docs/STEPSEQ.md](docs/STEPSEQ.md)**.

> **Read the prerequisites first.** The note numbers in `MIDI_Map.py` come from a
> pad bank that was configured by hand in the M-Vave editor, and all sixteen encoder assignments
> must be switched to relative mode. A factory unit sends different numbers and
> will appear to do nothing until you either match the configuration or edit
> `MIDI_Map.py`. `docs/INSTALL.md` covers both routes.

## Layout

```
├── MVave_SMC_PAD/      pads, transport, LED feedback   (copy this into Live)
├── MVave_SMC_KNOBS/    encoders: navigation + macros   (and this)
├── MVave_SMC_STEPSEQ/        step sequencer on a second pad preset  (and this, optionally)
├── docs/
│   ├── INSTALL.md      setup, verification, troubleshooting
│   ├── HARDWARE.md     the measured MIDI reference — ports, notes, LED palette,
│   │                   encoder map, and the decoded .spc config format
│   ├── DEVELOPMENT.md  architecture, _Framework gotchas, porting to another controller
│   ├── PROBE.md        the measurement tool, mode by mode
│   ├── FINDINGS.md     how the device was reverse-engineered, and what went wrong
│   ├── STEPSEQ.md      the step sequencer: design, install, what is still unmeasured
│   └── STEPSEQ-BRIEF.md  the original build brief, kept verbatim
├── reference/
│   ├── launchpad.spc   the clip-launcher preset, as exported by the editor
│   └── sequencer.spc   the step-sequencer preset — 41 bytes differ
│                       (both are this project's own pad and encoder
│                        assignments: byte-scanned, they contain no vendor
│                        text, branding or serial — pure configuration data)
└── tools/
    ├── mvave_probe.py       the MIDI probe
    ├── run_probe.bat        Windows launcher; builds its own virtualenv
    ├── requirements-midi.txt
    └── stepseq_selftest.py  runs the sequencer against a fake Live, no DAW needed
```

## The probe

`tools/mvave_probe.py` talks straight to the controller's MIDI ports. It needs no
Remote Script and never touches Ableton. It can list ports, log everything the
device sends, light pads, walk the LED palette one velocity at a time, and map
every encoder to its CC with a checkpoint at each knob.

It is included because this device is undocumented and every number in
[HARDWARE.md](docs/HARDWARE.md) had to be measured. If you own a different
controller it adapts easily — see [PROBE.md](docs/PROBE.md).

## Status

The clip launcher and the encoder script are working and in use. The step
sequencer runs too, on its own port-3 pad preset. Known gaps, documented rather
than hidden:

- **Both knob banks are now claimed**, so nothing is left for Live's own MIDI
  mapping on that port. Bank 1 uses CC 1–8, two of which (CC 1, CC 7) are the mod
  wheel and channel volume — harmless while the port belongs to a Control Surface,
  since Live disables Remote on it, but a hazard if you ever hand the port back.
- **Two latent bugs inherited from the template** — a `_do_uncombine()` guard
  that can never fire because `list.remove()` returns `None`, and `TSB_X`/`TSB_Y`
  swapped in two places. Harmless with a square grid and the current mapping;
  both would bite anyone adapting this. See [DEVELOPMENT.md](docs/DEVELOPMENT.md).
- **`PARAMCONTROL` in the pad script maps CC 1–8 on a port that sends no CCs.**
  Inert, but it means both scripts build a device component.
- **The two pad scripts share `MIDIOUT3` but not note numbers.** The launcher
  writes only notes 1–21 and the sequencer only 101–121, and lighting a note the
  active preset does not use does nothing (measured — see
  `MVave_SMC_STEPSEQ/MIDI_Map.py`). So both can stay loaded and the preset switch
  is the mode switch. The one resource they do share is the device's MIDI input
  buffer; neither sends in bulk, so this has not been a problem in practice.
- **Every sequencer step is written at velocity 127.** The pads that light are
  the pads that cannot sense velocity, and no encoder is free to carry a paint-
  velocity knob. Three ways out in [STEPSEQ.md](docs/STEPSEQ.md) section 9.
- **macOS is untested.** This has only ever run against Windows.
- Several `_Framework` behaviours could not be verified outside Live and are
  marked as such in the code and docs.

## Attribution

`MVave_SMC_PAD/` descends from **Hanz Petrov's "Introduction to the Framework
Classes"** template, the long-standing starting point for custom Live Remote
Scripts. Its six `Special*Component.py` files — channel strip, mixer, session,
transport, view controller and zooming — are template code of **mixed and partly
unverified origin**: substantially Petrov's, but one is marked a partial
decompile of Ableton's own scripts and another credits an "OpenLabs" module for
its undo/redo block. See the Licence section below and the file-by-file table in
[DEVELOPMENT.md](docs/DEVELOPMENT.md). The clip-state colours, the modifier
button and every value in `MIDI_Map.py` are this project's. `MVave_SMC_KNOBS/`, `MVave_SMC_STEPSEQ/`, `tools/` and `docs/`
are original.
[DEVELOPMENT.md](docs/DEVELOPMENT.md) carries a file-by-file provenance table.

Not affiliated with or endorsed by Ableton, M-Vave/Cuvave, Novation or Focusrite.
Product names — including Live, Push, Launchpad and Mackie Control — belong to
their owners and are used here descriptively.

## Licence

**Not yet chosen, and it cannot be until the questions below are settled.**
`MVave_SMC_KNOBS/`, `MVave_SMC_STEPSEQ/`, `tools/` and `docs/` are original work.
`MVave_SMC_PAD/` is not, and what it inherits comes from **three** upstreams, not
one:

- **Hanz Petrov's "Introduction to the Framework Classes"** — the structural
  skeleton, the 128-element MIDI map and the `Special*` components. Published on
  [remotescripts.blogspot.com](http://remotescripts.blogspot.com/2010/03/introduction-to-framework-classes.html)
  from 12 March 2010, in four parts, with the example scripts on its
  [Support Files](http://remotescripts.blogspot.com/p/support-files.html) page.
  **Checked 2026-09-05: neither page states any licence, copyright notice or
  terms of use.** The material is presented as educational, with no permission
  granted or withheld in writing.
- **Ableton's own shipped scripts.** `SpecialViewControllerComponent.py:5` carries
  `# Partial --== Decompile ==-- with fixes`, which asserts on its face that the
  file was recovered from compiled bytecode rather than typed from a tutorial.
  The likely route is the template itself: Petrov's Support Files page also
  distributes **decompiled Live 8.2.2 `_Framework`, APC40 and APC20 scripts**, so
  this appears to arrive with the lineage rather than having been decompiled
  here. That identifies the path, not the permission.
- **An "OpenLabs" module.** `SpecialTransportComponent.py` credits it in seven
  places for the undo/redo block. Searched 2026-09-05 without finding a
  an identifiable OpenLabs release: `SpecialTransportComponent.py` is described in
  the community as a re-usable module that circulated with APC40 scripts, which
  Petrov's blog also distributes, so it plausibly arrived by the same route —
  but that is inference, and the origin remains unestablished. The block is
  unwired (`UNDO = -1`, `REDO = -1`), so removing it would cost nothing and
  would close this question outright.

There is no LICENSE, COPYING or NOTICE file in this repository. The upstream that
*can* be identified states no terms of its own, so what is inherited is an
absence rather than a permission — which is worth knowing before choosing a
licence for the parts that are original.

Two decisions remain: whether `SpecialViewControllerComponent.py`, marked a
partial decompile, can ship at all; and whether the unwired OpenLabs undo/redo
block stays or goes. Removing the block is free and settles one of them.
