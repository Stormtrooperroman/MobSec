<template>
  <div class="dynamic-testing">
    <h1>Dynamic Testing</h1>
    

    <div class="device-list" v-if="devices.length > 0">
      <div v-for="device in visibleDevices" :key="device.id" class="device-card">
          <div class="device-info">
            <h3>{{ device.name || device.id }}</h3>
            <p>Status: {{ device.status }}</p>
            <p v-if="device.device_type" class="device-type">
              Type: <span :class="['type-badge', device.device_type]">{{ device.device_type }}</span>
            </p>
          </div>

        <div class="device-actions">
          <button
            :class="['device-btn', device.isStreaming ? 'btn-stop' : 'btn-start']"
            @click="toggleStream(device)"
            :disabled="device.isLoading || !device.id"
          >
            <span v-if="device.isLoading" class="loading-spinner"></span>
            {{ device.isStreaming ? 'Stop' : 'Start' }}
          </button>
          
          <div v-if="device.isStreaming" class="app-install-dropdown">
            <button 
              @click="toggleAppInstallMenu(device)" 
              :class="['device-btn', 'btn-install', { 'active': device.showAppInstallMenu }]"
            >
              <font-awesome-icon icon="mobile-screen-button" />
              Install App
              <font-awesome-icon 
                :icon="device.showAppInstallMenu ? 'chevron-up' : 'chevron-down'" 
                class="dropdown-arrow"
              />
            </button>
            
            <div v-if="device.showAppInstallMenu" class="dropdown-menu">
              <div class="dropdown-item" @click="$refs[`apkFileInput-${device.id}`][0].click()">
                <font-awesome-icon icon="folder-open" />
                Upload APK File
              </div>
              <div class="dropdown-separator"></div>
              <div class="dropdown-section-title">Previously Uploaded Apps:</div>
              <div v-if="availableApps.length === 0" class="dropdown-item disabled">
                <font-awesome-icon icon="exclamation-circle" />
                No APK files available
              </div>
              <div v-else>
                <div 
                  v-for="app in availableApps" 
                  :key="app.file_hash"
                  class="dropdown-item app-item"
                  @click="installApp(device, app)"
                >
                  <font-awesome-icon :icon="['fab', 'android']" class="app-icon" />
                  <div class="app-info">
                    <div class="app-name">{{ app.original_name }}</div>
                    <div class="app-details">{{ formatFileSize(app.size) }} • {{ formatDate(app.timestamp) }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          <input 
            type="file" 
            @change="uploadApkFile($event, device)" 
            accept=".apk" 
            style="display: none" 
            :ref="`apkFileInput-${device.id}`"
          >
        </div>

        <device-streamer 
          v-if="device.isStreaming" 
          :device-id="device.id" 
          :key="device.id"
          @success="handleStreamerSuccess"
          @error="handleStreamerError"
        />
        
        <v-snackbar
          v-model="device.showError"
          color="error"
          timeout="3000"
        >
          {{ device.error }}
        </v-snackbar>
      </div>
    </div>

    <WiFiConnectionModal
      :show="showWiFiModal"
      @close="closeWiFiModal"
      @success="handleWiFiSuccess"
      @error="handleWiFiError"
    />

    <div v-if="devices.length > 0 || isLoadingDevices">
      <div v-if="isLoadingDevices" class="loading-devices">
        <div class="loading-content">
          <div class="loading-spinner"></div>
          <p>Loading devices...</p>
        </div>
      </div>
    </div>

    <div v-else-if="devices.length === 0" class="no-devices">
        <p>No connected devices</p>
        <button 
          class="btn btn-primary"
          @click="refreshDevices"
          :disabled="isLoadingDevices"
        >
          {{ isLoadingDevices ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    

    <div class="wifi-connection-section" v-if="!hasConnectedDevices">
      <button 
        class="wifi-connect-btn"
        @click="showWiFiConnectModal"
      >
        <font-awesome-icon icon="wifi" />
        Connect using WiFi
      </button>
    </div>
    
    <!-- Notification Toast -->
    <NotificationToast 
      :notifications="notifications"
      @remove="removeNotification"
    />
  </div>
</template>

<script>
import DeviceStreamer from '@/components/DeviceStreamer.vue';
import NotificationToast from '@/components/NotificationToast.vue';
import WiFiConnectionModal from '@/components/modals/WiFiConnectionModal.vue';
import axios from 'axios';

export default {
  name: 'DynamicTesting',
  components: {
    DeviceStreamer,
    NotificationToast,
    WiFiConnectionModal
  },
  data() {
    return {
      devices: [],
      error: null,
      isLoadingDevices: false,
      availableApps: [],
      notifications: [],
      showWiFiModal: false,
      isDisconnectingWiFi: false
    };
  },
  computed: {
    visibleDevices() {
      const streamingDevices = this.devices.filter(device => device.isStreaming);
      
      if (streamingDevices.length > 0) {
        return streamingDevices;
      }
      
      return this.devices;
    },
    hasConnectedDevices() {
      return this.devices.some(device => 
        device.isStreaming
      );
    }
  },
  async created() {
    await this.refreshDevices();
    document.addEventListener('click', this.handleClickOutside);
  },
  beforeUnmount() {
    document.removeEventListener('click', this.handleClickOutside);
  },
  methods: {
    addNotification(type, title, message) {
      const id = Date.now() + Math.random();
      this.notifications.push({
        id,
        type,
        title,
        message
      });
      
      setTimeout(() => {
        this.removeNotification(id);
      }, 5000);
    },
    
    removeNotification(id) {
      const index = this.notifications.findIndex(n => n.id === id);
      if (index !== -1) {
        this.notifications.splice(index, 1);
      }
    },

    handleStreamerSuccess(message) {
      this.addNotification('success', 'Success', message);
    },

    handleStreamerError(message) {
      this.addNotification('error', 'Error', message);
    },

    async refreshDevices() {
      this.isLoadingDevices = true;
      try {
        const response = await axios.get('/api/v1/dynamic-testing/devices');
        this.devices = response.data.map(device => ({
          id: device.udid,
          name: device.name || device.udid,
          status: device.status || 'unknown',
          isStreaming: false,
          isLoading: false,
          error: null,
          showError: false,
          showAppInstallMenu: false,
          device_type: device.device_type
        }));
      } catch (error) {
        console.error('Failed to fetch devices:', error);
        this.error = 'Error fetching device list';
        this.addNotification('error', 'Error', 'Failed to get device list');
      } finally {
        this.isLoadingDevices = false;
      }
    },
    async toggleStream(device) {
      if (!device.id) {
        device.error = 'Device ID not defined';
        device.showError = true;
        return;
      }

      device.isLoading = true;
      device.error = null;
      device.showError = false;
      
      try {
        if (device.isStreaming) {
          await axios.post(`/api/v1/dynamic-testing/device/${device.id}/stop`);
          device.isStreaming = false;
        } else {
          await axios.post(`/api/v1/dynamic-testing/device/${device.id}/start`);
          device.isStreaming = true;
        }
      } catch (error) {
        console.error('Failed to toggle stream:', error);
        device.error = error.response?.data?.detail || 'Error managing stream';
        device.showError = true;
        this.addNotification('error', 'Error', `Failed to ${device.isStreaming ? 'stop' : 'start'} stream for device ${device.name}`);
      } finally {
        device.isLoading = false;
      }
    },

    async toggleAppInstallMenu(device) {
      device.showAppInstallMenu = !device.showAppInstallMenu;
      
      if (device.showAppInstallMenu) {
        await this.loadAvailableApps();
      }
    },

    async loadAvailableApps() {
      try {
        const response = await axios.get('/api/v1/apps/?limit=100');
        this.availableApps = response.data.apps.filter(app => app.file_type === 'apk');
      } catch (error) {
        console.error('Error loading apps:', error);
        this.availableApps = [];
      }
    },

    async uploadApkFile(event, device) {
      const file = event.target.files[0];
      if (file) {
        if (!file.name.toLowerCase().endsWith('.apk')) {
          alert('Please select an APK file');
          return;
        }

        const formData = new FormData();
        formData.append('apk_file', file);

        try {
          
          const response = await axios.post(`/api/v1/dynamic-testing/device/${device.id}/install-apk-direct`, formData, {
            headers: {
              'Content-Type': 'multipart/form-data'
            }
          });

          console.log('APK installed successfully:', response.data);
          

          
        } catch (error) {
          console.error('Error uploading and installing APK:', error);

        }
      }
      
      event.target.value = '';
      device.showAppInstallMenu = false;
    },

    async installApp(device, app) {
      await this.installAppByHash(device, app.file_hash, app.original_name);
      device.showAppInstallMenu = false;
    },

    async installAppByHash(device, fileHash, appName) {
      try {
        const response = await axios.post(`/api/v1/dynamic-testing/device/${device.id}/install-app`, {
          file_hash: fileHash,
          app_name: appName
        });
        
        console.log(`Installation started for ${appName}:`, response.data);
        
        device.error = `Installing ${appName}...`;
        device.showError = true;
        
        setTimeout(() => {
          device.showError = false;
        }, 3000);
        
      } catch (error) {
        console.error('Error installing app:', error);
        device.error = `Failed to install ${appName}: ${error.response?.data?.detail || 'Unknown error'}`;
        device.showError = true;
      }
    },

    async enableWirelessDebugging(device) {
      if (!device.id) {
        device.error = 'Device ID not defined';
        device.showError = true;
        return;
      }

      device.isLoading = true;
      device.error = null;
      device.showError = false;

      try {
        const response = await axios.post(`/api/v1/dynamic-testing/device/${device.id}/enable-wireless-debugging`);
        this.addNotification('success', 'Success', `Wireless debugging enabled for ${device.name}`);
        device.status = response.data.status;
      } catch (error) {
        console.error('Failed to enable wireless debugging:', error);
        device.error = error.response?.data?.detail || 'Error enabling wireless debugging';
        device.showError = true;
      } finally {
        device.isLoading = false;
      }
    },

    showWiFiConnectModal(device = null) {
      console.log('Opening WiFi modal', device ? `for device: ${device.name}` : '');
      this.showWiFiModal = true;
    },

    closeWiFiModal() {
      console.log('Closing WiFi modal');
      this.showWiFiModal = false;
    },

    async handleWiFiSuccess(message) {
      this.addNotification('success', 'Success', message);
      this.closeWiFiModal();
      await this.refreshDevices();
      
      // Обновляем статус устройств после успешного WiFi подключения
      this.devices.forEach(device => {
        if (device.status === 'disconnected' || device.status === 'offline') {
          device.status = 'wireless_debugging_enabled';
        }
      });
    },

    handleWiFiError(message) {
      this.addNotification('error', 'Error', message);
    },

    formatFileSize(bytes) {
      if (bytes === 0) return '0 B';
      const k = 1024;
      const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    formatDate(timestamp) {
      if (!timestamp) return '';
      const date = new Date(timestamp);
      return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
    },

    handleClickOutside(event) {
      const dropdowns = document.querySelectorAll('.app-install-dropdown');
      let isOutside = true;
      
      dropdowns.forEach(dropdown => {
        if (dropdown.contains(event.target)) {
          isOutside = false;
        }
      });
      
      if (isOutside) {
        this.devices.forEach(device => {
          device.showAppInstallMenu = false;
        });
      }
    },

    async disconnectWiFi() {
      this.isDisconnectingWiFi = true;
      try {
        await axios.post('/api/v1/dynamic-testing/disconnect-wifi');
        this.addNotification('success', 'Success', 'WiFi connection disconnected.');
        
        // Обновляем статус устройств после отключения WiFi
        this.devices.forEach(device => {
          if (device.status === 'wireless_debugging_enabled') {
            device.status = 'disconnected';
          }
        });
        
        await this.refreshDevices();
      } catch (error) {
        console.error('Failed to disconnect WiFi:', error);
        this.addNotification('error', 'Error', 'Failed to disconnect WiFi: ' + (error.response?.data?.detail || error.message));
      } finally {
        this.isDisconnectingWiFi = false;
      }
    }
  }
};
</script>

<style scoped>
:root {
  --border-color: #e0e0e0;
  --stream-bg: #000000;
  --wifi-status-bg: #e0f2f7;
  --wifi-status-border: #17a2b8;
  --wifi-status-text: #17a2b8;
  --disconnect-btn-bg: #f44336;
  --disconnect-btn-hover: #d32f2f;
}

@media (prefers-color-scheme: dark) {
  :root {
    --stream-bg: #000000;
    --wifi-status-bg: #1a3a4a;
    --wifi-status-border: #17a2b8;
    --wifi-status-text: #17a2b8;
    --disconnect-btn-bg: #f44336;
    --disconnect-btn-hover: #d32f2f;
  }
}

.dynamic-testing {
  padding: 2rem;
  color: var(--text-primary);
}

.wifi-connection-section {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 2rem;
  margin-top: 2rem;
}

.wifi-connect-btn {
  background-color: #17a2b8;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.3s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.wifi-connect-btn:hover {
  background-color: #138496;
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid transparent;
  border-top: 2px solid currentColor;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.device-list {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  margin-top: 2rem;
}

.device-card {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  transition: border-color 0.3s ease, box-shadow 0.3s ease;
}

.device-info h3 {
  margin: 0;
  color: var(--text-primary);
}

.device-info p {
  margin: 0.5rem 0 0;
  color: var(--text-secondary);
}

.device-type {
  margin-top: 0.5rem;
  font-size: 0.9rem;
  color: var(--text-secondary);
}

.type-badge {
  padding: 4px 8px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 0.8rem;
  text-transform: uppercase;
}

.type-badge.physical {
  background-color: #e0f2f7;
  color: #17a2b8;
}

.type-badge.emulator {
  background-color: #f8f9fa;
  color: #6c757d;
}

.type-badge.unknown {
  background-color: #f8f9fa;
  color: #6c757d;
}

.device-actions {
  display: flex;
  gap: 1rem;
}

.physical-device-actions {
  display: flex;
  gap: 0.5rem;
  margin-left: auto;
}

.device-btn {
  padding: 12px 24px;
  font-weight: 600;
  font-size: 14px;
  border: 2px solid;
  border-radius: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
  transition: all 0.3s ease;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 80px;
  justify-content: center;
}

.device-btn:hover {
  transform: translateY(-1px);
}

.btn-start {
  border-color: #4CAF50;
  color: #4CAF50;
}

.btn-start:hover {
  background-color: #4CAF50;
  color: white;
}

.btn-stop {
  border-color: #f44336;
  color: #f44336;
}

.btn-stop:hover {
  background-color: #f44336;
  color: white;
}

.btn-wireless {
  border-color: #28a745;
  color: #28a745;
}

.btn-wireless:hover {
  background-color: #28a745;
  color: white;
}

.btn-wifi-connect {
  border-color: #007bff;
  color: #007bff;
}

.btn-wifi-connect:hover {
  background-color: #007bff;
  color: white;
}

.device-btn:disabled {
  opacity: 0.6;
  transform: none;
  box-shadow: none;
  cursor: not-allowed;
}

/* App Installation Dropdown Styles */
.app-install-dropdown {
  position: relative;
  display: inline-block;
  margin-left: auto;
  margin-right: 0px;
}

.btn-install {
  border-color: #28a745;
  color: #28a745;
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-install:hover {
  background-color: #28a745;
  color: white;
}

.btn-install.active {
  background-color: #1e7e34;
  border-color: #1e7e34;
  color: white;
  box-shadow: 0 0 0 2px rgba(40, 167, 69, 0.25);
}

.dropdown-arrow {
  font-size: 10px;
  transition: transform 0.2s ease;
  margin-left: 4px;
}

.app-icon {
  margin-right: 8px;
  color: #28a745;
  font-size: 14px;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  background: white;
  border: 1px solid #ccc;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  min-width: 280px;
  max-width: 400px;
  z-index: 1000;
  max-height: 300px;
  overflow-y: auto;
  animation: dropdownFadeIn 0.2s ease-out;
  transform-origin: top right;
}

.dropdown-item {
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid #eee;
  transition: background-color 0.2s ease;
}

.dropdown-item:last-child {
  border-bottom: none;
}

.dropdown-item:hover:not(.disabled) {
  background-color: #f8f9fa;
}

.dropdown-item.disabled {
  color: #999;
  cursor: not-allowed;
  font-style: italic;
}

.dropdown-separator {
  height: 1px;
  background: #eee;
  margin: 0;
}

.dropdown-section-title {
  padding: 8px 12px;
  font-weight: 600;
  color: #333;
  background: #f8f9fa;
  border-bottom: 1px solid #eee;
  font-size: 12px;
  text-transform: uppercase;
}

.app-item {
  padding: 10px 12px;
  display: flex;
  align-items: center;
}

.app-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.app-name {
  font-weight: 500;
  color: #333;
  font-size: 14px;
  word-break: break-word;
}

.app-details {
  font-size: 12px;
  color: #666;
}

.app-item:hover {
  background-color: #e3f2fd;
}

/* Ensure dropdown appears above other elements */
.dropdown-menu::-webkit-scrollbar {
  width: 6px;
}

.dropdown-menu::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.dropdown-menu::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.dropdown-menu::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

@keyframes dropdownFadeIn {
  from {
    opacity: 0;
    transform: scaleY(0.8);
  }
  to {
    opacity: 1;
    transform: scaleY(1);
  }
}

.loading-devices {
  text-align: center;
  margin-top: 4rem;
}

.loading-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.loading-content p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.1rem;
}

.no-devices {
  text-align: center;
  margin-top: 4rem;
}

.no-devices p {
  margin-bottom: 1rem;
  color: var(--text-secondary);
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background-color: #007bff;
  color: #fff;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.btn-primary:hover:not(:disabled) {
  background-color: #0056b3;
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}

.connection-status {
  margin-bottom: 2rem;
  text-align: right;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  background-color: var(--wifi-status-bg);
  border: 1px solid var(--wifi-status-border);
  border-radius: 6px;
  padding: 10px 15px;
  color: var(--wifi-status-text);
  font-weight: 600;
  font-size: 14px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.status-indicator .wifi-icon {
  color: var(--wifi-status-text);
  font-size: 18px;
}

.status-indicator .disconnect-btn {
  background-color: var(--disconnect-btn-bg);
  color: white;
  border: none;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.3s ease;
  white-space: nowrap;
}

.status-indicator .disconnect-btn:hover {
  background-color: var(--disconnect-btn-hover);
}

.status-indicator .disconnect-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.status-indicator .disconnect-btn:disabled:hover {
  background-color: var(--disconnect-btn-bg);
}

@media (max-width: 768px) {
  .wifi-connect-btn {
    font-size: 14px;
    padding: 10px 20px;
  }
  
  .connection-status {
    text-align: center;
  }
  
  .status-indicator {
    flex-direction: column;
    gap: 8px;
    padding: 12px;
  }
  
  .status-indicator .disconnect-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
