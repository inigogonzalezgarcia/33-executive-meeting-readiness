# Data format

Put the files in one folder and run `python -m boardready review <folder>`. Only `meetings.csv` is required; every other file adds its checks when present. Comma, semicolon or tab separated, UTF-8. Column names are matched loosely (case, accents and punctuation are ignored), and the common alternatives below are accepted.

## meetings.csv (required)

The meetings to prepare, usually the bookings of the board and executive rooms plus the ones the executive office asks for.

| Column | Also accepted | Notes |
|---|---|---|
| Meeting ID | id, ref | Links attendees and incidents to the meeting |
| Title | subject, asunto | |
| Type | kind, category, tipo | board, committee, executive (ExCo), investor, AGM, town hall, other. If empty, it is guessed from the title ("Audit Committee", "Consejo") |
| Start, End | start time, inicio, fin | `YYYY-MM-DD HH:MM`, ISO or `DD/MM/YYYY HH:MM`; a missing end means one hour |
| Room | location, sala | Must match the room register |
| Hybrid | teams, online | `yes`/`no`; empty means yes |
| In room, Remote | presenciales, remotos | Numbers of people; "in room" is compared with the capacity |
| Tech owner | support, engineer, soporte | The engineer on site |
| Tech check done, Tech check planned | rehearsal, ensayo | Dates. A tech check counts if done within `tech_check_window_days` before the meeting |

## rooms.csv

The room register with the health of each Teams Room. `scripts/Export-MeetingReadiness.ps1` writes it from Microsoft Graph; add the site and capacity from your register.

| Column | Also accepted | Notes |
|---|---|---|
| Room, Site | display name, sede | |
| Platform | teams rooms | Empty or `none` for a room without a Teams Room |
| Hardware, Capacity | kit, seats, aforo | |
| Health | health status, status | healthy, degraded (non urgent), unhealthy (critical), offline |
| Last heartbeat | last seen | Older than `heartbeat_hours` counts as not reporting |
| Version, Target version | current version, available version | Teams Rooms app or firmware |
| Next update | update scheduled | Date and time of the next planned update, compared with the freeze before each meeting |
| Camera, Microphone, Speaker, Display, Console | mic, pantalla, touch panel | ok, degraded (intermittent), disconnected; empty = not applicable |

## attendees.csv

The VIP attendees of each meeting: `Meeting ID`, `Name`, `Role`, `VIP` (yes/no, empty = yes), `Devices` (one or more device IDs separated by `;`), `Remote` (yes/no). Only the VIP attendees are needed.

## devices.csv

| Column | Also accepted | Notes |
|---|---|---|
| Device ID, User | device name, assigned to | |
| Type, OS, OS version | model, operating system | iPadOS, iOS, macOS or Windows, compared with `min_os` |
| Compliant | compliance state | compliant / noncompliant; empty = unknown |
| Last check-in | last sync, last inventory update | Older than `checkin_days` makes the device not ready |
| Board app version | app version | Compared with `min_app_version` |
| Battery health, Warranty end | battery, garantía | Percentage and date |
| Managed by | MDM | Jamf Pro, Intune |

## incidents.csv

From the service desk, filtered on meeting rooms and VIP devices: `Date`, `Room`, `Device`, `Meeting ID`, `Category`, `Minutes lost`, `Summary`.

## settings.json

All keys are optional; the demo's file in `sample_data/` shows every key.

| Key | Default | Meaning |
|---|---|---|
| `organisation`, `as_of` | | Title and review time (`YYYY-MM-DD HH:MM`) |
| `horizon_days` | 14 | Meetings starting within this window are reviewed |
| `tech_check_kinds` | board, committee, investor, agm | Meeting types that need a tech check |
| `tech_check_window_days`, `tech_check_lead_days` | 7, 3 | A tech check counts if done within 7 days before; a missing one is critical within 3 days of the meeting |
| `setup_minutes` | 30 | Free time needed in the room before a meeting |
| `heartbeat_hours`, `freeze_hours` | 24, 48 | Room reporting limit; no updates in the 48 hours before a meeting |
| `checkin_days`, `min_os`, `min_app_version`, `app_name` | 7, iPadOS/iOS 18.0, macOS 15.0 | Device readiness |
| `battery_min_pct`, `warranty_warn_days` | 80, 60 | |
| `repeat_incidents`, `incident_window_days` | 3, 90 | Incidents in a room before it is flagged |
| `owners` | | Owner per area: meetings, rooms, devices, incidents |
