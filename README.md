# Mobile Security Testing Platform

![](images/first.png)

A modular platform for analyzing and security testing mobile applications. It is an alternative to [MobSF](https://github.com/MobSF/Mobile-Security-Framework-MobSF/) that is easier to customize and extend.

> [!WARNING]
> This project is under active development and has not been thoroughly tested. Expect bugs and breaking changes, and use it at your own risk.

## Features

### Module System
- Pluggable architecture with independent analysis modules
- Real-time module status monitoring
- Support for [custom modules](https://github.com/Stormtrooperroman/MobSec/blob/master/docs)

### Static Testing
- Analysis of APK files, IPA files, and source code

### Dynamic Testing
- Testing in a Dockerized Android environment
- Testing on a physical device

## Getting Started

### Requirements
- Docker ([installation guide](https://docs.docker.com/get-started/get-docker/))

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/Stormtrooperroman/MobSec.git
   ```

2. Start the platform with Docker Compose:

   ```bash
   cd MobSec
   docker compose up -d --build
   ```

3. Open the web interface at http://127.0.0.1/. The Swagger UI is available at http://127.0.0.1:8000/docs.

## Interface

![Stored apps](images/StoredApps.png)
![Modules](images/Modules.png)
![Chains](images/Chains.png)
![Running an analysis](images/Run.png)
![Report, part 1](images/Report1.png)
![Report, part 2](images/Report2.png)
![Settings](images/Settings.png)
![Dynamic testing](images/dynamic_testing.png)
![Dynamic testing screen](images/dynamic_testing_screen.png)