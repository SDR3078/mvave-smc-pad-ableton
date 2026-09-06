#!/usr/bin/env python3
"""
mvave_probe.py -- run this on the machine the SMC-PAD is plugged into.

Answers the two questions that gate the whole Remote Script project, without
installing a Remote Script first:

  1. What MIDI do the pads and buttons actually send?   ->  --listen
  2. Can the host colour the pads by sending MIDI?      ->  --light / --colours

Nothing here touches Ableton. It talks straight to the SMC-PAD's MIDI ports.

ON WINDOWS -- MIDI ports are exclusive.
If Ableton has a port open, this script cannot open it and you will get an
"access denied" style error. Either close Live, or untick that port in
Preferences > Link/Tempo/MIDI before running. On Linux (ALSA) and macOS
(CoreMIDI) ports are multi-client, so you can probe alongside a running DAW.

Teardown: delete this file, run_probe.bat, requirements-midi.txt and the
venv-midi folder next to them. Nothing is written anywhere else.
"""

import argparse
import sys
import time

try:
    import mido
except ImportError:                                 # pragma: no cover
    # Deliberately not deferred to main(): every mode needs mido, and a bare
    # ModuleNotFoundError names no remedy. --help needs no MIDI stack at all,
    # so say what to run instead of printing a traceback at the first thing
    # anyone types.
    sys.exit("mido is not installed.\n"
             "  Windows: run tools\\run_probe.bat, which builds its own venv.\n"
             "  macOS/Linux: python3 -m venv venv-midi && "
             "./venv-midi/bin/pip install -r tools/requirements-midi.txt")

# Relative encoders centre on 64: 63 is one step back, 65 one step forward.
# The other convention in the wild is two's complement (127 back, 1 forward).
# Both are reported by name -- they are the two values of ENCODER_MODE in
# MVave_SMC_KNOBS.py.
CENTRE_VALUE = 64

# The SMC-PAD's generic preset and its Mackie/DAW mode both sit on MIDI
# channel 1. Channel is 1-16 on the command line, 0-15 on the wire.
DEFAULT_CHANNEL = 1


def _reject_bare_index(wanted, kind, names):
    """A bare number is never a port selector here.

    RtMidi appends a 0-based index to every port name, so "1" is a substring
    that uniquely matches "MIDIIN2 (SMC-PAD) 1" -- the pair this documentation
    calls port 2. HARDWARE.md 1.3 tells the reader to disambiguate by index,
    which makes that an easy and completely silent way to measure the wrong
    port. Refuse it and show the real names instead.
    """
    if wanted is not None and wanted.strip().isdigit():
        sys.exit("%r is ambiguous: port names end in a 0-based index, so %r also\n"
                 "matches the pair one higher than you probably mean. Pass part of\n"
                 "the name instead. Available %s ports:\n  %s"
                 % (wanted, wanted, kind, "\n  ".join(names)))


def pick_port(names, wanted, kind):
    """Resolve a substring to exactly one port name, or explain what went wrong."""
    if not names:
        sys.exit("No MIDI %s ports found at all. Is the SMC-PAD plugged in and awake?" % kind)
    if wanted is None:
        sys.exit("Pass --port with part of a port name. Available %s ports:\n  %s"
                 % (kind, "\n  ".join(names)))
    _reject_bare_index(wanted, kind, names)
    hits = [n for n in names if wanted.lower() in n.lower()]
    if not hits:
        sys.exit("No %s port matching %r. Available:\n  %s" % (kind, wanted, "\n  ".join(names)))
    if len(hits) > 1:
        sys.exit("%r matches %d %s ports -- be more specific:\n  %s"
                 % (wanted, len(hits), kind, "\n  ".join(hits)))
    return hits[0]


def pick_ports(names, wanted, kind):
    """Like pick_port, but returns EVERY match.

    For --listen, matching several ports at once is the point rather than an
    ambiguity to complain about -- when you do not yet know which port a control
    lives on, watching all of them is the whole question.
    """
    if not names:
        sys.exit("No MIDI %s ports found at all. Is the SMC-PAD plugged in and awake?" % kind)
    if wanted is None:
        sys.exit("Pass --port with part of a port name. Available %s ports:\n  %s"
                 % (kind, "\n  ".join(names)))
    _reject_bare_index(wanted, kind, names)
    hits = [n for n in names if wanted.lower() in n.lower()]
    if not hits:
        sys.exit("No %s port matching %r. Available:\n  %s" % (kind, wanted, "\n  ".join(names)))
    return hits


def cmd_list(_args):
    print("MIDI INPUTS  (what the SMC-PAD sends us)")
    for n in mido.get_input_names():
        print("   ", n)
    print()
    print("MIDI OUTPUTS  (what we can send to the SMC-PAD)")
    for n in mido.get_output_names():
        print("   ", n)
    print()
    print("The DAW manual calls these Port 2 (generic) and Port 3 (Mackie/DAW);")
    print("on Windows they usually show up as MIDIIN2/MIDIIN3 or similar.")


def cmd_listen(args):
    names = pick_ports(mido.get_input_names(), args.port, "input")
    print("Listening on %d port(s) for %d seconds:" % (len(names), args.seconds))
    for n in names:
        print("    %s" % n)
    print("\nPress the pads and buttons, and turn every knob both ways.")
    print("Ctrl+C to stop early.\n")

    seen = {}
    started = time.time()
    # Open what we can. Windows MIDI ports are exclusive, so if Live is holding
    # one, skip it and watch the rest rather than aborting the whole run.
    ports = []
    for n in names:
        try:
            ports.append(mido.open_input(n))
        except (IOError, OSError) as exc:
            print("  ! could not open %s -- in use by Live? (%s)" % (n, exc))
    if not ports:
        sys.exit("Could not open any port -- busy or unavailable.\n"
                 "On Windows, ports are exclusive: close Live, or untick the "
                 "SMC-PAD in Preferences > Link/Tempo/MIDI.\n"
                 "On Linux/macOS, ports are multi-client, so a busy port means "
                 "the device is unplugged or the name is wrong -- try --list.")
    try:
        while time.time() - started < args.seconds:
            for port in ports:
                for msg in port.iter_pending():
                    # Aftertouch floods the log and says nothing about layout.
                    if msg.type in ("aftertouch", "polytouch"):
                        continue
                    print("  %7.2fs  %-22s %s" % (time.time() - started, port.name[:22], msg))
                    key = (port.name, msg.type,
                           getattr(msg, "channel", None),
                           getattr(msg, "note", getattr(msg, "control", None)))
                    seen.setdefault(key, []).append(
                        getattr(msg, "velocity", getattr(msg, "value", None)))
            time.sleep(0.001)
    except KeyboardInterrupt:
        pass
    finally:
        for port in ports:
            port.close()

    print("\n--- summary: %d distinct controls ---" % len(seen))
    # Channel is in here because on some devices it carries meaning -- a preset
    # can be identified by the channel it transmits on -- and a summary that
    # omits it will happily agree with two mutually exclusive theories.
    print("  %-22s %-14s %-3s %-5s %6s  %s"
          % ("port", "type", "ch", "num", "count", "values seen"))
    for key in sorted(seen, key=lambda k: (k[0], k[1], k[2] or 0, k[3] or 0)):
        pname, mtype, chan, num = key
        values = seen[key]
        vals = [v for v in values if v is not None]
        distinct = sorted(set(vals))
        shown = ", ".join(str(v) for v in distinct[:10])
        if len(distinct) > 10:
            shown += ", ... (%d distinct, range %d-%d)" % (len(distinct), min(vals), max(vals))
        print("  %-22s %-14s %-3s %-5s %6d  %s"
              % (pname[:22], mtype, "-" if chan is None else chan + 1,
                 num, len(values), shown))
    if not seen:
        print("  (nothing received on any port)")
    channels = sorted({k[2] + 1 for k in seen if k[2] is not None})
    print("\nMIDI channels seen: %s" % (", ".join(str(c) for c in channels) or "none"))
    if any(k[1] == "control_change" for k in seen):
        print("\nEncoder encoding: only a couple of distinct values (1 and 127, or")
        print("65 and 63) means RELATIVE -- each tick reports a direction. A wide")
        print("spread over 0-127 means ABSOLUTE -- it reports a position.")


# The device drops messages that arrive faster than it can service them, and it
# is the TAIL of a burst that goes missing. This has now faked a dead pad twice --
# once with a 128-note blast, once with only 16 -- so every bulk send here is
# paced. 2 ms is well under a human's notice and well over the device's need.
SEND_GAP = 0.002


def _paced(port, messages):
    for message in messages:
        port.send(message)
        time.sleep(SEND_GAP)


def _off(port, channel, note):
    """Extinguish one pad.

    Note-on with velocity 0, NOT a real note-off (0x80). The SMC-PAD reports its
    own pad releases as note-on/velocity-0 and appears to ignore 0x80 entirely --
    clearing with note-off leaves every pad stuck lit.
    """
    port.send(mido.Message("note_on", channel=channel, note=note, velocity=0))


def _send_all_off(port, channel, lo, hi):
    _paced(port, [mido.Message("note_on", channel=channel, note=n, velocity=0)
                  for n in range(lo, hi + 1)])


def cmd_light(args):
    """Blunt instrument: light everything at once. Does ANY pad respond?"""
    name = pick_port(mido.get_output_names(), args.port, "output")
    ch = args.channel - 1
    print("Sending note-on to notes %d-%d, velocity %d, channel %d on %r."
          % (args.lo, args.hi, args.velocity, args.channel, name))
    print("WATCH THE PADS. Holding for %.0fs, then clearing.\n" % args.hold)
    with mido.open_output(name) as port:
        try:
            _paced(port, [mido.Message("note_on", channel=ch, note=n, velocity=args.velocity)
                          for n in range(args.lo, args.hi + 1)])
            time.sleep(args.hold)
        except KeyboardInterrupt:
            # Swallowed as --sweep does, so the closing prompt still prints and
            # the launcher does not report a non-zero exit and pause.
            pass
        finally:
            # Ctrl+C during the hold used to leave the whole grid lit, needing a
            # separate --clear run. --sweep already handled this.
            _send_all_off(port, ch, args.lo, args.hi)
    print("Cleared. Did anything light up?")


def cmd_sweep(args):
    """Narrow down WHICH notes address pads, a block at a time."""
    name = pick_port(mido.get_output_names(), args.port, "output")
    ch = args.channel - 1
    print("Sweeping notes %d-%d in blocks of %d on %r, %.1fs per block.\n"
          % (args.lo, args.hi, args.step, name, args.hold))
    with mido.open_output(name) as port:
        try:
            for base in range(args.lo, args.hi + 1, args.step):
                top = min(base + args.step - 1, args.hi)
                print("  notes %3d-%3d ..." % (base, top))
                _paced(port, [mido.Message("note_on", channel=ch, note=n, velocity=args.velocity)
                              for n in range(base, top + 1)])
                time.sleep(args.hold)
                _send_all_off(port, ch, base, top)
                time.sleep(0.15)
        except KeyboardInterrupt:
            _send_all_off(port, ch, args.lo, args.hi)
    print("\nWhich block lit the pads?")


def cmd_curves(args):
    """Measure what VELOCITY 1-4 (Shift + Pad 9-12) actually change.

    Two things per setting in a single pass: the velocity numbers the pads
    transmit, and whatever the LEDs do locally while you play. Can watch two
    ports at once -- the playing port and the DAW port -- because the whole
    question is whether they behave differently.
    """
    names = mido.get_input_names()
    primary = pick_port(names, args.port, "input")
    secondary = pick_port(names, args.port2, "input") if args.port2 else None
    if secondary == primary:
        sys.exit("--port and --port2 resolved to the same port (%s)" % primary)

    print("Measuring VELOCITY 1-4 on:")
    print("   %s" % primary)
    if secondary:
        print("   %s" % secondary)
    print()

    ports = [mido.open_input(primary)]
    if secondary:
        ports.append(mido.open_input(secondary))

    results = []
    try:
        for n in (1, 2, 3, 4):
            print("--- VELOCITY %d ---" % n)
            try:
                input("  Select it: hold SHIFT, press PAD %d, release. Then Enter here. " % (8 + n))
                # The shift combo itself may emit traffic -- drop it, or it
                # lands in the sample and skews the numbers.
                for p in ports:
                    list(p.iter_pending())
                input("  Now hit ONE pad about 10 times, softest to hardest. Enter when done. ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            row = {"setting": n, "ports": {}}
            for p in ports:
                row["ports"][p.name] = [m.velocity for m in p.iter_pending()
                                        if m.type == "note_on" and m.velocity > 0]
            try:
                row["led"] = input("  What did the pad's own LED do while you played? ").strip()
            except (EOFError, KeyboardInterrupt):
                row["led"] = ""
                results.append(row)
                break
            results.append(row)
            print()
    finally:
        for p in ports:
            p.close()

    if not results:
        return
    print("\n=== VELOCITY setting -> transmitted velocity ===")
    print("%-8s %-24s %5s %5s %5s  %s" % ("setting", "port", "hits", "min", "max", "distinct values"))
    for row in results:
        for port_name, vels in row["ports"].items():
            if vels:
                distinct = sorted(set(vels))
                shown = ", ".join(str(v) for v in distinct[:12])
                if len(distinct) > 12:
                    shown += ", ... (%d total)" % len(distinct)
                print("%-8d %-24s %5d %5d %5d  %s"
                      % (row["setting"], port_name[:24], len(vels), min(vels), max(vels), shown))
            else:
                print("%-8d %-24s %5s %5s %5s  %s"
                      % (row["setting"], port_name[:24], 0, "-", "-", "nothing received"))
    print("\n=== LED behaviour while playing ===")
    for row in results:
        print("  VELOCITY %d: %s" % (row["setting"], row.get("led") or "(not recorded)"))
    print("\nIf every setting gives the same min/max/spread, the curves do nothing")
    print("on that port -- most likely because the pads carry a fixed velocity")
    print("byte in the .spc, which would override any curve.")


def _classify(values):
    """Relative or absolute, from the values alone."""
    distinct = sorted(set(values))
    if not distinct:
        return "-"
    # The two conventions are reported separately because they are exactly the
    # two values of ENCODER_MODE in MVave_SMC_KNOBS.py -- collapsing them to
    # one word threw away the only thing this mode exists to determine, and
    # feeding the wrong one to the session box moves it 63 tracks per click,
    # silently.
    #
    # Clustered rather than exact: an encoder that accelerates, or a poll that
    # catches two ticks at once, emits 2/126 or 62/66 -- which the old exact
    # sets called "absolute", the one answer that wires it up wrong.
    if distinct and all(abs(v - CENTRE_VALUE) <= 8 for v in distinct):
        return "relative (centre)"
    if distinct and all(v <= 8 or v >= 120 for v in distinct):
        return "relative (twos)"
    if len(distinct) <= 3:
        return "relative?"
    return "absolute"


def cmd_knobs(args):
    """Map every encoder to its CC, one knob at a time.

    A flat --listen run asks you to turn sixteen things in the right order and
    only reveals a missed one at the end. Here each knob is confirmed as you go,
    so a knob that sends nothing -- or sends the same CC as its neighbour --
    shows up on the spot, while you are still holding it.
    """
    name = pick_port(mido.get_input_names(), args.port, "input")
    print("Mapping %d encoder(s) across %d bank(s) on %r." % (args.count, args.banks, name))
    print("Enter alone records nothing and moves on. 'q' stops and prints what we have.\n")

    rows = []
    with mido.open_input(name) as port:
        try:
            for bank in range(1, args.banks + 1):
                if input("=== knob bank %d -- press KNOB BANK until you are on it, then Enter. "
                         % bank).strip().lower() in ("q", "quit"):
                    raise KeyboardInterrupt
                for encoder in range(1, args.count + 1):
                    list(port.iter_pending())          # clear the previous step
                    if input("   encoder %d: turn it a few clicks each way, then Enter. "
                             % encoder).strip().lower() in ("q", "quit"):
                        raise KeyboardInterrupt
                    per_cc = {}
                    for msg in port.iter_pending():
                        if msg.type != "control_change":
                            continue
                        # Keyed on (channel, CC), not CC alone. A controller
                        # whose KNOB BANK switches channel instead of CC numbers
                        # would otherwise read as two identical banks, and two
                        # encoders separable by channel would be called a clash.
                        per_cc.setdefault((msg.channel, msg.control), []).append(msg.value)
                    if not per_cc:
                        rows.append((bank, encoder, None, None, "-", 0, ""))
                        print("      nothing received")
                        continue
                    for key in sorted(per_cc, key=lambda k: -len(per_cc[k])):
                        channel, cc = key
                        values = per_cc[key]
                        mode = _classify(values)
                        distinct = sorted(set(values))
                        shown = ", ".join(str(v) for v in distinct[:6])
                        if len(distinct) > 6:
                            shown += ", ... (%d distinct)" % len(distinct)
                        rows.append((bank, encoder, channel, cc, mode, len(values), shown))
                        print("      ch %-2d CC %-3d  %-9s  %d msgs  [%s]"
                              % (channel + 1, cc, mode, len(values), shown))
                print()
        except (KeyboardInterrupt, EOFError):
            print("\n(stopped)\n")

    if not rows:
        return
    print("=== encoder map ===")
    print("  %-5s %-8s %-3s %-5s %-10s %6s  %s"
          % ("bank", "encoder", "ch", "CC", "mode", "msgs", "values"))
    for bank, encoder, channel, cc, mode, n, shown in rows:
        print("  %-5d %-8d %-3s %-5s %-10s %6d  %s"
              % (bank, encoder, "-" if channel is None else channel + 1,
                 "-" if cc is None else cc, mode, n, shown))

    silent = [(b, e) for b, e, _, cc, _, _, _ in rows if cc is None]
    if silent:
        print("\nSent nothing: " + ", ".join("bank %d enc %d" % be for be in silent))
    seen = {}
    for bank, encoder, channel, cc, _, _, _ in rows:
        if cc is not None:
            seen.setdefault((bank, channel, cc), []).append(encoder)
    clashes = {k: v for k, v in seen.items() if len(v) > 1}
    for (bank, channel, cc), encoders in sorted(clashes.items()):
        print("CLASH: bank %d ch %d CC %d came from encoders %s"
              % (bank, channel + 1, cc, ", ".join(str(e) for e in encoders)))


def cmd_clear(args):
    """Extinguish every pad. Use after a probe run leaves the grid lit."""
    name = pick_port(mido.get_output_names(), args.port, "output")
    with mido.open_output(name) as port:
        _send_all_off(port, args.channel - 1, 0, 127)
    print("Sent note-on/velocity-0 to notes 0-127 on %r." % name)


def cmd_colours(args):
    """Walk one pad through velocities, one keypress at a time.

    Deliberately interactive rather than timed: a timed sweep asks you to
    remember a sequence of colours, which is the thing humans are worst at.
    Here each step waits for you, and whatever you type is recorded straight
    into the summary table at the end.
    """
    name = pick_port(mido.get_output_names(), args.port, "output")
    ch = args.channel - 1
    print("Note %d on %r -- %d steps." % (args.note, name, len(args.velocities)))
    print("Look at the pad, type the colour, press Enter.")
    print("Enter on its own records nothing. Type 'q' to stop early.\n")

    seen = []
    with mido.open_output(name) as port:
        try:
            for vel in args.velocities:
                port.send(mido.Message("note_on", channel=ch, note=args.note, velocity=vel))
                try:
                    answer = input("  velocity %3d  colour? " % vel).strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if answer.lower() in ("q", "quit"):
                    break
                seen.append((vel, answer or "?"))
        finally:
            _off(port, ch, args.note)

    if not seen:
        return
    print("\n--- velocity -> colour ---")
    for vel, colour in seen:
        print("  %3d  %s" % (vel, colour))

    # Collapse runs of the same answer: this is the form that actually matters,
    # since what we need is which velocity RANGE gives which colour.
    print("\n--- grouped ---")
    start, current = seen[0][0], seen[0][1]
    for i, (vel, colour) in enumerate(seen[1:] + [(None, None)]):
        if colour != current:
            last = seen[i][0]
            span = "%d" % start if start == last else "%d-%d" % (start, last)
            print("  %-9s %s" % (span, current))
            start, current = vel, colour


def bounded_int(low, high, what):
    """An argparse type that rejects out-of-range values up front.

    Without this a bad --channel or --note reaches mido only after the port is
    open and the human is already answering prompts, and surfaces as a
    traceback whose wording contradicts our own --help ("channel must be in
    range 0..15" against "MIDI channel 1-16").
    """
    def parse(text):
        try:
            value = int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(
                "%s must be a whole number, got %r" % (what, text))
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(
                "%s must be %d-%d, got %d" % (what, low, high, value))
        return value
    return parse


def bounded_float(low, high, what):
    """Like bounded_int, for the one flag that is a duration.

    --hold reaches time.sleep() after the port is open, and in --sweep the
    resulting ValueError is not caught by `except KeyboardInterrupt`, so
    _send_all_off never runs and the whole block stays lit. nan and inf get
    through a bare float() and fail the same way.
    """
    def parse(text):
        try:
            value = float(text)
        except ValueError:
            raise argparse.ArgumentTypeError(
                "%s must be a number, got %r" % (what, text))
        if not (value == value and low <= value <= high):   # value != value -> nan
            raise argparse.ArgumentTypeError(
                "%s must be between %g and %g, got %r" % (what, low, high, text))
        return value
    return parse


def velocity_list(text):
    if text == "all":
        return list(range(1, 128))
    if text == "coarse":
        # Enough to reveal a colour table without watching 127 steps.
        return [1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 40, 48, 60, 64, 80, 96, 112, 127]
    try:
        values = [int(v) for v in text.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(
            "--velocities takes 'coarse', 'all', or a comma list of 0-127")
    bad = [v for v in values if not 0 <= v <= 127]
    if bad:
        # Caught here rather than mid-run: --colours prompts the human for a
        # colour name at every step, and a value mido rejects halfway through
        # throws away every answer already typed.
        raise argparse.ArgumentTypeError(
            "velocities must be 0-127, got %s" % ", ".join(str(v) for v in bad))
    return values


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", help="substring of the MIDI port name (see --list)")
    p.add_argument("--port2", help="second input port to watch simultaneously (--curves only)")
    p.add_argument("--channel", type=bounded_int(1, 16, "channel"),
                   default=DEFAULT_CHANNEL, help="MIDI channel 1-16")
    p.add_argument("--lo", type=bounded_int(0, 127, "--lo"), default=0,
                   help="lowest note to touch")
    p.add_argument("--hi", type=bounded_int(0, 127, "--hi"), default=127,
                   help="highest note to touch")
    p.add_argument("--velocity", type=bounded_int(0, 127, "--velocity"), default=127,
                   help="velocity for --light/--sweep")
    p.add_argument("--hold", type=bounded_float(0.0, 3600.0, "--hold"),
                   default=3.0, help="seconds to hold each step")
    p.add_argument("--step", type=bounded_int(1, 128, "--step"), default=16,
                   help="block size for --sweep")
    p.add_argument("--seconds", type=bounded_int(1, 86400, "--seconds"), default=60,
                   help="how long --listen runs")
    p.add_argument("--banks", type=bounded_int(1, 16, "--banks"), default=2,
                   help="knob banks to walk (--knobs)")
    p.add_argument("--count", type=bounded_int(1, 64, "--count"), default=8,
                   help="encoders per bank (--knobs)")
    p.add_argument("--note", type=bounded_int(0, 127, "--note"), default=0,
                   help="which note --colours walks")
    p.add_argument("--velocities", type=velocity_list, default="coarse",
                   help="'coarse', 'all', or a comma list, for --colours")

    mode = p.add_mutually_exclusive_group(required=True)
    for flag, fn in (("list", cmd_list), ("listen", cmd_listen), ("light", cmd_light),
                     ("sweep", cmd_sweep), ("colours", cmd_colours), ("clear", cmd_clear),
                     ("curves", cmd_curves), ("knobs", cmd_knobs)):
        mode.add_argument("--" + flag, dest="mode", action="store_const", const=fn)

    args = p.parse_args()
    if args.mode in (cmd_light, cmd_sweep) and args.lo > args.hi:
        # Individually legal, jointly empty: range(100, 6) sends nothing, and
        # the mode still prints its "did anything light up?" prompt, so the
        # human watches a dark grid and records the wrong answer. Scoped to the
        # two modes that read the range: --clear documents that it ignores
        # --lo/--hi entirely, and refusing to clear a lit grid over an unused
        # flag pair would break the one command that recovers from a bad run.
        p.error("--lo (%d) must not exceed --hi (%d)" % (args.lo, args.hi))
    args.mode(args)


if __name__ == "__main__":
    main()
