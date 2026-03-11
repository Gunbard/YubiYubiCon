import sys
import asyncio
import struct
import math
from bleak import BleakScanner, BleakClient
from qasync import QEventLoop, asyncSlot
from pythonosc import udp_client
from mainWindow import Ui_MainWindow
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication

APP_TITLE = 'YubiYubiCon'
VERSION = '1.0.0'
WINDOW_TITLE = '{}'.format(APP_TITLE)
VMC_IP = '127.0.0.1'
VMC_PORT = 39539
SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
GLOVE_R_NAME = "ESP32GloveR"

osc_client = udp_client.SimpleUDPClient(VMC_IP, VMC_PORT)

def handle_close(event):
    # Create the task in the loop
    loop.create_task(cleanup_ble())
    
    # Give the task a moment to run before killing the app
    # (Optional: if the app closes too fast, the disconnect packet might not send)
    event.accept()

# APP SETUP

QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_DisableWindowContextHelpButton)

app = QtWidgets.QApplication(sys.argv)
loop = QEventLoop(app)
asyncio.set_event_loop(loop)

# Smoothing Factor
# 1.0 = No smoothing (raw data, very twitchy)
# 0.1 = Heavy smoothing (very stable, but adds slight delay)
alpha = 0.2  

# This stores the previous state to calculate the next smoothed value
smoothed_values = [0.0] * 5

MainWindow = QtWidgets.QMainWindow()
ui = Ui_MainWindow()
ui.setupUi(MainWindow)
status_label = ui.statusLabel
client = None

MainWindow.setWindowTitle("{} {}".format(
  WINDOW_TITLE, VERSION))
MainWindow.closeEvent = handle_close
MainWindow.show()

async def run_ble_client(address, char_uuid, callback):
  async with BleakClient(address) as client:
    # Subscribe to the ESP32 characteristic
    await client.start_notify(char_uuid, callback)
    while True:
      await asyncio.sleep(1.0)

async def start_connection():
  global status_label, client, osc_client
  #osc_client.send_message("/VMC/Ext/Bone/Pos", ["Head", 0.0, 0.0, 0.0, 0.3, 0.0, 0.0, 0.9])
  status_label.setText("Scanning for VR Glove...")
  
  # We look for a device that is specifically advertising your Service UUID
  device = await BleakScanner.find_device_by_filter(
    lambda d, ad: SERVICE_UUID.lower() in [s.lower() for s in ad.service_uuids]
  )
  
  if not device:
    status_label.setText("Glove not found. Is it turned on?")
    return

  status_label.setText(f"Connecting to {device.name}...")
  client = BleakClient(device)
  
  try:
    await client.connect()
    status_label.setText("Connected! Syncing with VNYan...")
    
    # This 'notifies' our Python code whenever the ESP32 calls pCharacteristic->notify()
    await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
      
  except Exception as e:
    status_label.setText(f"Connection Failed: {str(e)}")

def map_and_send_to_vmc(raw_curls):
  """
  raw_curls: list/tuple of 5 floats (0-1024)
  Order: Thumb, Index, Middle, Ring, Little
  """
  global osc_client

  finger_names = ["Thumb", "Index", "Middle", "Ring", "Little"]
  
  for i, raw_val in enumerate(raw_curls):
    # 1. Normalize to 0.0 - 1.0
    # If 1024 is "open" and 0 is "fist", use: 1.0 - (raw_val / 1024.0)
    norm = max(0.0, min(1.0, raw_val / 1024.0))
    
    # 2. Smoothing (using the global alpha and smoothed_values)
    global smoothed_values
    smoothed_values[i] = (norm * alpha) + (smoothed_values[i] * (1 - alpha))
    
    # 3. Convert to Angle (in Radians)
    # 1.6 radians is about 90 degrees.

    # 4. Calculate Quaternion (Rotation on X-axis)
    # [qx, qy, qz, qw]
    if i == 0:  # THUMB SPECIAL CASE
      angle = smoothed_values[i] * 2.0
      s = math.sin(angle / 2)
      c = math.cos(angle / 2)
      # If Z-axis made it go "down", try moving 's' to the X or Y slot.
      # Try this first (X-axis):
      qx, qy, qz, qw = s, 0.0, 0.0, c 
    else:
      angle = -(smoothed_values[i] * 1.6)
      s = math.sin(angle / 2)
      c = math.cos(angle / 2)
      # Fingers (Confirmed working Z-axis)
      qx, qy, qz, qw = 0.0, 0.0, s, c

    # 5. Send to VNYan via OSC
    # VMC Protocol: /vmt/rt/bone, (str)Name, (float)px, py, pz, rx, ry, rz, rw
    # We assume Left Hand here.
    for segment in ["Proximal", "Intermediate", "Distal"]:
      bone_id = f"Right{finger_names[i]}{segment}"
      
      # Bone positions (px, py, pz) are 0.0 because VMC handles 
      # rotations relative to the avatar's existing pose.
      osc_client.send_message("/VMC/Ext/Bone/Pos", [
        bone_id, 
        0.0, 0.0, 0.0, # Position
        qx, qy, qz, qw # Rotation
      ])

def notification_handler(characteristic, data):
  try:
    # 1. Unpack the 20 bytes into 5 floats
    # 'f' is 4 bytes, so 'fffff' is 20 bytes
    raw_curls = struct.unpack('fffff', data)
    
    # 2. Print to the Terminal Console
    # Using [int(x) for x in ...] makes it easier to read than long floats
    #print(f"ESP32 Data: {[int(val) for val in raw_curls]}")
    
    # 3. Update the PyQt5 GUI
    # Note: Depending on your setup, you might need to use a Signal 
    # to update the UI from a background thread, but qasync often handles this.
    data_string = ", ".join([str(int(val)) for val in raw_curls])
    #data_display.setText(f"Glove Data: [{data_string}]")
    print(f"Glove Data: [{data_string}]")

    # 4. (Existing VMC Logic)
    map_and_send_to_vmc(raw_curls)
      
  except Exception as e:
      print(f"Unpack Error: {e}")

async def cleanup_ble():
    global client
    if client and client.is_connected:
        print("Cleaning up BLE connection...")
        try:
            # Stop listening to the data stream first
            await client.stop_notify(CHARACTERISTIC_UUID)
            # Gracefully tell the ESP32 we are leaving
            await client.disconnect()
            print("Disconnected safely.")
        except Exception as e:
            print(f"Error during cleanup: {e}")

def on_connect_clicked():
  # This schedules the async task into the existing qasync loop
  asyncio.ensure_future(start_connection())

# EVENTS
ui.connectButton.clicked.connect(lambda: on_connect_clicked())

with loop:
  loop.run_forever()