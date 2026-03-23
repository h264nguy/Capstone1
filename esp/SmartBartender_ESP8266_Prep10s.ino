#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecureBearSSL.h>
#include <ArduinoJson.h>

/*
  Smart Bartender ESP8266 Worker (Single Mixing Slot + 10s Prep Time)

  Behavior:
  - If idle, poll the server every 10 seconds for the next drink job.
  - When a job is received, make ONE drink, then call /api/esp/complete.
  - After finishing, wait 10 seconds "prep time", then poll again.
  - If no job is available, stay idle and keep polling every 10 seconds.

  Server endpoints (FastAPI):
  - GET  /api/esp/next?key=ESP_POLL_KEY
  - POST /api/esp/complete?key=ESP_POLL_KEY   body: {"id": "<orderId>"}

  Notes:
  - The backend in this repo is designed to advance an order item-by-item
    (so multiple drinks in one checkout are dispensed sequentially).
*/

// --------------------
// WiFi
// --------------------
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

// --------------------
// Server + key
// --------------------
const char* SERVER_BASE = "https://YOUR-RENDER-APP.onrender.com"; // or http://<your-computer-ip>:8000
const char* ESP_KEY     = "YOUR_ESP_POLL_KEY";                    // must match server env ESP_POLL_KEY

// --------------------
// Timing
// --------------------
const unsigned long PREP_MS = 10000;   // 10 seconds prep time / idle poll interval
unsigned long nextAllowedPoll = 0;
bool busy = false;

// --------------------
// Current job fields
// --------------------
String currentOrderId = "";
String currentDrinkName = "";

// timing from server (seconds)
int stepSeconds = 25;
int prepSeconds = 10;

String currentDrinkId = "";

// --------------------
// Helpers
// --------------------
void printHttpDebug(int code, const String& payload) {
  Serial.print("[ESP] HTTP code: ");
  Serial.println(code);
  Serial.print("[ESP] Payload: ");
  Serial.println(payload);
}

String urlJoin(const char* base, const char* pathWithQuery) {
  String u(base);
  u += pathWithQuery;
  return u;
}

bool pollNextDrink() {
  // Support BOTH HTTPS (Render) and HTTP (local LAN) based on SERVER_BASE
  HTTPClient http;
  String url = String(SERVER_BASE) + "/api/esp/next?key=" + ESP_KEY;

  Serial.print("[ESP] Polling: ");
  Serial.println(url);

  bool began = false;
  if (String(SERVER_BASE).startsWith("https://")) {
    std::unique_ptr<BearSSL::WiFiClientSecure> client(new BearSSL::WiFiClientSecure);
    client->setInsecure(); // demo: skip cert validation
    began = http.begin(*client, url);
  } else {
    WiFiClient client;
    began = http.begin(client, url);
  }

  if (!began) {
    Serial.println("[ESP] http.begin failed");
    return false;
  }

  int code = http.GET();
  String payload = http.getString();
  http.end();

  if (code != 200) {
    printHttpDebug(code, payload);
    return false;
  }

  // The server may return a full order object (including an items[] list),
  // which can exceed 2KB. Use a larger buffer to avoid deserializeJson NoMemory.
  StaticJsonDocument<8192> doc;
  DeserializationError err = deserializeJson(doc, payload);
  if (err) {
    Serial.print("[ESP] JSON parse error: ");
    Serial.println(err.c_str());
    Serial.println("[ESP] Tip: If you see 'NoMemory', increase JSON buffer size.");
    return false;
  }

  bool ok = doc["ok"] | false;
  if (!ok) return false;

  if (doc["order"].isNull()) {
    Serial.println("[ESP] No job. Staying idle.");
    return false;
  }

  JsonObject order = doc["order"].as<JsonObject>();
  currentOrderId   = String((const char*)order["id"]);
  currentDrinkId   = String((const char*)order["drinkId"]);
  currentDrinkName = String((const char*)order["drinkName"]);

  // Optional timing hints from server
  if (!order["stepSeconds"].isNull()) stepSeconds = int(order["stepSeconds"]);
  if (!order["prepSeconds"].isNull()) prepSeconds = int(order["prepSeconds"]);
  Serial.print("  stepSeconds: "); Serial.println(stepSeconds);
  Serial.print("  prepSeconds: "); Serial.println(prepSeconds);

  Serial.println("[ESP] Job received:");
  Serial.print("  Order ID: "); Serial.println(currentOrderId);
  Serial.print("  Drink:    "); Serial.println(currentDrinkName);

  return currentOrderId.length() > 0;
}

bool completeCurrentJob() {
  HTTPClient http;
  String url = String(SERVER_BASE) + "/api/esp/complete?key=" + ESP_KEY;

  StaticJsonDocument<256> bodyDoc;
  bodyDoc["id"] = currentOrderId;
  String body;
  serializeJson(bodyDoc, body);

  Serial.print("[ESP] Completing: ");
  Serial.println(url);

  bool began = false;
  if (String(SERVER_BASE).startsWith("https://")) {
    std::unique_ptr<BearSSL::WiFiClientSecure> client(new BearSSL::WiFiClientSecure);
    client->setInsecure();
    began = http.begin(*client, url);
  } else {
    WiFiClient client;
    began = http.begin(client, url);
  }

  if (!began) {
    Serial.println("[ESP] http.begin failed");
    return false;
  }
  http.addHeader("Content-Type", "application/json");

  int code = http.POST(body);
  String payload = http.getString();
  http.end();

  if (code != 200) {
    printHttpDebug(code, payload);
    return false;
  }

  Serial.println("[ESP] Complete acknowledged.");
  return true;
}

// --------------------
// Your pump / mixing logic goes here
// --------------------
void makeDrink() {
  // TODO: Replace with your real pump timings based on currentDrinkId/name.
  // For now we simulate mixing time.
  Serial.print("[ESP] Making drink: ");
  Serial.println(currentDrinkName);

  // Simulated dispense duration from server hint (minimum 5s)
  int s = stepSeconds;
  if (s < 5) s = 5;
  delay((unsigned long)s * 1000UL);


  Serial.println("[ESP] Done making drink.");
}

// --------------------
// Setup / Loop
// --------------------
void setup() {
  Serial.begin(115200);
  delay(200);

  Serial.println();
  Serial.println("[ESP] Booting...");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.print("[ESP] Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("[ESP] Connected. IP: ");
  Serial.println(WiFi.localIP());

  // Start immediately
  nextAllowedPoll = 0;
}

void loop() {
  // If currently making a drink, do nothing (single slot)
  if (busy) return;

  // Wait until prep / idle interval expires
  if (millis() < nextAllowedPoll) return;

  // Poll for next job
  bool gotJob = pollNextDrink();

  if (gotJob) {
    busy = true;

    makeDrink();          // physical dispense
    completeCurrentJob(); // tell backend one drink is finished

    busy = false;

    // Start 10s prep time before the next drink
    nextAllowedPoll = millis() + (unsigned long)prepSeconds * 1000UL;
    Serial.print("[ESP] Prep/cooldown "); Serial.print(prepSeconds); Serial.println("s...");
  } else {
    // No job -> stay idle, poll again in 10 seconds
    nextAllowedPoll = millis() + (unsigned long)prepSeconds * 1000UL;
  }
}
