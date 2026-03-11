import sys
import asyncio
from pythonosc import udp_client
from bleak import BleakScanner
from qasync import QEventLoop, asyncSlot
from mainWindow import Ui_MainWindow
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication

APP_TITLE = 'YubiYubiCon'
VERSION = '1.0.0'
WINDOW_TITLE = '{}'.format(APP_TITLE)
VMC_IP = '127.0.0.1'
VMC_PORT = 39539

# APP SETUP

QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_DisableWindowContextHelpButton)

app = QtWidgets.QApplication(sys.argv)
loop = QEventLoop(app)
asyncio.set_event_loop(loop)

MainWindow = QtWidgets.QMainWindow()
ui = Ui_MainWindow()
ui.setupUi(MainWindow)

MainWindow.setWindowTitle("{} {}".format(
    WINDOW_TITLE, VERSION))
MainWindow.show()

# EVENTS

with loop:
  loop.run_forever()