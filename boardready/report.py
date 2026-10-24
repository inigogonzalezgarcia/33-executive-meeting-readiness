"""Outputs: report.html, readiness-pack.md and the CSVs (meeting readiness, room health, VIP devices, incidents by room, actions, findings)."""
from __future__ import annotations

import csv
import html
from collections import Counter
from pathlib import Path

from .checks import AREAS, CRITICAL, INFO, WARNING, Finding, area_status, device_state, meeting_rows, recent_incidents, room_state
from .model import Data, _norm

e = html.escape


def build(d: Data) -> dict:
    rows = meeting_rows(d)
    rooms = [room_state(d, r) for r in d.rooms]
    used = {_norm(r["meeting"].room) for r in rows}
    vip = []
    for dev in d.devices:
        st = device_state(d, dev)
        nxt = next((r["meeting"] for r in rows for p in r["people"] if any(x.lower() == dev.device_id.lower() for x in p["attendee"].devices)), None)
        vip.append(dict(st, next=nxt))
    return dict(rows=rows, rooms=rooms, used=used, vip=vip)


def summary(d: Data, findings: list[Finding], b: dict) -> dict:
    rows = b["rows"]
    v = Counter(r["verdict"] for r in rows)
    booked = [x for x in b["rooms"] if _norm(x["room"].room) in b["used"]]
    return dict(meetings=len(rows), at_risk=v["at risk"], attention=v["attention"], ready=v["ready"],
                board=sum(r["meeting"].kind in ("board", "committee") for r in rows),
                checks_missing=sum(r["check"] == "missing" for r in rows), rooms_booked=len(booked),
                rooms_faulty=sum(bool(x["down"] or x["faults"]) for x in booked),
                vip_devices=len(b["vip"]), vip_not_ready=sum(bool(x["critical"]) for x in b["vip"]),
                vip_warn=sum(bool(x["warning"]) and not x["critical"] for x in b["vip"]),
                incidents=len(recent_incidents(d)), minutes_lost=sum(i.minutes_lost for i in recent_incidents(d)),
                critical=sum(f.severity == CRITICAL for f in findings), warning=sum(f.severity == WARNING for f in findings),
                info=sum(f.severity == INFO for f in findings))


# ---------------------------------------------------------------- csv

def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def _t(v, f="%Y-%m-%d %H:%M") -> str:
    return v.strftime(f) if v else ""


def write_findings(findings: list[Finding], path: Path) -> None:
    _w(path, ["severity", "area", "code", "subject", "detail", "next_step", "owner", "items"],
       [[f.severity, f.area, f.code, f.subject, f.detail, f.fix, f.owner, "; ".join(f.items)] for f in findings])


def write_actions(findings: list[Finding], path: Path) -> None:
    _w(path, ["ref", "action", "next_step", "owner", "severity", "due", "done"],
       [[f.code, f.subject, f.fix, f.owner, f.severity, "", ""] for f in findings if f.severity != INFO])


def write_meetings(b: dict, path: Path) -> None:
    _w(path, ["meeting_id", "title", "kind", "start", "end", "room", "hybrid", "in_room", "remote", "tech_owner", "tech_check", "vip_attendees",
              "verdict", "issues"],
       [[m.meeting_id, m.title, m.kind, _t(m.start), _t(m.end), m.room, "yes" if m.hybrid else "no", m.in_room, m.remote, m.tech_owner, r["check"],
         len(r["people"]), r["verdict"], " | ".join(f"{i.code} {i.text}" for i in r["issues"])] for r in b["rows"] for m in [r["meeting"]]])


def write_rooms(d: Data, b: dict, path: Path) -> None:
    nxt = {}
    for r in b["rows"]:
        nxt.setdefault(_norm(r["meeting"].room), []).append(r["meeting"])
    _w(path, ["room", "site", "platform", "hardware", "capacity", "health", "last_heartbeat", "version", "target_version", "next_update",
              "peripheral_faults", "meetings_in_horizon", "next_meeting", f"incidents_{d.settings.incident_window_days}d", "minutes_lost"],
       [[r.room, r.site, r.platform, r.hardware, r.capacity, r.health if r.platform else "", _t(r.heartbeat), r.version, r.target, _t(r.next_update),
         "; ".join(f"{p} {s}" for p, s in x["faults"].items()), len(nxt.get(_norm(r.room), [])),
         _t(nxt[_norm(r.room)][0].start) if nxt.get(_norm(r.room)) else "", len(x["incidents"]), f"{x['minutes']:g}"]
        for x in b["rooms"] for r in [x["room"]]])


def write_devices(b: dict, path: Path) -> None:
    _w(path, ["device", "user", "type", "os", "os_version", "compliant", "last_check_in", "board_app", "battery_health", "warranty_end", "managed_by",
              "next_meeting", "status", "issues"],
       [[v.device_id, v.user, v.kind, v.os, v.os_version, "" if v.compliant is None else "yes" if v.compliant else "no", _t(v.checkin), v.app_version,
         "" if v.battery is None else f"{v.battery:g}", _t(v.warranty, "%Y-%m-%d"), v.managed_by,
         f"{x['next'].meeting_id} {_t(x['next'].start)}" if x["next"] else "",
         "not ready" if x["critical"] else "attention" if x["warning"] else "ready", "; ".join(x["critical"] + x["warning"] + x["notes"])]
        for x in b["vip"] for v in [x["device"]]])


def write_incidents(d: Data, path: Path) -> None:
    by = {}
    for i in recent_incidents(d):
        key = i.room or (f"device {i.device_id}" if i.device_id else "other")
        by.setdefault(key, []).append(i)
    rows = sorted(by.items(), key=lambda kv: (-len(kv[1]), -sum(i.minutes_lost for i in kv[1]), kv[0]))
    _w(path, ["room_or_device", "incidents", "minutes_lost", "categories", "last_incident", "last_summary"],
       [[k, len(v), f"{sum(i.minutes_lost for i in v):g}", ", ".join(f"{c} {n}" for c, n in Counter(i.category for i in v).most_common()),
         _t(max(v, key=lambda i: i.date).date), max(v, key=lambda i: i.date).summary] for k, v in rows])


# ---------------------------------------------------------------- readiness pack

def readiness_md(d: Data, findings: list[Finding], b: dict) -> str:
    s, sm = d.settings, summary(d, findings, b)
    out = [f"# Executive meeting readiness · {s.organisation}", "",
           f"As of {d.as_of:%a %d %b %Y %H:%M} · meetings in the next {s.horizon_days} days.", "", "## Summary", "",
           f"- Meetings: {sm['meetings']} ({sm['board']} board and committee): {sm['at_risk']} at risk, {sm['attention']} need attention, "
           f"{sm['ready']} ready.",
           f"- Rooms: {sm['rooms_faulty']} of the {sm['rooms_booked']} rooms booked have a fault.",
           f"- VIP devices: {sm['vip_not_ready']} not ready, {sm['vip_warn']} with something to fix, out of {sm['vip_devices']}.",
           f"- Incidents: {sm['incidents']} in {s.incident_window_days} days, {sm['minutes_lost']:g} minutes lost.",
           f"- Findings: {sm['critical']} critical, {sm['warning']} warnings, {sm['info']} for information.", "", "## Decisions", ""]
    out += [f"- [ ] **{f.code} {f.subject}** ({f.owner or 'owner?'}) → {f.fix}" for f in findings if f.severity != INFO] or ["- None."]
    out += ["", "## Meeting by meeting", ""]
    for r in b["rows"]:
        m, room = r["meeting"], r["room"]
        out += [f"### {m.start:%a %d %b %H:%M}–{m.end:%H:%M} · {m.title} · {m.room} — {r['verdict'].upper()}", ""]
        mode = f"hybrid, {m.in_room} in the room and {m.remote} remote" if m.hybrid else f"{m.in_room} in the room"
        out.append(f"- {m.kind.title()} meeting, {mode}. Support: {m.tech_owner or '**nobody assigned**'}.")
        if r["needs_check"]:
            out.append(f"- [{'x' if r['check'].startswith('done') else ' '}] Tech check: {r['check']}.")
        if room:
            state = "no Teams Room" if not room.platform else f"{room.health}" + (f", {', '.join(f'{p} {v}' for p, v in r['room_state']['faults'].items())}"
                                                                               if r["room_state"]["faults"] else "")
            ok = not any(i.code.startswith(("MTG-02", "ROOM", "INC")) for i in r["issues"])
            out.append(f"- [{'x' if ok else ' '}] Room: {room.hardware or 'no AV kit'} · {state} · capacity {room.capacity}.")
        for p in r["people"]:
            a = p["attendee"]
            st = "; ".join(p["critical"] + p["warning"]) or "ready"
            out.append(f"- [{' ' if p['critical'] or p['warning'] else 'x'}] {a.name} ({a.role}{', remote' if a.remote else ''}): "
                       f"{', '.join(a.devices) or 'no device'} · {st}")
        for i in r["issues"]:
            if i.code.startswith(("MTG-02", "MTG-03", "ROOM-03", "INC-01", "ROOM-01")):
                out.append(f"- [ ] {i.code}: {i.text}")
        out.append("")
    out += ["## For information", ""]
    out += [f"- {f.code} {f.subject}: {f.detail}" for f in findings if f.severity == INFO] or ["- Nothing."]
    out += ["", "Generated by boardready from the meeting list, the room health export, the device inventory and the incident log.", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--info:#0b6bcb}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;--warn:#f0a83a;--bad:#f2685c;--info:#5aa9f0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:10px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:26px}
.areas{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.area{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);border-radius:10px;padding:10px 14px}
.area.critical{border-left-color:var(--bad)}.area.warning{border-left-color:var(--warn)}
.area .lbl{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px}.area .cnt{display:block;font-size:13px;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.critical,.red{color:var(--bad)}.warning,.amber{color:var(--warn)}.info{color:var(--info)}.ok,.green{color:var(--ok)}
.area.critical,.area.warning,.area.ok{color:inherit}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--ok);margin-right:6px}.dot.red{background:var(--bad)}.dot.amber{background:var(--warn)}
.pill.ready{color:var(--ok)}.pill.attention{color:var(--warn)}.pill.at-risk{color:var(--bad)}
.bar{display:inline-block;height:9px;border-radius:5px;background:var(--warn);vertical-align:middle;margin-right:8px}.day td{background:var(--bg);font-weight:600;font-size:13px}td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);max-width:380px}code{font-size:12px}
footer{margin-top:40px;font-size:13px}
"""


def _pill(cls: str, text: str) -> str:
    return f"<span class='pill {cls}'>{e(text)}</span>"


def _vpill(v: str) -> str:
    return _pill(v.replace(" ", "-"), v.upper())


def render_html(d: Data, findings: list[Finding], title: str, b: dict) -> str:
    s, sm, st = d.settings, summary(d, findings, b), area_status(findings)
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>Rooms, VIP devices and support for every meeting in the next {s.horizon_days} days · "
         f"as of {d.as_of:%a %d %b %Y %H:%M}</p><div class='tiles'>"]
    tiles = [("Meetings", str(sm["meetings"]), f"{sm['board']} board and committee"),
             ("At risk", str(sm["at_risk"]), "a critical issue"),
             ("Attention", str(sm["attention"]), f"{sm['ready']} ready"),
             ("Tech checks missing", str(sm["checks_missing"]), "where required"),
             ("Rooms with a fault", f"{sm['rooms_faulty']}/{sm['rooms_booked']}", "rooms booked"),
             ("VIP devices not ready", f"{sm['vip_not_ready']}/{sm['vip_devices']}", f"{sm['vip_warn']} more to fix"),
             ("Minutes lost", f"{sm['minutes_lost']:g}", f"{sm['incidents']} incidents, {s.incident_window_days} days"),
             ("Critical", str(sm["critical"]), f"{sm['warning']} warnings · {sm['info']} info")]
    h += [f"<div class='tile'><span class='muted'>{e(a)}</span><b>{e(x)}</b><span class='muted'>{e(y)}</span></div>" for a, x, y in tiles]
    h.append("</div><h2>Status by area</h2><div class='areas'>")
    for a in AREAS:
        n = sum(f.area == a and f.severity != INFO for f in findings)
        h.append(f"<div class='area {st[a]}'><span class='lbl'>{e(a)}</span>{_pill(st[a], 'OK' if st[a] == 'ok' else st[a].upper())}"
                 f"<span class='cnt'>{n} to act on</span></div>")
    h.append("</div>")
    # meetings
    h.append("<h2>Meetings</h2><div class='wrap'><table><tr><th>Time</th><th>Meeting</th><th>Room</th><th>Tech check</th><th>Status</th>"
             "<th>What to fix</th></tr>")
    day = None
    for r in b["rows"]:
        m = r["meeting"]
        if m.start.date() != day:
            day = m.start.date()
            h.append(f"<tr class='day'><td colspan='6'>{day:%A %d %B}</td></tr>")
        iss = "<br>".join(f"<span class='{i.severity}'>●</span> {e(i.text)}" for i in sorted(r["issues"], key=lambda i: i.severity != CRITICAL))
        h.append(f"<tr><td class='nw'>{m.start:%H:%M}–{m.end:%H:%M}</td><td><b>{e(m.title)}</b><br><span class='muted'>{e(m.kind)} · "
                 f"{m.in_room} in room{f' · {m.remote} remote' if m.hybrid else ''} · {len(r['people'])} VIP</span></td>"
                 f"<td>{e(m.room)}</td><td class='nw {'warning' if r['check'] == 'missing' else ''}'>{e(r['check'])}</td>"
                 f"<td>{_vpill(r['verdict'])}</td><td>{iss or '–'}</td></tr>")
    h.append("</table></div>")
    crit = [f for f in findings if f.severity == CRITICAL]
    if crit:
        h.append("<h2>Fix first</h2><div class='wrap'><table><tr><th>Subject</th><th>What</th><th>Next step</th><th>Owner</th></tr>")
        h += [f"<tr><td><b>{e(f.subject)}</b><br><span class='muted'>{e(f.area)} · {e(f.code)}</span></td><td>{e(f.detail)}</td>"
              f"<td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in crit]
        h.append("</table></div>")
    # rooms
    h.append("<h2>Rooms</h2><div class='wrap'><table><tr><th>Room</th><th>Kit</th><th>Health</th><th>Version</th><th>Next update</th>"
             f"<th class='num'>Incidents {s.incident_window_days} d</th></tr>")
    for x in sorted(b["rooms"], key=lambda x: (_norm(x["room"].room) not in b["used"], not (x["down"] or x["faults"]), x["room"].room)):
        r = x["room"]
        if not r.platform:
            health, cls = "no Teams Room", "warning"
        else:
            cls = "critical" if x["down"] or "disconnected" in x["faults"].values() else "warning" if x["faults"] or r.health != "healthy" else "ok"
            health = ("offline" if r.health == "offline" else "not reporting" if x["stale"] else r.health) + \
                     "".join(f"<br><span class='muted'>{e(p)} {e(v)}</span>" for p, v in x["faults"].items())
        booked = "" if _norm(r.room) in b["used"] else " <span class='muted'>· not booked</span>"
        h.append(f"<tr><td class='nw'><b>{e(r.room)}</b>{booked}<br><span class='muted'>{e(r.site)} · {r.capacity} seats</span></td>"
                 f"<td>{e(r.hardware) or '–'}</td><td class='{cls}'>{health}</td>"
                 f"<td class='nw {'warning' if x['behind'] else ''}'>{e(r.version) or '–'}</td><td class='nw'>{_t(r.next_update, '%d %b %H:%M') or '–'}</td>"
                 f"<td class='num'>{len(x['incidents'])} · {x['minutes']:g} min</td></tr>")
    h.append("</table></div>")
    # VIP devices with something to do
    todo = [x for x in b["vip"] if x["critical"] or x["warning"] or x["notes"]]
    h.append(f"<h2>VIP devices with something to do ({len(todo)} of {len(b['vip'])})</h2><div class='wrap'><table><tr><th>Device</th><th>User</th>"
             "<th>OS · app</th><th>Last check-in</th><th>Next meeting</th><th>Issues</th></tr>")
    for x in sorted(todo, key=lambda x: (not x["critical"], not x["warning"], x["device"].device_id)):
        v = x["device"]
        cls = "critical" if x["critical"] else "warning" if x["warning"] else "info"
        h.append(f"<tr><td class='nw'><b>{e(v.device_id)}</b><br><span class='muted'>{e(v.kind)} · {e(v.managed_by)}</span></td><td>{e(v.user)}</td>"
                 f"<td class='nw'>{e(v.os)} {e(v.os_version)}<br><span class='muted'>{e(s.app_name)} {e(v.app_version) or '–'}</span></td>"
                 f"<td class='nw'>{_t(v.checkin, '%d %b %H:%M')}</td>"
                 f"<td>{(e(x['next'].title) + '<br><span class=muted>' + x['next'].start.strftime('%a %d %b') + '</span>') if x['next'] else '–'}</td>"
                 f"<td class='{cls}'>{'<br>'.join(e(t) for t in x['critical'] + x['warning'] + x['notes'])}</td></tr>")
    h.append("</table></div>")
    # incidents
    inc = recent_incidents(d)
    if inc:
        by = Counter()
        mins = Counter()
        for i in inc:
            k = i.room or f"device {i.device_id}"
            by[k] += 1
            mins[k] += i.minutes_lost
        top = max(mins.values()) or 1
        h.append(f"<h2>Incidents in the last {s.incident_window_days} days</h2><div class='wrap'><table><tr><th>Room or device</th>"
                 "<th class='num'>Incidents</th><th>Minutes lost</th></tr>")
        h += [f"<tr><td>{e(k)}</td><td class='num'>{n}</td><td class='nw'><span class='bar' style='width:{max(4, round(160 * mins[k] / top))}px'></span>"
              f"{mins[k]:g}</td></tr>" for k, n in sorted(by.items(), key=lambda kv: (-mins[kv[0]], kv[0]))]
        h.append("</table></div>")
    h.append("<h2>All findings</h2><div class='wrap'><table><tr><th>Severity</th><th>Area</th><th>Subject</th><th>Detail</th><th>Next step</th><th>Owner</th></tr>")
    h += [f"<tr><td>{_pill(f.severity, f.severity.upper())}</td><td class='nw'>{e(f.area)}</td><td>{e(f.subject)}</td>"
          f"<td>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in findings]
    h.append("</table></div><footer class='muted'>Generated by boardready. Fictional demo data unless you ran it on your own exports.</footer></main></body></html>")
    return "".join(h)
