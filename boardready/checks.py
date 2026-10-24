"""The checks: for every meeting in the horizon, the tech check, the room (fit, health, peripherals, updates, history), the VIP attendees'
devices and the support plan, with a verdict per meeting. Each finding says what to do and who owns it."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from .model import Data, Device, Meeting, Room, _norm, version

CRITICAL, WARNING, INFO = "critical", "warning", "info"
ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}
AREAS = ("Meetings", "Rooms", "Devices", "Incidents")
AV = ("camera", "microphone", "speaker")
VERDICT = {CRITICAL: "at risk", WARNING: "attention", None: "ready"}


@dataclass
class Finding:
    severity: str
    area: str
    code: str
    subject: str
    detail: str
    fix: str
    owner: str = ""
    items: list[str] = field(default_factory=list)


@dataclass
class Issue:
    severity: str
    code: str
    text: str


def _n(k: int, word: str, plural: str | None = None) -> str:
    return f"{k} {word if k == 1 else (plural or word + 's')}"


def _top(items: list[str], k: int = 6) -> str:
    return ", ".join(items[:k]) + (f" and {len(items) - k} more" if len(items) > k else "")


def _when(m: Meeting) -> str:
    return f"{m.start:%a %d %b %H:%M}"


# ---------------------------------------------------------------- rooms and devices

def recent_incidents(d: Data) -> list:
    since = d.as_of - timedelta(days=d.settings.incident_window_days)
    return [i for i in d.incidents if since <= i.date <= d.as_of]


def room_state(d: Data, r: Room) -> dict:
    s = d.settings
    stale = r.heartbeat is None or (d.as_of - r.heartbeat) > timedelta(hours=s.heartbeat_hours)
    faults = {p: st for p, st in r.peripherals.items() if st != "ok"}
    down = r.health == "offline" or (r.health == "unhealthy" and not faults) or (bool(r.platform) and stale)
    behind = bool(r.target and r.version and version(r.version) < version(r.target))
    inc = [i for i in recent_incidents(d) if i.room and _norm(i.room) == _norm(r.room)]
    return dict(room=r, down=down, stale=stale, faults=faults, behind=behind, incidents=inc,
                minutes=sum(i.minutes_lost for i in inc), repeat=len(inc) >= s.repeat_incidents)


def _os_key(dev: Device) -> str:
    n = _norm(dev.os or dev.kind)
    for k in ("ipados", "ios", "macos", "windows"):
        if k in n:
            return k
    if "ipad" in n:
        return "ipados"
    if "iphone" in n:
        return "ios"
    if "mac" in n:
        return "macos"
    return n


def device_state(d: Data, dev: Device) -> dict:
    """Issues of one device, judged at the review time: not ready (critical), to fix (warning) and for information (notes)."""
    s = d.settings
    crit, warn, notes = [], [], []
    if dev.compliant is False:
        crit.append("not compliant")
    if dev.checkin is None:
        crit.append("never checked in")
    elif (d.as_of - dev.checkin).days > s.checkin_days:
        crit.append(f"last check-in {(d.as_of - dev.checkin).days} days ago")
    mn = s.min_os.get(_os_key(dev))
    if mn and dev.os_version and version(dev.os_version) < version(mn):
        warn.append(f"{dev.os or 'OS'} {dev.os_version} below {mn}")
    if s.min_app_version and dev.app_version and version(dev.app_version) < version(s.min_app_version):
        warn.append(f"{s.app_name} {dev.app_version} below {s.min_app_version}")
    if dev.battery is not None and dev.battery < s.battery_min_pct:
        warn.append(f"battery health {dev.battery:g}%")
    if dev.warranty and (dev.warranty - d.today).days <= s.warranty_warn_days:
        notes.append(f"warranty {'ended' if dev.warranty < d.today else 'ends'} {dev.warranty:%d %b %Y}")
    return dict(device=dev, critical=crit, warning=warn, notes=notes)


# ---------------------------------------------------------------- per meeting

def meeting_rows(d: Data) -> list[dict]:
    s = d.settings
    ups = d.upcoming()
    rooms = {r.room: room_state(d, r) for r in d.rooms}
    by_room = defaultdict(list)
    for m in sorted(d.meetings, key=lambda m: m.start):
        by_room[_norm(m.room)].append(m)
    rows = []
    for m in ups:
        iss: list[Issue] = []
        add = lambda sev, code, text: iss.append(Issue(sev, code, text))  # noqa: E731
        # tech check
        needs = m.kind in s.tech_check_kinds
        check = "not required"
        if needs:
            lo = m.start.date() - timedelta(days=s.tech_check_window_days)
            if m.check_done and lo <= m.check_done <= m.start.date():
                check = f"done {m.check_done:%d %b}"
            elif m.check_planned and d.today <= m.check_planned <= m.start.date():
                check = f"planned {m.check_planned:%d %b}"
            else:
                check = "missing"
                why = (f"tech check planned {m.check_planned:%d %b} and not recorded as done" if m.check_planned and m.check_planned < d.today
                       else f"last tech check {m.check_done:%d %b}, more than {s.tech_check_window_days} days before" if m.check_done
                       else "no tech check done or planned")
                soon = (m.start - d.as_of) <= timedelta(days=s.tech_check_lead_days)
                add(CRITICAL if soon else WARNING, "MTG-01", why)
        # room fit
        rs = next((v for k, v in rooms.items() if _norm(k) == _norm(m.room)), None)
        r = rs["room"] if rs else None
        if r is None:
            if d.rooms:
                add(CRITICAL if m.hybrid else WARNING, "MTG-02", f"room '{m.room}' is not in the room register")
        else:
            if r.capacity and m.in_room > r.capacity:
                add(CRITICAL, "MTG-02", f"{m.in_room} people in a room for {r.capacity}")
            if m.hybrid and not r.platform:
                add(CRITICAL, "MTG-02", f"hybrid meeting with {m.remote} remote in a room with no Teams Room")
        # neighbours in the same room
        others = [o for o in by_room[_norm(m.room)] if o is not m]
        for o in others:
            if o.start < m.end and m.start < o.end:
                add(CRITICAL, "MTG-03", f"overlaps '{o.title}' ({o.start:%H:%M}–{o.end:%H:%M}) in the same room")
        before = [o for o in others if o.end <= m.start and o.end.date() == m.start.date()]
        if before and not any(i.code == "MTG-03" for i in iss):
            last = max(before, key=lambda o: o.end)
            gap = (m.start - last.end).total_seconds() / 60
            if gap < s.setup_minutes:
                add(WARNING, "MTG-03", f"starts {gap:.0f} min after '{last.title}' ends in the same room ({s.setup_minutes} min needed to set up)")
        if not m.tech_owner and (needs or m.hybrid):
            add(WARNING, "MTG-04", "no support engineer assigned")
        # room health
        if rs and r.platform:
            if rs["down"]:
                seen = f", last heartbeat {r.heartbeat:%d %b %H:%M}" if r.heartbeat else ""
                add(CRITICAL, "ROOM-01", f"room system {r.health if r.health != 'healthy' else 'not reporting'}{seen}")
            for p, st in rs["faults"].items():
                sev = CRITICAL if st == "disconnected" and p in AV and m.hybrid else WARNING
                add(sev, "ROOM-02", f"{p} {st}")
            if r.next_update and m.start - timedelta(hours=s.freeze_hours) <= r.next_update <= m.end:
                add(WARNING, "ROOM-03", f"update scheduled {r.next_update:%a %d %b %H:%M}, inside the {s.freeze_hours} h freeze")
        if rs and rs["repeat"]:
            cats = Counter(i.category for i in rs["incidents"] if i.category)
            add(WARNING, "INC-01", f"{len(rs['incidents'])} incidents in the room in {s.incident_window_days} days ({', '.join(c for c, _ in cats.most_common(3))})")
        # VIP devices
        people = []
        for a in d.attendees_of(m.meeting_id):
            if not a.vip:
                continue
            devs = [d.device(x) for x in a.devices]
            states = [device_state(d, x) for x in devs if x]
            unknown = [x for x, y in zip(a.devices, devs) if y is None]
            p = dict(attendee=a, states=states, unknown=unknown, critical=[], warning=[])
            if not a.devices or (unknown and not states):
                p["warning"].append("no registered device" if not a.devices else f"device {', '.join(unknown)} not in the device list")
                add(WARNING, "DEV-04", f"{a.name}: {p['warning'][-1]}")
            for st in states:
                dv = st["device"]
                for t in st["critical"]:
                    p["critical"].append(f"{dv.device_id} {t}")
                    add(CRITICAL, "DEV-01", f"{a.name}: {dv.kind or 'device'} {dv.device_id} {t}")
                for t in st["warning"]:
                    p["warning"].append(f"{dv.device_id} {t}")
                    add(WARNING, "DEV-03" if t.startswith("battery") else "DEV-02", f"{a.name}: {dv.device_id} {t}")
            people.append(p)
        sev = CRITICAL if any(i.severity == CRITICAL for i in iss) else WARNING if iss else None
        rows.append(dict(meeting=m, room=r, room_state=rs, check=check, needs_check=needs, issues=iss, people=people,
                         verdict=VERDICT[sev], severity=sev))
    return rows


# ---------------------------------------------------------------- findings

def _collect(rows: list[dict], code: str) -> list[tuple[dict, Issue]]:
    return [(r, i) for r in rows for i in r["issues"] if i.code == code]


def run_all(d: Data, rows: list[dict] | None = None) -> list[Finding]:
    s = d.settings
    rows = rows if rows is not None else meeting_rows(d)
    o = s.owner
    out: list[Finding] = []

    def per_meeting(code, area, owner, word, fix):
        hits = _collect(rows, code)
        if not hits:
            return
        for sev in (CRITICAL, WARNING):
            hs = [(r, i) for r, i in hits if i.severity == sev]
            if not hs:
                continue
            ids = sorted({r["meeting"].meeting_id for r, _ in hs})
            det = [f"{r['meeting'].title} ({_when(r['meeting'])}): {i.text}" for r, i in hs]
            out.append(Finding(sev, area, code, f"{_n(len(ids), 'meeting')} {word}", _top(det, 8), fix, owner, ids))

    per_meeting("MTG-01", "Meetings", o("meetings"), "without a tech check in the last week before it",
                "Book a tech check in the room with the secretary's office: join from the room and from a remote laptop, share the pack, "
                "test every microphone at the table, and record it in meetings.csv.")
    per_meeting("MTG-02", "Meetings", o("meetings"), "in a room that does not fit",
                "Move the meeting to a room that fits, or set up and test a portable kit (camera and speaker bar) at the tech check.")
    per_meeting("MTG-03", "Meetings", o("meetings"), "too close to another meeting in the same room",
                "Ask the organisers to move one of them; block setup time before every board and committee meeting in the room calendar.")
    per_meeting("MTG-04", "Meetings", o("meetings"), "with no support engineer assigned",
                "Name the engineer on site for the meeting and a back-up, and send them the agenda and the tech check notes.")
    per_meeting("ROOM-01", "Rooms", o("rooms"), "in a room whose system is offline or not reporting",
                "Check the room today: power, network and the resource account sign-in; if it does not come back, open a priority case with "
                "the AV provider and book the fallback room now.")
    per_meeting("ROOM-02", "Rooms", o("rooms"), "in a room with a faulty peripheral",
                "Reseat or replace the peripheral and test a call before the tech check; keep a spare camera, speaker and cable kit in the AV store.")
    per_meeting("ROOM-03", "Rooms", o("rooms"), "with a room update scheduled inside the freeze",
                "Move the update to after the meeting, or apply it now and repeat the tech check.")
    per_meeting("DEV-01", "Devices", o("devices"), "with a VIP device that is not ready",
                "Get the device online with the attendee's assistant today: sync it with Intune or Jamf, fix the compliance issue, or prepare "
                "a loaner with the board app and the pack downloaded.")
    per_meeting("DEV-02", "Devices", o("devices"), "with VIP devices below the minimum OS or app version",
                "Update the OS and the board app at a desk visit before the meeting, then open the pack once to check it downloads.")
    per_meeting("DEV-03", "Devices", o("devices"), "with VIP devices whose battery is worn",
                "Replace the device or its battery before the meeting, or have a charged loaner and a charger at the attendee's seat.")
    per_meeting("DEV-04", "Devices", o("devices"), "with VIP attendees and no registered device",
                "Register the device the attendee uses, or prepare a loaner with the board app; check that their account can open the pack.")
    per_meeting("INC-01", "Incidents", o("incidents"), "in a room with repeated incidents",
                "Look for the common cause across the incidents (the same display, microphone, cable or time of day) and fix it before the meeting.")

    # room versions behind target (every Teams Room, not only the ones booked)
    behind = [room_state(d, r) for r in d.rooms if r.platform]
    behind = [x for x in behind if x["behind"]]
    if behind:
        out.append(Finding(INFO, "Rooms", "ROOM-04", f"{_n(len(behind), 'room')} behind the target version",
                           _top([f"{x['room'].room} {x['room'].version} (target {x['room'].target})" for x in behind]),
                           "Schedule the updates outside the freeze windows of the meetings in each room.", o("rooms"), [x["room"].room for x in behind]))
    # VIP devices with warranty ending (all devices, for information)
    notes = [device_state(d, x) for x in d.devices]
    notes = [x for x in notes if x["notes"]]
    if notes:
        out.append(Finding(INFO, "Devices", "DEV-05", f"{_n(len(notes), 'VIP device')} out of warranty or ending within {s.warranty_warn_days} days",
                           _top([f"{x['device'].device_id} ({x['device'].user}) {x['notes'][0]}" for x in notes]),
                           "Plan the replacement with the attendee's assistant, outside the weeks of board meetings.", o("devices"),
                           [x["device"].device_id for x in notes]))
    inc = recent_incidents(d)
    if inc:
        lost = Counter()
        for i in inc:
            lost[i.category or "Other"] += i.minutes_lost
        out.append(Finding(INFO, "Incidents", "INC-02", f"{_n(len(inc), 'incident')} and {sum(lost.values()):g} minutes lost in "
                                                        f"{s.incident_window_days} days",
                           ", ".join(f"{c} {m:g} min" for c, m in lost.most_common(5)),
                           "Review the top categories with the AV provider at the monthly service review.", o("incidents")))
    out.sort(key=lambda f: (ORDER[f.severity], AREAS.index(f.area), f.code))
    return out


def area_status(findings: list[Finding]) -> dict[str, str]:
    st = {}
    for a in AREAS:
        sev = [f.severity for f in findings if f.area == a and f.severity != INFO]
        st[a] = CRITICAL if CRITICAL in sev else WARNING if sev else "ok"
    return st
