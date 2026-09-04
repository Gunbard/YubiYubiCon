/**
 * VRGlove AceBott
 * Author: Gunbard
 * Hardware:
 *  AceBott ESP32 Glove
 */

#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLE2902.h>

#define BT_NAME             "ESP32GloveR"
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"         
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8" 

#define PIN_THUMB     36  
#define PIN_INDEX     39
#define PIN_MIDDLE    34
#define PIN_RING      35
#define PIN_PINKY     32
#define PIN_LED       17 // Status LED, low ON
#define PIN_K1        23 // K1 button

bool deviceConnected = false;
BLECharacteristic *pCharacteristic;
BLEServer *pServer;
BLEService *pService;

class ServerCallback: public BLEServerCallbacks 
{
  void onConnect(BLEServer* pServer)
  {
    deviceConnected = true; 
  };
  
  void onDisconnect(BLEServer* pServer) 
  {
    deviceConnected = false; 
    BLEDevice::startAdvertising();
  };  
};

void setup() 
{
  pinMode(PIN_THUMB,  INPUT);
  pinMode(PIN_INDEX,  INPUT);
  pinMode(PIN_MIDDLE, INPUT);
  pinMode(PIN_RING,   INPUT);
  pinMode(PIN_PINKY,  INPUT);
  pinMode(PIN_K1,     INPUT_PULLUP);
  pinMode(PIN_LED,    OUTPUT);
  
  Serial.begin(115200);
  Serial.println("Start!");

  BLEDevice::init(BT_NAME);  // set the device name
  pServer = BLEDevice::createServer();
  pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(
                                         CHARACTERISTIC_UUID,
                                         BLECharacteristic::PROPERTY_READ |
                                         BLECharacteristic::PROPERTY_NOTIFY
                                       );

  pCharacteristic->addDescriptor(new BLEDescriptor((uint16_t)0x2902));
  pServer->setCallbacks(new ServerCallback());
  pService->start();

  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setAppearance(0x03C0); // Generic HID
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);  // functions that help with iPhone connections issue
  pAdvertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();
}

void loop() 
{
//  Serial.print("(");
//  Serial.print(analogRead(PIN_THUMB));
//  Serial.print(", ");
//  Serial.print(analogRead(PIN_INDEX));
//  Serial.print(", ");
//  Serial.print(analogRead(PIN_MIDDLE));
//  Serial.print(", ");
//  Serial.print(analogRead(PIN_RING));
//  Serial.print(", ");
//  Serial.print(analogRead(PIN_PINKY));
//  Serial.println(")");

  if (deviceConnected)
  {
    digitalWrite(PIN_LED, LOW);
    
    float fingers[5];
    fingers[0] = analogRead(PIN_THUMB);
    fingers[1] = analogRead(PIN_INDEX);
    fingers[2] = analogRead(PIN_MIDDLE);
    fingers[3] = analogRead(PIN_RING);
    fingers[4] = analogRead(PIN_PINKY);

    // Pacakge and send the raw bytes (20 total) for the fingers
    pCharacteristic->setValue((uint8_t*)fingers, 20);
    pCharacteristic->notify();

    delay(10); // ~100Hz is plenty for VMC
  }
  else
  {
    digitalWrite(PIN_LED, HIGH);
  }
}
