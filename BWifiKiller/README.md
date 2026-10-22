# BWifiKill ESP32 V4.0

## Pi USB diagnostics addition (2026-10-22)

The local source now accepts bounded `PIOT1 PING ID` and `PIOT1 SELFTEST ID`
requests over USB serial at 115200 baud. These report a round trip, both nRF24
SPI connections, and existing button input levels without selecting menu tools.
They do not verify physical switches, display pixels, touch input, or antennas.
The bundled binaries do not include this addition; flashing updated source is
required. Full Pi/SSH instructions are in the parent project's
`docs/ssh-and-usb-testing.md`.

Use `pio run -e esp32diag` for a build against the standard ESP32 SDK. This
profile retains SDK raw-frame validation and omits the legacy override that
otherwise causes a duplicate-symbol link error without a separately patched
SDK. Features that depend on bypassing that validation are not supported by
this profile. Physical button mappings are unchanged. Self-tests work from the
idle menu; active tools return busy or may delay replies if their loops block.

![Version](https://img.shields.io/badge/version-4.0-blue)
![Platform](https://img.shields.io/badge/platform-ESP32-orange)
![Framework](https://img.shields.io/badge/framework-PlatformIO-green)
![Display](https://img.shields.io/badge/display-SSD1306%20128x64-lightgrey)
![RF](https://img.shields.io/badge/RF-nRF24L01-red)
![License](https://img.shields.io/badge/license-MIT-black)

[![Web Flasher](https://img.shields.io/badge/Web%20Flasher-Install%20V4.0-00ff66?style=for-the-badge)](https://pepeangell5.github.io/BWifiKill-ESP32-V4.0/)
[![GitHub](https://img.shields.io/badge/GitHub-pepeangell5-181717?style=for-the-badge&logo=github)](https://github.com/pepeangell5)
[![Instagram](https://img.shields.io/badge/Instagram-esp32_tools-E4405F?style=for-the-badge&logo=instagram&logoColor=white)](https://www.instagram.com/esp32_tools)
[![Facebook](https://img.shields.io/badge/Facebook-esp32tools-1877F2?style=for-the-badge&logo=facebook&logoColor=white)](https://www.facebook.com/esp32tools)

BWifiKill ESP32 V4.0 is a portable suite for lab work, learning, and authorized auditing of WiFi networks, Bluetooth, and RF activity at 2.4 GHz. This version organizes the firmware into categories, improves the OLED interface, adds new passive tools, and prepares the project for installation using Web Flasher or PlatformIO.

The source interface, web pages, comments, documentation, and SVG diagrams are in English. See the [English construction and user manual](BUILD_MANUAL_EN.md) for a page-by-page translation of the original PDF's text. Original photographs, screenshots, and the illustrated PDF retain their embedded text.

The bundled `.bin` files and hosted installer still contain the original firmware. Build this local source with PlatformIO to use the English interface; cloning the upstream repository downloads its original source.

> Responsible use: some features are intended only for a controlled lab. Do not use this firmware against networks, devices, or people without explicit permission.

<p align="center">
  <img src="img/Firmware/splash.JPG" width="70%" alt="BWifiKill V4.0 splash">
</p>

## Contents

- [What's new in V4.0](#whats-new-in-v40)
- [Required hardware](#required-hardware)
- [Hardware connections](#hardware-connections)
- [Gallery](#gallery)
- [Firmware features](#firmware-features)
- [Installation and flashing](#installation-and-flashing)
- [Project structure](#project-structure)
- [V3.3 vs V4.0 differences](#v33-vs-v40-differences)
- [Social links](#social-links)
- [Disclaimer](#disclaimer)
- [License](#license)

## What's new in V4.0

- Main menu organized by category: WiFi, RF Tools, Bluetooth, Illegal, Games, and System.
- Updated OLED interface with headers, icons, animations, and better use of space.
- New WiFi tools: WiFi Radar and Channel Scan.
- New passive RF tools: RF Heatmap, CH Advisor, BT/WiFi Coex View, and Dual nRF Oscilloscope.
- New nRF tools for communication between your own devices: nRF Link and nRF Chat.
- Improved Bluetooth Scanner with manufacturer, RSSI, and a detail view.
- BT Analyzer and BT Spectrum for visual monitoring of BLE activity.
- Improved IP Scanner with a list of detected hosts and diagnostic actions.
- New restricted Deauther feature for your own lab and authorized testing.
- Games reorganized under Arcade.
- Web Dashboard with a dedicated AP: `BWifiKill_V4`, password `bwifikill40`, IP `192.168.4.1`.

<p align="center">
  <img src="img/diagramas/arquitectura-firmware.svg" width="78%" alt="Firmware architecture">
</p>

<p align="right"><a href="#contents">Back to contents</a></p>

## Required hardware

| Component | Quantity | Notes |
| --- | ---: | --- |
| ESP32 DevKit / ESP32-WROOM | 1 | Main firmware board. |
| SSD1306 I2C 128x64 OLED display | 1 | Common address: `0x3C`. |
| nRF24L01+ module | 2 | A 10 uF to 100 uF capacitor between VCC and GND is recommended. |
| Tactile buttons | 5 | UP, DOWN, OK, BACK, and AUX. |
| LiPo battery | 1 | Optional for portable use. |
| TP4056 | 1 | LiPo battery charging. |
| Step-up 5V | 1 | Stable ESP32 power when using a battery. |
| Switch | 1 | Main power switch. |
| PCB / breadboard / wires | 1 | Depending on your assembly. |

<p align="center">
  <img src="img/componentes/esp32U.png" width="23%" alt="ESP32">
  <img src="img/componentes/2NRF24.png" width="23%" alt="Two NRF24 modules">
  <img src="img/componentes/Pines_pantalla.png" width="23%" alt="OLED display">
  <img src="img/componentes/placapcb.png" width="23%" alt="PCB">
</p>

<p align="right"><a href="#contents">Back to contents</a></p>

## Hardware connections

### General diagram

<p align="center">
  <img src="img/componentes/conexiones-bwifikill.jpg" width="78%" alt="BWifiKill connections">
</p>

<p align="center">
  <img src="img/diagramas/pinout-general.svg" width="78%" alt="General pinout BWifiKill">
</p>

### OLED display SSD1306

| OLED | ESP32 | Note |
| --- | --- | --- |
| VCC | 3V3 | Use 3.3V if your module supports it. |
| GND | GND | Common ground for the entire circuit. |
| SDA | GPIO 21 | I2C data bus. |
| SCL | GPIO 22 | I2C clock bus. |

### Buttons

Connect the buttons between GPIO and GND. The firmware uses `INPUT_PULLUP`, so no external resistor is needed with this wiring.

| Button | GPIO | Feature |
| --- | ---: | --- |
| UP | 26 | Navigate up / increase value. |
| DOWN | 33 | Navigate down / decrease value. |
| OK | 32 | Enter / confirm / start. |
| BACK | 25 | Back / exit. |
| AUX | 27 | Secondary action depending on the app. |

### nRF24L01+ modules

Both nRF modules share the SPI bus. Only `CE` and `CSN` differ.

| Pin nRF24 | ESP32 | Note |
| --- | --- | --- |
| VCC | 3V3 | Never power with 5V. |
| GND | GND | Common ground. |
| SCK | GPIO 18 | SPI clock. |
| MISO | GPIO 19 | SPI MISO. |
| MOSI | GPIO 23 | SPI MOSI. |
| CE NRF1 | GPIO 5 | Control for the first nRF. |
| CSN NRF1 | GPIO 17 | Chip select for the first nRF. |
| CE NRF2 | GPIO 16 | Control for the second nRF. |
| CSN NRF2 | GPIO 4 | Chip select for the second nRF. |

<p align="center">
  <img src="img/componentes/Pines_NRF24.png" width="45%" alt="NRF24 pins">
  <img src="img/componentes/NRF24.png" width="35%" alt="NRF24 module">
</p>

### Portable power

| Module | Recommended connection |
| --- | --- |
| LiPo battery | To `B+` and `B-` on the TP4056. |
| TP4056 OUT+ / OUT- | Switch and step-up input. |
| Step-up 5V | To `VIN/5V` and `GND` on the ESP32. |
| nRF24 | Always to `3V3`, never to the 5V step-up. |

<p align="center">
  <img src="img/componentes/bateria.png" width="23%" alt="Battery">
  <img src="img/componentes/tp4056.png" width="23%" alt="TP4056">
  <img src="img/componentes/stepup.png" width="23%" alt="Step-up">
  <img src="img/componentes/interruptor.png" width="23%" alt="Switch">
</p>

<p align="right"><a href="#contents">Back to contents</a></p>

## Gallery

### WiFi

| Category | WiFi Scanner | WiFi Radar | Channel Scan |
| --- | --- | --- | --- |
| <img src="img/Firmware/wifi/cat-wifi.JPG" width="220" alt="Category WiFi"> | <img src="img/Firmware/wifi/wifi-scanner.JPG" width="220" alt="WiFi Scanner"> | <img src="img/Firmware/wifi/wifi-radar.JPG" width="220" alt="WiFi Radar"> | <img src="img/Firmware/wifi/chanel-scan.JPG" width="220" alt="Channel Scan"> |

| Packet Monitor | Sentinel Mode | IP Scanner | Web Dashboard |
| --- | --- | --- | --- |
| <img src="img/Firmware/wifi/packet-monitor.JPG" width="220" alt="Packet Monitor"> | <img src="img/Firmware/wifi/centinela.JPG" width="220" alt="Sentinel Mode"> | <img src="img/Firmware/wifi/ip-scanner.JPG" width="220" alt="IP Scanner"> | <img src="img/Firmware/wifi/web-dashboard.JPG" width="220" alt="Web Dashboard"> |

### RF Tools

| Category | Analyzer | RF Heatmap | CH Advisor |
| --- | --- | --- | --- |
| <img src="img/Firmware/rf/cat-rf.JPG" width="220" alt="Category RF Tools"> | <img src="img/Firmware/rf/analizador.JPG" width="220" alt="Analyzer"> | <img src="img/Firmware/rf/heatmap.JPG" width="220" alt="RF Heatmap"> | <img src="img/Firmware/rf/advisor.JPG" width="220" alt="CH Advisor"> |

| nRF Link | nRF Chat | BT/WiFi Coex | Dual nRF Scope |
| --- | --- | --- | --- |
| <img src="img/Firmware/rf/nrf-link.JPG" width="220" alt="nRF Link"> | <img src="img/Firmware/rf/nrf-chat.JPG" width="220" alt="nRF Chat"> | <img src="img/Firmware/rf/coex.JPG" width="220" alt="BT WiFi Coex"> | <img src="img/Firmware/rf/dual-scope.JPG" width="220" alt="Dual nRF Scope"> |

### Bluetooth

| Category | BT Scanner | BT Analyzer |
| --- | --- | --- |
| <img src="img/Firmware/bluetooth/cat-bt.JPG" width="260" alt="Category Bluetooth"> | <img src="img/Firmware/bluetooth/bt-scann.JPG" width="260" alt="BT Scanner"> | <img src="img/Firmware/bluetooth/bt-analyzer.JPG" width="260" alt="BT Analyzer"> |

| BT Spectrum | BT Remote |
| --- | --- |
| <img src="img/Firmware/bluetooth/bt-spectrum.JPG" width="260" alt="BT Spectrum"> | <img src="img/Firmware/bluetooth/bt-remote.JPG" width="260" alt="BT Remote"> |

### Restricted area

| Category | Channel Jammer | Full Sweep | BT Jammer |
| --- | --- | --- | --- |
| <img src="img/Firmware/ilegal/cat-ilegal.JPG" width="220" alt="Category Illegal"> | <img src="img/Firmware/ilegal/jam-canal.JPG" width="220" alt="Channel Jammer"> | <img src="img/Firmware/ilegal/barrido-total.JPG" width="220" alt="Full Sweep"> | <img src="img/Firmware/ilegal/jam-bt.JPG" width="220" alt="BT Jammer"> |

| Beacon Spam | BLE Spam | Hybrid Mode | Evil Portal |
| --- | --- | --- | --- |
| <img src="img/Firmware/ilegal/beacon-spam.JPG" width="220" alt="Beacon Spam"> | <img src="img/Firmware/ilegal/ble-spam.JPG" width="220" alt="BLE Spam"> | <img src="img/Firmware/ilegal/hybrid.JPG" width="220" alt="Hybrid Mode"> | <img src="img/Firmware/ilegal/evil-portal.JPG" width="220" alt="Evil Portal"> |

### Games

| Category | Snake | Pong |
| --- | --- | --- |
| <img src="img/Firmware/games/cat-games.JPG" width="260" alt="Category Games"> | <img src="img/Firmware/games/snake.JPG" width="260" alt="Snake"> | <img src="img/Firmware/games/pong.JPG" width="260" alt="Pong"> |

| Flappy | Invaders | Dino |
| --- | --- | --- |
| <img src="img/Firmware/games/flappy.JPG" width="260" alt="Flappy"> | <img src="img/Firmware/games/invaders.JPG" width="260" alt="Invaders"> | <img src="img/Firmware/games/dino.JPG" width="260" alt="Dino"> |

### System

| Category | Slave Control | View Logs | About |
| --- | --- | --- | --- |
| <img src="img/Firmware/system/cat-system.JPG" width="220" alt="Category System"> | <img src="img/Firmware/system/control-slave.JPG" width="220" alt="Slave Control"> | <img src="img/Firmware/system/logs.JPG" width="220" alt="View Logs"> | <img src="img/Firmware/system/about.JPG" width="220" alt="About"> |

<p align="right"><a href="#contents">Back to contents</a></p>

## Firmware features

### WiFi

| Feature | Short description |
| --- | --- |
| WiFi Scanner | Scans nearby networks and displays SSID, channel, RSSI, and security. Can connect to open networks for diagnostics. |
| WiFi Radar | Selects an AP and displays an RSSI-based proximity reading that updates as you move. |
| Channel Scan | Counts APs per channel, lists networks by channel, and displays details for each AP. |
| Packet Monitor | Graphical view of WiFi packets in monitor mode to observe nearby activity. |
| Sentinel Mode | Monitors unusual activity and displays an intensity bar to detect major changes in RF or WiFi management activity. |
| IP Scanner | Scans the connected local network, lists discovered hosts, and provides basic diagnostics such as ping. |
| Web Dashboard | Starts a local AP to view status, download logs, and manage data from a browser. |

### RF Tools

| Feature | Short description |
| --- | --- |
| Analyzer | General 2.4 GHz RF spectrum with adjusted sensitivity and visual alerts. |
| RF Heatmap | Passive RF energy map by area, useful for viewing accumulated activity. |
| CH Advisor | Recommends quieter WiFi/nRF channels based on passive nRF24 readings. |
| nRF Link | Tests communication between two BWifiKill devices using master/slave roles. |
| nRF Chat | Sends preset messages between two ESP32 devices with nRF24 for your own testing. |
| BT/WiFi Coex View | Compares typical WiFi and BLE frequency ranges to show their overlap at 2.4 GHz. |
| Dual nRF Scope | Uses two nRF24 modules as simultaneous probes, one for lower channels and one for higher channels. |

### Bluetooth

| Feature | Short description |
| --- | --- |
| BT Scanner | Scans Bluetooth/BLE devices and displays name, manufacturer, MAC, RSSI, and details. |
| BT Analyzer | Analyzes BLE activity per device, with a graph and detail view. |
| BT Spectrum | BLE/RF activity view focused on 2402-2480 MHz. |
| BT Remote | BLE HID remote control for testing with your own paired devices. |

### Restricted area / lab

These features are intended for controlled testing and education. Do not run them on networks, devices, or in spaces where you do not have authorization.

| Feature | Short description |
| --- | --- |
| Channel Jammer | Lab RF interference test on a selected channel. |
| Full Sweep | Wide RF sweep test at 2.4 GHz for an isolated environment. |
| BT Jammer | Lab interference test focused on the Bluetooth frequency range. |
| Beacon Spam | Generates test WiFi beacons to analyze scanner behavior. |
| BLE Spam (POP) | Lab BLE transmission to check responses from your own devices. |
| Hybrid Mode | Combines WiFi/RF tests in a controlled lab workflow. |
| Evil Portal | Local captive portal for training and authorized awareness testing. |
| Deauther | Lab feature for controlled WiFi management tests on your own networks or with explicit authorization. |

### Games

| Game | Short description |
| --- | --- |
| Snake | Classic snake game with button controls. |
| Pong | Pong against the CPU with corrected screen boundaries. |
| Flappy | Jumping game with obstacles adjusted to the visible area. |
| Invaders | Mini OLED arcade shooter. |
| Dino | Dinosaur-style runner for testing controls and the display. |

### System

| Feature | Short description |
| --- | --- |
| Slave Control | Controls a second compatible device in slave mode for your own tests. |
| View Logs | Local viewer for logs stored in internal memory. |
| About | Version, author, and social link information. |

<p align="right"><a href="#contents">Back to contents</a></p>

## Installation and flashing

### Method 1: Web Flasher

1. Open the web installer in Chrome or Edge:
   [Open BWifiKill V4.0 Web Flasher](https://pepeangell5.github.io/BWifiKill-ESP32-V4.0/)
2. Connect the ESP32 via USB.
3. Click `Install BWifiKill V4.0`.
4. Select the serial port.
5. If flashing does not start, hold `BOOT` while writing begins.

### Method 2: full binary with esptool

Use this file:

```bash
binarios/BWifiKill-ESP32-V4.0-full.bin
```

Recommended command:

```bash
esptool.py --chip esp32 --baud 921600 write_flash 0x0 binarios/BWifiKill-ESP32-V4.0-full.bin
```

### Method 3: PlatformIO

```bash
git clone https://github.com/pepeangell5/BWifiKill-ESP32-V4.0.git
cd BWifiKill-ESP32-V4.0
pio run
pio run -t upload
```

If you use VS Code:

1. Install the PlatformIO extension.
2. Open the project folder.
3. Connect the ESP32.
4. Click `Upload`.

<p align="right"><a href="#contents">Back to contents</a></p>

## Project structure

```text
BWifiKill-ESP32-V4.0/
|-- include/              Firmware headers
|-- src/                  Source code
|-- img/
|   |-- componentes/      Photos of parts, pins, and connections
|   |-- diagramas/        Explanatory diagrams
|   `-- Firmware/         Screenshots organized by category
|-- binarios/             Ready-to-flash binaries
|-- index.html            Web Flasher
|-- manifest.json         ESP Web Tools manifest
|-- platformio.ini        PlatformIO configuration
|-- LICENSE               License MIT
`-- README.md             Main documentation
```

<p align="right"><a href="#contents">Back to contents</a></p>

## V3.3 vs V4.0 differences

| Area | V3.3 | V4.0 |
| --- | --- | --- |
| Menu | Linear app list | Categories with icons and submenus. |
| UI | Simpler screens | Headers, animations, better layout, and less unnecessary text. |
| WiFi | Scanner, monitor, sentinel, IP scanner | Adds WiFi Radar and Channel Scan; improves IP Scanner. |
| Bluetooth | Scanner and basic BT Remote | Improves the scanner; adds BT Analyzer and BT Spectrum. |
| RF | Analyzer and nRF tests | Adds Heatmap, CH Advisor, Coex View, and Dual nRF Scope. |
| nRF communication | Not a primary focus | Adds nRF Link and nRF Chat between your own devices. |
| Documentation | Basic | Professional README, tables, images, flasher, and binaries. |

<p align="right"><a href="#contents">Back to contents</a></p>

## Social links

- Instagram: [@esp32_tools](https://www.instagram.com/esp32_tools)
- GitHub: [pepeangell5](https://github.com/pepeangell5)
- Facebook: [esp32tools](https://www.facebook.com/esp32tools)

<p align="right"><a href="#contents">Back to contents</a></p>

## Disclaimer

This firmware is published for education, research, learning electronics, RF analysis, and authorized auditing. Users are responsible for complying with their country's laws and obtaining permission before testing networks or devices they do not own.

The author accepts no responsibility for damage, interruptions, data loss, misuse, or legal consequences arising from use of this project.

<p align="right"><a href="#contents">Back to contents</a></p>

## License

Distributed under the MIT license. See [LICENSE](LICENSE) for details.

<p align="right"><a href="#contents">Back to contents</a></p>
