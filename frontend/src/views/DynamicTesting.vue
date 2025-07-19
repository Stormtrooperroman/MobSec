<template>
  <div class="dynamic-testing">
    <h1>Dynamic Testing</h1>
    
    <div class="device-list" v-if="devices.length > 0">
      <div v-for="device in visibleDevices" :key="device.id" class="device-card">
          <div class="device-info">
          <h3>{{ device.name || device.id }}</h3>
          <p>Status: {{ device.status }}</p>
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
              <font-awesome-icon icon="mobile" />
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

    <div v-else-if="isLoadingDevices" class="loading-devices">
      <div class="loading-content">
        <v-progress-circular 
          indeterminate 
          color="primary"
          size="64"
        ></v-progress-circular>
        <p>Loading devices...</p>
      </div>
    </div>

    <div v-else class="no-devices">
      <p>No connected devices</p>
      <v-btn 
        color="primary" 
        @click="refreshDevices"
        :loading="isLoadingDevices"
        :disabled="isLoadingDevices"
      >
        Refresh
      </v-btn>
    </div>
  </div>
</template>

<script>
import DeviceStreamer from '@/components/DeviceStreamer.vue';
import axios from 'axios';

export default {
  name: 'DynamicTesting',
  components: {
    DeviceStreamer
  },
  data() {
    return {
      devices: [],
      error: null,
      isLoadingDevices: false,
      availableApps: []
    };
  },
  computed: {
    visibleDevices() {
      const streamingDevices = this.devices.filter(device => device.isStreaming);
      
      if (streamingDevices.length > 0) {
        return streamingDevices;
      }
      
      return this.devices;
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
    async refreshDevices() {
      this.isLoadingDevices = true;
      try {
        const response = await axios.get('/api/v1/dynamic-testing/devices');
        this.devices = response.data.map(device => ({
          id: device.udid,
          name: device.name || device.udid,
          status: device.status,
          isStreaming: false,
          isLoading: false,
          error: null,
          showError: false,
          showAppInstallMenu: false
        }));
      } catch (error) {
        console.error('Failed to fetch devices:', error);
        this.error = 'Error fetching device list';
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
    }
  }
};
</script>

<style scoped>
:root {
  
  --border-color: #e0e0e0;
  --stream-bg: #000000;
}

@media (prefers-color-scheme: dark) {
  :root {
    
    --stream-bg: #000000;
  }
}

.dynamic-testing {
  padding: 2rem;
  color: var(--text-primary);
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

.device-actions {
  display: flex;
  gap: 1rem;
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

.device-btn:disabled {
  opacity: 0.6;
  transform: none;
  box-shadow: none;
  cursor: not-allowed;
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
</style>
