# Gavin's sequencer contribution

Prepared against SDR3078/mvave-smc-pad-ableton `db15547` on 25 October 2026.
Original project by Sander (SDR3078); additions contributed by Gavin (gavincastle).
Original attribution and licence/provenance notes are retained.

## Changes

- Hold one or more active steps and turn a macro to write parameter locks.
- Select drums and control eight Instrument Rack macros per drum.
- Mute drums, pin Drum Rack tracks, navigate drum banks and page patterns.
- Record macro gestures through Live's native Session recorder, with automatic
  arming and restoration of previous arm states.
- Set native note probability to 25%, 50%, 75% or 100%, with LED feedback.
- Display cached programmed-hit activity in drum selection and mute views.

The contribution includes the current working source, controls guide and offline
regression tests. Archived scale snapping, record-latch and custom-recorder
experiments are excluded. The original sequencer design guide is retained as
`STEPSEQ-ORIGINAL.md` for reference; current controls are in `STEPSEQ.md`.

## Validation

On 25 October 2026, Python unittest discovery ran all 185 tests successfully:

```text
python -m unittest discover -s tools -p "*selftest.py"
Ran 185 tests
OK
```

These tests use a fake Live API; they do not establish real Live envelope,
undo, MIDI routing or hardware behaviour. No new DAW or hardware validation was
performed during this contribution preparation. The existing local notes record
Gavin's successful jamming, probability, drum indicators and native recording on
Windows with Live 12.4.6 Suite. macOS remains untested.

## Known limitations for review

- Lock/curve metadata is session-only. External envelope edits, undo and loop
  changes can stale it.
- Envelope adoption and held-step edits can reduce curves to step resolution.
- Recording can replace earlier automation; use separate clips for experiments.
- No controller clear-lock command is implemented.
- Only the first Drum Rack on a track is supported.
- Activity LEDs show programmed notes, including muted/probability-skipped hits,
  rather than detected audio output. Disabled notes do not pulse.

Install the complete `MVave_SMC_STEPSEQ` and `MVave_SMC_KNOBS` folders together.
Keep a backup of existing installed scripts before testing this contribution.
