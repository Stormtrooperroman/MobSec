# Dynamic Testing Module

This module provides dynamic testing capabilities using ReDroid and Frida for Android applications.

## Features

- Android emulation using ReDroid
- Automatic Frida server installation
- APK installation and management
- Frida instrumentation support

## Prerequisites

- Docker
- ADB (Android Debug Bridge)
- Python 3.8+

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Build the ReDroid container:
```bash
docker-compose build dynamic-testing
```

## API Endpoints

### Start Environment
- **POST** `/api/dynamic-testing/start`
- Starts a new ReDroid environment with Frida server

### Stop Environment
- **POST** `/api/dynamic-testing/stop`
- Stops the running ReDroid environment

### Install APK
- **POST** `/api/dynamic-testing/install-apk`
- Installs an APK file in the ReDroid environment
- Requires APK file in form-data with key 'apk'

### List Packages
- **GET** `/api/dynamic-testing/packages`
- Returns a list of installed packages

### Attach Frida
- **POST** `/api/dynamic-testing/attach`
- Attaches Frida to a specified package
- Requires JSON body with package_name

## Usage Example

```python
import requests

# Start environment
requests.post('http://localhost:8000/api/dynamic-testing/start')

# Install APK
with open('app.apk', 'rb') as f:
    requests.post('http://localhost:8000/api/dynamic-testing/install-apk', files={'apk': f})

# List packages
packages = requests.get('http://localhost:8000/api/dynamic-testing/packages').json()

# Attach Frida
requests.post('http://localhost:8000/api/dynamic-testing/attach', json={'package_name': 'com.example.app'})

# Stop environment
requests.post('http://localhost:8000/api/dynamic-testing/stop')
``` 