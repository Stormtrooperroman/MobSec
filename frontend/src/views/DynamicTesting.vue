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
      isLoadingDevices: false
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
          showError: false
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
</style>
