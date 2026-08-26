#!/usr/bin/env python3
"""
mvave_probe.py -- run this ON THE WINDOWS PC (the one the SMC-PAD is plugged into).

Answers the two questions that gate the whole Remote Script project, without
installing a Remote Script first:

  1. What MIDI do the pads and buttons actually send?   ->  --listen
  2. Can the host colour the pads by sending MIDI?      ->  --light / --colours

Nothing here touches Ableton. It talks straight to the SMC-PAD's MIDI ports.

IMPORTANT -- Windows MIDI ports are exclusive.
If Ableton has a port open, this script cannot open it and you will get an
"access denied" style error. Either close Live, or untick that port in
Preferences > Link/Tempo/MIDI before running.

Teardown: delete this file, run_probe.bat, requirements-midi.txt and the
venv-midi folder next to them. Nothing is written anywhere else.
"""

import argparse
import sys
import time

import mido

# The SMC-PAD's generic preset and its Mackie/DAW mode both sit on MIDI
# channel 1. Channel is 1-16 on the command line, 0-15 on the wire.
DEFAULT_CHANNEL = 1


def pick_port(names, wanted, kind):
    """Resolve a substring to exactly one port name, or explain what went wrong."""
    if not names:
        sys.exit("No MIDI %s ports found at all. Is the SMC-PAD plugged in and awake?" % kind)
    if wanted is None:
        sys.exit("Pass --port with part of a port name. Available %s ports:\n  %s"
                 % (kind, "\n  ".join(names)))
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
        sys.exit("Could not open any port. Close Live, or untick the SMC-PAD in "
                 "Preferences > Link/Tempo/MIDI.")
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
        _paced(port, [mido.Message("note_on", channel=ch, note=n, velocity=args.velocity)
                      for n in range(args.lo, args.hi + 1)])
        time.sleep(args.hold)
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
    if set(distinct) <= set([63, 64, 65]):
        return "relative"
    if set(distinct) <= set([1, 127]) or set(distinct) <= set([1, 64, 127]):
        return "relative"
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
                        per_cc.setdefault(msg.control, []).append(msg.value)
                    if not per_cc:
                        rows.append((bank, encoder, None, "-", 0, ""))
                        print("      nothing received")
                        continue
                    for cc in sorted(per_cc, key=lambda c: -len(per_cc[c])):
                        values = per_cc[cc]
                        mode = _classify(values)
                        distinct = sorted(set(values))
                        shown = ", ".join(str(v) for v in distinct[:6])
                        if len(distinct) > 6:
                            shown += ", ... (%d distinct)" % len(distinct)
                        rows.append((bank, encoder, cc, mode, len(values), shown))
                        print("      CC %-3d  %-9s  %d msgs  [%s]" % (cc, mode, len(values), shown))
                print()
        except (KeyboardInterrupt, EOFError):
            print("\n(stopped)\n")

    if not rows:
        return
    print("=== encoder map ===")
    print("  %-5s %-8s %-5s %-10s %6s  %s" % ("bank", "encoder", "CC", "mode", "msgs", "values"))
    for bank, encoder, cc, mode, n, shown in rows:
        print("  %-5d %-8d %-5s %-10s %6d  %s"
              % (bank, encoder, "-" if cc is None else cc, mode, n, shown))

    silent = [(b, e) for b, e, cc, _, _, _ in rows if cc is None]
    if silent:
        print("\nSent nothing: " + ", ".join("bank %d enc %d" % be for be in silent))
    seen = {}
    for bank, encoder, cc, _, _, _ in rows:
        if cc is not None:
            seen.setdefault((bank, cc), []).append(encoder)
    clashes = {k: v for k, v in seen.items() if len(v) > 1}
    for (bank, cc), encoders in sorted(clashes.items()):
        print("CLASH: bank %d CC %d came from encoders %s"
              % (bank, cc, ", ".join(str(e) for e in encoders)))


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


def velocity_list(text):
    if text == "all":
        return list(range(1, 128))
    if text == "coarse":
        # Enough to reveal a colour table without watching 127 steps.
        return [1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 40, 48, 60, 64, 80, 96, 112, 127]
    return [int(v) for v in text.split(",")]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", help="substring of the MIDI port name (see --list)")
    p.add_argument("--port2", help="second input port to watch simultaneously (--curves only)")
    p.add_argument("--channel", type=int, default=DEFAULT_CHANNEL, help="MIDI channel 1-16")
    p.add_argument("--lo", type=int, default=0, help="lowest note to touch")
    p.add_argument("--hi", type=int, default=127, help="highest note to touch")
    p.add_argument("--velocity", type=int, default=127, help="velocity for --light/--sweep")
    p.add_argument("--hold", type=float, default=3.0, help="seconds to hold each step")
    p.add_argument("--step", type=int, default=16, help="block size for --sweep")
    p.add_argument("--seconds", type=int, default=60, help="how long --listen runs")
    p.add_argument("--banks", type=int, default=2, help="knob banks to walk (--knobs)")
    p.add_argument("--count", type=int, default=8, help="encoders per bank (--knobs)")
    p.add_argument("--note", type=int, default=0, help="which note --colours walks")
    p.add_argument("--velocities", type=velocity_list, default="coarse",
                   help="'coarse', 'all', or a comma list, for --colours")

    mode = p.add_mutually_exclusive_group(required=True)
    for flag, fn in (("list", cmd_list), ("listen", cmd_listen), ("light", cmd_light),
                     ("sweep", cmd_sweep), ("colours", cmd_colours), ("clear", cmd_clear),
                     ("curves", cmd_curves), ("knobs", cmd_knobs)):
        mode.add_argument("--" + flag, dest="mode", action="store_const", const=fn)

    args = p.parse_args()
    args.mode(args)


if __name__ == "__main__":
    main()
