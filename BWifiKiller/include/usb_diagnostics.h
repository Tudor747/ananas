#pragma once

// Called by the main loop; accepts only PING and SELFTEST requests.
// Does not launch tools, emulate buttons, or change radio configuration.
void pollUsbDiagnostics(bool appRunning);
