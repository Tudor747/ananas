# Raspberry Pi appliance: hardware and screen requirements

Updated 2026-10-22. This is the current build scope and supersedes older
multi-ESP and antenna-count proposals. These are requirements, not a claim that
the hardware integration or screen layout is already implemented.

## Confirmed build

- Raspberry Pi is the only application host; no separate computer is required
  during normal operation. Raspberry Pi OS and SSH are already configured.
  The earlier plan names Pi 5; exact model is to confirm.
- Exactly one ESP companion device, connected to the Raspberry Pi via USB.
- Four physical buttons and two switches in the user's ESP assembly. Preserve
  their existing behavior. The user confirms the second switch is on/off;
  the reference source differs as detailed below.
- Two 2.4 GHz antennas. The BWifiKiller reference build specifies two nRF24L01+
  radio modules; physical module variant and antenna connections are unverified.
- The operator uses an interactive menu on the Raspberry Pi screen, identified
  by the user as `HSD28309 EI`, with touch already working. Resolution and
  interface have not been established from this identifier.

Existing Windows/Kali instructions describe development or compatibility use,
not additional hardware required for the appliance. The user has requested Pi
diagnostics and ESP USB self-tests over SSH. A limited diagnostic firmware
addition is implemented in source; it preserves physical button mappings and
requires a one-time firmware update. See [SSH and USB testing](ssh-and-usb-testing.md).

## Screen interaction

- Present two large primary menu buttons per page, using the available screen
  area. Page 1 contains two options; page 2 contains the next two, and so on.
- Navigate vertically through pages by sliding/swiping to see further options.
  Snap to a page after the gesture so two options remain visible at rest.
- Provide button-based page scrolling as well. Use on-screen previous/next
  controls as the provisional design, preserving existing ESP button behavior.
- Menu ordering is unrestricted; choose a practical order from existing features.
- Keep the selected item clear and provide a way to activate it and return.
- The two large screen buttons are distinct from the four physical buttons.
  Forwarding physical ESP buttons to the Pi is not an existing capability.
- Use the existing touch input for tapping options and vertical swipe paging.
  Check the screen size, resolution, and orientation on the Pi when tuning layout.

The current website has not yet been converted to this menu. Full-screen browser
startup on the Pi and physical input integration remain implementation work.
The existing firmware has no verified general Pi control/telemetry API; wiring
buttons to the ESP does not by itself make them control the Pi menu.
USB is the confirmed physical connection. The new source implements PING and
SELFTEST at 115200 baud with a matching Python CLI. Installed original firmware
does not implement this protocol. No automatic scan-result stream or general
ESP menu control is implemented.

## Existing ESP controls and radios: repository evidence

`BWifiKiller/include/app_config.h` and `src/input_manager.cpp` already define
and read the ESP controls. These mappings are not new assignments:

| Input | ESP GPIO | Existing role |
| --- | --- | --- |
| UP | 26 | Navigate up / increase |
| DOWN | 33 | Navigate down / decrease |
| OK | 32 | Enter / confirm |
| BACK | 25 | Return / exit |
| AUX | 27 | App-specific secondary action |

The reference README lists five tactile buttons and one main power switch.
`BWifiKiller/BUILD_MANUAL_EN.md` describes that switch as cutting power, not a
programmed menu input. The user's four-button/two-switch assembly remains the
build requirement. The user confirms the second switch is on/off. Preserve that
function; do not repurpose it for menu navigation or assume it replaces AUX.
Its exact wiring and the first switch's mapping are not established by this
confirmation.

The reference README specifies an ESP32 DevKit / ESP32-WROOM and two nRF24L01+
modules. `src/main.cpp` instantiates two RF24 devices, and `app_config.h` defines
their separate CE/CSN pairs. This identifies the reference radio design without
requiring the user to identify a radio model from scratch. The ESP's reference
SSD1306 OLED is distinct from the user's Raspberry Pi screen. Checked-in source
does not prove which firmware binary or wiring is present on the assembled unit.

## Remaining hardware checks

1. Read the screen's resolution, connection, and orientation from the Pi when
   tuning the layout. Touch support is confirmed by the user.
2. Before any wiring or firmware changes, reconcile the existing assembly with
   the reference build. Keep the second switch's confirmed on/off function.
3. Confirm the exact Pi model and installed ESP firmware when hardware is available.
4. Install and test the USB diagnostic firmware on the actual ESP. The user will
   connect over SSH and run the checks themselves; no physical deployment has
   been performed from this workspace.

## Acceptance criteria for the planned implementation

- Normal operation uses only the Pi and the single ESP assembly.
- The Pi screen shows two large primary menu choices at a time.
- Swiping and the agreed scrolling buttons reach the same menu choices.
- Selection, activation, and return work with the agreed input mapping.
- Each physical button and switch has a documented, verified function.
- Disconnected ESP hardware is shown accurately; manual instrument records
  are not presented as a live connection.
