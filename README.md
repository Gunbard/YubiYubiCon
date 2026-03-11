# YubiYubiCon
Converts custom VR glove finger tracking data to VMC/OSC 

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