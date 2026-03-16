#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecureBearSSL.h>
#include <ArduinoJson.h>

const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* SERVER_BASE = "https://YOUR-RENDER-APP.onrender.com";
const char* ESP_KEY     = "YOUR_ESP_POLL_KEY";

unsigned long nextAllowedPoll = 0;
bool busy = false;
String currentOrderId = "";
String currentDrinkName = "";
String currentDrinkId = "";
int stepSeconds = 25;
int prepSeconds = 10;
String recipeBuffer[8];
int recipeCount = 0;

String prettyName(const String& raw) {
  String s = raw;
  s.replace("_", " ");
  s.replace("-", " ");
  bool cap = true;
  for (unsigned int i = 0; i < s.length(); i++) {
    char c = s[i];
    if (cap && c >= 'a' && c <= 'z') s.setCharAt(i, c - 32);
    cap = (c == ' ');
  }
  return s;
}

void printHttpDebug(int code, const String& payload) {
  Serial.print("[ESP] HTTP code: "); Serial.println(code);
  Serial.print("[ESP] Payload: "); Serial.println(payload);
}

bool beginRequest(HTTPClient& http, const String& url) {
  if (String(SERVER_BASE).startsWith("https://")) {
    auto client = std::make_unique<BearSSL::WiFiClientSecure>();
    client->setInsecure();
    return http.begin(*client, url);
  } else {
    WiFiClient client;
    return http.begin(client, url);
  }
}

void setRecipeFallback(const String& drinkId) {
  recipeCount = 0;
  if (drinkId == "tropical_charge") {
    recipeBuffer[0] = "Red Bull"; recipeBuffer[1] = "Sprite"; recipeBuffer[2] = "Lemonade"; recipeCount = 3;
  } else if (drinkId == "amber_storm") {
    recipeBuffer[0] = "Orange Juice"; recipeBuffer[1] = "Coca-Cola"; recipeBuffer[2] = "Ginger Ale"; recipeCount = 3;
  } else if (drinkId == "citrus_shine") {
    recipeBuffer[0] = "Lemonade"; recipeBuffer[1] = "Sprite"; recipeBuffer[2] = "Water"; recipeCount = 3;
  } else if (drinkId == "golden_breeze") {
    recipeBuffer[0] = "Lemonade"; recipeBuffer[1] = "Ginger Ale"; recipeBuffer[2] = "Water"; recipeCount = 3;
  } else if (drinkId == "sunset_fizz") {
    recipeBuffer[0] = "Ginger Ale"; recipeBuffer[1] = "Lemonade"; recipeCount = 2;
  } else {
    recipeBuffer[0] = "Mixed Pour"; recipeCount = 1;
  }
}

bool postStatus(const char* machine, const char* headline, const char* stage, const char* ingredient, int ingredientIndex, int totalIngredients, int remainingSeconds, int progress) {
  HTTPClient http;
  String url = String(SERVER_BASE) + "/api/esp/status?key=" + ESP_KEY;
  if (!beginRequest(http, url)) return false;

  StaticJsonDocument<768> doc;
  doc["orderId"] = currentOrderId;
  doc["drink"] = currentDrinkName;
  doc["drinkId"] = currentDrinkId;
  doc["machine"] = machine;
  doc["headline"] = headline;
  doc["stage"] = stage;
  doc["currentIngredient"] = ingredient;
  doc["currentIngredientIndex"] = ingredientIndex;
  doc["totalIngredients"] = totalIngredients;
  doc["remainingSeconds"] = remainingSeconds;
  doc["progress"] = progress;
  JsonArray ing = doc.createNestedArray("ingredients");
  for (int i = 0; i < recipeCount; i++) ing.add(recipeBuffer[i]);

  String body; serializeJson(doc, body);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  String payload = http.getString();
  http.end();
  if (code != 200) { printHttpDebug(code, payload); return false; }
  return true;
}

bool pollNextDrink() {
  HTTPClient http;
  String url = String(SERVER_BASE) + "/api/esp/next?key=" + ESP_KEY;
  if (!beginRequest(http, url)) return false;

  int code = http.GET();
  String payload = http.getString();
  http.end();
  if (code != 200) { printHttpDebug(code, payload); return false; }

  StaticJsonDocument<8192> doc;
  if (deserializeJson(doc, payload)) return false;
  if (!(doc["ok"] | false)) return false;

  if (doc["order"].isNull()) return false;

  JsonObject order = doc["order"].as<JsonObject>();
  currentOrderId = String((const char*)order["id"]);
  currentDrinkId = String((const char*)order["drinkId"]);
  currentDrinkName = String((const char*)order["drinkName"]);
  recipeCount = 0;

  if (order.containsKey("ingredients") && order["ingredients"].is<JsonArray>()) {
    JsonArray arr = order["ingredients"].as<JsonArray>();
    for (JsonVariant v : arr) {
      if (recipeCount >= 8) break;
      recipeBuffer[recipeCount++] = prettyName(String((const char*)v));
    }
  }
  if (recipeCount <= 0) setRecipeFallback(currentDrinkId);
  if (!order["stepSeconds"].isNull()) stepSeconds = int(order["stepSeconds"]);
  if (!order["prepSeconds"].isNull()) prepSeconds = int(order["prepSeconds"]);

  postStatus("queued", "Order queued", "queued", recipeCount > 0 ? recipeBuffer[0].c_str() : "", 0, recipeCount, int(order["queueEtaSeconds"] | stepSeconds), 0);
  return currentOrderId.length() > 0;
}

bool completeCurrentJob() {
  HTTPClient http;
  String url = String(SERVER_BASE) + "/api/esp/complete?key=" + ESP_KEY;
  StaticJsonDocument<128> bodyDoc;
  bodyDoc["id"] = currentOrderId;
  String body; serializeJson(bodyDoc, body);
  if (!beginRequest(http, url)) return false;
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  String payload = http.getString();
  http.end();
  if (code != 200) { printHttpDebug(code, payload); return false; }
  return true;
}

void makeDrink() {
  if (recipeCount <= 0) setRecipeFallback(currentDrinkId);
  int totalSec = max(stepSeconds, recipeCount);
  int baseStepSec = max(1, totalSec / max(1, recipeCount));
  int extra = totalSec % max(1, recipeCount);
  int elapsed = 0;

  for (int i = 0; i < recipeCount; i++) {
    int thisStep = baseStepSec + (i < extra ? 1 : 0);
    const char* ingredient = recipeBuffer[i].c_str();
    for (int sec = 0; sec < thisStep; sec++) {
      int remaining = max(0, totalSec - elapsed);
      int progress = (elapsed * 100) / max(1, totalSec);
      postStatus("pouring", ingredient, "pouring", ingredient, i + 1, recipeCount, remaining, progress);
      delay(1000);
      elapsed++;
    }
  }
  postStatus("finishing", "Ready to serve", "finishing", "", recipeCount, recipeCount, 0, 100);
}

void setup() {
  Serial.begin(115200);
  delay(200);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); }
  postStatus("idle", "Idle", "waiting", "", 0, 0, 0, 0);
}

void loop() {
  if (busy || millis() < nextAllowedPoll) return;
  bool gotJob = pollNextDrink();
  if (gotJob) {
    busy = true;
    makeDrink();
    completeCurrentJob();

    for (int sec = prepSeconds; sec > 0; sec--) {
      postStatus("done", "Ready to serve", "done", "", recipeCount, recipeCount, sec, 100);
      delay(1000);
    }

    postStatus("idle", "Idle", "waiting", "", 0, 0, 0, 0);
    busy = false;
    nextAllowedPoll = millis() + 500UL;
  } else {
    nextAllowedPoll = millis() + 500UL;
  }
}
