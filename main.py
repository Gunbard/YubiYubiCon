import sys
import asyncio
import struct
import math
import time
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
finger_state = [0, 0, 0, 0, 0]
calibration_open = [0, 0, 0, 0, 0]
calibration_closed = [1024, 1024, 1024, 1024, 1024]
packet_count = 0
last_packet_check = time.time()

health_timer = QtCore.QTimer()

def handle_close(event):
  global loop
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
alpha = 0.4  

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
MainWindow.setFixedSize(640, 480)
MainWindow.statusBar().setSizeGripEnabled(False)
MainWindow.show()

async def run_ble_client(address, char_uuid, callback):
  async with BleakClient(address) as client:
    # Subscribe to the ESP32 characteristic
    await client.start_notify(char_uuid, callback)
    while True:
      await asyncio.sleep(1.0)

async def start_connection():
  global status_label, client, osc_client
  ui.connectButton.setEnabled(False)
  status_label.setText("Scanning for VR Glove...")
  
  # Look for a device that is specifically advertising your Service UUID
  device = await BleakScanner.find_device_by_filter(
    lambda d, ad: SERVICE_UUID.lower() in [s.lower() for s in ad.service_uuids]
  )
  
  if not device:
    status_label.setText("Glove not found. Is it turned on?")
    ui.connectButton.setEnabled(True)
    gloveMonitoringEnabled(False)
    return

  status_label.setText(f"Device found! Connecting...")
  client = BleakClient(device)
  
  try:
    await client.connect()
    status_label.setText("Connected! Sending via VMC...")
    ui.connectButton.setText("Disconnect")
    ui.connectButton.setEnabled(True)
    gloveMonitoringEnabled(True)

    
    # This 'notifies' our Python code whenever the ESP32 calls pCharacteristic->notify()
    await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
      
  except Exception as e:
    status_label.setText(f"Connection Failed: {str(e)}")
    ui.connectButton.setEnabled(True)
    gloveMonitoringEnabled(False)

def map_and_send_to_vmc(raw_curls):
  """
  raw_curls: list/tuple of 5 floats (0-1024)
  Order: Thumb, Index, Middle, Ring, Little
  """
  global osc_client

  finger_names = ["Thumb", "Index", "Middle", "Ring", "Little"]
  
  for i, raw_val in enumerate(raw_curls):
    # Apply calibration ((raw - open)/(closed - open))

    #if (calibration_closed[i] - calibration_open[i] != 0):
    #  raw_val = (raw_val - calibration_open[i]) / (calibration_closed[i] - calibration_open[i])

    # Normalize to 0.0 - 1.0
    # If 1024 is "open" and 0 is "fist", use: 1.0 - (raw_val / 1024.0)
    #norm = max(0.0, min(1.0, raw_val / 1024.0))
    
    c_min = calibration_open[i]
    c_max = calibration_closed[i]

    # 1. Normalize between 0.0 and 1.0 using the calibrated range
    # Use a small epsilon to avoid division by zero
    denom = (c_max - c_min) if (c_max - c_min) != 0 else 1
    norm = (raw_val - c_min) / denom
    norm = max(0.0, min(1.0, norm)) # Clamp to 0-1 range

    # Smoothing (using the global alpha and smoothed_values)
    global smoothed_values
    smoothed_values[i] = (norm * alpha) + (smoothed_values[i] * (1 - alpha))

    # Calculate Quaternion (Rotation on X-axis)
    # [qx, qy, qz, qw]
    if i == 0:  # Thumb rotates differently
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

    # VMC Protocol: /VMC/Ext/Bone/Pos, (str)Name, (float)px, py, pz, rx, ry, rz, rw
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

def update_health_metrics():
  global last_packet_check, packet_count, client
  if not client or not client.is_connected:
    return

  current_time = time.time()
  elapsed = current_time - last_packet_check
  
  # Calculate Packets Per Second (PPS)
  pps = packet_count / elapsed
  
  # Reset counters for the next second
  packet_count = 0
  last_packet_check = current_time
  #print(f"Packets/sec: {pps}")
  ui.signalBar.setValue(int(pps))

  # >50 = good, 30-50 = okay, <30 = low battery or signal

def notification_handler(characteristic, data):
  global finger_state, packet_count
  try:
    packet_count += 1

    # Unpack the 20 bytes into 5 floats
    # 'f' is 4 bytes, so 'fffff' is 20 bytes
    raw_curls = struct.unpack('fffff', data)
    finger_state = raw_curls
    
    #data_string = ", ".join([str(int(val)) for val in raw_curls])
    #data_display.setText(f"Glove Data: [{data_string}]")
    #print(f"Glove Data: [{data_string}]")

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
    except Exception as e:
        print(f"Error during cleanup: {e}")

def on_connect_clicked():
  global client, loop
  if client and client.is_connected:
    loop.create_task(cleanup_ble())
    ui.statusLabel.setText("Disconnected from glove.")
    ui.connectButton.setText("Connect")
    return

  # This schedules the async task into the existing qasync loop
  asyncio.ensure_future(start_connection())

def gloveMonitoringEnabled(enabled):
  ui.calibrateClosedButton.setEnabled(enabled)
  ui.calibrateOpenButton.setEnabled(enabled)
  ui.signalBar.setEnabled(enabled)

def calibrate_open(event):
  global calibration_open
  calibration_open = list(finger_state)
  print(f"Open Calibration: {calibration_open}")

def calibrate_closed(event):
  global calibration_closed
  calibration_closed = list(finger_state)
  print(f"Closed Calibration: {calibration_closed}")

# EVENTS
ui.connectButton.clicked.connect(lambda: on_connect_clicked())
ui.calibrateClosedButton.clicked.connect(calibrate_closed)
ui.calibrateOpenButton.clicked.connect(calibrate_open)

health_timer.timeout.connect(update_health_metrics)
health_timer.start(1000)

gloveMonitoringEnabled(False)

with loop:
  loop.run_forever()