#!/usr/bin/env python3
"""Race results tracker - add and query your running history.

Data lives in races.json (the single source of truth, committed to git).
The website (index.html) is regenerated from it automatically whenever you
add or delete a race. See README.md for usage.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

DATA_PATH = Path(__file__).parent / "races.json"

DEFAULT_RUNNER = "Steve"

FIELDS = ["name", "date", "location", "overall_place", "overall_total",
          "gender_place", "gender_total", "division_place", "division_total",
          "pace", "final_time"]

# Each tuple: (name, date, location, overall_place, overall_total,
#              gender_place, gender_total, division_place, division_total, pace, final_time)
STEVE_RACES = [
    ("Cooper River Bridge Run", "2018-04-07", "Charleston, SC, USA", 13993, 27447, 7236, 11259, 679, 1116, "11:57", "1:14:17"),
    ("Fleet Feet Sports Soldier Field 10 Mile", "2013-05-25", "Chicago, IL, USA", 10114, 12593, 4739, 5348, 759, 869, "11:19", "1:53:19"),
    ("Hot Chocolate 15K/5K - Chicago", "2011-11-05", "Chicago, IL, USA", 10008, 18362, 3227, 4601, 387, 555, "11:43", "36:26"),
    ("Bank of America Shamrock Shuffle 2011", "2011-04-10", "Chicago, IL, USA", 20989, 32296, 10827, 13777, 1767, 2279, "11:01", "54:48"),
    ("Rock 'n' Roll Chicago 1/2 Marathon 2010", "2010-08-01", "Chicago, IL, USA", 14649, 18830, 5946, 6872, 985, 1110, "12:29", "2:43:37"),
    ("Fleet Feet Sports Soldier Field 10 Mile", "2010-05-29", "Chicago, IL, USA", 6604, 8329, 3235, 3685, 601, 681, "11:07", "1:51:18"),
    ("Bank of America Shamrock Shuffle 8K", "2010-03-21", "Chicago, IL, USA", 15153, 25573, 8591, 11526, 1412, 1934, "10:17", "51:12"),
    ("Rock 'n Roll Las Vegas Marathon", "2009-12-06", "Las Vegas, NV, USA", 10855, 17919, 4840, 6530, 937, 1203, "11:51", "2:35:18"),
    ("Pumpkins in the Park 5K 2009", "2009-10-17", "Chicago, IL, USA", 644, 1492, 337, 546, 53, 83, "9:22", "29:08"),
    ("Chicago Marathon", "2009-10-11", "Chicago, IL, USA", 28533, 33703, 16956, 19077, 2961, 3249, "12:17", "5:21:59"),
    ("The Chicago Half Marathon & 5k 2009", "2009-09-13", "Chicago, IL, USA", 11051, 13536, 5180, 5806, 878, 972, "11:50", "2:35:07"),
    ("Rock 'N' Roll Chicago Half Marathon 2009", "2009-08-02", "Chicago, IL, USA", 8073, 14453, 3711, 5111, 634, 853, "10:34", "2:18:36"),
    ("Fleet Feet Sports Soldier Field 10 Mile", "2009-05-23", "Chicago, IL, USA", 4639, 7478, 2517, 3321, 470, 639, "9:49", "1:38:18"),
    ("Trick Or Treat Trot 2008", "2008-10-26", "Chicago, IL, USA", 334, 918, 179, 332, 17, 35, "9:22", "29:07"),
    ("The 2008 Other Half", "2008-10-19", "Moab, UT, USA", 767, 1200, 310, 392, 61, 73, "10:44", "2:20:37"),
    ("The Banco Popular Chicago Half Marathon 2008", "2008-09-14", "Chicago, IL, USA", 6848, 10312, 3282, 4144, 550, 684, "10:36", "2:18:55"),
    ("Nike+ Human Race", "2008-08-31", "Chicago, IL, USA", 7213, 10299, 3727, 4588, 465, 583, "10:43", "1:06:41"),
    ("2008 Athens Sister City Shuffle", "2008-08-21", "Chicago, IL, USA", 505, 1478, 384, 806, 68, 130, "8:46", "27:15"),
    ("Muddy Buddy Chicago 2008", "2008-08-03", "Gilberts, IL, USA", 1558, 2398, 922, 1202, 210, 256, "11:49", "1:07:24"),
    ("Race To Wrigley Run 2008", "2008-04-19", "Chicago, IL, USA", 1133, 2009, 741, 1017, 97, 141, "9:23", "29:11"),
    ("Pumpkins In The Park 5K 2007", "2007-10-13", "Chicago, IL, USA", 723, 1432, 402, 568, 61, 84, "9:35", "29:47"),
    ("Aids Run & Walk Chicago 2007", "2007-09-15", "Chicago, IL, USA", 463, 704, 242, 313, 23, 31, "10:01", "31:08"),
    ("United Run For The Zoo 2007", "2007-06-03", "Chicago, IL, USA", 544, 1138, 297, 473, 52, 99, "9:38", "29:58"),
    ("2006 Salt Lake City Marathon & Half Marathon & 5K", "2006-06-03", "Salt Lake City, UT, USA", 1805, 1956, 1075, 1125, 197, 204, "13:15", "5:47:51"),
    ("The Other Half - Half Marathon 2005", "2005-10-23", "Moab, UT, USA", 423, 525, 184, 201, 42, 45, "11:20", "2:28:37"),
    ("Provo River Trail Half Marathon", "2005-08-13", "Orem, UT, USA", 1128, 1531, 502, 589, 87, 101, "10:24", "2:16:27"),
    ("Deseret Morning News/Jzz - Tv Marathon/10K", "2005-07-25", "Salt Lake City, UT, USA", 1453, 2011, 893, 1045, 88, 105, "9:42", "1:00:21"),
    ("Bryce Canyon Half Marathon & 5K", "2005-07-16", "Bryce Canyon, UT, USA", 298, 355, 136, 148, 22, 25, "10:52", "2:22:31"),
    ("Salt Lake City Classic", "2005-06-04", "Salt Lake City, UT, USA", 557, 655, 340, 370, 49, 52, "10:43", "1:06:36"),
    ("SLC Komen Race for the Cure", "2005-05-07", "Salt Lake City, UT, USA", 1174, 2117, 562, 823, 64, 97, "10:44", "33:23"),
    ("The Other Half - Half Marathon", "2004-10-23", "Moab, UT, USA", 331, 361, 126, 134, 23, 24, "11:49", "2:34:51"),
    ("Greek Festival 5K", "2004-09-11", "Salt Lake City, UT, USA", 206, 286, 120, 142, 12, 14, "10:12", "31:43"),
    ("Deseret Morning News 10K And Marathon 2004", "2004-07-24", "Salt Lake City, UT, USA", 1490, 1618, 796, 830, 108, 111, "10:44", "1:06:47"),
    ("Salt Lake City Classic", "2004-06-05", "Salt Lake City, UT, USA", 549, 840, 321, 385, 48, 52, "11:06", "34:30"),
    ("Salt Lake City Classic 2003", "2003-05-31", "Salt Lake City, UT, USA", 551, 840, 320, 384, 49, 52, "10:55", "33:58"),
]

KELLY_RACES = [
    ("Hot Chocolate 15K/5K - Chicago", "2014-11-09", "Chicago, IL, USA", 25704, 25849, 19291, 19397, 2413, 2427, "24:05", "1:14:51"),
    ("Fleet Feet Sports Soldier Field 10 Mile", "2014-05-24", "Chicago, IL, USA", 3500, 12281, 1249, 7179, 213, 1339, "9:00", "1:30:04"),
    ("Fleet Feet Sports Soldier Field 10 Mile", "2013-05-25", "Chicago, IL, USA", 4439, 12593, 1684, 7245, 387, 1633, "9:05", "1:30:55"),
    ("Fleet Feet Sports Soldier Field 10 Mile", "2012-05-26", "Chicago, IL, USA", 7314, 12858, 3350, 7325, 759, 1661, "10:08", "1:41:23"),
    ("Hot Chocolate 15K/5K - Chicago", "2011-11-05", "Chicago, IL, USA", 4316, 18362, 2348, 13725, 415, 2391, "10:11", "31:40"),
    ("Rock 'n' Roll Chicago 1/2 Marathon 2010", "2010-08-01", "Chicago, IL, USA", 7348, 18830, 3572, 11958, 723, 2228, "10:06", "2:12:22"),
    ("Fleet Feet Sports Women's Festival 2010", "2010-07-18", "Chicago, IL, USA", 433, 1472, 433, 1471, 114, 349, "9:25", "58:32"),
    ("Fleet Feet Sports Soldier Field 10 Mile", "2010-05-29", "Chicago, IL, USA", 4303, 8329, 1826, 4644, 417, 1119, "9:44", "1:37:28"),
    ("Rock 'n Roll Las Vegas Marathon", "2009-12-06", "Las Vegas, NV, USA", 8842, 17919, 4592, 11380, 925, 2044, "11:00", "2:24:09"),
    ("Pumpkins in the Park 5K 2009", "2009-10-17", "Chicago, IL, USA", 348, 1492, 132, 946, 29, 238, "8:23", "26:05"),
    ("Chicago Marathon", "2009-10-11", "Chicago, IL, USA", 18919, 33703, 6389, 14626, 1237, 2678, "10:20", "4:30:53"),
    ("Rock 'N' Roll Chicago Half Marathon 2009", "2009-08-02", "Chicago, IL, USA", 4617, 14453, 1993, 9336, 405, 1778, "9:22", "2:02:47"),
    ("Fleet Feet Sports Women's Festival 5K & 10K 2009", "2009-07-19", "Chicago, IL, USA", 389, 1507, 389, 1505, 90, 361, "8:53", "55:16"),
    ("Fleet Feet Sports Soldier Field 10 Mile", "2009-05-23", "Chicago, IL, USA", 4053, 7478, 1681, 3987, 371, 875, "9:29", "1:34:58"),
    ("Trick Or Treat Trot 2008", "2008-10-26", "Chicago, IL, USA", 334, 918, 151, 575, 58, 193, "9:22", "29:07"),
    ("The 2008 Other Half", "2008-10-19", "Moab, UT, USA", 767, 1200, 458, 806, 89, 150, "10:44", "2:20:37"),
    ("The Banco Popular Chicago Half Marathon 2008", "2008-09-14", "Chicago, IL, USA", 6864, 10312, 3564, 6150, 1079, 1769, "10:36", "2:18:59"),
    ("Nike+ Human Race", "2008-08-31", "Chicago, IL, USA", 7213, 10299, 3477, 5699, 1172, 1775, "10:43", "1:06:41"),
    ("2008 Athens Sister City Shuffle", "2008-08-21", "Chicago, IL, USA", 669, 1478, 190, 669, 41, 128, "9:13", "28:39"),
    ("Muddy Buddy Chicago 2008", "2008-08-03", "Gilberts, IL, USA", 1558, 2398, 637, 1196, 186, 332, "11:49", "1:07:24"),
    ("2008 She's Got Sole", "2008-06-22", "Chicago, IL, USA", 143, 285, 143, 285, 38, 60, "9:48", "48:44"),
    ("Race To Wrigley Run 2008", "2008-04-19", "Chicago, IL, USA", 1133, 2009, 393, 992, 166, 371, "9:23", "29:11"),
    ("Pumpkins In The Park 5K 2007", "2007-10-13", "Chicago, IL, USA", 726, 1432, 324, 864, 127, 280, "9:35", "29:48"),
    ("Aids Run & Walk Chicago 2007", "2007-09-15", "Chicago, IL, USA", 466, 704, 223, 391, 50, 89, "10:01", "31:09"),
    ("Women's 5K, 10K & Festival 2007", "2007-07-29", "Chicago, IL, USA", 924, 1372, 923, 1371, 316, 454, "10:31", "1:05:24"),
    ("United Run For The Zoo 2007", "2007-06-03", "Chicago, IL, USA", 544, 1138, 248, 665, 74, 198, "9:38", "29:58"),
    ("2006 Salt Lake City Marathon & Half Marathon & 5K", "2006-06-03", "Salt Lake City, UT, USA", 1805, 1956, 718, 818, 171, 190, "13:15", "5:47:51"),
    ("The Other Half - Half Marathon 2005", "2005-10-23", "Moab, UT, USA", 422, 525, 238, 323, 51, 61, "11:20", "2:28:36"),
    ("Provo River Trail Half Marathon", "2005-08-13", "Orem, UT, USA", 1129, 1531, 627, 942, 138, 199, "10:24", "2:16:32"),
    ("Deseret Morning News/Jzz - Tv Marathon/10K", "2005-07-25", "Salt Lake City, UT, USA", 1453, 2011, 557, 961, 103, 170, "9:42", "1:00:21"),
    ("Bryce Canyon Half Marathon & 5K", "2005-07-16", "Bryce Canyon, UT, USA", 297, 355, 162, 206, 42, 52, "10:52", "2:22:31"),
    ("Salt Lake City Classic", "2005-06-04", "Salt Lake City, UT, USA", 558, 655, 217, 284, 49, 69, "10:43", "1:06:37"),
    ("SLC Komen Race for the Cure", "2005-05-07", "Salt Lake City, UT, USA", 1177, 2117, 611, 1288, 118, 232, "10:44", "33:23"),
    ("The Other Half - Half Marathon", "2004-10-23", "Moab, UT, USA", 330, 361, 203, 225, 45, 51, "11:49", "2:34:50"),
    ("Greek Festival 5K", "2004-09-11", "Salt Lake City, UT, USA", 207, 286, 87, 144, 13, 23, "10:12", "31:43"),
    ("Deseret Morning News 10K And Marathon 2004", "2004-07-24", "Salt Lake City, UT, USA", 1490, 1618, 688, 781, 154, 171, "10:44", "1:06:47"),
    ("Salt Lake City Classic", "2004-06-05", "Salt Lake City, UT, USA", 549, 840, 229, 455, 50, 86, "11:06", "34:30"),
    ("Salt Lake City Classic 2003", "2003-05-31", "Salt Lake City, UT, USA", 551, 840, 232, 456, 48, 85, "10:55", "33:58"),
    ("28Th Annual Moab Half Marathon", "2003-03-15", "Moab, UT, USA", 1735, 2542, 785, 1377, 98, 167, "9:58", "2:10:40"),
]

SEED_DATA = {"Steve": STEVE_RACES, "Kelly": KELLY_RACES}


# --------------------------------------------------------------------------
# Storage: a single races.json file is the source of truth.
# --------------------------------------------------------------------------

def _seed_records():
    records = []
    for runner, races in SEED_DATA.items():
        for r in races:
            records.append(dict(runner=runner, **dict(zip(FIELDS, r))))
    return records


def load_races():
    """Return the list of race dicts, creating races.json from the historical
    seed the first time if it doesn't exist yet."""
    if not DATA_PATH.exists():
        records = _seed_records()
        save_races(records)
        return records
    with DATA_PATH.open() as f:
        return json.load(f)


def save_races(records):
    records = sorted(records, key=lambda r: r["date"], reverse=True)
    with DATA_PATH.open("w") as f:
        json.dump(records, f, indent=2)
        f.write("\n")


def rebuild_site():
    """Regenerate index.html from the current data."""
    try:
        import build_site
        build_site.build()
    except Exception as e:  # site rebuild is best-effort; data is already saved
        print(f"(Note: could not rebuild website automatically: {e})")
        print("Run 'python3 build_site.py' manually to refresh index.html.")


def fmt_place(place, total):
    if place and total:
        pct = round(place / total * 100)
        return f"{place:,} of {total:,} ({pct}%)"
    return "—"


def normalize_date(s):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s  # leave as-is if unrecognized


def parse_place(val):
    """Parse '1234 of 5678' or '1234/5678' into (place, total)."""
    if not val:
        return None, None
    parts = val.replace(" of ", "/").split("/")
    try:
        return int(parts[0].replace(",", "")), int(parts[1].replace(",", ""))
    except (IndexError, ValueError):
        return None, None


def cmd_add(args):
    # Use command-line flags when given, otherwise prompt interactively.
    interactive = not (args.name and args.date and args.time)

    if interactive:
        print("Add a new race result (press Enter to skip optional fields)")
        runner = args.runner or input(f"Runner [{DEFAULT_RUNNER}]: ").strip() or DEFAULT_RUNNER
        name = args.name or input("Race name: ").strip()
        date_str = args.date or input("Date (YYYY-MM-DD or MM/DD/YYYY): ").strip()
        location = args.location or input("Location (City, ST, Country): ").strip()
        final_time = args.time or input("Final time (H:MM:SS or M:SS): ").strip()
        pace = args.pace or (input("Pace (M:SS min/mi, optional): ").strip() or None)
        overall = args.overall or input("Overall place (e.g. 1234 of 5678, optional): ").strip()
        gender = args.gender or input("Gender place (e.g. 567 of 2345, optional): ").strip()
        division = args.division or input("Division place (e.g. 89 of 120, optional): ").strip()
    else:
        runner = args.runner or DEFAULT_RUNNER
        name, date_str, location = args.name, args.date, (args.location or "")
        final_time, pace = args.time, args.pace
        overall, gender, division = args.overall, args.gender, args.division

    op, ot = parse_place(overall)
    gp, gt = parse_place(gender)
    dp, dt = parse_place(division)

    record = {
        "runner": runner, "name": name, "date": normalize_date(date_str),
        "location": location, "overall_place": op, "overall_total": ot,
        "gender_place": gp, "gender_total": gt, "division_place": dp,
        "division_total": dt, "pace": pace, "final_time": final_time,
    }

    records = load_races()
    records.append(record)
    save_races(records)
    print(f"\nAdded ({runner}): {name} on {record['date']} — {final_time}")
    rebuild_site()
    print("Done. Commit & push to publish, or just ask Claude to do it.")


def cmd_list(args):
    rows = load_races()
    if args.runner:
        rows = [r for r in rows if r["runner"].lower() == args.runner.lower()]
    if args.year:
        rows = [r for r in rows if r["date"][:4] == str(args.year)]
    if args.search:
        q = args.search.lower()
        rows = [r for r in rows if q in r["name"].lower() or q in r["location"].lower()]
    rows.sort(key=lambda r: r["date"], reverse=True)
    if args.limit:
        rows = rows[:args.limit]

    if not rows:
        print("No races found.")
        return

    print(f"{'#':<4} {'Runner':<7} {'Date':<12} {'Race':<45} {'Time':<10} {'Pace':<9} {'Overall'}")
    print("-" * 118)
    for i, r in enumerate(rows, 1):
        overall = fmt_place(r.get("overall_place"), r.get("overall_total"))
        print(f"{i:<4} {r['runner']:<7} {r['date']:<12} {r['name'][:44]:<45} {r['final_time']:<10} {(r.get('pace') or '—'):<9} {overall}")

    print(f"\n{len(rows)} race(s) shown.")


def cmd_stats(args):
    data = load_races()
    runners = [args.runner] if args.runner else sorted({r["runner"] for r in data})

    for idx, runner in enumerate(runners):
        if idx:
            print()
        rows = sorted([r for r in data if r["runner"].lower() == runner.lower()],
                      key=lambda r: r["date"])
        if not rows:
            print(f"{runner}: no races found.")
            continue

        years = len({r["date"][:4] for r in rows})
        print(f"=== {rows[0]['runner']} ===")
        print(f"Total races:   {len(rows)}")
        print(f"Years active:  {years}")
        print(f"First race:    {rows[0]['date']}  {rows[0]['name']}")
        print(f"Latest race:   {rows[-1]['date']}  {rows[-1]['name']}")

        print("Races per year:")
        per_year = {}
        for r in rows:
            per_year[r["date"][:4]] = per_year.get(r["date"][:4], 0) + 1
        for yr in sorted(per_year, reverse=True):
            print(f"  {yr}  {'█' * per_year[yr]}  ({per_year[yr]})")


def cmd_delete(args):
    records = load_races()
    rows = sorted(records, key=lambda r: r["date"], reverse=True)
    print(f"{'#':<5} {'Runner':<7} {'Date':<12} {'Race'}")
    print("-" * 75)
    for i, r in enumerate(rows, 1):
        print(f"{i:<5} {r['runner']:<7} {r['date']:<12} {r['name']}")
    sel = input("\nEnter # to delete (or Enter to cancel): ").strip()
    if not sel:
        return
    try:
        target = rows[int(sel) - 1]
    except (ValueError, IndexError):
        print("Invalid selection.")
        return
    confirm = input(f"Delete {target['runner']}'s '{target['name']}' on {target['date']}? (y/N): ").strip().lower()
    if confirm == "y":
        records.remove(target)
        save_races(records)
        print("Deleted.")
        rebuild_site()


def main():
    parser = argparse.ArgumentParser(description="Race results tracker")
    sub = parser.add_subparsers(dest="cmd")

    ad = sub.add_parser("add", help="Add a new race result (prompts if flags omitted)")
    ad.add_argument("--runner", "-r", help="Runner name (default: Steve)")
    ad.add_argument("--name", help="Race name")
    ad.add_argument("--date", help="Date (YYYY-MM-DD or MM/DD/YYYY)")
    ad.add_argument("--location", help="Location, e.g. 'Chicago, IL, USA'")
    ad.add_argument("--time", help="Final time, e.g. 1:53:19 or 29:08")
    ad.add_argument("--pace", help="Pace, e.g. 9:30")
    ad.add_argument("--overall", help="Overall place, e.g. '1234 of 5678'")
    ad.add_argument("--gender", help="Gender place, e.g. '567 of 2345'")
    ad.add_argument("--division", help="Division place, e.g. '89 of 120'")

    ls = sub.add_parser("list", help="List races")
    ls.add_argument("--runner", "-r", help="Filter by runner (e.g. Steve, Kelly)")
    ls.add_argument("--year", "-y", type=int, help="Filter by year")
    ls.add_argument("--search", "-s", help="Search by name or location")
    ls.add_argument("--limit", "-n", type=int, help="Limit results")

    st = sub.add_parser("stats", help="Show overall stats")
    st.add_argument("--runner", "-r", help="Filter by runner (e.g. Steve, Kelly)")

    sub.add_parser("delete", help="Delete a race entry")

    args = parser.parse_args()

    if args.cmd == "add":
        cmd_add(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "stats":
        cmd_stats(args)
    elif args.cmd == "delete":
        cmd_delete(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
