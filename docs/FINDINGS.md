# Findings

How an undocumented controller was measured, what went wrong along the way, and
what that cost. Kept because the wrong turns are more instructive than the
result, and because anyone doing this to a different device will hit the same
shapes of problem.

The measured facts themselves live in [HARDWARE.md](HARDWARE.md). This file is
the reasoning.

---

## The starting position

The SMC-PAD ships with no MIDI implementation chart. Both the user manual and
the "DAW setup" manual are marketing copy plus screenshots — 16 RGB pads, 8
assignable encoders, a list of DAWs. Neither states a single note or CC number.

So every number in [HARDWARE.md](HARDWARE.md) was measured, and the only reason
this project exists in a usable state is that measuring turned out to be cheap
once the right tool existed.

## Cracking the `.spc` config file

The M-Vave editor saves its configuration as a binary `.spc` with no magic bytes,
no header and no obvious structure. What broke it open was **arithmetic on record
sizes**: three candidate record lengths, guessed from repeating byte patterns,
that summed to exactly the file length with nothing left over.

```
5 x 23  +  16 x 6  +  128 x 26  =  115 + 96 + 3328  =  3539 bytes
```

An exact fit across three different record sizes is not a coincidence you get by
chance. That single check converted a guess into a segmentation confident enough
to build on — and the 128-record section immediately made sense as 8 preset banks
of 16 pads.

**Generalisable:** when reverse-engineering a fixed-record binary format, solve
for record counts and sizes that account for the file exactly. It is a far
stronger signal than any individual field looking plausible.

## The question that gated everything

The whole project rested on one thing: **can the pads be coloured by incoming
MIDI?** If not, there is no clip launcher worth having — you get clip launching
with dead pads, which is worse than the mixer control the device already does.

That question went unverified for a long time while plans were built on top of
it. Ports were chosen, an architecture was designed, a Remote Script was renamed
and a build was nearly started. The actual test took about ten minutes.

**Generalisable:** find the assumption every other decision hangs off, and test
that one first. Not the easiest thing to test, not the thing you are most curious
about — the load-bearing one.

## Seven wrong turns

**1. Assuming MCU numbering because the port is called "DAW".** The device
presents three MIDI ports and the manufacturer's setup guide says to point Mackie
Control at port 3. Reasonable inference: port 3 speaks MCU, so pads will arrive
on the standard Mackie note numbers — arm 0–7, solo 8–15, mute 16–23, select
24–31. They do not. They arrive as notes 1–16 in reading order. *A port's name
tells you nothing about its protocol.*

**2. Reading a `0x00` byte as "disabled".** Two of the sixteen pad records in the
`.spc` had a type byte of `0x00` where the others had `0x09`. That looked like an
enable flag, and it was written down as a prediction: those two pads should
transmit nothing. Both fired normally on the first press. Whatever that byte
means, it is not what it looked like.

**3. Calling a working configuration a bug.** The `MIDI_Map.py` in hand had
`PLAY=17 STOP=18 REC=19`, and pads occupying notes 1–16. Since notes 17–19 sat
just past the pad range, this was reported as a collision waiting to happen. It
was not — the device's buttons genuinely send 17–21, and the map had been
deliberately written to match. *The `.spc` and the script were designed as a
pair; reasoning about either in isolation produced nonsense.*

**4. "All the pads lit green" is not "the host controls the colour."** The first
lighting test sent note-on to every note at velocity 127 and the grid lit up
green. That was reported as "the host can set pad colours." It does not follow —
green was the colour already configured on the device, and the pads might simply
have been switching on. Separating the two required sweeping velocity and
watching the colour change. One is on/off feedback; the other is a real colour
grid. They look identical in a single test.

**5. Nearly designing around a dead pad that was not dead.** That same blunt
test lit 15 of 16 pads. The natural conclusion — one pad's LED is broken, design
around it. The actual cause was the test itself: 128 note-on messages sent
back-to-back overran the device's MIDI buffer. Addressed on its own, the pad
lights fine. *When a measurement disagrees with expectation, suspect the
measuring instrument before the subject.*

**6. A flat capture that lied.** Mapping all sixteen encoder assignments was
first attempted as a single 180-second log while turning knobs in a prescribed
order. It returned 14 of 16 — two CCs missing, one wrongly reported as relative —
and, worse, gave no way to tell *which* step had gone wrong, because nothing was
confirmed as it happened. Rewritten to stop and report after every individual
knob, the same measurement produced a clean 16 of 16 with silent knobs and CC
clashes named explicitly. *When a measurement asks a human to sequence many
steps, checkpoint every step, not the end.*

**7. An open question answered destructively.** When the ports were chosen, one
uncertainty was noted and deliberately worked around: does Live keep a port
available for Ctrl+M once a Control Surface claims it? The workaround was sound —
ports 1 and 2 carry identical CCs, so the script takes one and mapping keeps the
other. But the question got its answer anyway, by silently breaking existing
macro mappings that had been arriving on the claimed port. **It does not:**
assigning a Control Surface disables Track/Sync/Remote on that port. Documented
now as fact rather than as an open question.

## Failures that are silent by construction

Three things in this project fail without any error, which is why they get their
own defensive treatment in the code:

- **`receive_midi` swallowing what it does not handle.** Override it, forget to
  forward the rest to `ControlSurface.receive_midi`, and navigation works
  perfectly while the device macros quietly do nothing at all.
- **`set_parameter_controls` with the wrong count.** Some `_Framework` versions
  assert exactly 8 controls. An assert inside `__init__` does not disable the
  macros — it takes the entire script down, including the parts that worked.
- **`ClipSlotComponent` setters that vary by Live version.** Call one that does
  not exist and the script dies at load. They are called by name through
  `getattr` and skipped with a log line if absent, because losing a colour is an
  acceptable failure and losing the script is not.

The pattern: when a failure produces silence rather than an error, spend the
extra code to make it announce itself.

## What is still unknown

Recorded rather than quietly dropped:

- **The `.spc` flag byte as a port selector.** Pad records in the hand-edited
  bank carry flag `0x04` and appear on port 3; encoder records carry flag `0x03`
  and appear on ports 1 and 2. (An earlier revision of this bullet said the
  encoder flag was `0x00` — that is the *third* byte of the record, a different
  field. All 32 encoder records across both shipped presets read
  `03 02 00 <cc> 3f 41`.) Two observations, consistent, never proven — and
  **superseded** by [HARDWARE.md](HARDWARE.md) 5.6, which argues the port
  follows the assignment *type* rather than any flag, and where the confirming
  experiment is still unrun.
- **What VELOCITY 1–4 change.** All four transmit velocity 127 on the DAW port
  and none affect LED colour. What they *do* affect was never established,
  because the port a velocity curve would shape transmitted nothing in the bank
  under test.
- **Why port 1 was silent for pads** while carrying encoder CCs perfectly. Likely
  the same flag byte above.
- **Whether the cross-script instance lookup is robust across load orders.** It
  works, and it is resolved lazily on every use specifically because Control
  Surface slot initialisation order is not controllable — but only one ordering
  has ever actually been observed.
