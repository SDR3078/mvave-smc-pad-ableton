# Hardware and layout constants for the SMC-PAD step sequencer.
#
# Everything the script knows about the controller lives in this file.
# smc_stepseq.py contains no note numbers, no CC numbers and no colour values,
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

# MIDI channel the sequencer preset must transmit on, 0-indexed: 15 = channel 16.
#
# UNVERIFIED -- and a correction. An earlier revision of this file set channel 10
# and notes 52-67 here, taken from a capture that mixed two device states and had
# already been identified as contaminated. A clean single-state capture on
# 2026-08-26 showed the controller sending notes 1-16 on CHANNEL 1, PORT 3, fixed
# velocity 127 -- byte for byte what the clip launcher sends. There is no second
# mapping to piggyback on.
#
# So the original plan stands: a distinct pad preset is genuinely required, and
# channel 16 is the discriminator because nothing else on the device uses it.
# It has to be programmed in the M-Vave editor and then confirmed with a monitor.
PAD_CHANNEL = 15

# The 16 pads, in READING order: index 0 is top-left, index 15 bottom-right.
#
# UNVERIFIED -- these are the notes the new preset must be PROGRAMMED to send,
# not something observed. They must differ from the clip launcher's 1-16 even
# though channel 16 already separates the two, because a note collision on a
# shared port is one editor mistake away from both scripts acting on one press.
#
# The M-Vave editor numbers pads BOTTOM-UP -- its PAD1 is the bottom-left pad,
# not the top-left one (HARDWARE.md 5.3). The tuple below is in screen reading
# order regardless of what the editor calls each pad.
PAD_NOTES = tuple(range(0, 16))

# Second pad note set, if the PAD BANK button turns out to be a silent switch
# between two note sets rather than something that emits its own message.
#
# UNVERIFIED, and left empty on purpose. When PAD BANK is silent the script
# cannot know which hardware bank is live, so it cannot address bank B's LEDs
# either -- which is why bank-B notes are treated as plain ALIASES for the same
# 16 pad positions rather than as steps 17-32. Left/Right is the real step-page
# control. Fill this in only if you program a second note set and want a stray
# PAD BANK press to keep the pads working instead of going dead.
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

BTN_PLAY = 17               # play/stop toggle -- see below for why the script owns it
BTN_VIEW = 18               # focus <-> overview
BTN_SHIFT = 19              # momentary modifier
BTN_LEFT = 20               # previous step page
BTN_RIGHT = 21              # next step page

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
#      _active_instances hook in smc_stepseq.py for the way out.
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
LED_CHANNEL = 0             # MEASURED 2026-08-26: channel 1, regardless of the
                            # channel the pads transmit on. LED addressing did
                            # not follow the mode switch.
LED_NOTES = tuple(range(1, 17))   # MEASURED 2026-08-26 on MIDIOUT3, and NOT the
                            # notes the pads send. Found by sweeping: notes 1-15
                            # lit fifteen pads and note 16 the last one. The
                            # earlier reading that "note 16 does nothing" was the
                            # probe blasting sixteen note-ons with no gap and the
                            # device dropping the tail -- see FINDINGS.md, and
                            # the clip-launcher bank at least

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


# ------------------------------------------------------------------- sequencer

STEP = 0.25                 # one step in beats: 0.25 = a 16th note
STEPS_MAX = 32              # two bars of 16ths. v1 edits inside the loop only.

# Velocity written into a new note when USE_STRIKE_VELOCITY is False, or when a
# pad reports 0. With velocity-sensitive pads this is only a fallback.
PAINT_VELOCITY = 100

# Paint each step with the velocity you actually hit the pad at, Push-style.
# Costs nothing when the pads are not velocity-sensitive: a fixed-127 pad simply
# paints 127, and PAINT_VELOCITY takes over if the preset is ever configured to
# send a constant. Worth keeping on, because if a velocity-sensitive preset can
# be built it removes the need for a velocity encoder entirely -- and both knob
# banks are now spent on device macros, so there is nowhere to put one.
#
# NOT yet demonstrated on this device. The velocity-sensitive stream seen on
# 2026-08-26 came from an unidentified device state and has never been isolated.
USE_STRIKE_VELOCITY = True
                            # moves it

DEFAULT_LANE = 36           # C1, the bottom-left pad of a Live drum rack
LANE_SELECT_BASE = 36       # SHIFT + pad selects pitches 36-51 in drum-rack
                            # orientation: bottom-left is the lowest, ascending
                            # left to right then bottom to top, so it mirrors
                            # what the rack looks like on screen

LOG_PREFIX = 'SMC_StepSeq: '
