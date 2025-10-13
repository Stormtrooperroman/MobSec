<template>
  <div v-if="show" class="modal" @click="closeModal">
    <div class="modal-content" @click.stop>
      <div class="modal-header">
        <h5>Request Details</h5>
        <button @click="closeModal" class="close-btn">
          <font-awesome-icon icon="times" />
        </button>
      </div>
      
      <div class="modal-body" v-if="localEntry">
        <div class="content-loading" v-if="isLoading">
          <div class="spinner"></div>
          <span>Loading content...</span>
        </div>
        
        <div class="detail-section">
          <h6>Basic Information</h6>
          <div class="detail-grid">
            <div class="detail-item">
              <label>URL:</label>
              <span>{{ localEntry.url }}</span>
            </div>
            <div class="detail-item">
              <label>Method:</label>
              <span>{{ localEntry.method }}</span>
            </div>
            <div class="detail-item">
              <label>Status:</label>
              <span>{{ localEntry.status_code }}</span>
            </div>
            <div class="detail-item">
              <label>Time:</label>
              <span>{{ formatTime(localEntry.timestamp) }}</span>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <h6>Request Headers</h6>
          <div class="headers-list">
            <div 
              v-for="(value, key) in localEntry.request_headers" 
              :key="key"
              class="header-item"
            >
              <span class="header-key">{{ key }}:</span>
              <span class="header-value">{{ value }}</span>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <h6>Response Headers</h6>
          <div class="headers-list">
            <div 
              v-for="(value, key) in localEntry.response_headers" 
              :key="key"
              class="header-item"
            >
              <span class="header-key">{{ key }}:</span>
              <span class="header-value">{{ value }}</span>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <div class="section-header">
            <h6>Request Content</h6>
            <div class="section-controls">
              <div class="content-view-controls" v-if="localEntry.id">
                <button 
                  @click="changeContentView('request', 'auto')"
                  :class="['btn', 'btn-xs', localEntry.request_view === 'auto' ? 'btn-primary' : 'btn-outline-secondary']"
                  title="Auto mode"
                >
                  <font-awesome-icon icon="magic" />
                </button>
                <button 
                  @click="changeContentView('request', 'text')"
                  :class="['btn', 'btn-xs', localEntry.request_view === 'text' ? 'btn-primary' : 'btn-outline-secondary']"
                  title="Text mode"
                >
                  <font-awesome-icon icon="font" />
                </button>
                <button 
                  @click="changeContentView('request', 'hex')"
                  :class="['btn', 'btn-xs', localEntry.request_view === 'hex' ? 'btn-primary' : 'btn-outline-secondary']"
                  title="Hex mode"
                >
                  <font-awesome-icon icon="code" />
                </button>
                <button 
                  @click="changeContentView('request', 'raw')"
                  :class="['btn', 'btn-xs', localEntry.request_view === 'raw' ? 'btn-primary' : 'btn-outline-secondary']"
                  title="Raw mode"
                >
                  <font-awesome-icon icon="file-code" />
                </button>
              </div>
              <button 
                v-if="localEntry.id" 
                @click="downloadFlowContent(localEntry.id, 'request')"
                class="btn btn-xs btn-outline-secondary"
                title="Download request content"
              >
                <font-awesome-icon icon="download" />
              </button>
            </div>
          </div>
          <pre class="content-block" v-if="localEntry.request_content">{{ localEntry.request_content }}</pre>
          <div class="content-placeholder" v-else>
            <font-awesome-icon icon="info-circle" />
            <span>Request content unavailable or empty</span>
          </div>
        </div>

        <div class="detail-section">
          <div class="section-header">
            <h6>Response Content</h6>
            <div class="section-controls">
              <div class="content-view-controls" v-if="localEntry.id">
                <button 
                  @click="changeContentView('response', 'auto')"
                  :class="['btn', 'btn-xs', localEntry.response_view === 'auto' ? 'btn-primary' : 'btn-outline-secondary']"
                  title="Auto mode"
                >
                  <font-awesome-icon icon="magic" />
                </button>
                <button 
                  @click="changeContentView('response', 'text')"
                  :class="['btn', 'btn-xs', localEntry.response_view === 'text' ? 'btn-primary' : 'btn-outline-secondary']"
                  title="Text mode"
                >
                  <font-awesome-icon icon="font" />
                </button>
                <button 
                  @click="changeContentView('response', 'hex')"
                  :class="['btn', 'btn-xs', localEntry.response_view === 'hex' ? 'btn-primary' : 'btn-outline-secondary']"
                  title="Hex mode"
                >
                  <font-awesome-icon icon="code" />
                </button>
                <button 
                  @click="changeContentView('response', 'raw')"
                  :class="['btn', 'btn-xs', localEntry.response_view === 'raw' ? 'btn-primary' : 'btn-outline-secondary']"
                  title="Raw mode"
                >
                  <font-awesome-icon icon="file-code" />
                </button>
              </div>
              <button 
                v-if="localEntry.id" 
                @click="downloadFlowContent(localEntry.id, 'response')"
                class="btn btn-xs btn-outline-secondary"
                title="Download response content"
              >
                <font-awesome-icon icon="download" />
              </button>
            </div>
          </div>
          <pre class="content-block" v-if="localEntry.response_content">{{ localEntry.response_content }}</pre>
          <div class="content-placeholder" v-else>
            <font-awesome-icon icon="info-circle" />
            <span>Response content unavailable or empty</span>
          </div>
        </div>

        <!-- Additional flow information -->
        <div class="detail-section" v-if="localEntry.detailed">
          <h6>Additional Information</h6>
          <div class="detail-grid">
            <div class="detail-item" v-if="localEntry.intercepted">
              <label>Intercepted:</label>
              <span class="badge badge-warning">Yes</span>
            </div>
            <div class="detail-item" v-if="localEntry.is_replay">
              <label>Replay:</label>
              <span class="badge badge-info">Yes</span>
            </div>
            <div class="detail-item" v-if="localEntry.modified">
              <label>Modified:</label>
              <span class="badge badge-warning">Yes</span>
            </div>
            <div class="detail-item" v-if="localEntry.marked">
              <label>Marked:</label>
              <span>{{ localEntry.marked }}</span>
            </div>
            <div class="detail-item" v-if="localEntry.comment">
              <label>Comment:</label>
              <span>{{ localEntry.comment }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  name: 'TrafficDetailsModal',
  props: {
    show: {
      type: Boolean,
      default: false
    },
    entry: {
      type: Object,
      default: null
    },
    deviceId: {
      type: String,
      required: true
    }
  },
  emits: ['close', 'content-changed'],
  data() {
    return {
      isLoading: false,
      localEntry: null
    };
  },
  watch: {
    async show(newVal) {
      if (newVal && this.entry && this.entry.id) {
        this.localEntry = { ...this.entry };
        await this.loadContent();
      }
    },
    entry: {
      handler(newVal) {
        if (newVal) {
          this.localEntry = { ...newVal };
        }
      },
      immediate: true,
      deep: true
    }
  },
  methods: {
    closeModal() {
      this.$emit('close');
    },

    async loadContent() {
      if (!this.localEntry || !this.localEntry.id) return;
      
      try {
        this.isLoading = true;
        
        const [requestContent, responseContent] = await Promise.allSettled([
          this.getFlowContent(this.localEntry.id, 'request', 'auto'),
          this.getFlowContent(this.localEntry.id, 'response', 'auto')
        ]);
        
        if (requestContent.status === 'fulfilled' && requestContent.value) {
          this.localEntry.request_content = requestContent.value;
        } else {
          this.localEntry.request_content = 'Request content unavailable';
        }
        
        if (responseContent.status === 'fulfilled' && responseContent.value) {
          this.localEntry.response_content = responseContent.value;
        } else {
          this.localEntry.response_content = 'Response content unavailable';
        }
      } catch (error) {
        console.error('Error loading content:', error);
      } finally {
        this.isLoading = false;
      }
    },

    formatTime(timestamp) {
      return new Date(timestamp * 1000).toLocaleString('ru-RU');
    },

    async changeContentView(messageType, viewType) {
      if (!this.localEntry || !this.localEntry.id) {
        return;
      }

      try {
        this.isLoading = true;
        
        if (messageType === 'request') {
          this.localEntry.request_view = viewType;
        } else if (messageType === 'response') {
          this.localEntry.response_view = viewType;
        }
        
        const content = await this.getFlowContent(this.localEntry.id, messageType, viewType);
        
        if (content) {
          if (messageType === 'request') {
            this.localEntry.request_content = content;
          } else if (messageType === 'response') {
            this.localEntry.response_content = content;
          }
          this.$emit('content-changed', { messageType, content, viewType });
        }
      } catch (error) {
        console.error('Error changing content view:', error);
        this.$emit('error', 'Error changing content view');
      } finally {
        this.isLoading = false;
      }
    },

    async getFlowContent(flowId, messageType, contentView = 'auto') {
      try {
        const response = await axios.get(`/api/v1/mitmproxy/flows/${flowId}/${messageType}/content/${contentView}`, {
          params: { 
            device_id: this.deviceId,
            lines: 1000 
          },
          responseType: contentView === 'raw' ? 'arraybuffer' : 'text'
        });
        
        if (typeof response.data === 'string') {
          return response.data;
        } else if (response.data instanceof ArrayBuffer) {
          try {
            const decoder = new TextDecoder('utf-8');
            return decoder.decode(response.data);
          } catch (e) {
            return `[Binary data, size: ${response.data.byteLength} bytes]`;
          }
        } else {
          return JSON.stringify(response.data, null, 2);
        }
      } catch (error) {
        console.error('Error getting flow content:', error);
        if (error.response?.status === 404) {
          return 'Content unavailable (404)';
        } else if (error.response?.status === 400) {
          return 'Bad request (400)';
        } else {
          return `Loading error: ${error.message}`;
        }
      }
    },

    async downloadFlowContent(flowId, messageType) {
      try {
        const url = `/api/v1/mitmproxy/flows/${flowId}/${messageType}/content.data?device_id=${encodeURIComponent(this.deviceId)}`;
        const link = document.createElement('a');
        link.href = url;
        link.download = `${flowId}_${messageType}.data`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        this.$emit('success', `${messageType} content downloaded`);
      } catch (error) {
        console.error('Error downloading flow content:', error);
        this.$emit('error', 'Error downloading content');
      }
    }
  }
};
</script>

<style scoped>
.modal {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0,0,0,0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 2000;
}

.modal-content {
  background: white;
  border-radius: 8px;
  max-width: 800px;
  max-height: 80vh;
  width: 90%;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #dee2e6;
  background: #f8f9fa;
}

.modal-header h5 {
  margin: 0;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #6c757d;
  padding: 4px;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  max-height: calc(80vh - 80px);
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section h6 {
  margin: 0 0 10px 0;
  color: #333;
  font-weight: 600;
  border-bottom: 1px solid #dee2e6;
  padding-bottom: 5px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.section-header h6 {
  margin: 0;
  border-bottom: none;
  padding-bottom: 0;
}

.section-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.content-view-controls {
  display: flex;
  gap: 2px;
}

.content-view-controls .btn {
  padding: 4px 8px;
  font-size: 10px;
  min-width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.content-view-controls .btn i {
  font-size: 10px;
}

.badge {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  display: inline-block;
}

.badge-warning {
  background: #fff3cd;
  color: #856404;
  border: 1px solid #ffeaa7;
}

.badge-info {
  background: #d1ecf1;
  color: #0c5460;
  border: 1px solid #bee5eb;
}

.badge-success {
  background: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.badge-danger {
  background: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 10px;
}

.detail-item {
  display: flex;
  flex-direction: column;
}

.detail-item label {
  font-size: 12px;
  color: #6c757d;
  font-weight: 600;
  margin-bottom: 2px;
}

.detail-item span {
  color: #333;
  word-break: break-all;
}

.headers-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.header-item {
  display: flex;
  font-size: 13px;
}

.header-key {
  font-weight: 600;
  color: #495057;
  min-width: 150px;
  margin-right: 10px;
}

.header-value {
  color: #333;
  word-break: break-all;
}

.content-block {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  padding: 15px;
  font-size: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

.content-placeholder {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  padding: 20px;
  text-align: center;
  color: #6c757d;
  font-style: italic;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 60px;
}

.content-placeholder i {
  font-size: 16px;
  color: #adb5bd;
}

.content-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 20px;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  margin-bottom: 15px;
  color: #6c757d;
}

.content-loading .spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #f3f3f3;
  border-top: 2px solid #007bff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #007bff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: #007bff;
  color: white;
}

.btn-outline-secondary {
  background: transparent;
  color: #6c757d;
  border: 1px solid #6c757d;
}

.btn-xs {
  padding: 2px 6px;
  font-size: 11px;
}

@media (max-width: 768px) {
  .modal-content {
    width: 95%;
    margin: 10px;
  }
}
</style> 