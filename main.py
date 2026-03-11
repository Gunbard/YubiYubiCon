import sys
import asyncio

from bleak import BleakScanner
from mainWindow import Ui_MainWindow
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtMultimedia import QSoundEffect
from PyQt5.QtWidgets import QMessageBox, QTableWidgetItem, QHeaderView, QInputDialog, QLineEdit

APP_TITLE = 'YubiYubiCon'
VERSION = '1.0.0'
WINDOW_TITLE = "{}".format(APP_TITLE)

# APP SETUP

QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_DisableWindowContextHelpButton)
app = QtWidgets.QApplication(sys.argv)

MainWindow = QtWidgets.QMainWindow()
ui = Ui_MainWindow()
ui.setupUi(MainWindow)

MainWindow.setWindowTitle("{} {}".format(
    WINDOW_TITLE, VERSION))
MainWindow.show()

# EVENTS
app.exec_()