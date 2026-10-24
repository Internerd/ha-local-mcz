# MCZ Maestro (local) for Home Assistant

A Home Assistant custom integration that controls MCZ pellet stoves with the
**Maestro** Wi-Fi module **locally**, over the module's WebSocket interface on
your LAN. It needs no cloud account and no internet connection.

> **Status: early / experimental.** Only the functions listed below are
> implemented. Further functions are added once their protocol details are
> confirmed on a real stove.

*Deutsche Kurzfassung weiter unten.*

## Features

| Entity | Function |
|--------|----------|
| Climate | Switch the stove on and off, set the room temperature (0.5 °C steps on board firmware ≥ 1.9.0), shows the current room temperature and what the stove is doing (heating / idle / off) |
| Number | Power level 1–5 |
| Select | Front fan and ducted fans 1/2 (off, 1–5, auto). Only created for fans your stove reports as installed |
| Button | Reset an alarm |
| Sensor | Stove state (including alarm codes A01–A23), room / exhaust / board temperature, exhaust fan and auger speed, hours until service, control mode, adaptive mode, wireless probes 1–3 (disabled by default) |
| Binary sensor | Alarm, brazier needs cleaning, igniter, eco stop |
| Hydro models | Buffer, water, hot water tank and return temperatures, water setpoints, pump, 3-way valve (read-only for now) |

The integration also supports Home Assistant **diagnostics**. A diagnostics
download contains the raw frames from the stove, which helps when you report a
problem.

## Requirements

* An MCZ stove with a Maestro Wi-Fi module that your Home Assistant host can reach
  over the network. The default port is 81.
* A fixed IP address or a DHCP reservation for the stove is recommended.
* Home Assistant 2025.8 or newer.

## Installation

### HACS (recommended)

1. In HACS, open the menu → **Custom repositories**.
2. Add `https://github.com/internerd/ha-local-mcz` as type **Integration**.
3. Install **MCZ Maestro (local)** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and search for
   **MCZ Maestro (local)**.

### Manual

Copy `custom_components/mcz_local` into the `custom_components` folder of your
Home Assistant configuration, then restart Home Assistant.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| Host | – | IP address or hostname of the stove |
| Port | 81 | WebSocket port |
| Polling interval | 5 s | Under **Configure**, 3–300 seconds |

If the IP address of the stove changes, open the integration's menu (⋮) and
choose **Reconfigure**. You don't need to remove and re-add it.

## Safety

This software sends commands to a heating appliance. Always follow the
manufacturer's operating and safety instructions, and never rely on this
integration for anything related to safety. Before you use it in automations,
check every function on your own stove while you are present.

## Legal notice

* This is an independent community project. It is **not affiliated with,
  endorsed by or supported by MCZ Group S.p.A.** or any of its subsidiaries.
* "MCZ" and "Maestro" are trademarks of their respective owners. They are used
  here only to say which devices this software works with.
* This repository contains only original code written for interoperability. It
  does not contain any code, assets, images or documentation of the
  manufacturer or of the manufacturer's apps.
* The software is provided "as is", without any warranty, under the
  [MIT License](LICENSE). You use it at your own risk.

---

## Deutsch (Kurzfassung)

Diese Home-Assistant-Integration steuert MCZ-Pelletöfen mit Maestro-WLAN-Modul
**lokal** über das WebSocket-Interface des Moduls (Port 81). Sie braucht weder
Cloud noch Konto.

**Installation:** In HACS das Repository
`https://github.com/internerd/ha-local-mcz` als benutzerdefiniertes
Repository vom Typ **Integration** hinzufügen, die Integration installieren und
Home Assistant neu starten. Danach unter **Einstellungen → Geräte & Dienste**
„MCZ Maestro (lokal)“ hinzufügen und die IP-Adresse des Ofens eingeben.

**Hinweise:** Dies ist ein inoffizielles Projekt ohne Verbindung zu MCZ Group
S.p.A. Die Marken gehören ihren Inhabern. Die Software steuert ein Heizgerät:
Halte dich an die Bedienungs- und Sicherheitsanleitung des Herstellers und
teste jede Funktion vor Ort. Die Nutzung erfolgt auf eigene Gefahr und ohne
Gewährleistung (MIT-Lizenz).
