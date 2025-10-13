<template>
  <div v-if="show" class="modal-overlay" @click="closeModal">
    <div class="modal-content" @click.stop>
      <div class="modal-header">
        <h3>Connect to WiFi Device</h3>
        <button class="modal-close" @click="closeModal">&times;</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label for="wifi-ip">IP Address:</label>
          <input 
            id="wifi-ip"
            v-model="connection.ip"
            type="text"
            placeholder="192.168.1.100"
            class="form-input"
          >
        </div>
        <div class="form-group">
          <label for="wifi-port">Port:</label>
          <input 
            id="wifi-port"
            v-model="connection.port"
            type="number"
            placeholder="5555"
            class="form-input"
          >
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="closeModal">
          Cancel
        </button>
        <button class="btn btn-primary" @click="connectDevice" :disabled="isConnecting">
          {{ isConnecting ? 'Connecting...' : 'Connect' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  name: 'WiFiConnectionModal',
  props: {
    show: {
      type: Boolean,
      default: false
    }
  },
  emits: ['close', 'success', 'error'],
  data() {
    return {
      connection: {
        ip: '',
        port: 5555
      },
      isConnecting: false
    };
  },
  watch: {
    show(newVal) {
      if (newVal) {
        this.connection.ip = '';
        this.connection.port = 5555;
      }
    }
  },
  methods: {
    closeModal() {
      this.$emit('close');
    },

    async connectDevice() {
      if (!this.connection.ip || !this.connection.port) {
        this.$emit('error', 'Please enter both IP address and port.');
        return;
      }

      this.isConnecting = true;
      try {
        const response = await axios.post('/api/v1/dynamic-testing/device/connect-wifi', {
          ip_address: this.connection.ip,
          port: this.connection.port
        });
        
        this.$emit('success', `WiFi connection successful for ${this.connection.ip}:${this.connection.port}`);
        this.closeModal();
      } catch (error) {
        console.error('Failed to connect WiFi device:', error);
        this.$emit('error', `Failed to connect WiFi device ${this.connection.ip}:${this.connection.port}: ${error.response?.data?.detail || 'Unknown error'}`);
      } finally {
        this.isConnecting = false;
      }
    }
  }
};
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 8px;
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e9ecef;
}

.modal-header h3 {
  margin: 0;
  color: #333;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #666;
  padding: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-close:hover {
  color: #333;
}

.modal-body {
  padding: 20px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 20px;
  border-top: 1px solid #e9ecef;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
  font-weight: 600;
  color: #333;
}

.form-input {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  box-sizing: border-box;
  max-width: 100%;
}

.form-input:focus {
  outline: none;
  border-color: #007bff;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
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
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background-color: #0056b3;
}

.btn-secondary {
  background-color: #6c757d;
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background-color: #545b62;
}
</style> 