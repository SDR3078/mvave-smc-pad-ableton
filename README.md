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
| Knob bank 2, encoders 1–6 | Macros 1–6 of the **selected** device — Live's "blue hand" |
| Knob bank 2, encoders 7–8 | Move the session box across tracks and through scenes |
| Knob bank 1 | Unassigned, left free for Live's own MIDI mapping |

Pad colours: green playing · orange loaded · red-pink recording · blue queued ·
off empty.

### And a step sequencer

`SMC_StepSeq/` is a separate script on a separate pad preset. The 16 pads become
16 steps of one drum lane in the selected MIDI clip, with a playhead that chases
Live's playback; a second view shows four lanes by four steps, for reading a
kick/clap/hat/open-hat groove at a glance.

The clip is the only state it keeps, so Ctrl+Z undoes a step, saving the set
saves the pattern, and a note drawn with the mouse lights up on the pads.

**Written and self-tested, not yet run on hardware.** Several values in
`SMC_StepSeq/consts.py` are still guesses and are marked as such.
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
> pad bank that was configured by hand in the M-Vave editor, and two encoders
> must be switched to relative mode. A factory unit sends different numbers and
> will appear to do nothing until you either match the configuration or edit
> `MIDI_Map.py`. `docs/INSTALL.md` covers both routes.

## Layout

```
├── MVave_SMC_PAD/      pads, transport, LED feedback   (copy this into Live)
├── MVave_SMC_KNOBS/    encoders: navigation + macros   (and this)
├── SMC_StepSeq/        step sequencer on a second pad preset  (and this, optionally)
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
│   └── Ableton.spc     a real config dump — the binary decoded in HARDWARE.md
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
sequencer is written and self-tested but has **never run in Live** — see
[STEPSEQ.md](docs/STEPSEQ.md) section 5 for the hardware questions it is still
carrying. Known gaps, documented rather than hidden:

- **Knob bank 1 is unassigned.** Eight free absolute encoders. Candidates: eight
  track volumes via `MixerComponent`, all eight macros via a second
  `DeviceComponent`, or leaving it for Live's own MIDI mapping.
- **Two latent bugs inherited from the template** — a `_do_uncombine()` guard
  that can never fire because `list.remove()` returns `None`, and `TSB_X`/`TSB_Y`
  swapped in two places. Harmless with a square grid and the current mapping;
  both would bite anyone adapting this. See [DEVELOPMENT.md](docs/DEVELOPMENT.md).
- **`PARAMCONTROL` in the pad script maps CC 1–8 on a port that sends no CCs.**
  Inert, but it means both scripts build a device component.
- **macOS is untested.** This has only ever run against Windows.
- Several `_Framework` behaviours could not be verified outside Live and are
  marked as such in the code and docs.

## Attribution

`MVave_SMC_PAD/` descends from **Hanz Petrov's "Introduction to the Framework
Classes"** template, the long-standing starting point for custom Live Remote
Scripts. The session, mixer, transport, zooming and view components are
substantially his; the clip-state colours, the modifier button and every value in
`MIDI_Map.py` are not. `MVave_SMC_KNOBS/`, `SMC_StepSeq/`, `tools/` and `docs/`
are original.
[DEVELOPMENT.md](docs/DEVELOPMENT.md) carries a file-by-file provenance table.

Not affiliated with or endorsed by Ableton or M-Vave/Cuvave. Product names belong
to their owners.

## Licence

**Not yet chosen.** Because `MVave_SMC_PAD/` derives from a publicly published
tutorial template, its licensing position is inherited rather than free to pick,
and that should be settled before this is shared widely. `MVave_SMC_KNOBS/`,
`SMC_StepSeq/`, `tools/` and `docs/` are original work.
