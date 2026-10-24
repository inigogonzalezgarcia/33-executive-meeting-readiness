# Weekly meeting readiness runbook

A 20-minute check every Monday (and the day before each board meeting) with the workplace engineers, the AV provider if there is one, and the executive office or the company secretary's team. The tool only reads exports; rooms, devices and bookings are changed in their own tools.

## Before the check (15 minutes)

1. Export the room health, the room bookings and the VIP devices (read-only):
   ```powershell
   .\scripts\Export-MeetingReadiness.ps1 -OutputFolder .\data -Days 14 -RoomMailboxes boardroom@contoso.com -VipUsers chair@contoso.com
   ```
   For iPads and Macs in Jamf Pro, export the same columns from an advanced search into `devices.csv`.
2. Fill in the meeting type, the remote attendees, the support engineer and the tech checks in `meetings.csv`, and the VIP attendees in `attendees.csv`.
3. Export the meeting-room and VIP incidents of the last 90 days from the service desk into `incidents.csv`.
4. Build the outputs and send `readiness-pack.md` to the team:
   ```bash
   python -m boardready review data/ --title "Meeting readiness · week 44"
   ```

## Agenda

| Minutes | Topic | Output |
|---|---|---|
| 5 | Meetings at risk: room down or unsuitable, VIP device not ready, missing tech check close to the date | `report.html` → Fix first |
| 5 | Rooms: faults, updates inside the freeze, repeated incidents | `room-health.csv` |
| 5 | VIP devices: desk visits to book this week | `vip-devices.csv` |
| 5 | Tech checks and support engineers for every board and committee meeting | `meeting-readiness.csv` |

## How to read it

- **The verdict is per meeting, not per room.** The same degraded display is a note for an internal workshop and a decision for the board.
- **A tech check is only as good as its date.** A rehearsal three weeks ago says nothing about a microphone that failed yesterday, so the check must be inside the last week.
- **A device that has not checked in is unknown,** not fine: it may not have the latest pack, the right OS or a valid certificate.
- **No updates in the freeze.** A Teams Rooms or firmware update the night before a board meeting is a change nobody tested in that room.
- **Repeated incidents are a pattern.** Three display incidents in one boardroom in 90 days usually share a cause (a cable, a switcher, a power setting).

## Day before each board meeting

- Run the review again with `--as-of` set to the morning of the meeting.
- Confirm the tech check result, the support engineer and the back-up, and that a charged loaner device with the pack is in the room.
