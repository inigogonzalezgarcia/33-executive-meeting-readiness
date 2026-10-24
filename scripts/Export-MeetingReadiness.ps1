<#
.SYNOPSIS
    Read-only export from Microsoft Graph of the room health, the room calendars and the managed devices used by boardready.

.DESCRIPTION
    Writes three CSVs to -OutputFolder:
      - rooms.csv: one row per Teams Rooms device from /teamwork/devices (beta) with its health: connection, last heartbeat, Teams Rooms
        app version and available version, and the state of camera, microphone, speaker, displays and touch console;
      - meetings.csv: the bookings of the room mailboxes in -RoomMailboxes for the next -Days days (subject, start, end, room, online
        meeting, number of attendees). Add the type, the tech check and the support engineer by hand or from your request form;
      - devices.csv: the Intune managed devices of the users in -VipUsers (OS version, compliance, last sync, model).
    attendees.csv (the VIP attendees of each meeting and their devices) and settings.json are written by hand; incidents.csv comes from the
    service desk (see docs/data-format.md). Apple devices managed in Jamf Pro: export the same columns from an advanced search instead.

    It only reads. Delegated permissions, consented once by an administrator:
      TeamworkDevice.Read.All, Calendars.Read.Shared (the room calendars must be shared with you), DeviceManagementManagedDevices.Read.All.

    Times are written in the local time zone of the machine running the script.

.EXAMPLE
    .\scripts\Export-MeetingReadiness.ps1 -OutputFolder .\data -Days 14 `
        -RoomMailboxes boardroom@contoso.com, boardroom2@contoso.com -VipUsers chair@contoso.com, ceo@contoso.com
#>
[CmdletBinding()]
param(
    [string] $OutputFolder = '.\data',
    [int] $Days = 14,
    [string[]] $RoomMailboxes = @(),
    [string[]] $VipUsers = @()
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Module -ListAvailable -Name Microsoft.Graph.Authentication)) {
    throw 'Install the Microsoft.Graph.Authentication module first: Install-Module Microsoft.Graph.Authentication -Scope CurrentUser'
}
Import-Module Microsoft.Graph.Authentication
Connect-MgGraph -Scopes 'TeamworkDevice.Read.All', 'Calendars.Read.Shared', 'DeviceManagementManagedDevices.Read.All' -NoWelcome | Out-Null
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null

function Get-All([string] $uri) {
    $items = @()
    while ($uri) {
        $page = Invoke-MgGraphRequest -Method GET -Uri $uri -OutputType PSObject
        $items += $page.value
        $uri = $page.'@odata.nextLink'
    }
    $items
}

function Local([object] $value) {
    if (-not $value) { return '' }
    ([datetime]$value).ToLocalTime().ToString('yyyy-MM-dd HH:mm')
}

function Peripheral([object] $health) {
    if (-not $health) { return '' }
    switch ("$($health.connection.connectionState)") { 'connected' { 'ok' } 'disconnected' { 'disconnected' } default { 'degraded' } }
}

# ---- rooms: Teams Rooms devices and their health (beta endpoint)
$rooms = foreach ($d in Get-All 'https://graph.microsoft.com/beta/teamwork/devices?$filter=deviceType eq ''teamsRoom''') {
    $h = Invoke-MgGraphRequest -Method GET -Uri "https://graph.microsoft.com/beta/teamwork/devices/$($d.id)/health" -OutputType PSObject
    $p = $h.peripheralsHealth
    $sw = $h.softwareUpdateHealth.teamsClientSoftwareUpdateStatus
    $displays = @($p.displayHealthCollection | ForEach-Object { Peripheral $_ })
    [pscustomobject]@{
        Room             = $d.currentUser.displayName
        Site             = ''
        Platform         = "Teams Rooms ($($d.hardwareDetail.manufacturer))"
        Hardware         = "$($d.hardwareDetail.manufacturer) $($d.hardwareDetail.model)"
        Capacity         = ''
        Health           = "$($d.healthStatus)"
        'Last heartbeat' = Local $h.connection.lastModifiedDateTime
        Version          = $sw.currentVersion
        'Target version' = $sw.availableVersion
        'Next update'    = ''
        Camera           = Peripheral $p.roomCameraHealth
        Microphone       = Peripheral $p.microphoneHealth
        Speaker          = Peripheral $p.communicationSpeakerHealth
        Display          = if ($displays -contains 'disconnected') { 'disconnected' } elseif ($displays -contains 'degraded') { 'degraded' } elseif ($displays) { 'ok' } else { '' }
        Console          = ''
    }
}
$rooms | Export-Csv -Path (Join-Path $OutputFolder 'rooms.csv') -NoTypeInformation -Encoding UTF8
Write-Host ("rooms.csv: {0} Teams Rooms (add Site and Capacity from your room register)" -f @($rooms).Count)

# ---- meetings: the bookings of the room mailboxes
$from = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$to = (Get-Date).AddDays($Days).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$n = 0
$meetings = foreach ($mb in $RoomMailboxes) {
    $sel = 'subject,start,end,location,isOnlineMeeting,attendees,sensitivity'
    foreach ($e in Get-All "https://graph.microsoft.com/v1.0/users/$mb/calendarView?startDateTime=$from&endDateTime=$to&`$select=$sel&`$top=100") {
        $n++
        [pscustomobject]@{
            'Meeting ID'         = 'M{0:d3}' -f $n
            Title                = if ($e.sensitivity -in 'private', 'confidential') { '(private)' } else { $e.subject }
            Type                 = ''
            Start                = Local "$($e.start.dateTime)Z"
            End                  = Local "$($e.end.dateTime)Z"
            Room                 = $e.location.displayName
            Hybrid               = if ($e.isOnlineMeeting) { 'yes' } else { 'no' }
            'In room'            = @($e.attendees | Where-Object { $_.type -ne 'resource' }).Count
            Remote               = ''
            'Tech owner'         = ''
            'Tech check done'    = ''
            'Tech check planned' = ''
        }
    }
}
$meetings | Export-Csv -Path (Join-Path $OutputFolder 'meetings.csv') -NoTypeInformation -Encoding UTF8
Write-Host ("meetings.csv: {0} bookings (fill in Type, Remote, Tech owner and the tech check)" -f @($meetings).Count)

# ---- devices: Intune managed devices of the VIP users
$sel = 'deviceName,userPrincipalName,model,operatingSystem,osVersion,complianceState,lastSyncDateTime,managementAgent'
$devices = foreach ($u in $VipUsers) {
    foreach ($d in Get-All "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices?`$filter=userPrincipalName eq '$u'&`$select=$sel") {
        [pscustomobject]@{
            'Device ID'         = $d.deviceName
            User                = $d.userPrincipalName
            Type                = $d.model
            OS                  = $d.operatingSystem
            'OS version'        = $d.osVersion
            Compliant           = $d.complianceState
            'Last check-in'     = Local $d.lastSyncDateTime
            'Board app version' = ''
            'Battery health'    = ''
            'Warranty end'      = ''
            'Managed by'        = 'Intune'
        }
    }
}
$devices | Export-Csv -Path (Join-Path $OutputFolder 'devices.csv') -NoTypeInformation -Encoding UTF8
Write-Host ("devices.csv: {0} devices" -f @($devices).Count)
Write-Host 'Add attendees.csv, incidents.csv and settings.json, then: python -m boardready review .\data'
