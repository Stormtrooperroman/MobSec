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
              <span class="detail-key">URL: </span>
              <span class="detail-value">{{ localEntry.url }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-key">Method: </span>
              <span class="method-badge detail-value" :class="'method-' + localEntry.method.toLowerCase()">
                {{ localEntry.method }}
              </span>
            </div>
            <div class="detail-item">
              <span class="detail-key">Status:</span>
              <span class="status-badge detail-value" :class="getStatusClass(localEntry.status_code)">
                {{ localEntry.status_code }}
              </span>
            </div>
            <div class="detail-item">
              <span class="detail-key">Time:</span>
              <span class="detail-value">{{ formatTime(localEntry.timestamp) }}</span>
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
          <pre class="content-block" v-if="localEntry.request_content !== null && localEntry.request_content !== undefined">{{ localEntry.request_content || '(empty body)' }}</pre>
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
          <pre class="content-block" v-if="localEntry.response_content !== null && localEntry.response_content !== undefined">{{ localEntry.response_content || '(empty body)' }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'TrafficDetailsModal',
  props: {
    show: { type: Boolean, default: false },
    entry: { type: Object, default: null },
    deviceId: { type: String, required: true }
  },
  emits: ['close', 'content-changed', 'success', 'error'],
  data() {
    return {
      localEntry: null,
      requestSourceContent: '',
      responseSourceContent: '',
      requestEncoding: 'utf-8',
      responseEncoding: 'utf-8'
    }
  },
  watch: {
    show(newValue) {
      if (newValue && this.entry) this.setEntry(this.entry)
    },
    entry: {
      handler(newValue) {
        if (newValue) this.setEntry(newValue)
      },
      immediate: true,
      deep: true
    }
  },
  methods: {
    setEntry(entry) {
      this.localEntry = { ...entry }
      this.requestSourceContent = structuredClone(entry.request_content) || ''
      this.responseSourceContent = structuredClone(entry.response_content) || ''
      this.requestEncoding = entry.request_content_encoding || 'utf-8'
      this.responseEncoding = entry.response_content_encoding || 'utf-8'
    },
    closeModal() {
      this.$emit('close')
    },
    getStatusClass(statusCode) {
      if (statusCode >= 200 && statusCode < 300) return 'status-success'
      if (statusCode >= 300 && statusCode < 400) return 'status-warning'
      if (statusCode >= 400 && statusCode < 500) return 'status-error'
      if (statusCode >= 500) return 'status-critical'
      return 'status-unknown'
    },
    async loadContent() {
      // Flow bodies arrive with get_flows/flow_add/flow_update WebSocket messages.
      return Promise.resolve()
    },
    formatTime(timestamp) {
      return new Date(timestamp * 1000).toLocaleString('ru-RU')
    },
    base64ToBytes(base64Content) {
      const binary = atob(base64Content || '')
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i)
      }
      return bytes
    },
    contentToBytes(content, encoding) {
      if (encoding === 'base64') {
        return this.base64ToBytes(content)
      }
      return new TextEncoder().encode(content || '')
    },
    formatContent(content, encoding, viewType) {
      if (content === null || content === undefined || content === '') {
        return content
      }
      if (viewType === 'hex') {
        const bytes = this.contentToBytes(content, encoding)
        return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join(' ')
      }
      if (viewType === 'raw') {
        return content
      }
 
      if (encoding === 'base64') {
        const byteLength = this.base64ToBytes(content).length
        return `[Binary content — ${byteLength} bytes, not valid UTF-8. Switch to Hex mode or use Download to inspect the raw bytes.]`
      }
      return content
    },
    changeContentView(messageType, viewType, emit = true) {
      if (!this.localEntry) return
      const sourceContent =
        messageType === 'request'
          ? this.requestSourceContent
          : this.responseSourceContent
      const encoding =
        messageType === 'request'
          ? this.requestEncoding
          : this.responseEncoding
      this.localEntry[`${messageType}_view`] = viewType
      this.localEntry[`${messageType}_content`] =
        this.formatContent(sourceContent, encoding, viewType)
      if (emit) {
        this.$emit('content-changed', {
          messageType,
          viewType,
          content: this.localEntry[`${messageType}_content`]
        })
      }
    },
    downloadFlowContent(flowId, messageType) {
      if (!this.localEntry) return
      const rawContent = messageType === 'request'
        ? this.rawRequestContent
        : this.rawResponseContent
      const encoding = messageType === 'request'
        ? this.rawRequestEncoding
        : this.rawResponseEncoding
      const bytes = this.contentToBytes(rawContent, encoding)
      const blob = new Blob([bytes], { type: 'application/octet-stream' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${flowId}_${messageType}.data`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      this.$emit('success', `${messageType} content downloaded`)
    }
  }
}
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
  max-width: 80vw;
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
  gap: 10px;
}

.detail-item {
  display: flex;
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

.detail-key{
  font-weight: 600;
  color: #495057;
  min-width: 150px;
  margin-right: 10px;
}

.detail-value {
  color: #333;
  word-break: break-all;
}

.method-badge {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.method-get {
  background: #d4edda;
  color: #155724;
}

.method-post {
  background: #fff3cd;
  color: #856404;
}

.method-put {
  background: #d1ecf1;
  color: #0c5460;
}

.method-delete {
  background: #f8d7da;
  color: #721c24;
}

.status-badge {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
}

.status-success {
  background: #d4edda;
  color: #155724;
}

.status-warning {
  background: #fff3cd;
  color: #856404;
}

.status-error {
  background: #f8d7da;
  color: #721c24;
}

.status-critical {
  background: #721c24;
  color: white;
}

.status-unknown {
  background: #e2e3e5;
  color: #383d41;
}

</style>