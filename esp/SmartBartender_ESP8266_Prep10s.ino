
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecureBearSSL.h>
#include <ArduinoJson.h>

/*
  Smart Bartender ESP8266 Worker
  + Live iPad status display support

  New feature:
  - Sends live status updates to /api/esp/status
  - Lets your iPad show the current drink, ingredient being poured,
    progress, and remaining time.
*/

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

struct RecipeStep {
  const char* label;
};

RecipeStep recipeBuffer[4];
int recipeCount = 0;

void printHttpDebug(int code, const String& payload) {
  Serial.print("[ESP] HTTP code: ");
  Serial.println(code);
  Serial.print("[ESP] Payload: ");
  Serial.println(payload);
}

bool beginRequest(HTTPClient& http, const String& url) {
  if (String(SERVER_BASE).startsWith("https://")) {
    std::unique_ptr<BearSSL::WiFiClientSecure> client(new BearSSL::WiFiClientSecure);
    client->setInsecure();
    return http.begin(*client, url);
  } else {
    WiFiClient client;
    return http.begin(client, url);
  }
}

void setRecipe(const String& drinkId) {
  recipeCount = 0;

  if (drinkId == "amber_storm") {
    recipeBuffer[0] = {"Coca-Cola"};
    recipeBuffer[1] = {"Ginger Ale"};
    recipeCount = 2;
  } else if (drinkId == "classic_fusion") {
    recipeBuffer[0] = {"Water"};
    recipeBuffer[1] = {"Lemonade"};
    recipeCount = 2;
  } else if (drinkId == "chaos_punch") {
    recipeBuffer[0] = {"Coca-Cola"};
    recipeBuffer[1] = {"Red Bull"};
    recipeCount = 2;
  } else if (drinkId == "crystal_chill") {
    recipeBuffer[0] = {"Water"};
    recipeBuffer[1] = {"Sprite"};
    recipeCount = 2;
  } else if (drinkId == "cola_spark") {
    recipeBuffer[0] = {"Coca-Cola"};
    recipeBuffer[1] = {"Sprite"};
    recipeCount = 2;
  } else if (drinkId == "dark_amber") {
    recipeBuffer[0] = {"Coca-Cola"};
    recipeBuffer[1] = {"Ginger Ale"};
    recipeCount = 2;
  } else if (drinkId == "voltage_fizz") {
    recipeBuffer[0] = {"Red Bull"};
    recipeBuffer[1] = {"Sprite"};
    recipeCount = 2;
  } else if (drinkId == "golden_breeze") {
    recipeBuffer[0] = {"Lemonade"};
    recipeBuffer[1] = {"Ginger Ale"};
    recipeBuffer[2] = {"Water"};
    recipeCount = 3;
  } else if (drinkId == "energy_sunrise") {
    recipeBuffer[0] = {"Red Bull"};
    recipeBuffer[1] = {"Lemonade"};
    recipeCount = 2;
  } else if (drinkId == "citrus_cloud") {
    recipeBuffer[0] = {"Sprite"};
    recipeBuffer[1] = {"Lemonade"};
    recipeCount = 2;
  } else if (drinkId == "citrus_shine") {
    recipeBuffer[0] = {"Lemonade"};
    recipeBuffer[1] = {"Sprite"};
    recipeBuffer[2] = {"Water"};
    recipeCount = 3;
  } else if (drinkId == "sparking_citrus") {
    recipeBuffer[0] = {"Sprite"};
    recipeBuffer[1] = {"Lemonade"};
    recipeBuffer[2] = {"Ginger Ale"};
    recipeCount = 3;
  } else if (drinkId == "sunset_fizz") {
    recipeBuffer[0] = {"Ginger Ale"};
    recipeBuffer[1] = {"Lemonade"};
    recipeCount = 2;
  } else if (drinkId == "tropical_charge") {
    recipeBuffer[0] = {"Red Bull"};
    recipeBuffer[1] = {"Sprite"};
    recipeBuffer[2] = {"Lemonade"};
    recipeCount = 3;
  } else {
    recipeBuffer[0] = {"Mixed Pour"};
    recipeCount = 1;
  }
}

bool postStatus(const char* machine, const char* headline, const char* stage, const char* ingredient, int ingredientIndex, int totalIngredients, int remainingSeconds, int progress) {
  HTTPClient http;
  String url = String(SERVER_BASE) + "/api/esp/status?key=" + ESP_KEY;
  if (!beginRequest(http, url)) {
    Serial.println("[ESP] status http.begin failed");
    return false;
  }

  StaticJsonDocument<512> doc;
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

  String body;
  serializeJson(doc, body);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  String payload = http.getString();
  http.end();

  if (code != 200) {
    printHttpDebug(code, payload);
    return false;
  }
  return true;
}

bool pollNextDrink() {
  HTTPClient http;
  String url = String(SERVER_BASE) + "/api/esp/next?key=" + ESP_KEY;

  Serial.print("[ESP] Polling: ");
  Serial.println(url);

  if (!beginRequest(http, url)) {
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

  StaticJsonDocument<8192> doc;
  DeserializationError err = deserializeJson(doc, payload);
  if (err) {
    Serial.print("[ESP] JSON parse error: ");
    Serial.println(err.c_str());
    return false;
  }

  bool ok = doc["ok"] | false;
  if (!ok) return false;

  if (doc["order"].isNull()) {
    Serial.println("[ESP] No job. Staying idle.");
    postStatus("idle", "Idle", "waiting", "", 0, 0, 0, 0);
    return false;
  }

  JsonObject order = doc["order"].as<JsonObject>();
  currentOrderId   = String((const char*)order["id"]);
  currentDrinkId   = String((const char*)order["drinkId"]);
  currentDrinkName = String((const char*)order["drinkName"]);

  if (!order["stepSeconds"].isNull()) stepSeconds = int(order["stepSeconds"]);
  if (!order["prepSeconds"].isNull()) prepSeconds = int(order["prepSeconds"]);

  setRecipe(currentDrinkId);
  postStatus("preparing", "Preparing Drink", "preparing", "", 0, recipeCount, stepSeconds, 0);

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

  if (!beginRequest(http, url)) {
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

void makeDrink() {
  Serial.print("[ESP] Making drink: ");
  Serial.println(currentDrinkName);

  if (recipeCount <= 0) {
    setRecipe(currentDrinkId);
  }
  if (recipeCount <= 0) recipeCount = 1;

  int totalSec = stepSeconds;
  if (totalSec < recipeCount) totalSec = recipeCount;
  int baseStepSec = totalSec / recipeCount;
  int extra = totalSec % recipeCount;
  int elapsed = 0;

  for (int i = 0; i < recipeCount; i++) {
    int thisStep = baseStepSec + (i < extra ? 1 : 0);
    const char* ingredient = recipeBuffer[i].label;

    for (int sec = 0; sec < thisStep; sec++) {
      int remaining = totalSec - elapsed;
      int progress = (elapsed * 100) / totalSec;
      postStatus("pouring", "Pouring Now", "pouring", ingredient, i + 1, recipeCount, remaining, progress);
      delay(1000);
      elapsed++;
    }
  }

  postStatus("finishing", "Finalizing Drink", "finishing", "", recipeCount, recipeCount, 0, 100);
  Serial.println("[ESP] Done making drink.");
}

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

  postStatus("idle", "Idle", "waiting", "", 0, 0, 0, 0);
  nextAllowedPoll = 0;
}

void loop() {
  if (busy) return;
  if (millis() < nextAllowedPoll) return;

  bool gotJob = pollNextDrink();

  if (gotJob) {
    busy = true;
    makeDrink();
    completeCurrentJob();
    busy = false;

    postStatus("cooldown", "Drink Complete", "cooldown", "", 0, recipeCount, prepSeconds, 100);
    nextAllowedPoll = millis() + (unsigned long)prepSeconds * 1000UL;
    Serial.print("[ESP] Prep/cooldown "); Serial.print(prepSeconds); Serial.println("s...");
  } else {
    nextAllowedPoll = millis() + (unsigned long)prepSeconds * 1000UL;
  }
}
