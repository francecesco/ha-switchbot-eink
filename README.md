# SwitchBot E-Ink Home Dashboard for Home Assistant

Shows **an agenda that merges the Home Assistant calendars you choose** on the 7.5" e-ink
panel of the SwitchBot E-Ink Home Dashboard (SKU `W8902500`).

The device is not modified: no firmware to replace, no reflashing. The integration writes
to the panel's home page through the same API used by SwitchBot's official web editor, and
replaces its weather content. The sidebar on the left, with date, time and weather, is drawn
by the firmware and stays as it is.

```
┌────────────┬──────────────────────────────────────┐
│            │  W  14:30  Weekly meeting            │
│  Mon 28    │  H  16:30  Lunch with Mark           │
│  September │  W  17:30  Project review            │
│            │  H  18:30  Groceries                 │
│  15:30     │  H  19:30  Gym                       │
│            │                              +3 more │
│  weather   ├──────────────────────────────────────┤
│  (firmware)│  TOMORROW                            │
│            │  H  08:30  Dentist                   │
│            │  W  15:00  Hand in documents         │
│            │  WED 30   Holiday (all day)          │
│            │  W Work · H Home      updated 15:30  │
└────────────┴──────────────────────────────────────┘
```

## How it works

Every hour (configurable) the integration reads the next three days of events from the
calendars you picked, builds the page and publishes it, **only if the content has
changed**.

The panel **downloads its content on its own, roughly every three hours**, and that
cadence cannot be changed. A new or moved event therefore reaches the panel with some
delay. To get it right away, press the **Refresh agenda** button in Home Assistant, then
**hold the button on the panel for two seconds**: the panel downloads immediately.

The time of the last update is shown in the bottom right corner (`updated 15:30`): with a
read every three hours, without it you could not tell a fresh agenda from this morning's.

## What it shows

- **Today**: up to five events, with time and title. Events that are already over make
  room for the ones still to come; events already in progress are shown anyway. Beyond
  the fifth, a `+N more` line: no event disappears silently.
- **Tomorrow**: a preview of the first two events, with its own `+N more`.
- **The day after**: a one-line summary.
- **Several calendars**: the panel only has black and grey, so calendars cannot be told
  apart by colour. Each event carries a one- or two-letter marker taken from the calendar
  name (`W` for Work, `H` for Home), and a legend in the bottom left corner explains
  them. With a single calendar, neither markers nor legend are shown.
- **Language**: the panel text follows the Home Assistant language. Italian and English
  are available; any other language falls back to English.

Event titles never go through the Home Assistant template engine: they come from
invitations and shared calendars, and a title containing curly braces must not be
executed.

## Requirements

- A SwitchBot E-Ink Home Dashboard, added to your account in the SwitchBot app, with **up
  to date firmware** (see [Troubleshooting](#troubleshooting))
- Home Assistant 2026.8 or later
- [HACS](https://hacs.xyz), for the recommended installation
- At least one `calendar.*` entity in Home Assistant (Google Calendar, CalDAV, Local
  Calendar, …)

## Installation, step by step

### 1. Prepare the panel

1. In the SwitchBot app, make sure the panel is added to your account and online.
2. Open the panel's settings in the app and **install any pending firmware update**. Wait
   for the panel to restart and reconnect to Wi-Fi.
3. Note the email, password and region of your SwitchBot account: you will need them in
   Home Assistant.

### 2. Install the integration with HACS

1. If HACS is not installed yet, follow the [HACS installation guide](https://hacs.xyz/docs/use/)
   and restart Home Assistant.
2. In Home Assistant open **HACS**, then the **⋮** menu in the top right corner, then
   **Custom repositories**.
3. Enter `https://github.com/francecesco/ha-switchbot-eink` as the repository, choose
   **Integration** as the type, and click **Add**.
4. Search for **SwitchBot E-Ink Home Dashboard** in HACS, open it and click **Download**.
5. **Restart Home Assistant** (Settings → System → Restart).

Manual alternative: copy `custom_components/switchbot_eink` from this repository into the
`custom_components` folder of your Home Assistant configuration, then restart.

### 3. Add the integration

1. Go to **Settings → Devices & services → Add integration** and search for **SwitchBot
   E-Ink Home Dashboard**.
2. Enter the email, password and region (`eu`, `us` or `ap`) of your SwitchBot account.
3. Choose your panel from the list.

The password is stored in Home Assistant, together with the tokens. SwitchBot's refresh
token has a limited lifetime and is never renewed, so without the password the integration
would ask you to sign in again every day. With it, the integration signs in again on its
own; Home Assistant only asks for the password if that sign-in fails, for example after you
changed it.

If you installed a version earlier than 0.4.0, the password was not stored: the next time
the token expires, Home Assistant asks for it once, and from then on the renewal is
automatic.

### 4. Choose the calendars

1. On the integration card, click **Configure**.
2. Under **Calendars to show**, select one or more calendars.
3. Leave the interval at 3600 seconds, or change it (see [Options](#options)).

Until at least one calendar is selected, the panel shows "No events in the next 3 days".

### 5. Publish and check

1. Open the panel's device page (**Settings → Devices & services → SwitchBot E-Ink Home
   Dashboard**, then your panel) and press **Refresh agenda**.
2. **Hold the button on the panel for two seconds.** After a few seconds the agenda
   appears.

### 6. Optional: put the button on a dashboard

On any dashboard, add a **Button** card and pick the panel's **Refresh agenda** entity. Or
in YAML, using the entity id shown on the device page:

```yaml
type: button
entity: button.your_panel_refresh_agenda
name: Refresh agenda
icon: mdi:calendar-refresh
```

## Options

| Option | Default | Notes |
|---|---|---|
| Calendars to show | none | multiple choice among the `calendar.*` entities |
| Seconds between publishes | 3600 (one hour) | minimum 60 |

## Entities

| Entity | What it does |
|---|---|
| Button *Refresh agenda* | rebuilds the agenda and publishes it right away, even if unchanged |
| Sensor *Last published* | when the agenda was last published successfully |
| Binary sensor *Authentication* | whether access to the SwitchBot account works |

They stay available even when publishing fails: that is exactly when they are needed. The
button shows the error if a publication fails.

## Service

`switchbot_eink.refresh` does what the button does, for all configured panels at once. It
is meant for automations. Both the service and the button respect a minimum of 60
seconds between two publications.

## Troubleshooting

**The panel shows SwitchBot's weather instead of the agenda.** This can happen after a
factory reset: the server has the agenda, but the panel keeps showing its native home.
In the observed case it was fixed by **installing the firmware update** offered by the
SwitchBot app and then holding the panel button for two seconds.

**The agenda is old.** The panel downloads about every three hours. Check *Last
published*, press *Refresh agenda*, then hold the panel button for two seconds.

**Authentication errors in the logs.** The *Authentication* binary sensor turns to
*problem* and Home Assistant offers to sign in again from the integrations page.

**Anything else.** Check the logs (Settings → System → Logs) filtering for
`switchbot_eink`, and open an [issue](https://github.com/francecesco/ha-switchbot-eink/issues).

### Command-line diagnostics

The layer that talks to SwitchBot also works on its own, without Home Assistant, from a
clone of this repository:

```bash
python -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install --group dev
export SWITCHBOT_USER='you@example.com' SWITCHBOT_REGION=eu
read -rsp "Password: " SWITCHBOT_PASS && export SWITCHBOT_PASS

.venv/bin/python -m tools.probe devices           # devices on the account
.venv/bin/python -m tools.probe templates         # the panel's templates, with their slot
.venv/bin/python -m tools.probe preview           # what the server will hand to the panel
.venv/bin/python -m tools.probe homepage          # where the panel takes its home page from
.venv/bin/python -m tools.probe agenda --lang en  # publish the agenda with sample events
```

`preview` is the first thing to try when something does not show up: it separates "the
publication did not reach the server" from "the panel has not downloaded it yet".

## Development

```bash
python -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install --group dev
.venv/bin/pytest
```

Do not use `pip install -e`: the editable install adds a path hook to `sys.path` that the
Home Assistant loader mistakes for a folder, and the tests in `tests/ha` fail.

The code is split into three layers with a single dependency direction:
`custom_components/switchbot_eink/api/` talks to SwitchBot and imports nothing from Home
Assistant; `layout/` is pure functions that turn events into components; the rest is the
integration proper. The icon in `custom_components/switchbot_eink/brand/` is generated by
`python -m tools.make_icon`.

## Disclaimer

This integration uses the private API of the SwitchBot web editor, reverse engineered from
its public JavaScript bundles. It is undocumented, and SwitchBot may change or shut it down
without notice. Everything that depends on it lives in
`custom_components/switchbot_eink/api/`.

Not affiliated with or endorsed by SwitchBot / Wonderlabs.

## License

[MIT](LICENSE)
