"""Fictional demo: Woodgrove Insurance, two weeks of board, committee and executive meetings in eleven rooms across three offices, the
VIP attendees' devices and 90 days of meeting-room incidents. Every name is made up; the problems are placed on purpose."""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ORG = "Woodgrove Insurance"
AS_OF = datetime(2026, 10, 25, 8, 0)
SEED = 33
TARGET = "5.4.112"

# room, site, platform, hardware, capacity, health, heartbeat (hours ago), version, next update, peripherals
ROOMS = [
    ("Boardroom", "Head office", "Teams Rooms on Windows", "Crestron Flex UC-C160 · ceiling mics · 2 displays", 22, "degraded", 0.2, "5.3.88",
     "2026-10-26 22:00", dict(display="degraded")),
    ("Board room 2", "Head office", "Teams Rooms on Windows", "Crestron Flex UC-C100 · table mics · 1 display", 14, "unhealthy", 0.1, TARGET, "",
     dict(microphone="disconnected")),
    ("ExCo room", "Head office", "Teams Rooms on Windows", "Logitech Rally Plus · Tap · 2 displays", 16, "healthy", 0.1, TARGET, "", {}),
    ("Studio", "Head office", "Teams Rooms on Windows", "Logitech Rally Bar · Tap · 1 display", 6, "healthy", 0.3, TARGET, "", {}),
    ("Lisbon board room", "Lisbon", "Teams Rooms on Android", "Poly Studio X70 · TC10", 12, "offline", 73.8, "5.2.41", "", {}),
    ("Barcelona board room", "Barcelona", "Teams Rooms on Android", "Poly Studio X50 · TC10", 10, "healthy", 0.5, "5.3.88", "", {}),
    ("Meeting room 4.2", "Head office", "Teams Rooms on Windows", "Logitech Rally Bar Mini · Tap", 8, "healthy", 0.2, TARGET, "", {}),
    ("Meeting room 4.5", "Head office", "Teams Rooms on Windows", "Logitech Rally Bar Mini · Tap", 8, "healthy", 0.4, "5.3.88", "", {}),
    ("Auditorium", "Head office", "Teams Rooms on Windows", "Crestron Flex · Logitech Rally Plus · stage mics", 120, "healthy", 0.1, TARGET,
     "2026-11-06 21:00", {}),
    ("Chair's office", "Head office", "", "", 6, "", None, "", "", {}),
    ("Training room", "Head office", "Teams Rooms on Windows", "Logitech Rally Bar · Tap", 20, "degraded", 0.6, TARGET, "", dict(console="degraded")),
]

# id, title, kind, start, end, room, hybrid, in room, remote, tech owner, check done, check planned
MEETINGS = [
    ("M01", "ExCo weekly", "executive", "2026-10-26 09:00", "2026-10-26 11:00", "ExCo room", "yes", 9, 2, "Workplace engineer A", "", ""),
    ("M02", "Board of Directors · Q3 results", "board", "2026-10-27 09:00", "2026-10-27 13:30", "Boardroom", "yes", 13, 3, "Workplace engineer A",
     "", "2026-10-26"),
    ("M03", "Audit Committee", "committee", "2026-10-28 10:00", "2026-10-28 12:30", "Board room 2", "yes", 6, 2, "Workplace engineer B",
     "2026-10-21", ""),
    ("M04", "Q3 results call · rehearsal", "other", "2026-10-29 13:30", "2026-10-29 14:45", "Boardroom", "yes", 5, 3, "Workplace engineer A", "", ""),
    ("M05", "Risk Committee", "committee", "2026-10-29 15:00", "2026-10-29 17:30", "Boardroom", "yes", 7, 1, "Workplace engineer A", "", "2026-10-22"),
    ("M06", "Q3 results · investor call", "investor", "2026-10-30 08:00", "2026-10-30 09:30", "Studio", "yes", 4, 180, "", "2026-10-23", ""),
    ("M07", "ExCo weekly", "executive", "2026-11-02 09:00", "2026-11-02 11:00", "ExCo room", "yes", 9, 2, "Workplace engineer B", "", ""),
    ("M08", "Credit Committee", "committee", "2026-11-02 11:10", "2026-11-02 12:30", "ExCo room", "yes", 8, 3, "Workplace engineer B", "", "2026-10-30"),
    ("M09", "Remuneration Committee", "committee", "2026-11-03 10:00", "2026-11-03 12:00", "Lisbon board room", "yes", 5, 2, "Lisbon IT", "", ""),
    ("M10", "Strategy workshop", "executive", "2026-11-04 09:00", "2026-11-04 17:00", "Meeting room 4.2", "yes", 12, 2, "Workplace engineer A", "", ""),
    ("M11", "Town hall · Q3", "town hall", "2026-11-05 16:00", "2026-11-05 17:00", "Auditorium", "yes", 95, 640, "Workplace engineer B", "", ""),
    ("M12", "Board · Iberia subsidiary", "board", "2026-11-05 10:00", "2026-11-05 13:00", "Barcelona board room", "yes", 7, 2, "Barcelona IT",
     "", "2026-11-04"),
    ("M13", "Nomination Committee", "committee", "2026-11-06 12:00", "2026-11-06 13:00", "Chair's office", "yes", 3, 1, "Workplace engineer A",
     "", "2026-11-05"),
    ("M14", "ExCo weekly", "executive", "2026-11-09 09:00", "2026-11-09 11:00", "ExCo room", "yes", 9, 2, "Workplace engineer B", "", ""),
    ("M00", "Board strategy day", "board", "2026-10-15 09:00", "2026-10-15 17:00", "Boardroom", "yes", 14, 2, "Workplace engineer A", "2026-10-14", ""),
]

# person: role, devices
PEOPLE = {
    "Chair": ("Chair of the Board", "IPAD-B01"),
    "CEO": ("Chief Executive", "IPAD-B02;IPH-E01"),
    "CFO": ("Chief Financial Officer", "MBP-E03;IPH-E03"),
    "COO": ("Chief Operating Officer", "MBP-E07"),
    "CRO": ("Chief Risk Officer", "MBP-E06"),
    "CHRO": ("HR Director", "MBP-E08"),
    "General Counsel": ("General Counsel", "IPAD-B12"),
    "Company Secretary": ("Company Secretary", "MBP-E05"),
    "NED 1": ("Non-executive director, Audit chair", "IPAD-B04"),
    "NED 2": ("Non-executive director", "IPAD-B05"),
    "NED 3": ("Non-executive director, Risk chair", "IPAD-B06"),
    "NED 4": ("Non-executive director, Remuneration chair", "IPAD-B07"),
    "NED 5": ("Non-executive director", "IPAD-B08"),
    "NED 6": ("Non-executive director", "IPAD-B09"),
    "NED 7": ("Non-executive director", "IPAD-B10"),
    "NED 8": ("Non-executive director", "IPAD-B11"),
    "Iberia director 1": ("Subsidiary director", "IPAD-S01"),
    "Iberia director 2": ("Subsidiary director", "IPAD-S02"),
    "Iberia director 3": ("Subsidiary director", ""),
}
EXCO = ["CEO", "CFO", "COO", "CRO", "CHRO", "General Counsel", "Company Secretary"]
BOARD = ["Chair", "CEO", "CFO"] + [f"NED {i}" for i in range(1, 9)] + ["Company Secretary", "General Counsel"]
ATTEND = {
    "M00": (BOARD, {"NED 5", "NED 8"}),
    "M01": (EXCO, {"COO"}), "M07": (EXCO, set()), "M14": (EXCO, set()), "M10": (EXCO, set()),
    "M02": (BOARD, {"NED 3", "NED 5", "NED 8"}),
    "M03": (["NED 1", "NED 2", "NED 6", "CFO", "CRO", "Company Secretary"], {"NED 6"}),
    "M04": (["CEO", "CFO"], set()),
    "M05": (["NED 3", "NED 7", "CRO", "CEO", "Company Secretary"], {"NED 7"}),
    "M06": (["CEO", "CFO"], set()),
    "M08": (["CRO", "CFO", "COO"], set()),
    "M09": (["NED 4", "NED 8", "Chair", "CHRO", "Company Secretary"], {"NED 8"}),
    "M11": (["CEO"], set()),
    "M12": (["Iberia director 1", "Iberia director 2", "Iberia director 3", "CEO", "General Counsel"], {"CEO"}),
    "M13": (["Chair", "NED 1", "Company Secretary"], set()),
}

# device, user, type, os, os version, compliant, check-in (days ago), board app, battery, warranty end, managed by
DEVICES = [
    ("IPAD-B01", "Chair", "iPad Pro 11", "iPadOS", "18.6", "yes", 12.4, "5.2.1", 88, "2027-09-30", "Jamf Pro"),
    ("IPAD-B02", "CEO", "iPad Pro 13", "iPadOS", "26.0.1", "yes", 0.3, "5.2.1", 95, "2028-03-31", "Jamf Pro"),
    ("IPH-E01", "CEO", "iPhone 15 Pro", "iOS", "26.0.1", "yes", 0.1, "", 84, "2026-11-20", "Intune"),
    ("MBP-E03", "CFO", "MacBook Pro 14", "macOS", "15.7", "yes", 0.2, "5.2.0", 91, "2027-06-30", "Jamf Pro"),
    ("IPH-E03", "CFO", "iPhone 16", "iOS", "26.0.1", "yes", 0.2, "", 97, "2027-10-31", "Intune"),
    ("MBP-E05", "Company Secretary", "MacBook Air 13", "macOS", "15.7", "yes", 0.4, "5.2.1", 89, "2027-12-31", "Jamf Pro"),
    ("MBP-E06", "CRO", "MacBook Pro 14", "macOS", "15.7", "yes", 1.2, "5.2.1", 93, "2028-01-31", "Jamf Pro"),
    ("MBP-E07", "COO", "MacBook Air 13", "macOS", "15.6", "yes", 0.6, "5.2.1", 86, "2027-04-30", "Jamf Pro"),
    ("MBP-E08", "CHRO", "MacBook Air 13", "macOS", "15.7", "yes", 2.1, "5.2.1", 82, "2026-08-31", "Jamf Pro"),
    ("IPAD-B04", "NED 1", "iPad Air 11", "iPadOS", "18.6", "yes", 0.9, "5.2.1", 92, "2027-09-30", "Jamf Pro"),
    ("IPAD-B05", "NED 2", "iPad Air 11", "iPadOS", "18.6", "yes", 1.4, "5.2.1", 71, "2027-03-31", "Jamf Pro"),
    ("IPAD-B06", "NED 3", "iPad Air 11", "iPadOS", "18.6", "yes", 0.8, "5.2.1", 90, "2027-09-30", "Jamf Pro"),
    ("IPAD-B07", "NED 4", "iPad Air 11", "iPadOS", "18.5", "yes", 3.0, "4.8.3", 87, "2027-09-30", "Jamf Pro"),
    ("IPAD-B08", "NED 5", "iPad Air 11", "iPadOS", "18.6", "yes", 0.7, "5.2.1", 94, "2027-09-30", "Jamf Pro"),
    ("IPAD-B09", "NED 6", "iPad Air 11", "iPadOS", "18.6", "no", 0.5, "5.2.1", 90, "2027-09-30", "Jamf Pro"),
    ("IPAD-B10", "NED 7", "iPad Air 10.9", "iPadOS", "17.7", "yes", 1.9, "5.0.2", 83, "2026-12-15", "Jamf Pro"),
    ("IPAD-B11", "NED 8", "iPad Air 11", "iPadOS", "18.6", "yes", 0.6, "5.2.1", 91, "2027-09-30", "Jamf Pro"),
    ("IPAD-B12", "General Counsel", "iPad Pro 11", "iPadOS", "18.6", "yes", 0.4, "5.2.1", 89, "2027-09-30", "Jamf Pro"),
    ("IPAD-S01", "Iberia director 1", "iPad Air 11", "iPadOS", "18.6", "yes", 2.2, "5.2.1", 92, "2028-02-29", "Jamf Pro"),
    ("IPAD-S02", "Iberia director 2", "iPad Air 11", "iPadOS", "18.6", "yes", 4.1, "5.2.1", 88, "2028-02-29", "Jamf Pro"),
]

# placed incidents: days ago, room, device, meeting, category, minutes lost, summary
PLACED = [
    (10, "Boardroom", "", "M00", "Display", 12, "Display 2 lost signal twice during the strategy day; reconnected at the switcher"),
    (24, "Boardroom", "", "", "Display", 6, "Display 2 flickering at the start of a committee meeting"),
    (41, "Boardroom", "", "", "Audio", 15, "Echo for remote attendees; ceiling mic gain reset after a firmware update"),
    (58, "Boardroom", "", "", "Display", 9, "Display 2 black after the room woke up; power cycle"),
    (76, "Boardroom", "", "", "Content sharing", 7, "HDMI ingest not detected; used wireless share"),
    (2, "Board room 2", "", "", "Audio", 25, "Table microphone array not detected by the room; meeting moved to the ExCo room"),
    (3, "Lisbon board room", "", "", "Network", 30, "Room offline after a switch change at the Lisbon office"),
    (33, "Lisbon board room", "", "", "Join", 18, "Room could not join; resource account password expired"),
    (61, "Lisbon board room", "", "", "Camera", 11, "Camera frozen; reboot of the Studio X70"),
    (10, "", "IPAD-B07", "M00", "Board app", 8, "Board app closed while opening the pack; reinstalled"),
    (27, "", "IPAD-B01", "", "Device sync", 5, "Pack annotations not synced; fixed after sign-in"),
]
FILLER_ROOMS = ["ExCo room", "Meeting room 4.2", "Meeting room 4.5", "Auditorium", "Studio", "Training room", "Barcelona board room"]
FILLER = [("Join", "Teams meeting did not start from the console; joined from the Tap again"),
          ("Content sharing", "Laptop could not share to the room; cable replaced"),
          ("Audio", "Remote attendees could not hear the room; speaker set back to default"),
          ("Camera", "Camera framing stuck on one side; reset"),
          ("Room console", "Touch console unresponsive; restarted")]


def _rows() -> dict[str, list[list]]:
    rnd = random.Random(SEED)
    rooms = []
    for r, site, plat, hw, cap, health, hb, ver, upd, per in ROOMS:
        beat = "" if hb is None else (AS_OF - timedelta(hours=hb)).strftime("%Y-%m-%d %H:%M")
        if not plat:
            rooms.append([r, site, "", hw, cap, "", "", "", "", "", "", "", "", "", ""])
            continue
        st = {p: per.get(p, "ok") for p in ("camera", "microphone", "speaker", "display", "console")}
        rooms.append([r, site, plat, hw, cap, health.title(), beat, ver, TARGET, upd, st["camera"], st["microphone"], st["speaker"], st["display"],
                      st["console"]])
    meetings = [list(m) for m in MEETINGS]
    att = []
    for mid, (names, remote) in ATTEND.items():
        for n in names:
            role, devs = PEOPLE[n]
            att.append([mid, n, role, "yes", devs, "yes" if n in remote else "no"])
    devices = []
    for dv, user, kind, os_, ver, comp, ago, app, bat, war, mdm in DEVICES:
        devices.append([dv, user, kind, os_, ver, comp, (AS_OF - timedelta(days=ago)).strftime("%Y-%m-%d %H:%M"), app, bat, war, mdm])
    inc = []
    for ago, room, dev, mid, cat, mins, text in PLACED:
        t = AS_OF - timedelta(days=ago) + timedelta(hours=rnd.choice([1, 2, 3, 5, 6]))
        inc.append([t, room, dev, mid, cat, mins, text])
    for k in range(14):
        cat, text = FILLER[k % len(FILLER)]
        t = AS_OF - timedelta(days=rnd.randint(1, 88), hours=-rnd.randint(1, 9))
        inc.append([t, FILLER_ROOMS[k % len(FILLER_ROOMS)], "", "", cat, rnd.choice([0, 3, 4, 5, 6, 8, 10]), text])
    inc.sort(key=lambda x: x[0])
    inc = [[f"INC{4100 + i}", t.strftime("%Y-%m-%d %H:%M")] + rest for i, (t, *rest) in enumerate(inc)]
    return dict(rooms=rooms, meetings=meetings, attendees=att, devices=devices, incidents=inc)


HEADERS = {
    "meetings": ["Meeting ID", "Title", "Type", "Start", "End", "Room", "Hybrid", "In room", "Remote", "Tech owner", "Tech check done",
                 "Tech check planned"],
    "rooms": ["Room", "Site", "Platform", "Hardware", "Capacity", "Health", "Last heartbeat", "Version", "Target version", "Next update", "Camera",
              "Microphone", "Speaker", "Display", "Console"],
    "attendees": ["Meeting ID", "Name", "Role", "VIP", "Devices", "Remote"],
    "devices": ["Device ID", "User", "Type", "OS", "OS version", "Compliant", "Last check-in", "Board app version", "Battery health", "Warranty end",
                "Managed by"],
    "incidents": ["Ticket", "Date", "Room", "Device", "Meeting ID", "Category", "Minutes lost", "Summary"],
}

SETTINGS = {
    "organisation": ORG,
    "as_of": AS_OF.strftime("%Y-%m-%d %H:%M"),
    "horizon_days": 14,
    "tech_check_kinds": ["board", "committee", "investor", "agm"],
    "tech_check_window_days": 7,
    "tech_check_lead_days": 3,
    "setup_minutes": 30,
    "heartbeat_hours": 24,
    "freeze_hours": 48,
    "checkin_days": 7,
    "min_os": {"iPadOS": "18.0", "iOS": "18.0", "macOS": "15.0"},
    "min_app_version": "5.0",
    "app_name": "Board app",
    "battery_min_pct": 80,
    "warranty_warn_days": 60,
    "repeat_incidents": 3,
    "incident_window_days": 90,
    "owners": {"meetings": "Executive support lead", "rooms": "Workplace AV team", "devices": "VIP support", "incidents": "Workplace AV team"},
}


def write(folder: Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, rows in _rows().items():
        with open(folder / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(HEADERS[name])
            w.writerows(rows)
    (folder / "settings.json").write_text(json.dumps(SETTINGS, indent=2) + "\n", encoding="utf-8")
    return folder
