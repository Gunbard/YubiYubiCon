# YubiYubiCon
Converts custom VR glove finger tracking data to VMC/OSC listeners through ESP32 Bluetooth Low Energy.

Tested on Windows 10

## Local Development

Developed on Python 3.14

### Install Dependencies
```sh
pip install -r requirements.in
```

### (Re)compiling the UI
```sh
pyuic5 mainWindow.ui -o mainWindow.py;
```

### Running
```sh
python main.py
```

### Building standalone executable
```sh
pip install pyinstaller
pyinstaller --onefile --noconsole main.py
```

Built exe will be in 'dist' folder

## Usage
- Turn on gloves
- Ensure Bluetooth is turned on on desktop. No need to pair.
- Run app and set an IP and port the VMC/OSC listener is on. Click connect.
- App will search for both gloves and try to connect to them
- If connected, signal meter will display.
- Bluetooth is a little flaky, so if both don't connect, try again. You may need to turn desktop Bluetooth off and on again to reset it and clear some caches.
- Once connected, finger data formatted for standard VMC fingees for each hand will be sent at about 100 Hz
- Click Calibrate OPEN while your hand is fully open
- Click Calibrate CLOSED while your hand is in a fist
- Give the finger

## TODO
- [ ] Adjustable smoothing in app
- [ ] Reconnect each hand separately