# Current local build - 2026-10-15

The main source contains the tested probability and drum-activity features.
This is the working baseline; earlier experiments remain in workspace backups.

Read [STEPSEQ.md](STEPSEQ.md), the [changelog](../CHANGELOG.md), and the
[hands-on reference](HANDS-ON.md).

The five essentials are step sequencing, parameter locks, on-the-fly mutes,
native real-time macro recording and eight-knob per-drum Instrument Rack macros.
Hold steps + arrows for chance: 25/50/75/100%, colours 7/21/9/64. Hold Record
or Pause/Stop for drum selection/mutes with cyan pattern-activity pulses.

Activity follows the bound clip's programmed notes, including muted drums and
probability-skipped hits. It does not detect actual output. Disabled notes do
not pulse. No additional activity timers or playback clip writes are introduced.

Native recording uses Live's Session recorder. Record + Play toggles capture;
automatic arming restores previous track states afterward. Free curves resume
after about 0.3 seconds of knob inactivity. Curve/lock metadata is session-only.
Live base editing is supported for step locks. Continuous curves can be reduced
to step resolution by envelope adoption or held-step edits; use separate clips.
External automation edits, undo and loop changes can stale the lock snapshot.

The user confirmed successful native recording, probability, drum indicators
and smooth controller jamming. 185 API-stub tests pass. Scale snapping, record
latch and the old custom recorder remain archived, not active.
