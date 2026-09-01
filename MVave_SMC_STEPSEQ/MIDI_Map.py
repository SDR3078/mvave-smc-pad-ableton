# Hardware and layout constants for the SMC-PAD step sequencer.
#
# Everything the script knows about the controller lives in this file.
# MVave_SMC_STEPSEQ.py contains no note numbers, no CC numbers and no colour values,
# so answering a Phase 0 question is an edit here and nowhere else.
#
# Two kinds of value live here and they are NOT equally trustworthy:
#
#   MEASURED    observed on real hardware. docs/HARDWARE.md carries the method
#               and the dates; this file only restates what the sequencer needs.
#   UNVERIFIED  the design's intent, not yet confirmed on the device. Each one
#               is an open Phase 0 question in docs/STEPSEQ.md.
#
# The distinction is kept in the comments on purpose. Treating an inference as a
# measurement is how this project lost time before -- docs/FINDINGS.md, "Seven
# wrong turns", is four separate instances of exactly that.


# ---------------------------------------------------------------- what arrives

# MIDI channel the sequencer preset transmits on, 0-indexed: 0 = channel 1.
#
# MEASURED 2026-08-31 on the purpose-built preset. Channel 16 was the original
# plan and it was never reachable: on this device the channel is not what
# separates the two scripts -- the NOTE RANGE is.
PAD_CHANNEL = 0

# The 16 pads, in READING order: index 0 is top-left, index 15 bottom-right.
#
# MEASURED 2026-08-31: notes 101-116 on port 3, channel 1, fixed velocity 127.
#
# Why this range and not something adjacent to the clip launcher's 1-16: both
# presets land on port 3 and both use channel 1, so the note range is the ONLY
# thing distinguishing them. 101-116 is far enough from 1-21 that no editor slip
# can make them overlap.
#
# Getting here required a port-3 bank. In the .spc that is the flag byte -- 0x04
# routes a bank to port 3, 0x00 routes it to ports 1 and 2 (HARDWARE.md 5.6).
# Only port-3 banks light their pads, and only they are fixed-velocity; the
# ports-1/2 banks are velocity-sensitive but cannot be lit at all. That trade is
# a property of the hardware, not a configuration choice.
PAD_NOTES = tuple(range(101, 117))

PAD_NOTES_B = ()

# The five buttons above the grid.
#
# MEASURED 2026-08-02: notes 17-21 on MIDI channel 1, port 3, with the same
# press/release encoding as the pads (HARDWARE.md 2.4). They are a separate
# section of the .spc from the pad banks, so they are very likely global rather
# than per-preset -- hence channel 1 here while the pads are on channel 16.
#
# Physically: 17 play, 18 stop, 19 record, 20 '<', 21 '>'.
BUTTON_CHANNEL = 0
BUTTON_IS_CC = False        # set True if you manage to reassign them to CCs

# MEASURED 2026-08-31 on the sequencer preset. The buttons are PER-PRESET, not
# global -- an earlier revision of this file claimed the opposite, from reading
# the .spc's five button records as the whole device's when they are in fact one
# preset's. A .spc holds ONE preset: 5 buttons, 2 knob banks of 8 encoders, and
# 8 PAD BANKS of 16 pads. The PAD BANK button moves between those 8; Shift+Pad
# moves between presets, which is a different file.
#
# That is what makes the two scripts separable with no code: this preset offsets
# everything by 100 from the clip launcher's 1-16 / 17-21, so neither script ever
# sees the other's traffic, and LED writes only land when they match the active
# preset's map.
#
# BTN_SHIFT is the RECORD button, not the physical key labelled SHIFT -- that one
# is firmware-local and transmits nothing at all (HARDWARE.md 6.1).
BTN_PLAY = 117              # play/stop toggle -- see below for why the script owns it
BTN_VIEW = 118              # focus <-> overview
BTN_SHIFT = 119             # momentary modifier: hold for the lane picker
BTN_LEFT = 120              # previous step page; +SHIFT lane bank down
BTN_RIGHT = 121             # next step page;     +SHIFT lane bank up

# Why the script implements transport at all: claiming a port with a Control
# Surface disables Track/Sync/Remote on it (HARDWARE.md 1.4), so any button the
# script does not handle is simply a dead button while this preset is live.
# Set BTN_PLAY to None if you would rather have it dead than owned.

# The eight encoders.
#
# UNVERIFIED, and the least likely part of this file to survive contact with the
# hardware. Two measured facts work against it:
#
#   1. The encoders appear on ports 1 and 2 and NEVER on port 3, while the pads
#      appear only on port 3 (HARDWARE.md 1.1). A Remote Script gets exactly one
#      input port, so unless the sequencer preset moves one of them, these CCs
#      cannot reach the same script as the pads. See the class-level
#      _active_instances hook in MVave_SMC_STEPSEQ.py for the way out.
#   2. Encoder assignments are not per pad-preset. The .spc holds exactly 16
#      encoder records -- 2 banks of 8 (HARDWARE.md 5.2) -- so putting the
#      sequencer's CCs on the encoders spends one of the two KNOB BANK banks
#      globally, and both are already accounted for: bank 2 drives the device
#      macros, bank 1 is deliberately left free for Live's own MIDI mapping.
#
# The script works without any of this. Only paint velocity and pattern length
# are unreachable, and both have mouse equivalents in Live.
KNOB_CHANNEL = 15
CC_LANE = 20                # focus: scroll lane. overview: scroll lane window.
CC_VELOCITY = 21            # paint velocity, 1-127
CC_LENGTH = 22              # pattern length in steps, 1-32
CC_SPARE = 23               # reserved: nudge/swing later. Read and ignored.

# How a relative encoder encodes one click.
#
#   'centre'  63 = one step back, 64 = nothing, 65 = one step forward.
#   'twos'    127 = one step back, 1 = one step forward.
#
# MEASURED 2026-08-03: the two encoders switched to relative in the M-Vave
# editor use 'centre' (HARDWARE.md 4.4). The build brief assumed 'twos'. They
# are mutually ambiguous -- under 'twos' a value of 63 means +63, under 'centre'
# it means -1 -- so this has to be a setting rather than something detected.
KNOB_MODE = 'centre'

# Set True to log every MIDI byte the script receives. Phase 0 only: a single
# encoder turn produces hundreds of lines and Log.txt is not the place for them.
# Messages the script does NOT recognise are always logged once per signature,
# regardless of this flag, which is what actually answers "what is this thing
# sending?" without the firehose.
LOG_MIDI = False


# ------------------------------------------------------------------- what goes

# LEDs are driven by sending note-on back to the device. Two measured facts
# shape every line of the render path:
#
#   - Velocity is a PALETTE INDEX, not a brightness (HARDWARE.md 3.1). It is
#     absolute: it overrides whatever colour the pad is configured with in the
#     editor. There is no dim variant of a colour, which is why "step off" below
#     is off rather than dim.
#   - Turning a pad off needs note-on velocity 0. A real note-off (0x80) is
#     ignored entirely, silently (HARDWARE.md 3.3).
LED_CHANNEL = PAD_CHANNEL    # MEASURED 2026-08-31: the LEDs answer on the same
                             # channel the pads transmit on.
LED_NOTES = PAD_NOTES        # MEASURED 2026-08-31: the LEDs follow the pad note
                             # map. Lighting 1-16 on a preset whose pads send
                             # 101-116 does nothing; lighting 101-116 works.
                             #
                             # This was briefly recorded as a fixed 1-16 map,
                             # from a sweep taken in a state where the pads also
                             # sent 1-16 -- a confound that fitted both theories
                             # and discriminated neither. Re-measured on a preset
                             # with a different note range, which separates them.
                             #
                             # Only port-3 banks light at all (flag 0x04). The
                             # ports-1/2 banks are velocity-sensitive and cannot
                             # be lit on any port, note range or channel tried.

# The palette, sampled 2026-08-02 (HARDWARE.md 3.2). Usable, well-separated
# anchors -- and this really is the whole usable range, because everything from
# 64 to 112 is one flat blue:
#
#     0 off        5 green      6 turquoise   14 red-pink
#    15 orange    20 turquoise  21 blue       24 light purple    40 white
#
# There is no saturated red on this device. 14 is as close as it gets, and 14
# and 15 are adjacent in the hue cycle, so red-pink and orange are the one pair
# here that can be hard to tell apart.
COLOR_STEP_ON = 20          # teal: a step that holds a note
COLOR_STEP_OFF = 0          # off: a step outside the loop, or an unlit empty one
COLOR_PLAYHEAD = 15         # amber: the step the clip is playing right now
COLOR_PLAYHEAD_ON = 40      # white: the playhead sitting on an active step

# Optional markers for empty steps that are still inside the loop. Both off by
# default because the palette has no dim variant -- every colour is full
# brightness, so a lit empty grid is loud. Try them once you can see the pads:
# 4 quarter-note markers make 16 steps countable at a glance, which is what a
# dim white does on a Push.
COLOR_STEP_EMPTY = 0        # every in-loop empty step
COLOR_STEP_DOWNBEAT = 0     # every 4th in-loop empty step, overrides the above

# Overview row colours, one per lane, top row first. Chosen from the separated
# anchors and deliberately avoiding both playhead colours, so a playhead column
# never reads as a lane.
LANE_COLORS = (5, 14, 21, 24)

# Shown on the top-left pad when no MIDI clip is bound. 0 = the grid just goes
# dark, which is unambiguous but tells you nothing; try 24 if you want a "script
# is alive, select a clip" light.
COLOR_NO_CLIP = 0

# Button LEDs.
#
# These only do anything if the buttons' feedback option is ON in the M-Vave
# editor: with it off the button lights locally on its own press and ignores what
# the host sends. With it on, the button is dark unless something lights it --
# which is why this exists, since the script otherwise writes only to the pads.
#
# UNMEASURED: whether the button LEDs take the pad palette or are simply on/off.
# These are velocities either way, so if the buttons turn out to be colour
# capable, pick from the palette in HARDWARE.md 3.2.
BUTTON_LEDS = True
BTN_LED_ON = 127
BTN_LED_OFF = 0


# ------------------------------------------------------------------- sequencer

STEP = 0.25                 # one step in beats: 0.25 = a 16th note
STEPS_MAX = 256             # 16 bars of 16ths -- a safety ceiling, not the
                            # working length. The visible window follows the
                            # playhead, so the clip's own loop decides how many
                            # pages there are. Edits stay inside the loop.

# Move the visible 16 steps to wherever the playhead is, so a 16, 32 or 64-step
# loop needs no manual paging. Paging by hand switches this off for the rest of
# the take; stopping the transport switches it back on.
FOLLOW_PLAYHEAD = True

# Paging by hand has to stop the chase for a moment, or the next audio buffer
# yanks the view straight back and the arrow looks broken. This decides how long
# "a moment" is: with it True the chase resumes the next time the loop comes
# round, so paging away is a peek at the current cycle rather than a mode you
# have to leave by hand. Set False to make a manual page stick until you either
# page back onto the playhead or stop the transport.
FOLLOW_RESUMES_ON_WRAP = True

# Velocity written into a new note when USE_STRIKE_VELOCITY is False, or when a
# pad reports 0. With velocity-sensitive pads this is only a fallback.
PAINT_VELOCITY = 100

# Paint each step with the velocity you actually hit the pad at, Push-style.
#
# INERT on this hardware: the only banks that light their pads are fixed-velocity,
# so every strike arrives as 127 and PAINT_VELOCITY effectively governs. Kept on
# because it costs nothing and is correct the moment a device can do both.
# Costs nothing when the pads are not velocity-sensitive: a fixed-127 pad simply
# paints 127, and PAINT_VELOCITY takes over if the preset is ever configured to
# send a constant. Worth keeping on, because if a velocity-sensitive preset can
# be built it removes the need for a velocity encoder entirely -- and both knob
# banks are now spent on device macros, so there is nowhere to put one.
#
# NOT yet demonstrated on this device. The velocity-sensitive stream seen on
# 2026-08-31 came from an unidentified device state and has never been isolated.
USE_STRIKE_VELOCITY = True
                            # moves it

DEFAULT_LANE = 36           # C1, the bottom-left pad of a Live drum rack
LANE_SELECT_BASE = 36       # SHIFT + pad selects pitches 36-51 in drum-rack
                            # orientation: bottom-left is the lowest, ascending
                            # left to right then bottom to top, so it mirrors
                            # what the rack looks like on screen

LOG_PREFIX = 'MVave_SMC_STEPSEQ: '
