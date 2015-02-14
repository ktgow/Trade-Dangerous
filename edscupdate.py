#! /usr/bin/env python

"""
Usage:
    edscupdate.py "<current system name>" ["<date>"]

This tool looks for changes in the EDSC service since the most
recent "modified" date in the System table or the date supplied
on the command line.

It then tries to do some validation but also requires user
confirmation.

For each star that appears to be new, it copies the name into
the clipboard so you can paste it into the "SEARCH" box in the
game to verify that the name is correct.

Additionally it shows you the distance from "current system"
to the star as a way to verify the co-ordinates.

This helps to catch cases where people have typo'd system names,
but given the right coordinates; it also helps catch cases where
people have used the star name from in-system which sometimes
differs from the star name in the galaxy map.

For each star you can type "y" to accept the star, "n" to skip it
or "q" to stop recording.
"""

import argparse
import math
import misc.clipboard
import misc.edsc
import os
import re
import sys
import tradedb


# Systems we know are bad.
ignore = []


class UsageError(Exception):
    """ Raised when command line usage is invalid. """
    pass


def get_cmdr(tdb):
    """ Look up the commander name """
    try:
        return os.environ['CMDR']
    except KeyError:
        pass

    if 'SHLVL' not in os.environ and platform.system() == 'Windows':
        how = 'set CMDR="yourname"'
    else:
        how = 'export CMDR="yourname"'

    raise UsageError(
        "No 'CMDR' variable set.\n"
        "You can set an environment variable by typing:\n"
        "  "+how+"\n"
        "at the command/shell prompt."
    )


def is_change(tdb, sysinfo):
    """ Check if a system's EDSC data is different than TDs """
    name = sysinfo['name'] = sysinfo['name'].upper()
    if name.startswith("argetl"):
        return False
    if name in ignore:
        return False
    x, y, z = sysinfo['coord']
    try:
        place = tdb.systemByName[name]
        if place.posX == x and place.posY == y and place.posZ == z:
            return False
    except KeyError:
        place = None
    sysinfo['place'] = place
    return True


def has_position_changed(sysinfo):
    place = sysinfo['place']
    if not place:
        return False

    print("! @{} [{},{},{}] vs @{} [{},{},{}]".format(
        name, x, y, z,
        place.dbname, place.posX, place.posY, place.posZ
    ))

    return True


def check_database(tdb, name, x, y, z):
    # is it in the database?
    cur = tdb.query("""
        SELECT name, pos_x, pos_y, pos_z
          FROM System
         WHERE pos_x BETWEEN ? and ?
           AND pos_y BETWEEN ? and ?
           AND pos_z BETWEEN ? and ?
    """, [ 
        x - 0.5, x + 0.5,
        y - 0.5, y + 0.5,
        z - 0.5, z + 0.5,
    ])
    for mname, mx, my, mz in cur:
        print(
                "! @{} [{},{},{}] matches coords for "
                "@{} [{},{},{}]".format(
                    name, x, y, z,
                    mname, mx, my, mz
        ), file=sys.stderr)


def get_distance(tdb, startSys, x, y, z):
    distance = tdb.calculateDistance(
        startSys.posX, startSys.posY, startSys.posZ,
        x, y, z
    )
    return float("{:.2f}".format(distance))


def main():
    if 'DEBUG' in os.environ or 'TEST' in os.environ:
        testMode = True
    else:
        testMode = False

    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: {} <origin system> [date]".format(sys.argv[0]))
        sys.exit(1)

    tdb = tradedb.TradeDB()
    date = tdb.query("SELECT MAX(modified) FROM System").fetchone()[0]

    cmdr = get_cmdr(tdb)

    startSys = tdb.lookupPlace(sys.argv[1])

    if len(sys.argv) > 2:
        date = sys.argv[2]
        if not date.startswith("201"):
            print("ERROR: Invalid date {}".format(date))
            sys.exit(2)

    print("start date: {}".format(date), file=sys.stderr)

    confidence = os.environ.get("CONF", 2)

    edsq = misc.edsc.StarQuery(
        test=testMode,
        confidence=confidence,
        date=date,
        )
    data = edsq.fetch()

    if edsq.status['statusnum'] != 0:
        raise Exception("Query failed: {} ({})".format(
                    edsq.status['msg'],
                    edsq.status['statusnum'],
                ))

    date = data['date']
    systems = data['systems']
    clip = misc.clipboard.SystemNameClip()

    print("{} results".format(len(systems)))
    # Filter out systems we already know that match the EDSC data.
    systems = [
        sysinfo for sysinfo in systems if is_change(tdb, sysinfo)
    ]
    print("{} deltas".format(len(systems)))

    if len(systems) <= 0:
        return

    print("At the prompt enter y, n or q. Default is n")
    print(
        "To correct a typo'd name that has the correct distance, "
        "use =correct name"
    )
    print()

    total = len(systems)
    current = 0
    with open("tmp/new.systems.csv", "a") as output:
        for sysinfo in systems:
            current += 1
            name = sysinfo['name']
            x, y, z = sysinfo['coord']

            if has_position_changed(sysinfo):
                continue

            check_database(tdb, name, x, y, z)

            created = sysinfo['createdate']

            distance = get_distance(tdb, startSys, x, y, z)
            clip.copy_text(name.lower())
            prompt = "{}/{}: '{}': {:.2f}ly? ".format(
                current, total,
                name,
                distance,
            )
            ok = input(prompt)
            if ok.lower() == 'q':
                break
            if ok.startswith('='):
                name = ok[1:].strip().upper()
                ok = 'y'
                with open("data/extra-stars.txt", "a") as fh:
                    print(name, file=fh)
                    print("Added to data/extra-stars.txt")
            if ok.lower() != 'y':
                continue

            print("'{}',{},{},{},'Release 1.00-EDStar','{}'".format(
                name, x, y, z, created,
            ), file=output)
            sub = misc.edsc.StarSubmission(
                star=name.upper(),
                commander=cmdr,
                distances={startSys.name(): distance},
                test=testMode,
            )
            r = sub.submit()
            result = misc.edsc.StarSubmissionResult(
                star=name.upper(),
                response=r,
            )

            print(str(result))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("^C")

