#ifndef WEB_SERVER_H
#define WEB_SERVER_H

#include <Arduino.h>
#include <ESPAsyncWebServer.h>
#include <WiFi.h>
#include "app_config.h"
#include "SPIFFS.h"

extern AsyncWebServer asyncServer;

const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE HTML><html lang="en">
<head>
  <meta charset='UTF-8'>
  <title>BWifiKill Terminal</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: 'Courier New', monospace; background-color: #0d0d0d; color: #00ff00; padding: 20px; margin: 0; }
    h1 { color: #ffffff; text-align: center; text-shadow: 0 0 10px #00ff00; border-bottom: 2px solid #00ff00; padding-bottom: 10px; font-size: 1.5em; }
    .card { background: #1a1a1a; border-radius: 5px; padding: 15px; margin: 10px auto; border: 1px solid #333; max-width: 600px; }
    #log-container { height: 350px; overflow-y: auto; background: #000; padding: 15px; border: 1px solid #00ff00; font-size: 0.85em; line-height: 1.4; white-space: pre-wrap; color: #00ff00; margin-bottom: 15px; }
    .btn { border: none; padding: 12px; font-weight: bold; cursor: pointer; border-radius: 3px; width: 100%; font-family: sans-serif; margin-bottom: 10px; text-decoration: none; display: block; text-align: center; }
    .btn-refresh { background: #00ff00; color: #000; }
    .btn-download { background: #008CBA; color: white; }
    .btn-clear { background: #ff3333; color: #ffffff; }
    footer { font-size: 0.7em; color: #444; margin-top: 20px; text-align: center; }
  </style>
  <script>
    function fetchLogs() {
      fetch('/get-logs').then(response => response.text()).then(data => {
        const container = document.getElementById('log-container');
        container.innerText = data.trim() === "" ? "No new records..." : data;
        container.scrollTop = container.scrollHeight;
      });
    }

    function clearLogs() {
      if(confirm("Are you sure you want to permanently delete all captures?")) {
        fetch('/clear-logs').then(response => response.text()).then(data => {
          alert(data);
          fetchLogs();
        });
      }
    }
    setInterval(fetchLogs, 5000);
  </script>
</head>
<body onload="fetchLogs()">
  <h1>⚡ BWifiKill Dashboard</h1>
  <div class="card">
    <div id="log-container">Loading database...</div>
    
    <button class="btn btn-refresh" onclick="fetchLogs()">REFRESH VIEW</button>
    
    <a href="/download-logs" class="btn btn-download">DOWNLOAD .TXT TO PHONE</a>
    
    <button class="btn btn-clear" onclick="clearLogs()">DELETE ALL (CLEAR ESP32)</button>
  </div>
  <footer>Admin: PepeAngell | v4.0</footer>
</body>
</html>)rawliteral";

void startWebServer() {
    if(!SPIFFS.begin(true)) Serial.println("SPIFFS error");

    WiFi.softAPdisconnect(true);
    delay(100);
    WiFi.mode(WIFI_OFF);
    delay(100);
    WiFi.mode(WIFI_AP); 
    bool apStarted = WiFi.softAP(AppConfig::WEB_AP_SSID, AppConfig::WEB_AP_PASSWORD, 6);
    if (!apStarted) Serial.println("Error starting Web Dashboard AP");
    
    asyncServer.reset();

    asyncServer.on("/", HTTP_GET, [](AsyncWebServerRequest *request){
        request->send(200, "text/html", index_html);
    });

    asyncServer.on("/get-logs", HTTP_GET, [](AsyncWebServerRequest *request){
        if (SPIFFS.exists(AppConfig::LOG_FILE_PATH)) {
            request->send(SPIFFS, AppConfig::LOG_FILE_PATH, "text/plain");
        } else {
            request->send(200, "text/plain", "");
        }
    });

    // NEW ROUTE: Force file download
    asyncServer.on("/download-logs", HTTP_GET, [](AsyncWebServerRequest *request){
        if (SPIFFS.exists(AppConfig::LOG_FILE_PATH)) {
            // The third parameter "true" enables download mode (Attachment)
            request->send(SPIFFS, AppConfig::LOG_FILE_PATH, "text/plain", true);
        } else {
            request->send(200, "text/plain", "No file available to download.");
        }
    });

    asyncServer.on("/clear-logs", HTTP_GET, [](AsyncWebServerRequest *request){
        if (SPIFFS.remove(AppConfig::LOG_FILE_PATH)) {
            request->send(200, "text/plain", "Database deleted.");
        } else {
            request->send(200, "text/plain", "Error deleting.");
        }
    });

    asyncServer.begin();
}
#endif
