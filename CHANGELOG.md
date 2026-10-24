# Changelog

## 2026-10-15 - Current working release

The tested probability/activity build is now the main source baseline.

### Added

- Native note probability: 25%, 50%, 75% and 100% (default). Hold active steps
  and tap arrows repeatedly; note IDs and unrelated data are preserved.
- Probability LEDs: 25% = 7, 50% = 21, 75% = 9, 100% = 64. Swapped the middle
  colours following the user's hardware comparison.
- Cyan pattern-activity pulses in held Pause/Stop and Record views. Restore
  state colours between pulses; unprogrammed drums stay steady, empty slots dark.
- Activity uses cached notes and the existing playhead callback, with no extra
  timers or playback writes. Muted/probability-skipped hits still pulse;
  disabled notes do not. It indicates programming, not actual output detection.
- Probability/activity regression tests and probe launcher fallback to bundled
  Python when a standalone installation is absent.

### Consolidated from recent local builds

- Step sequencing, multi-step parameter locks and eight-knob per-drum macros.
- On-the-fly mutes, automatic rack selection, pinned tracks, drum banks and paging.
- Live base edits preserving absolute step-lock values.
- Native real-time Session macro recording with Record + Play, automatic arming,
  previous arm-state restoration and idle-time automation resume.

These features span recent local sessions. This entry records their consolidation,
rather than assigning an unsupported first-implementation date to each.

### Documentation and verification

- Updated the current guides, release revision and installation information.
- Refreshed the PDF around the five performance essentials, probability,
  activity, stock-kit macro setup, recovery and current limits.
- Removed misleading label cards beneath the bass screenshot. Sting 2 is the
  smiley-face device before Analog.
- Stored guide screenshots under assets/guide for reproducible PDF builds.
- 185 offline tests pass. The user confirmed hardware jamming, probability and
  held-button indicators, with no glitches observed in those sessions.

### Known limits

- Pattern activity includes muted/probability-skipped hits, not actual output.
- Curve/lock metadata is session-only. Envelope adoption and held-step edits
  can reduce continuous curves to step resolution.
- Recording can replace earlier automation. External envelope/loop changes and
  undo can stale lock metadata. No hardware clear-lock command is implemented.
- Only the first Drum Rack on a track is supported.

## 2026-10-14 - Archived experiments

- Rolled back scale snapping and record latch after unstable playback.
- Archived the custom free-recorder/input-block experiment after controller
  input became unresponsive. It is excluded from the current native-recording path.
- Preserved earlier working scripts under workspace backups.

## Earlier upstream baseline

Launcher, knob integration, sequencing and the measured MIDI reference remain
documented in README.md, docs/DEVELOPMENT.md and docs/HARDWARE.md.
STEPSEQ-BRIEF.md and workspace backups preserve historical design information.
