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
GLOVE_L_NAME = "ESP32GloveL"
GLOVE_R_NAME = "ESP32GloveR"

osc_client = udp_client.SimpleUDPClient(VMC_IP, VMC_PORT)

# --- Left Glove State Arrays ---
finger_state_left = [0, 0, 0, 0, 0]
calibration_open_left = [0, 0, 0, 0, 0]
calibration_closed_left = [1024, 1024, 1024, 1024, 1024]
smoothed_values_left = [0.0] * 5
packet_count_left = 0
last_packet_check_left = time.time()

# --- Right Glove State Arrays ---
finger_state_right = [0, 0, 0, 0, 0]
calibration_open_right = [0, 0, 0, 0, 0]
calibration_closed_right = [1024, 1024, 1024, 1024, 1024]
smoothed_values_right = [0.0] * 5
packet_count_right = 0
last_packet_check_right = time.time()

# --- Dual Connection Management ---
client_left = None
client_right = None

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
smoothed_values_right = [0.0] * 5

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

async def start_connection():
  global status_label, client_left, client_right, osc_client
  ui.connectButton.setEnabled(False)
  status_label.setText("Scanning for left & right gloves...")
  
  # Scan for devices advertising our specific Service UUID
  devices = await BleakScanner.discover(
      timeout=4.0, 
      return_adv=True
  )
  
  target_left_device = None
  target_right_device = None

  for address, (device, adv_data) in devices.items():
      # Clean up potential UUID casing variations
      advertised_services = [s.lower() for s in adv_data.service_uuids]
      if SERVICE_UUID.lower() in advertised_services:
          if device.name == GLOVE_L_NAME:
              target_left_device = device
          elif device.name == GLOVE_R_NAME:
              target_right_device = device

  if not target_left_device and not target_right_device:
    status_label.setText("No gloves found. Are they turned on?")
    ui.connectButton.setEnabled(True)
    gloveMonitoringLeftEnabled(False)
    gloveMonitoringRightEnabled(False)
    return

  found_text = []
  if target_left_device: found_text.append("Left")
  if target_right_device: found_text.append("Right")
  status_label.setText(f"Found {', '.join(found_text)} glove(s). Connecting...")

  connection_tasks = []
  
  if target_left_device:
      client_left = BleakClient(target_left_device)
      connection_tasks.append(connect_glove(client_left, "Left", left_notification_handler))
  if target_right_device:
      client_right = BleakClient(target_right_device)
      connection_tasks.append(connect_glove(client_right, "Right", right_notification_handler))

  # Connect to found devices concurrently without letting one stall the other
  results = await asyncio.gather(*connection_tasks, return_exceptions=True)
  
  connected_success = [r for r in results if r is True]
  if connected_success:
      status_label.setText(f"Connected to {len(connected_success)} Glove(s)! Streaming via VMC...")
      ui.connectButton.setText("Disconnect")
      ui.connectButton.setEnabled(True)
  else:
      status_label.setText("Connection Failed for all detected devices.")
      ui.connectButton.setEnabled(True)
      gloveMonitoringLeftEnabled(False)
      gloveMonitoringRightEnabled(False)

async def connect_glove(client, side_name, handler):
    try:
        await client.connect()
        await client.start_notify(CHARACTERISTIC_UUID, handler)
        print(f"[{side_name} Glove] Successfully attached and notifying.")
        if side_name == "Left":
          gloveMonitoringLeftEnabled(True)
        else:
          gloveMonitoringRightEnabled(True)
        return True
    except Exception as e:
        print(f"[{side_name} Glove] Failed connection hook: {e}")
        return e

def map_and_send_to_vmc(raw_curls, side):
  """
  raw_curls: list/tuple of 5 floats
  side: "Left" or "Right"
  """
  global osc_client, alpha, smoothed_values_left, smoothed_values_right
  
  finger_names = ["Thumb", "Index", "Middle", "Ring", "Little"]
  
  # Select runtime variables based on target hand side context
  if side == "Left":
      c_min = calibration_open_left
      c_max = calibration_closed_left
      smoothed_vals = smoothed_values_left
  else:
      c_min = calibration_open_right
      c_max = calibration_closed_right
      smoothed_vals = smoothed_values_right

  for i, raw_val in enumerate(raw_curls):
    denom = (c_max[i] - c_min[i]) if (c_max[i] - c_min[i]) != 0 else 1
    norm = (raw_val - c_min[i]) / denom
    norm = max(0.0, min(1.0, norm))

    # Apply separate smoothing history
    smoothed_vals[i] = (norm * alpha) + (smoothed_vals[i] * (1 - alpha))

    # Calculate Quaternions
    if i == 0:  # Thumb
      angle = smoothed_vals[i] * 2.0
      s = math.sin(angle / 2)
      c = math.cos(angle / 2)
      qx, qy, qz, qw = s, 0.0, 0.0, c 
    else:  # Fingers
      # Mirroring the rotation angle for the left hand geometry structure
      multiplier = 1.6 if side == "Left" else -1.6
      angle = smoothed_vals[i] * multiplier
      s = math.sin(angle / 2)
      c = math.cos(angle / 2)
      qx, qy, qz, qw = 0.0, 0.0, s, c

    for segment in ["Proximal", "Intermediate", "Distal"]:
      bone_id = f"{side}{finger_names[i]}{segment}"
      
      osc_client.send_message("/VMC/Ext/Bone/Pos", [
        bone_id, 
        0.0, 0.0, 0.0, 
        qx, qy, qz, qw 
      ])

def update_health_metrics():
  global last_packet_check_left, packet_count_left, client_left
  global last_packet_check_right, packet_count_right, client_right
  
  current_time = time.time()

  # Left metrics
  if client_left and client_left.is_connected:
      elapsed_l = current_time - last_packet_check_left
      pps_l = packet_count_left / elapsed_l if elapsed_l > 0 else 0
      packet_count_left = 0
      last_packet_check_left = current_time
      if hasattr(ui, 'signalBarLeft'): # Safe backup wrapper check
          ui.signalBarLeft.setValue(int(pps_l))

  # Right metrics
  if client_right and client_right.is_connected:
      elapsed_r = current_time - last_packet_check_right
      pps_r = packet_count_right / elapsed_r if elapsed_r > 0 else 0
      packet_count_right = 0
      last_packet_check_right = current_time
      ui.signalBarRight.setValue(int(pps_r))

  # >50 = good, 30-50 = okay, <30 = low battery or signal

# def notification_handler(characteristic, data):
#   global finger_state_right, packet_count_right
#   try:
#     packet_count += 1

#     # Unpack the 20 bytes into 5 floats
#     # 'f' is 4 bytes, so 'fffff' is 20 bytes
#     raw_curls = struct.unpack('fffff', data)
#     finger_state_right = raw_curls
    
#     #data_string = ", ".join([str(int(val)) for val in raw_curls])
#     #data_display.setText(f"Glove Data: [{data_string}]")
#     #print(f"Glove Data: [{data_string}]")

#     map_and_send_to_vmc(raw_curls)
      
#   except Exception as e:
#       print(f"Unpack Error: {e}")

def left_notification_handler(characteristic, data):
  global finger_state_left, packet_count_left
  try:
    packet_count_left += 1
    raw_curls = struct.unpack('fffff', data)
    finger_state_left = raw_curls
    #data_string = ", ".join([str(int(val)) for val in raw_curls])
    #print(f"Glove Data L: [{data_string}]")
    map_and_send_to_vmc(raw_curls, "Left")
  except Exception as e:
      print(f"Left Unpack Error: {e}")

def right_notification_handler(characteristic, data):
  global finger_state_right, packet_count_right
  try:
    packet_count_right += 1
    raw_curls = struct.unpack('fffff', data)
    finger_state_right = raw_curls
    #data_string = ", ".join([str(int(val)) for val in raw_curls])
    #print(f"Glove Data R: [{data_string}]")
    map_and_send_to_vmc(raw_curls, "Right")
  except Exception as e:
      print(f"Right Unpack Error: {e}")

async def cleanup_ble():
  global client_left, client_right
  print("Cleaning up BLE connections...")
  
  cleanup_tasks = []
  
  if client_left and client_left.is_connected:
      async def clean_l():
          try:
              await client_left.stop_notify(CHARACTERISTIC_UUID)
              await client_left.disconnect()
          except Exception as e: print(f"Error cleaning Left: {e}")
      cleanup_tasks.append(clean_l())
      
  if client_right and client_right.is_connected:
      async def clean_r():
          try:
              await client_right.stop_notify(CHARACTERISTIC_UUID)
              await client_right.disconnect()
          except Exception as e: print(f"Error cleaning Right: {e}")
      cleanup_tasks.append(clean_r())

  if cleanup_tasks:
      await asyncio.gather(*cleanup_tasks)

  client_left = None
  client_right = None

def on_connect_clicked():
  global client_left, client_right, loop, osc_client
  
  is_any_connected = (client_left and client_left.is_connected) or (client_right and client_right.is_connected)
  
  if is_any_connected:
    loop.create_task(cleanup_ble())
    ui.statusLabel.setText("Disconnected from glove(s).")
    ui.connectButton.setText("Connect")
    gloveMonitoringLeftEnabled(False)
    gloveMonitoringRightEnabled(False)
    return

  ip = ui.vmcIpEdit.text()
  port = ui.vmcPortEdit.text()
  osc_client = udp_client.SimpleUDPClient(ip, int(port))

  asyncio.ensure_future(start_connection())

  ip = ui.vmcIpEdit.text()
  port = ui.vmcPortEdit.text()
  osc_client = udp_client.SimpleUDPClient(ip, int(port))

  # This schedules the async task into the existing qasync loop
  asyncio.ensure_future(start_connection())

def gloveMonitoringLeftEnabled(enabled):
  ui.calibrateClosedButtonL.setEnabled(enabled)
  ui.calibrateOpenButtonL.setEnabled(enabled)
  ui.signalBarLeft.setEnabled(enabled)
  if (not enabled):
    ui.signalBarLeft.setValue(0)

def gloveMonitoringRightEnabled(enabled):
  ui.calibrateClosedButtonR.setEnabled(enabled)
  ui.calibrateOpenButtonR.setEnabled(enabled)
  ui.signalBarRight.setEnabled(enabled)
  if (not enabled):
    ui.signalBarRight.setValue(0)

def calibrate_open_left(event):
  global calibration_open_left, finger_state_left
  calibration_open_left = list(finger_state_left)
  print(f"Open Calibration L: {calibration_open_left}")

def calibrate_closed_left(event):
  global calibration_closed_left, finger_state_left
  calibration_closed_left = list(finger_state_left)
  print(f"Closed Calibration L: {calibration_closed_left}")

def calibrate_open_right(event):
  global calibration_open_right, finger_state_right
  calibration_open_right = list(finger_state_right)
  print(f"Open Calibration R: {calibration_open_right}")

def calibrate_closed_right(event):
  global calibration_closed_right, finger_state_right
  calibrate_closed_right = list(finger_state_right)
  print(f"Closed Calibration R: {calibrate_closed_right}")

# EVENTS
ui.connectButton.clicked.connect(lambda: on_connect_clicked())
ui.calibrateClosedButtonL.clicked.connect(calibrate_closed_left)
ui.calibrateOpenButtonL.clicked.connect(calibrate_open_left)
ui.calibrateClosedButtonR.clicked.connect(calibrate_closed_right)
ui.calibrateOpenButtonR.clicked.connect(calibrate_open_right)

health_timer.timeout.connect(update_health_metrics)
health_timer.start(1000)

gloveMonitoringLeftEnabled(False)
gloveMonitoringRightEnabled(False)

with loop:
  loop.run_forever()