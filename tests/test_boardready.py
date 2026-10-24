import csv
import hashlib
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from boardready import cli
from boardready.checks import CRITICAL, INFO, ORDER, WARNING, device_state, meeting_rows, room_state, run_all
from boardready.model import (Attendee, Data, Device, Incident, Meeting, Room, Settings, kind_of, load, load_attendees, load_devices,
                              load_meetings, load_rooms, settings_from_dict, version)

AS_OF = datetime(2026, 10, 25, 8, 0)


def write(path: Path, header: list[str], rows: list[list], delimiter: str = ",") -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=delimiter)
        w.writerow(header)
        w.writerows(rows)
    return path


def at(days: float, hour: int = 10) -> datetime:
    return datetime.combine(AS_OF.date() + timedelta(days=days), datetime.min.time()) + timedelta(hours=hour)


def room(name="Boardroom", **kw) -> Room:
    base = dict(site="HQ", platform="Teams Rooms on Windows", hardware="Crestron Flex", capacity=20, health="healthy",
                heartbeat=AS_OF - timedelta(minutes=10), version="5.4.112", target="5.4.112")
    base.update(kw)
    return Room(name, **base)


def meeting(mid="M1", days=5, room_name="Boardroom", kind="board", **kw) -> Meeting:
    title = kw.pop("title", f"Meeting {mid}")
    base = dict(hybrid=True, in_room=10, remote=2, tech_owner="Engineer A", check_done=(AS_OF + timedelta(days=days - 1)).date())
    base.update(kw)
    st = at(days)
    return Meeting(mid, title, st, st + timedelta(hours=2), room_name, kind, **base)


def device(did="IPAD-1", **kw) -> Device:
    base = dict(user="Chair", kind="iPad Air", os="iPadOS", os_version="18.6", compliant=True, checkin=AS_OF - timedelta(hours=5),
                app_version="5.2.1", battery=90.0, warranty=date(2028, 1, 1), managed_by="Jamf Pro")
    base.update(kw)
    return Device(did, **base)


def data(meetings=None, rooms=None, attendees=None, devices=None, incidents=None, **kw) -> Data:
    s = kw.pop("settings", settings_from_dict({"min_app_version": "5.0"}))
    return Data(s, AS_OF, meetings or [meeting()], rooms if rooms is not None else [room()], attendees or [], devices or [], incidents or [])


def issues(d: Data, mid: str = "M1") -> dict:
    r = next(x for x in meeting_rows(d) if x["meeting"].meeting_id == mid)
    return {i.code: i for i in r["issues"]}, r


class TestLoading(unittest.TestCase):
    def test_meetings_with_other_names_and_semicolons(self):
        with tempfile.TemporaryDirectory() as t:
            p = write(Path(t) / "m.csv", ["ID", "Asunto", "Tipo", "Inicio", "Fin", "Sala", "Híbrida", "Presenciales", "Remotos", "Soporte", "Ensayo"],
                      [["1", "Consejo de Administración", "", "27/10/2026 09:00", "27/10/2026 13:00", "Boardroom", "sí", "12", "3", "Ana", "26/10/2026"],
                       ["2", "Audit Committee", "", "2026-10-28 10:00", "", "Board room 2", "no", "6", "", "", ""]], delimiter=";")
            ms = load_meetings(p)
        self.assertEqual([(m.kind, m.hybrid, m.in_room, m.remote, m.check_done) for m in ms],
                         [("board", True, 12, 3, date(2026, 10, 26)), ("committee", False, 6, 0, None)])
        self.assertEqual(ms[1].end, datetime(2026, 10, 28, 11, 0))
        self.assertEqual((kind_of("", "ExCo weekly"), kind_of("Junta general")), ("executive", "agm"))

    def test_rooms_devices_and_attendees(self):
        with tempfile.TemporaryDirectory() as t:
            r = write(Path(t) / "r.csv", ["Display name", "Platform", "Health status", "Last heartbeat", "Current version", "Available version",
                                          "Room camera", "Mic", "Pantalla"],
                      [["Boardroom", "Teams Rooms on Windows", "Degraded", "2026-10-25T07:50:00", "5.3.88", "5.4.112", "Healthy", "", "intermittent"],
                       ["Chair's office", "none", "", "", "", "", "", "", ""]])
            rooms = load_rooms(r)
            v = write(Path(t) / "d.csv", ["Device name", "Assigned to", "Operating system", "OS version", "Compliance state", "Last sync date time",
                                          "Battery health"],
                      [["IPAD-1", "Chair", "iPadOS", "18.6", "noncompliant", "2026-10-20 10:00", "79 %"], ["IPAD-2", "NED", "iPadOS", "18.6", "", "", ""]])
            devs = load_devices(v)
            a = write(Path(t) / "a.csv", ["Meeting", "Attendee", "Cargo", "Device IDs", "Remoto"], [["M1", "Chair", "Chair", "IPAD-1; IPH-1", "no"]])
            att = load_attendees(a)
        self.assertEqual((rooms[0].health, rooms[0].peripherals, rooms[1].platform), ("degraded", {"camera": "ok", "display": "degraded"}, ""))
        self.assertEqual([(x.compliant, x.battery) for x in devs], [(False, 79.0), (None, None)])
        self.assertEqual((att[0].devices, att[0].vip, att[0].remote), (["IPAD-1", "IPH-1"], True, False))
        self.assertLess(version("5.3.88"), version("5.4.112"))

    def test_settings_and_required_file(self):
        s = settings_from_dict({"as_of": "2026-10-25 08:00", "min_os": {"iPadOS": "26.0"}, "owners": {"rooms": "AV"}, "setup_minutes": "15"})
        self.assertEqual((s.min_os["ipados"], s.min_os["macos"], s.owner("rooms"), s.owner("devices"), s.setup_minutes),
                         ("26.0", "15.0", "AV", "VIP support", 15))
        with tempfile.TemporaryDirectory() as t, self.assertRaises(FileNotFoundError):
            load(Path(t))


class TestMeetings(unittest.TestCase):
    def test_ready_meeting_and_horizon(self):
        d = data(meetings=[meeting(), meeting("M2", days=20), meeting("M0", days=-3)])
        iss, r = issues(d)
        self.assertEqual((iss, r["verdict"], r["check"]), ({}, "ready", f"done {at(4):%d %b}"))
        self.assertEqual([x["meeting"].meeting_id for x in meeting_rows(d)], ["M1"])

    def test_tech_check_rules(self):
        cases = {"M1": meeting("M1", days=2, check_done=None),                                  # close, nothing: critical
                 "M2": meeting("M2", days=6, check_done=None),                                  # later, nothing: warning
                 "M3": meeting("M3", days=6, check_done=None, check_planned=AS_OF.date() + timedelta(days=4)),
                 "M4": meeting("M4", days=6, check_done=None, check_planned=AS_OF.date() - timedelta(days=2)),
                 "M5": meeting("M5", days=6, check_done=AS_OF.date() - timedelta(days=5)),       # 11 days before: too old
                 "M6": meeting("M6", days=2, kind="executive", check_done=None)}                 # not required
        rooms = [room(f"R{k}") for k in range(1, 7)]
        for k, m in enumerate(cases.values(), 1):
            m.room = f"R{k}"
        d = data(meetings=list(cases.values()), rooms=rooms)
        got = {mid: (issues(d, mid)[0].get("MTG-01").severity if "MTG-01" in issues(d, mid)[0] else None) for mid in cases}
        self.assertEqual(got, {"M1": CRITICAL, "M2": WARNING, "M3": None, "M4": WARNING, "M5": WARNING, "M6": None})
        self.assertIn("not recorded as done", issues(d, "M4")[0]["MTG-01"].text)

    def test_room_fit_overlap_and_setup_gap(self):
        a = meeting("A", days=3)
        b = meeting("B", days=3)
        b.start, b.end = a.end - timedelta(minutes=30), a.end + timedelta(hours=1)
        c = meeting("C", days=4, kind="executive")
        e = meeting("E", days=4, kind="executive")
        e.start, e.end = c.end + timedelta(minutes=10), c.end + timedelta(hours=1)
        small = meeting("S", days=5, room_name="Small", in_room=9)
        office = meeting("O", days=5, room_name="Office", in_room=2)
        d = data(meetings=[a, b, c, e, small, office], rooms=[room(), room("Small", capacity=6), room("Office", platform="")])
        self.assertEqual(issues(d, "A")[0]["MTG-03"].severity, CRITICAL)
        self.assertEqual(issues(d, "B")[0]["MTG-03"].severity, CRITICAL)
        self.assertNotIn("MTG-03", issues(d, "C")[0])
        self.assertEqual(issues(d, "E")[0]["MTG-03"].severity, WARNING)
        self.assertIn("9 people in a room for 6", issues(d, "S")[0]["MTG-02"].text)
        self.assertIn("no Teams Room", issues(d, "O")[0]["MTG-02"].text)

    def test_support_engineer(self):
        iss, _ = issues(data(meetings=[meeting(tech_owner="")]))
        self.assertEqual(iss["MTG-04"].severity, WARNING)


class TestRooms(unittest.TestCase):
    def test_health_peripherals_and_freeze(self):
        m = meeting(days=3)
        rooms = [room(health="offline", heartbeat=AS_OF - timedelta(days=3))]
        self.assertEqual(issues(data(meetings=[m], rooms=rooms))[0]["ROOM-01"].severity, CRITICAL)
        stale = [room(heartbeat=AS_OF - timedelta(hours=30))]
        self.assertIn("ROOM-01", issues(data(meetings=[m], rooms=stale))[0])
        # a fault in a peripheral makes the room unhealthy: reported once, as the peripheral
        mic = [room(health="unhealthy", peripherals={"microphone": "disconnected", "display": "degraded"},
                    next_update=m.start - timedelta(hours=12))]
        iss, r = issues(data(meetings=[m], rooms=mic))
        self.assertNotIn("ROOM-01", iss)
        self.assertEqual([(i.severity, i.text) for i in r["issues"] if i.code == "ROOM-02"],
                         [(CRITICAL, "microphone disconnected"), (WARNING, "display degraded")])
        self.assertEqual(iss["ROOM-03"].severity, WARNING)
        m.hybrid = False
        self.assertEqual(issues(data(meetings=[m], rooms=mic))[0]["ROOM-02"].severity, WARNING)

    def test_repeat_incidents_and_versions(self):
        inc = [Incident(AS_OF - timedelta(days=k * 20), "Boardroom", category="Display", minutes_lost=10) for k in range(1, 4)]
        inc.append(Incident(AS_OF - timedelta(days=120), "Boardroom", category="Audio", minutes_lost=30))     # outside the window
        d = data(rooms=[room(version="5.3.88")], incidents=inc)
        st = room_state(d, d.rooms[0])
        self.assertEqual((len(st["incidents"]), st["minutes"], st["repeat"], st["behind"]), (3, 30.0, True, True))
        f = {x.code: x for x in run_all(d)}
        self.assertEqual((f["INC-01"].severity, f["ROOM-04"].severity, f["INC-02"].subject),
                         (WARNING, INFO, "3 incidents and 30 minutes lost in 90 days"))


class TestDevices(unittest.TestCase):
    def test_device_states(self):
        d = data()
        ok = device_state(d, device())
        self.assertEqual((ok["critical"], ok["warning"], ok["notes"]), ([], [], []))
        bad = device_state(d, device(compliant=False, checkin=AS_OF - timedelta(days=9), os_version="17.7", app_version="4.8.3", battery=71,
                                     warranty=date(2026, 11, 20)))
        self.assertEqual(bad["critical"], ["not compliant", "last check-in 9 days ago"])
        self.assertEqual(bad["warning"], ["iPadOS 17.7 below 18.0", "Board app 4.8.3 below 5.0", "battery health 71%"])
        self.assertEqual(bad["notes"], ["warranty ends 20 Nov 2026"])
        self.assertEqual(device_state(d, device(os="macOS", kind="MacBook", os_version="14.7"))["warning"], ["macOS 14.7 below 15.0"])

    def test_vip_attendees_in_meetings(self):
        att = [Attendee("M1", "Chair", devices=["IPAD-1"]), Attendee("M1", "NED 1", devices=["IPAD-2"]), Attendee("M1", "NED 2"),
               Attendee("M1", "Guest", vip=False), Attendee("M1", "NED 3", devices=["IPAD-X"])]
        devs = [device("IPAD-1", checkin=None), device("IPAD-2", battery=70)]
        iss, r = issues(data(attendees=att, devices=devs))
        codes = sorted(i.code for i in r["issues"])
        self.assertEqual(codes, ["DEV-01", "DEV-03", "DEV-04", "DEV-04"])
        self.assertEqual((r["verdict"], len(r["people"])), ("at risk", 4))
        self.assertIn("never checked in", iss["DEV-01"].text)


class TestDemo(unittest.TestCase):
    def test_demo_end_to_end_is_deterministic(self):
        hashes = []
        with tempfile.TemporaryDirectory() as t:
            for k in range(2):
                out = Path(t) / f"out{k}"
                self.assertEqual(cli.main(["demo", "--data", str(Path(t) / f"data{k}"), "--out", str(out)]), 0)
                self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(cli.OUTPUTS))
                hashes.append({n: hashlib.sha1((out / n).read_bytes()).hexdigest() for n in cli.OUTPUTS})
            self.assertEqual(hashes[0], hashes[1])
            d = load(Path(t) / "data0")
        f = run_all(d)
        self.assertEqual([x.severity for x in f], sorted((x.severity for x in f), key=ORDER.get))
        for c in ("MTG-01", "MTG-02", "MTG-03", "MTG-04", "ROOM-01", "ROOM-02", "ROOM-03", "ROOM-04", "DEV-01", "DEV-02", "DEV-03", "DEV-04",
                  "DEV-05", "INC-01", "INC-02"):
            self.assertIn(c, {x.code for x in f})
        verdicts = {r["meeting"].meeting_id: r["verdict"] for r in meeting_rows(d)}
        self.assertEqual(sorted(k for k, v in verdicts.items() if v == "ready"), ["M01", "M07", "M11"])
        self.assertNotIn("M14", verdicts)
        self.assertEqual(d.settings.organisation, "Woodgrove Insurance")

    def test_review_reports_a_missing_meeting_list(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)


if __name__ == "__main__":
    unittest.main()
