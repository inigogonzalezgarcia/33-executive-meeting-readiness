"""Loading: the meetings, the room register with its health, the VIP attendees and their devices, the incident log and settings.json,
with forgiving column names, into plain dataclasses."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

MEETING_ALIASES = {
    "meeting_id": ["meeting id", "id", "ref", "reunion"],
    "title": ["title", "subject", "meeting", "name", "asunto", "titulo"],
    "kind": ["kind", "type", "meeting type", "category", "tipo"],
    "start": ["start", "start time", "begins", "inicio"],
    "end": ["end", "end time", "finishes", "fin"],
    "room": ["room", "location", "meeting room", "sala"],
    "hybrid": ["hybrid", "teams", "online", "hibrida", "online meeting"],
    "in_room": ["in room", "attendees in room", "in person", "presencial", "presenciales"],
    "remote": ["remote", "remote attendees", "online attendees", "remotos"],
    "tech_owner": ["tech owner", "support", "engineer", "on site support", "tecnico", "soporte"],
    "check_done": ["tech check done", "tech check", "rehearsal done", "rehearsal", "ensayo", "prueba tecnica"],
    "check_planned": ["tech check planned", "rehearsal planned", "ensayo previsto"],
    "notes": ["notes", "comments", "notas"],
}
ROOM_ALIASES = {
    "room": ["room", "name", "display name", "sala"],
    "site": ["site", "building", "location", "office", "sede"],
    "platform": ["platform", "teams rooms", "system", "plataforma"],
    "hardware": ["hardware", "kit", "devices", "model", "equipamiento"],
    "capacity": ["capacity", "seats", "capacidad", "aforo"],
    "health": ["health", "health status", "status", "estado"],
    "heartbeat": ["last heartbeat", "heartbeat", "last seen", "last contact", "last modified"],
    "version": ["version", "app version", "teams version", "current version", "firmware"],
    "target": ["target version", "target", "available version", "latest version"],
    "next_update": ["next update", "update scheduled", "scheduled update", "maintenance"],
    "camera": ["camera", "room camera", "camara"],
    "microphone": ["microphone", "mic", "microphones", "microfono"],
    "speaker": ["speaker", "speakers", "communication speaker", "altavoz"],
    "display": ["display", "displays", "screen", "pantalla"],
    "console": ["console", "touch panel", "touch console", "consola"],
}
ATTENDEE_ALIASES = {
    "meeting_id": ["meeting id", "meeting", "id", "reunion"],
    "name": ["name", "attendee", "person", "nombre"],
    "role": ["role", "title", "position", "cargo"],
    "vip": ["vip", "executive", "priority"],
    "devices": ["devices", "device", "device id", "device ids", "dispositivo"],
    "remote": ["remote", "joins remotely", "online", "remoto"],
}
DEVICE_ALIASES = {
    "device_id": ["device id", "device", "device name", "asset", "serial", "dispositivo"],
    "user": ["user", "assigned to", "owner", "usuario"],
    "kind": ["kind", "type", "model", "device type", "tipo"],
    "os": ["os", "operating system", "platform", "sistema operativo"],
    "os_version": ["os version", "version", "osversion"],
    "compliant": ["compliant", "compliance", "compliance state", "cumple"],
    "checkin": ["last check in", "last checkin", "last sync", "last sync date time", "last contact", "last inventory update"],
    "app_version": ["board app version", "app version", "portal version"],
    "battery": ["battery health", "battery", "battery health pct", "bateria"],
    "warranty": ["warranty end", "warranty", "warranty expires", "garantia"],
    "managed_by": ["managed by", "management", "mdm"],
}
INCIDENT_ALIASES = {
    "date": ["date", "opened", "created", "fecha"],
    "room": ["room", "location", "sala"],
    "device_id": ["device", "device id", "dispositivo"],
    "meeting_id": ["meeting id", "meeting", "reunion"],
    "category": ["category", "type", "categoria"],
    "minutes_lost": ["minutes lost", "delay minutes", "minutes", "minutos perdidos"],
    "summary": ["summary", "description", "short description", "resumen"],
}
YES = {"yes", "y", "true", "1", "si", "x", "hybrid", "teams", "online", "compliant"}
KINDS = {"board": "board", "consejo": "board", "committee": "committee", "comite": "committee", "comision": "committee",
         "executive": "executive", "exco": "executive", "comite de direccion": "executive", "investor": "investor", "agm": "agm",
         "shareholders": "agm", "junta": "agm", "town hall": "town hall", "all hands": "town hall"}
HEALTH = {"healthy": "healthy", "ok": "healthy", "online": "healthy", "degraded": "degraded", "warning": "degraded",
          "non urgent": "degraded", "nonurgent": "degraded", "unhealthy": "unhealthy", "critical": "unhealthy", "error": "unhealthy", "offline": "offline",
          "disconnected": "offline", "unknown": "offline"}
PERIPHERAL = {"ok": "ok", "healthy": "ok", "connected": "ok", "degraded": "degraded", "warning": "degraded", "intermittent": "degraded",
              "disconnected": "disconnected", "missing": "disconnected", "unhealthy": "disconnected", "error": "disconnected", "failed": "disconnected"}
PERIPHERALS = ("camera", "microphone", "speaker", "display", "console")
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d %b %Y")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in s if not unicodedata.combining(ch))).strip()


def parse_dt(v) -> datetime | None:
    s = str(v or "").strip().replace("Z", "")
    if not s or _norm(s) in {"never", "n a", "na", "none", "nunca"}:
        return None
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s[:19] if "T" in s else s, f)
        except ValueError:
            continue
    return None


def parse_date(v) -> date | None:
    d = parse_dt(v)
    return d.date() if d else None


def num(v, default: float | None = 0.0) -> float | None:
    s = str(v or "").strip().replace(" ", "").lower().replace("%", "").replace("min", "")
    if not s:
        return default
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return default


def _rows(path: Path, aliases: dict[str, list[str]]) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        heads = {_norm(h): h for h in (reader.fieldnames or [])}
        cols = {}
        for key, names in aliases.items():
            for n in [key.replace("_", " ")] + names:
                if _norm(n) in heads:
                    cols[key] = heads[_norm(n)]
                    break
        return [{k: (r.get(c) or "").strip() for k, c in cols.items()} for r in reader]


def _map(raw: str, table: dict, default: str) -> str:
    n = _norm(raw)
    return table.get(n) or table.get((n.split() or [default])[0], default)


def yes(v) -> bool:
    return _norm(v) in YES


def kind_of(v: str, title: str = "") -> str:
    for text in (v, title):
        n = _norm(text)
        for k, out in KINDS.items():
            if n == k or n.startswith(k + " ") or (text is title and k in n):
                return out
    return "other"


def version(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:4])


@dataclass
class Meeting:
    meeting_id: str
    title: str
    start: datetime
    end: datetime
    room: str
    kind: str = "other"               # board | committee | executive | investor | agm | town hall | other
    hybrid: bool = True
    in_room: int = 0
    remote: int = 0
    tech_owner: str = ""
    check_done: date | None = None
    check_planned: date | None = None
    notes: str = ""


@dataclass
class Room:
    room: str
    site: str = ""
    platform: str = ""                # empty: no Teams Room in the room
    hardware: str = ""
    capacity: int = 0
    health: str = "healthy"           # healthy | degraded | unhealthy | offline
    heartbeat: datetime | None = None
    version: str = ""
    target: str = ""
    next_update: datetime | None = None
    peripherals: dict = field(default_factory=dict)   # camera/microphone/speaker/display/console -> ok | degraded | disconnected


@dataclass
class Attendee:
    meeting_id: str
    name: str
    role: str = ""
    vip: bool = True
    devices: list[str] = field(default_factory=list)
    remote: bool = False


@dataclass
class Device:
    device_id: str
    user: str = ""
    kind: str = ""
    os: str = ""
    os_version: str = ""
    compliant: bool | None = None
    checkin: datetime | None = None
    app_version: str = ""
    battery: float | None = None
    warranty: date | None = None
    managed_by: str = ""


@dataclass
class Incident:
    date: datetime
    room: str = ""
    device_id: str = ""
    meeting_id: str = ""
    category: str = ""
    minutes_lost: float = 0.0
    summary: str = ""


@dataclass
class Settings:
    organisation: str = "Organisation"
    as_of: datetime | None = None
    horizon_days: int = 14
    tech_check_kinds: list = field(default_factory=lambda: ["board", "committee", "investor", "agm"])
    tech_check_window_days: int = 7
    tech_check_lead_days: int = 3
    setup_minutes: int = 30
    heartbeat_hours: int = 24
    freeze_hours: int = 48
    checkin_days: int = 7
    min_os: dict = field(default_factory=lambda: {"ipados": "18.0", "ios": "18.0", "macos": "15.0", "windows": "10.0.22631"})
    min_app_version: str = ""
    app_name: str = "Board app"
    battery_min_pct: int = 80
    warranty_warn_days: int = 60
    repeat_incidents: int = 3
    incident_window_days: int = 90
    owners: dict = field(default_factory=lambda: {"meetings": "Executive support lead", "rooms": "Workplace AV team", "devices": "VIP support",
                                                  "incidents": "Workplace AV team"})

    def owner(self, key: str) -> str:
        return self.owners.get(key, "")


def settings_from_dict(raw: dict) -> Settings:
    s = Settings()
    for k, v in raw.items():
        if not hasattr(s, k):
            continue
        cur = getattr(s, k)
        if k == "as_of":
            v = parse_dt(v)
        elif k in ("owners", "min_os"):
            v = {**cur, **{_norm(a) if k == "min_os" else a: b for a, b in v.items()}}
        elif k == "tech_check_kinds":
            v = [kind_of(x) for x in v]
        elif isinstance(cur, int):
            v = int(v)
        setattr(s, k, v)
    return s


def _int(v) -> int:
    return int(num(v, 0) or 0)


def load_meetings(path: Path) -> list[Meeting]:
    out = []
    for r in _rows(path, MEETING_ALIASES):
        st, en = parse_dt(r.get("start")), parse_dt(r.get("end"))
        if not st:
            continue
        out.append(Meeting(r.get("meeting_id") or f"M{len(out) + 1:02d}", r.get("title", ""), st, en or st + timedelta(hours=1), r.get("room", ""),
                           kind_of(r.get("kind", ""), r.get("title", "")), yes(r["hybrid"]) if r.get("hybrid") else True, _int(r.get("in_room")),
                           _int(r.get("remote")), r.get("tech_owner", ""), parse_date(r.get("check_done")), parse_date(r.get("check_planned")),
                           r.get("notes", "")))
    return out


def load_rooms(path: Path) -> list[Room]:
    out = []
    for r in _rows(path, ROOM_ALIASES):
        if not r.get("room"):
            continue
        plat = r.get("platform", "")
        per = {p: _map(r[p], PERIPHERAL, "disconnected") for p in PERIPHERALS if r.get(p)}
        out.append(Room(r["room"], r.get("site", ""), "" if _norm(plat) in {"", "none", "no", "n a"} else plat, r.get("hardware", ""),
                        _int(r.get("capacity")), _map(r.get("health", "") or "healthy", HEALTH, "offline"), parse_dt(r.get("heartbeat")),
                        r.get("version", ""), r.get("target", ""), parse_dt(r.get("next_update")), per))
    return out


def load_attendees(path: Path) -> list[Attendee]:
    out = []
    for r in _rows(path, ATTENDEE_ALIASES):
        if not r.get("meeting_id") or not r.get("name"):
            continue
        devs = [x.strip() for x in re.split(r"[;|]", r.get("devices", "")) if x.strip()]
        out.append(Attendee(r["meeting_id"], r["name"], r.get("role", ""), yes(r["vip"]) if r.get("vip") else True, devs, yes(r.get("remote", ""))))
    return out


def load_devices(path: Path) -> list[Device]:
    out = []
    for r in _rows(path, DEVICE_ALIASES):
        if not r.get("device_id"):
            continue
        c = _norm(r.get("compliant", ""))
        comp = None if not c or c in {"unknown", "n a"} else c in YES
        out.append(Device(r["device_id"], r.get("user", ""), r.get("kind", ""), r.get("os", ""), r.get("os_version", ""), comp,
                          parse_dt(r.get("checkin")), r.get("app_version", ""), num(r.get("battery"), None), parse_date(r.get("warranty")),
                          r.get("managed_by", "")))
    return out


def load_incidents(path: Path) -> list[Incident]:
    out = []
    for r in _rows(path, INCIDENT_ALIASES):
        t = parse_dt(r.get("date"))
        if not t:
            continue
        out.append(Incident(t, r.get("room", ""), r.get("device_id", ""), r.get("meeting_id", ""), r.get("category", ""), num(r.get("minutes_lost")) or 0.0,
                            r.get("summary", "")))
    return out


@dataclass
class Data:
    settings: Settings
    as_of: datetime
    meetings: list[Meeting]
    rooms: list[Room] = field(default_factory=list)
    attendees: list[Attendee] = field(default_factory=list)
    devices: list[Device] = field(default_factory=list)
    incidents: list[Incident] = field(default_factory=list)

    @property
    def today(self) -> date:
        return self.as_of.date()

    def room(self, name: str) -> Room | None:
        key = _norm(name)
        return next((r for r in self.rooms if _norm(r.room) == key), None)

    def device(self, device_id: str) -> Device | None:
        key = _norm(device_id)
        return next((x for x in self.devices if _norm(x.device_id) == key), None)

    def upcoming(self) -> list[Meeting]:
        end = self.as_of + timedelta(days=self.settings.horizon_days)
        return sorted([m for m in self.meetings if m.end > self.as_of and m.start < end], key=lambda m: (m.start, m.meeting_id))

    def attendees_of(self, meeting_id: str) -> list[Attendee]:
        return [a for a in self.attendees if a.meeting_id == meeting_id]


def load(folder: Path, as_of: datetime | date | None = None) -> Data:
    folder = Path(folder)
    if not (folder / "meetings.csv").exists():
        raise FileNotFoundError(f"{folder / 'meetings.csv'} not found: the list of meetings is required")
    sp = folder / "settings.json"
    s = settings_from_dict(json.loads(sp.read_text(encoding="utf-8"))) if sp.exists() else Settings()
    meetings = load_meetings(folder / "meetings.csv")
    if not meetings:
        raise ValueError("meetings.csv has no rows with a start time")
    opt = lambda name, fn: fn(folder / name) if (folder / name).exists() else []  # noqa: E731
    rooms, att, dev, inc = opt("rooms.csv", load_rooms), opt("attendees.csv", load_attendees), opt("devices.csv", load_devices), \
        opt("incidents.csv", load_incidents)
    if isinstance(as_of, date) and not isinstance(as_of, datetime):
        as_of = datetime.combine(as_of, datetime.min.time()) + timedelta(hours=8)
    when = as_of or s.as_of or datetime.now().replace(second=0, microsecond=0)
    return Data(s, when, meetings, rooms, att, dev, inc)
