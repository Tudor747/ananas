# BWifiKill ESP32 V4.0 — Construction and user manual

English translation of the text in the [original illustrated manual](Guia%20de%20construccion%20y%20conexiones/Manual_BWifiKill_ESP32_V4_Construccion.pdf). Page references below match that PDF. Original photographs, screenshots, and text embedded in images remain in the PDF; the editable [architecture](img/diagramas/arquitectura-firmware.svg) and [pinout](img/diagramas/pinout-general.svg) diagrams are translated separately.

The technical statements below are translated from the original manual, rather than independently verified specifications.

## Page 1 — Cover

Construction and user manual — BWifiKill ESP32 V4.0.

Portable lab suite for WiFi, RF, and Bluetooth analysis at 2.4 GHz.

Project: https://github.com/pepeangell5/BWifiKill-ESP32-V4.0

Instagram: @pepeangelll • Facebook: esp32tools • Website: PepeAngell.dev

The original manual repeats this footer on every page: **Responsible use — only on your own networks and devices or with explicit authorization.**

## Page 2 — Responsible use notice

This project is published for education, learning electronics, and authorized auditing.

Some firmware features are intended exclusively for controlled laboratory environments. Their use on networks, devices, or in spaces without the owner's explicit permission is strictly prohibited.

The author accepts no responsibility for damage, interruptions, data loss, misuse, or legal consequences arising from use of this project. Users are responsible for complying with their country's laws.

## Page 3 — What is BWifiKill ESP32 V4.0?

BWifiKill ESP32 V4.0 is a portable handheld device you can build yourself using common electronic components. Once assembled and programmed, it becomes a complete lab suite for learning about, analyzing, and auditing WiFi networks, Bluetooth signals, and radio-frequency (RF) activity in the 2.4 GHz band.

Think of it as an electronic Swiss Army knife: it fits in your hand, runs on a battery, has its own display and navigation buttons, and provides a full menu organized by category. All software runs inside the ESP32; you do not need to connect it to a computer to use it.

*Illustration: firmware architecture — available categories and tools.*

### What you will learn by building this project

Besides getting the device working, building it teaches you how to connect I2C, SPI, and GPIO modules to an ESP32, power a portable circuit with a LiPo battery, flash firmware from a browser, and understand how an interactive OLED menu works internally.

## Page 4 — Required components

Before soldering or connecting wires, obtain all the components on this list. You can find them at local electronics stores, MercadoLibre, AliExpress, or Amazon.

## Page 5 — 1. ESP32 DevKit / ESP32-WROOM-32U

*Illustration: 38-pin ESP32-WROOM-32U — the device's brain.*

This is the main component. It contains the dual-core microcontroller that runs all the firmware, plus integrated WiFi and Bluetooth. You need exactly one unit.

### Its role in this project

The ESP32 is the brain. It reads the buttons, controls the display, scans WiFi networks, analyzes RF signals through the nRF24 modules, and runs all firmware menus and tools.

## Page 6 — 2. SSD1306 OLED display — 128×64 pixels, I2C

*Illustration: 0.96-inch SSD1306 OLED module with I2C interface.*

This is the device's display. It measures 0.96 inches and shows text, graphs, animations, and menus. It communicates with the ESP32 using I2C, requiring only two data wires and four wires in total when GND (ground) and VCC (supply voltage) are included. You need one unit.

### Important technical details

Resolution: 128×64 pixels. Protocol: I2C. Address: 0x3C, the most common address. Operating voltage: 3.3V. It consumes very little current, making it suitable for battery-powered devices.

## Page 7 — 3. nRF24L01+ modules — two required

*Illustrations: standard nRF24L01+ module; nRF24 pin diagram; pair of nRF24L01+ modules.*

These are the device's eyes for the 2.4 GHz radio-frequency band. Each module has an RF receiver/transmitter that lets the ESP32 scan, analyze, and measure radio spectrum activity. You need two modules: one for lower channels and one for higher channels, allowing full spectrum coverage.

### Filter capacitor — very important

The nRF24L01 is sensitive to voltage variations. Soldering a 10–100 uF electrolytic capacitor directly between the module's VCC and GND pins is recommended. Without it, the module may behave unpredictably or simply fail to work.

### Technical details

Operating frequency: 2.400–2.525 GHz. 125 selectable channels. Operating voltage: 1.9–3.6V. NEVER connect to 5V, as this will cause permanent damage. Communication protocol with the ESP32: SPI.

## Page 8 — 4. Tactile buttons — five required

These are the device's five navigation buttons. The user interacts with all firmware menus through them. Each button has a specific function assigned in the code.

| Button | Menu function |
| --- | --- |
| UP | Navigate up / increase value |
| DOWN | Navigate down / decrease value |
| OK | Enter option / confirm / start |
| BACK | Go back / exit the current screen |
| AUX | Secondary action depending on the active tool |

## Page 9 — 5. LiPo battery — optional but recommended; one required

*Illustration: rechargeable LiPo battery — makes the device fully portable.*

A lithium-polymer (LiPo) battery makes the device fully portable. Without it, the ESP32 must remain connected by USB to a computer or charger. A capacity of 500–2000 mAh is recommended. The author notes that the battery can be reused and that they reuse batteries from old vapes.

### LiPo battery precautions

LiPo batteries can be dangerous if overcharged, short-circuited, or physically damaged. Never leave them charging unattended. Do not puncture, crush, or expose them to direct heat. Always use a dedicated charging module such as the TP4056.

## Page 10 — 6. TP4056 module — battery charger; one required

*Illustration: TP4056 module — manages LiPo charging with protection.*

The TP4056 is an integrated circuit designed specifically to charge LiPo batteries safely. It accepts USB input, using micro-USB or USB-C depending on the model, and regulates charging current and voltage to avoid damaging the battery. Some models include over-discharge and short-circuit protection.

### How it works

Connect the USB cable to the TP4056 to charge. The TP4056 protects and charges the LiPo battery. The battery powers the step-up converter, which supplies a stable 5V to the ESP32.

## Page 11 — 7. 5V step-up module — one required

*Illustration: step-up converter — raises the battery voltage to a stable 5V.*

A charged LiPo battery supplies between 3.7V and 4.2V. The ESP32 needs a stable 5V at its VIN pin to operate correctly. The step-up module, a voltage-boost converter, takes the battery's variable voltage and converts it into a constant 5V, regardless of the battery's charge level.

## Page 12 — 8. Power switch — one required

*Illustration: toggle switch — turns the device on and off.*

A simple toggle or slide switch cuts the power between the TP4056 and the step-up converter. This turns the device off completely without physically disconnecting the battery.

## Page 13 — 9. PCB or breadboard and wires

*Illustration: custom BWifiKill PCB — optional; a breadboard also works.*

## Page 14 — Assembly options

You can assemble the circuit in different ways depending on your experience and the materials available:

- **Breadboard:** easiest for beginners. No soldering required. Ideal for initial testing.

## Page 15 — Perforated board

- **Perforated PCB:** the more professional, compact option. Requires soldering all components.

The tools needed for these options are shown in the original illustration.

## Page 16 — Hardware connections

This section connects all components step by step. Read each entire section before making the connections. Double-check before applying power.

*Illustration: general BWifiKill V4.0 wiring diagram.*

## Page 17 — General hardware connections and OLED wiring

*Reference photograph: physical connections of the complete device.*

The OLED display communicates using I2C. It uses only two data wires, SDA and SCL, in addition to power. I2C is like an orderly conversation in which the ESP32 talks and the display listens, following a strict sequence.

| OLED pin | ESP32 pin | Description |
| --- | --- | --- |
| VCC | 3V3 | 3.3V power — do not use 5V |
| GND | GND | Common ground for the entire circuit |
| SDA | GPIO 21 | I2C data line |
| SCL | GPIO 22 | I2C clock line |

## Page 18 — OLED step 1

Connect OLED GND to ESP32 GND.

## Page 19 — OLED step 2

Connect OLED VCC to the ESP32 3V3 pin.

## Page 20 — OLED step 3

Connect OLED SCL to ESP32 GPIO 22.

## Page 21 — OLED step 4 and verification

Connect OLED SDA to ESP32 GPIO 21.

If the wiring is correct and the firmware is installed, the display will show the BWifiKill startup animation within the first few seconds after powering on the ESP32.

## Page 22 — Button connections and step 1

Connect each button between a GPIO pin and GND. The firmware uses the ESP32's `INPUT_PULLUP` function, meaning an internal resistor keeps the pin HIGH. Pressing the button connects the pin to GND and pulls it LOW. No external resistors are needed.

| Button | ESP32 GPIO | Other terminal | Function |
| --- | --- | --- | --- |
| UP | GPIO 26 | GND | Increase / navigate up |
| DOWN | GPIO 33 | GND | Decrease / navigate down |
| OK | GPIO 32 | GND | Confirm / enter |
| BACK | GPIO 25 | GND | Back / exit |
| AUX | GPIO 27 | GND | Secondary function |

Step 1: connect one terminal of UP to GPIO 26 and the other to GND.

## Page 23 — Buttons step 2

Connect DOWN between GPIO 33 and GND.

## Page 24 — Buttons step 3

Connect OK between GPIO 32 and GND.

## Page 25 — Buttons step 4

Connect BACK between GPIO 25 and GND.

## Page 26 — Buttons step 5

Connect AUX between GPIO 27 and GND.

## Page 27 — Connecting the nRF24L01+ modules

*Illustrations: nRF24L01+ pinout; front view of the module.*

Both nRF24 modules share the ESP32 SPI bus, using the same SCK, MISO, and MOSI pins. Their CE and CSN pins differ; the ESP32 uses these to select which module to communicate with at a given time.

### Never connect the nRF24 modules to 5V

The nRF24L01+ modules operate at a maximum of 3.3V. Connecting them to 5V causes permanent, irreversible damage. Always connect VCC to the ESP32's 3V3 pin, NEVER its 5V pin.

## Page 28 — nRF24 wiring table and step 1

| nRF24 pin | ESP32 | Applies to | Description |
| --- | --- | --- | --- |
| VCC | 3V3 | NRF1 and NRF2 | Power — 3.3V ONLY |
| GND | GND | NRF1 and NRF2 | Common ground |
| SCK | GPIO 18 | NRF1 and NRF2 | SPI shared clock |
| MISO | GPIO 19 | NRF1 and NRF2 | SPI data to ESP32 |
| MOSI | GPIO 23 | NRF1 and NRF2 | SPI data from ESP32 |
| CE NRF1 | GPIO 5 | NRF1 only | First module control |
| CSN NRF1 | GPIO 17 | NRF1 only | First module chip select |
| CE NRF2 | GPIO 16 | NRF2 only | Second module control |
| CSN NRF2 | GPIO 4 | NRF2 only | Second module chip select |

Step 1: connect VCC on NRF1 and NRF2 to ESP32 3V3. Add a 10–100 uF capacitor between VCC and GND on each nRF module. VCC is shared with the OLED display.

## Page 29 — nRF24 step 2

Connect GND on NRF1 and NRF2. These can connect together because this pin is shared with the display.

## Page 30 — nRF24 step 3

Connect NRF1 CE to GPIO 5 and NRF1 CSN to GPIO 17. GPIO 5 and GPIO 17 are dedicated to NRF1.

## Page 31 — nRF24 step 4

Connect NRF2 CE to GPIO 16 and NRF2 CSN to GPIO 4. GPIO 16 and GPIO 4 are dedicated to NRF2.

## Page 32 — nRF24 step 5

Connect SCK on both nRF modules to GPIO 18. Pin 18 is shared by both modules. You can join both wires together to connect them to GPIO 18.

## Page 33 — nRF24 step 6

Connect MOSI on both nRF modules to GPIO 23. Pin 23 is shared by both modules. You can join both wires together to connect them to GPIO 23.

## Page 34 — nRF24 step 7 and completion

Connect MISO on both nRF modules to GPIO 19. Pin 19 is shared by both modules. You can join both wires together to connect them to GPIO 19.

**Done — you have finished the connections!** Your device is now functional. The next step is optional if you want to make it portable with a battery.

## Page 35 — Connecting the portable power system

*Illustrations: LiPo battery, TP4056 module, 5V step-up converter, switch.*

The power system has four stages in sequence. Energy flows as follows:

1. **LiPo battery:** the energy source. Supplies 3.7–4.2V depending on its charge level.
2. **TP4056:** manages and protects battery charging. Connect the battery to B+ and B-. OUT+ and OUT- supply power to the rest of the circuit.
3. **Switch:** goes between TP4056 OUT+ and the step-up input. Turning it off cuts power without disconnecting the battery.
4. **5V step-up:** converts the variable battery voltage, 3.7–4.2V, into a stable 5V. Connect its output to ESP32 VIN 5V and GND. Adjust it manually to 5V before connecting the ESP32 because its factory output voltage is different.

## Page 36 — Power connections

| Module | Connection |
| --- | --- |
| LiPo battery | TP4056 B+ and B- terminals |
| TP4056 OUT+ | One terminal of the switch |
| TP4056 OUT- | Step-up GND and ESP32 GND |
| Switch | Between TP4056 OUT+ and step-up VIN input |
| Step-up output | ESP32 VIN (+5V) and GND |
| nRF24 VCC | ALWAYS ESP32 3V3, never directly to the step-up |

*Illustration: complete power system — battery, TP4056, switch, and step-up.*

## Page 37 — Firmware installation and Web Flasher step 1

Firmware is the software that makes the device work. There are three ways to install it. The easiest is Web Flasher, which requires no installation on your computer.

### Method 1: Web Flasher — recommended for beginners

No installations — you only need Chrome or Edge. Web Flasher works directly in the browser. It does not require drivers, Python, or any additional program. It is the fastest way to get the device running.

Step 1: open the flasher in Chrome or Edge at https://pepeangell5.github.io/BWifiKill-ESP32-V4.0/.

## Page 38 — Web Flasher step 2

Connect the ESP32 to your computer with a USB data cable.

## Page 39 — Web Flasher step 3

Click **Install BWifiKill V4.0** and select the serial port shown in the list.

## Page 40 — Web Flasher step 4

If writing does not start automatically, hold the ESP32 BOOT button while flashing begins.

## Page 41 — Web Flasher step 5

Wait for the progress bar to finish. The ESP32 will restart automatically with the new firmware.

## Page 42 — Advanced installation methods

### Method 2: Binary with esptool — advanced mode

If you prefer the command-line tool, use the full binary included in the repository:

```bash
esptool.py --chip esp32 --baud 921600 write_flash 0x0 binarios/BWifiKill-ESP32-V4.0-full.bin
```

### Method 3: PlatformIO — for developers

To compile and modify the source code:

```bash
git clone https://github.com/pepeangell5/BWifiKill-ESP32-V4.0.git
cd BWifiKill-ESP32-V4.0
pio run
pio run -t upload
```

## Page 43 — Firmware feature guide: WiFi

Once the firmware is installed and the device is powered on, the main menu appears, organized into categories. Use UP/DOWN to navigate and OK to enter an option.

*Screenshots: WiFi menu, WiFi Scanner, WiFi Radar, Channel Scan, Packet Monitor, Sentinel, IP Scanner, Web Dashboard.*

| Tool | What it does |
| --- | --- |
| WiFi Scanner | Scans nearby networks. Displays SSID, channel, RSSI, and security type. Allows connection to open networks for diagnostics. |
| WiFi Radar | Select an access point to see in real time how close or far away it is, based on signal strength (RSSI). |
| Channel Scan | Counts access points on each WiFi channel. Useful for choosing the least congested channel for an installation. |

## Page 44 — More WiFi tools

| Tool | What it does |
| --- | --- |
| Packet Monitor | Graphical view of WiFi packets in the air. Shows nearby activity in passive monitor mode. |
| Sentinel Mode | Watches nearby activity and generates a visual alert if it detects major unusual changes in RF or WiFi management activity. |
| IP Scanner | Connects to a WiFi network and scans active devices on the local network. Lists their IP addresses and allows diagnostic pings. |
| Web Dashboard | Creates its own WiFi access point: network `BWifiKill_V4`, password `bwifikill40`. Connect from a phone to view status and download logs at `192.168.4.1`. |

## Page 45 — RF Tools category

*Screenshots: RF Tools menu, RF Analyzer, RF Heatmap, CH Advisor, nRF Link, nRF Chat, BT/WiFi Coex, Dual nRF Scope.*

| Tool | What it does |
| --- | --- |
| RF Analyzer | Shows the general 2.4 GHz RF spectrum. Uses both nRF24 modules to measure energy on each channel and display it as an OLED graph. |
| RF Heatmap | Accumulates passive RF energy readings by spectrum area and displays a heatmap. Useful for seeing where activity accumulates. |
| CH Advisor | Analyzes WiFi and nRF channels and recommends the quietest for network installation or communication between your own devices. |
| nRF Link | Tests communication between two BWifiKill devices in master/slave mode. Useful for checking that both nRF24 modules work correctly. |
| nRF Chat | Sends preset text messages from one BWifiKill device to another through the nRF24 modules. |
| BT/WiFi Coex View | Shows how WiFi and Bluetooth frequency ranges overlap in the 2.4 GHz band, helping explain possible interference. |
| Dual nRF Scope | Uses both nRF24 modules as simultaneous probes. One monitors lower spectrum channels and the other monitors higher channels. |

## Page 46 — Bluetooth category

*Screenshots: Bluetooth menu, BT Scanner, BT Analyzer, BT Spectrum, BT Remote.*

| Tool | What it does |
| --- | --- |
| BT Scanner | Scans nearby Bluetooth and BLE devices. Displays device name, manufacturer, MAC address, signal strength (RSSI), and device type. |
| BT Analyzer | Analyzes BLE activity individually for each device. Shows signal strength over time and details of the selected device. |
| BT Spectrum | Graphical BLE/RF activity view in the 2402–2480 MHz band. Shows which frequencies have the most nearby Bluetooth activity. |
| BT Remote | Emulates a BLE HID remote control for testing your own Bluetooth-capable devices, such as paired computers or phones. |

## Page 47 — Games category: Arcade

*Screenshots: Games menu, Snake, Pong, Flappy, Invaders, Dino Runner.*

The device includes five classic games, fully playable on the OLED display using the navigation buttons. They are useful for checking that the buttons and display work correctly after assembly.

## Page 48 — System category

*Screenshots: System menu, Slave Control, View Logs, About.*

| Feature | What it does |
| --- | --- |
| Slave Control | Controls a second BWifiKill device in slave mode. The code must be modified to enter the second ESP32's MAC address. |
| View Logs | Displays records saved in the ESP32's internal memory during previous sessions. |
| About | Displays firmware version, author, and social links. |

## Page 49 — Restricted area / lab

*Screenshots: restricted area menu, Channel Jammer, Beacon Spam, Evil Portal.*

**For controlled laboratory use only.**

Features in this category generate interference or simulate network attacks. Using them outside a controlled environment and on networks or devices without explicit authorization is illegal in most countries and can have serious legal consequences.

These features exist exclusively for education: understanding how vulnerabilities work in order to defend against them. Use them only on your own networks or with documented permission from the owner.

## Page 50 — Troubleshooting common problems

### OLED display does not turn on

- Check that VCC connects to 3V3, not 5V.
- Confirm SDA goes to GPIO 21 and SCL to GPIO 22.
- Check for loose wires or poor contacts.
- Check that the module's I2C address is 0x3C.

### Buttons do not respond

- Confirm GPIO assignments: UP=26, DOWN=33, OK=32, BACK=25, AUX=27.
- Check that the other terminal of each button connects to GND.
- If a button activates by itself, check for a short circuit.

### nRF24 modules do not work

- Confirm VCC connects to 3V3, NEVER 5V.
- Add a 10–100 uF capacitor between VCC and GND on the nRF24 module.
- Check CE and CSN: NRF1 uses GPIO 5 and GPIO 17; NRF2 uses GPIO 16 and GPIO 4.
- Ensure SCK, MISO, and MOSI connect to GPIO 18, GPIO 19, and GPIO 23.

### Device turns itself off — brownout

- The ESP32 needs a stable current supply. Check that the step-up supplies 5V.
- Check the battery; it may be very discharged.
- If using USB directly, try a USB port on the computer rather than a hub.

## Page 51 — Web Flasher does not detect the ESP32

- Use Chrome or Edge; it does not work in Firefox or Safari.
- Check that the USB cable supports data, not just charging.
- Install the driver for the board's USB-to-serial chip: CP2102, CH340, or FTDI.
- If flashing does not start, hold the ESP32 BOOT button as the process begins.

## Page 52 — Back cover

BWifiKill ESP32 V4.0 — Construction and user manual.

Project: https://github.com/pepeangell5/BWifiKill-ESP32-V4.0

Instagram: @pepeangelll • Facebook: esp32tools • Website: PepeAngell.dev

Distributed under the MIT license.
