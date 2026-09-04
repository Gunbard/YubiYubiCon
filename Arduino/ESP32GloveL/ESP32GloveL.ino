/*
 * VRGlove ESP32
 * Author: Gunbard
 * Hardware: ESP32-WROOM-32, 5x Flex Sensors, 5x 10K Ohm Resistors
 * Pins Used: GPIO 4, 32, 33, 34, 35
 */

#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLE2902.h>

#define BT_NAME             "ESP32GloveL"
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"         
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8" 

const int NUM_FINGERS = 5;
const int MEDIAN_WINDOW = 5;
const int AVERAGE_WINDOW = 10;
const int PIN_LED = 2;

bool deviceConnected = false;
BLECharacteristic *pCharacteristic;
BLEServer *pServer;
BLEService *pService;

// Struct to hold all data buffers and configuration for a single finger
struct Finger {
  const char* name;
  int pin;
  
  // Calibration profile (Calibrate each finger individually!)
  int straightValue;
  int bentValue;
  
  // Filter buffers
  int medianBuffer[MEDIAN_WINDOW];
  int averageBuffer[AVERAGE_WINDOW];
  int medianIdx;
  int averageIdx;
  
  // Output states
  int ultraSmoothedValue;
  int flexionPercent;
};

// Initialize your 5-finger array with their specific pins and placeholder calibration values
Finger glove[NUM_FINGERS] = 
{
  { "Th",  4,  1600, 1450, {0}, {0}, 0, 0, 0, 0 },
  { "In",  33, 1600, 1450, {0}, {0}, 0, 0, 0, 0 },
  { "Mi", 32, 1600, 1450, {0}, {0}, 0, 0, 0, 0 },
  { "Ri",   35, 1600, 1450, {0}, {0}, 0, 0, 0, 0 },
  { "Pi",  34, 1600, 1450, {0}, {0}, 0, 0, 0, 0 }
};

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

// Helper function prototypes for filtering
int processMedian(Finger &f, int newValue);
int processAverage(Finger &f, int newValue);
void quick_sort(int arr[], int left, int right);

void setup() 
{
  Serial.begin(9600);
  pinMode(PIN_LED, OUTPUT);

  // Initialize and pre-warm buffers for all 5 fingers
  for (int i = 0; i < NUM_FINGERS; i++) 
  {
    pinMode(glove[i].pin, INPUT);
    
    int seedReading = analogRead(glove[i].pin);
    glove[i].medianIdx = 0;
    glove[i].averageIdx = 0;
    
    for (int j = 0; j < MEDIAN_WINDOW; j++) glove[i].medianBuffer[j] = seedReading;
    for (int j = 0; j < AVERAGE_WINDOW; j++) glove[i].averageBuffer[j] = seedReading;
  }

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
  
  Serial.println("ESP32 Glove Initialized");
}

void loop() 
{
  // Loop through and process each finger sequentially
  for (int i = 0; i < NUM_FINGERS; i++) 
  {
    int rawValue = analogRead(glove[i].pin);
    
    // Step 1 & 2: Apply the hybrid filter sequence
    int medianFiltered = processMedian(glove[i], rawValue);
    glove[i].ultraSmoothedValue = processAverage(glove[i], medianFiltered);
    
    // Step 3: Map and constrain to 0-100% flexion
    glove[i].flexionPercent = map(glove[i].ultraSmoothedValue, glove[i].straightValue, glove[i].bentValue, 0, 100);
    glove[i].flexionPercent = constrain(glove[i].flexionPercent, 0, 100);
  }
  
  // Print all values in a structured format readable by Serial Monitor/Plotter
//  for (int i = 0; i < NUM_FINGERS; i++) 
//  {
//    Serial.print(glove[i].name);
//    Serial.print(": ");
//    Serial.print(analogRead(glove[i].pin));
//    Serial.print("");
//    //Serial.print(glove[i].flexionPercent);
//    if (i < NUM_FINGERS - 1) Serial.print(","); // Format requirement for Serial Plotter
//  }
//  Serial.println(); // Dynamic newline at the end of the batch transmission
  
  if (deviceConnected)
  {
    digitalWrite(PIN_LED, HIGH);
    float fingers[5];
    
    for (int i = 0; i < NUM_FINGERS; i++) 
    {
      fingers[i] = glove[i].ultraSmoothedValue;
    }

    // Pacakge and send the raw bytes (20 total) for the fingers
    pCharacteristic->setValue((uint8_t*)fingers, 20);
    pCharacteristic->notify();

    delay(10); // ~100Hz is plenty for VMC
  }
  else
  {
    digitalWrite(PIN_LED, LOW);
  }
}

// Filter calculations scoped strictly via references to modify the specific finger object
int processMedian(Finger &f, int newValue) 
{
  f.medianBuffer[f.medianIdx] = newValue;
  f.medianIdx = (f.medianIdx + 1) % MEDIAN_WINDOW;
  
  int sortBuffer[MEDIAN_WINDOW];
  for(int i = 0; i < MEDIAN_WINDOW; i++) sortBuffer[i] = f.medianBuffer[i];
  
  quick_sort(sortBuffer, 0, MEDIAN_WINDOW - 1);
  return sortBuffer[MEDIAN_WINDOW / 2];
}

int processAverage(Finger &f, int newValue) 
{
  f.averageBuffer[f.averageIdx] = newValue;
  f.averageIdx = (f.averageIdx + 1) % AVERAGE_WINDOW;
  
  long sum = 0;
  for (int i = 0; i < AVERAGE_WINDOW; i++) sum += f.averageBuffer[i];
  return sum / AVERAGE_WINDOW;
}

void quick_sort(int arr[], int left, int right) 
{
  int i = left, j = right;
  int tmp;
  int pivot = arr[(left + right) / 2];
  while (i <= j) 
  {
    while (arr[i] < pivot) i++;
    while (arr[j] > pivot) j--;
    if (i <= j) {
      tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
      i++; j--;
    }
  }
  if (left < j) quick_sort(arr, left, j);
  if (i < right) quick_sort(arr, i, right);
}
