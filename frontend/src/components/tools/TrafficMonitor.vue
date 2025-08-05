<template>
  <div class="traffic-monitor">
    <div class="traffic-monitor-header">
      <h3>Network Traffic Monitoring</h3>
      <div class="status-section">
        <div class="status-item">
          <span class="status-label">Proxy:</span>
          <span class="status-value" :class="statusClass">{{ proxyStatusText }}</span>
        </div>
        <div class="status-item" v-if="status.device_ip">
          <span class="status-label">Device IP:</span>
          <span class="status-value">{{ status.device_ip }}</span>
        </div>
        <div class="status-item" v-if="status.backend_ip">
          <span class="status-label">Backend IP:</span>
          <span class="status-value">{{ status.backend_ip }}</span>
        </div>
        <div class="status-item">
          <span class="status-label">Proxy Port:</span>
          <span class="status-value">{{ status.proxy_port || 8082 }}</span>
        </div>
      </div>
    </div>

    <div class="control-section">
      <div class="control-group">
        <button 
          @click="startProxy" 
          :disabled="status.proxy_running || isLoading"
          class="btn btn-primary"
        >
          <font-awesome-icon icon="play" /> Start Proxy
        </button>
        
        <button 
          @click="stopProxy" 
          :disabled="!status.proxy_running || isLoading"
          class="btn btn-danger"
        >
          <font-awesome-icon icon="stop" /> Stop Proxy
        </button>
        
        <button 
          @click="configureProxy" 
          :disabled="!status.proxy_running || isLoading"
          class="btn btn-warning"
        >
          <font-awesome-icon icon="cog" /> Configure on Device
        </button>
      </div>

      <div class="control-group">
        <button 
          @click="generateCertificate" 
          :disabled="isLoading"
          class="btn btn-info"
        >
          <font-awesome-icon icon="certificate" /> Generate Certificate
        </button>
        
        <button 
          @click="installCertificate" 
          :disabled="isLoading"
          class="btn btn-success"
        >
          <font-awesome-icon icon="download" /> Install Certificate
        </button>
        
        <button 
          @click="downloadCertificate" 
          :disabled="isLoading"
          class="btn btn-secondary"
        >
          <font-awesome-icon icon="file-download" /> Download Certificate
        </button>
        
        <button 
          @click="rebootDevice" 
          :disabled="isLoading"
          class="btn btn-info"
          title="Reboot device to apply certificates"
        >
          <font-awesome-icon icon="power-off" /> Reboot Device
        </button>
      </div>
    </div>

    <div class="traffic-section">
      <div class="traffic-header">
        <h4>Captured Traffic</h4>
        <div class="traffic-controls">
          <button 
            @click="refreshTraffic" 
            :disabled="isLoading"
            class="btn btn-sm btn-outline-primary"
          >
            <font-awesome-icon icon="sync" /> Refresh
          </button>
          

          
          <button 
            @click="clearTraffic" 
            :disabled="isLoading"
            class="btn btn-sm btn-outline-danger"
          >
            <font-awesome-icon icon="trash" /> Clear
          </button>
          
          <div class="dropdown">
            <button 
              class="btn btn-sm btn-outline-secondary dropdown-toggle" 
              @click="showExportMenu = !showExportMenu"
            >
              <font-awesome-icon icon="download" /> Export
            </button>
            <div class="dropdown-menu" v-show="showExportMenu">
              <a @click="exportTraffic('json')" class="dropdown-item">JSON</a>
              <a @click="exportTraffic('csv')" class="dropdown-item">CSV</a>
              <a @click="exportTraffic('har')" class="dropdown-item">HAR</a>
            </div>
          </div>
        </div>
      </div>

      <div class="traffic-stats" v-if="trafficData.length > 0">
        <div class="stat-item">
          <span class="stat-label">Total Requests:</span>
          <span class="stat-value">{{ trafficData.length }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Unique Hosts:</span>
          <span class="stat-value">{{ uniqueHosts }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">HTTPS/HTTP:</span>
          <span class="stat-value">{{ httpsCount }}/{{ httpCount }}</span>
        </div>
      </div>

      <div class="traffic-table-container">
        <table class="traffic-table" v-if="trafficData.length > 0">
          <thead>
            <tr>
              <th>Time</th>
              <th>Method</th>
              <th>Host</th>
              <th>Path</th>
              <th>Status</th>
              <th>Size</th>
              <th>Duration</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr 
              v-for="(entry, index) in paginatedTraffic" 
              :key="index"
              @click="selectEntry(entry)"
              :class="{ 'selected': selectedEntry === entry }"
            >
              <td>{{ formatTime(entry.timestamp) }}</td>
              <td>
                <span class="method-badge" :class="'method-' + entry.method.toLowerCase()">
                  {{ entry.method }}
                </span>
              </td>
              <td>{{ entry.host }}</td>
              <td class="path-cell" :title="entry.path">{{ truncatePath(entry.path) }}</td>
              <td>
                <span class="status-badge" :class="getStatusClass(entry.status_code)">
                  {{ entry.status_code }}
                </span>
              </td>
              <td>{{ formatSize(entry.request_size + entry.response_size) }}</td>
              <td>{{ formatDuration(entry.duration) }}</td>
              <td>
                <div class="action-buttons">
                  <button 
                    @click.stop="viewDetails(entry)" 
                    class="btn btn-xs btn-outline-info"
                    title="View details"
                  >
                    <font-awesome-icon icon="eye" />
                  </button>
                  <button 
                    v-if="entry.intercepted"
                    @click.stop="resumeFlow(entry.id)" 
                    class="btn btn-xs btn-outline-success"
                    title="Resume flow"
                  >
                    <font-awesome-icon icon="play" />
                  </button>
                  <button 
                    @click.stop="killFlow(entry.id)" 
                    class="btn btn-xs btn-outline-danger"
                    title="Stop flow"
                  >
                    <font-awesome-icon icon="times" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        
        <div v-else class="no-traffic">
          <font-awesome-icon icon="inbox" />
          <p>No traffic captured</p>
          <small>Start proxy and configure device to capture traffic</small>
        </div>
      </div>

      <div class="pagination" v-if="totalPages > 1">
        <button 
          @click="currentPage--" 
          :disabled="currentPage === 1"
          class="btn btn-sm btn-outline-secondary"
        >
          <font-awesome-icon icon="chevron-left" />
        </button>
        
        <span class="pagination-info">
          Page {{ currentPage }} of {{ totalPages }}
        </span>
        
        <button 
          @click="currentPage++" 
          :disabled="currentPage === totalPages"
          class="btn btn-sm btn-outline-secondary"
        >
          <font-awesome-icon icon="chevron-right" />
        </button>
      </div>
    </div>

    <!-- Security Report Section -->
    <div class="security-section" v-if="securityReport.issues && securityReport.issues.length > 0">
      <h4>Security Analysis</h4>
      
      <div class="security-stats">
        <div class="security-stat high">
          <span class="count">{{ securityReport.summary.high }}</span>
          <span class="label">High Risk</span>
        </div>
        <div class="security-stat medium">
          <span class="count">{{ securityReport.summary.medium }}</span>
          <span class="label">Medium Risk</span>
        </div>
        <div class="security-stat low">
          <span class="count">{{ securityReport.summary.low }}</span>
          <span class="label">Low Risk</span>
        </div>
      </div>

      <div class="security-issues">
        <div 
          v-for="(issue, index) in securityReport.issues" 
          :key="index"
          class="security-issue"
          :class="'severity-' + issue.severity"
        >
          <div class="issue-header">
            <span class="severity-badge" :class="'severity-' + issue.severity">
              {{ issue.severity.toUpperCase() }}
            </span>
            <span class="issue-type">{{ issue.type }}</span>
          </div>
          <div class="issue-description">{{ issue.description }}</div>
          <div class="issue-url">{{ issue.url }}</div>
          <div class="issue-evidence">{{ issue.evidence }}</div>
        </div>
      </div>
    </div>

    <!-- Traffic Details Modal -->
    <div class="modal" v-if="showDetailsModal" @click="closeModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h5>Request Details</h5>
          <button @click="closeModal" class="close-btn">
            <font-awesome-icon icon="times" />
          </button>
        </div>
        
        <div class="modal-body" v-if="selectedEntry">
          <!-- Content loading indicator -->
          <div class="content-loading" v-if="isLoading">
            <div class="spinner"></div>
            <span>Loading content...</span>
          </div>
          <div class="detail-section">
            <h6>Basic Information</h6>
            <div class="detail-grid">
              <div class="detail-item">
                <label>URL:</label>
                <span>{{ selectedEntry.url }}</span>
              </div>
              <div class="detail-item">
                <label>Method:</label>
                <span>{{ selectedEntry.method }}</span>
              </div>
              <div class="detail-item">
                <label>Status:</label>
                <span>{{ selectedEntry.status_code }}</span>
              </div>
              <div class="detail-item">
                <label>Time:</label>
                <span>{{ formatTime(selectedEntry.timestamp) }}</span>
              </div>
            </div>
          </div>

          <div class="detail-section">
            <h6>Request Headers</h6>
            <div class="headers-list">
              <div 
                v-for="(value, key) in selectedEntry.request_headers" 
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
                v-for="(value, key) in selectedEntry.response_headers" 
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
                <div class="content-view-controls" v-if="selectedEntry.id">
                  <button 
                    @click="changeContentView('request', 'auto')"
                    :class="['btn', 'btn-xs', selectedEntry.request_view === 'auto' ? 'btn-primary' : 'btn-outline-secondary']"
                    title="Auto mode"
                  >
                    <font-awesome-icon icon="magic" />
                  </button>
                  <button 
                    @click="changeContentView('request', 'text')"
                    :class="['btn', 'btn-xs', selectedEntry.request_view === 'text' ? 'btn-primary' : 'btn-outline-secondary']"
                    title="Text mode"
                  >
                    <font-awesome-icon icon="font" />
                  </button>
                  <button 
                    @click="changeContentView('request', 'hex')"
                    :class="['btn', 'btn-xs', selectedEntry.request_view === 'hex' ? 'btn-primary' : 'btn-outline-secondary']"
                    title="Hex mode"
                  >
                    <font-awesome-icon icon="code" />
                  </button>
                  <button 
                    @click="changeContentView('request', 'raw')"
                    :class="['btn', 'btn-xs', selectedEntry.request_view === 'raw' ? 'btn-primary' : 'btn-outline-secondary']"
                    title="Raw mode"
                  >
                    <font-awesome-icon icon="file-code" />
                  </button>
                </div>
                <button 
                  v-if="selectedEntry.id" 
                  @click="downloadFlowContent(selectedEntry.id, 'request')"
                  class="btn btn-xs btn-outline-secondary"
                  title="Download request content"
                >
                  <font-awesome-icon icon="download" />
                </button>
              </div>
            </div>
            <pre class="content-block" v-if="selectedEntry.request_content">{{ selectedEntry.request_content }}</pre>
            <div class="content-placeholder" v-else>
              <font-awesome-icon icon="info-circle" />
              <span>Request content unavailable or empty</span>
            </div>
          </div>

          <div class="detail-section">
            <div class="section-header">
              <h6>Response Content</h6>
              <div class="section-controls">
                <div class="content-view-controls" v-if="selectedEntry.id">
                  <button 
                    @click="changeContentView('response', 'auto')"
                    :class="['btn', 'btn-xs', selectedEntry.response_view === 'auto' ? 'btn-primary' : 'btn-outline-secondary']"
                    title="Auto mode"
                  >
                    <font-awesome-icon icon="magic" />
                  </button>
                  <button 
                    @click="changeContentView('response', 'text')"
                    :class="['btn', 'btn-xs', selectedEntry.response_view === 'text' ? 'btn-primary' : 'btn-outline-secondary']"
                    title="Text mode"
                  >
                    <font-awesome-icon icon="font" />
                  </button>
                  <button 
                    @click="changeContentView('response', 'hex')"
                    :class="['btn', 'btn-xs', selectedEntry.response_view === 'hex' ? 'btn-primary' : 'btn-outline-secondary']"
                    title="Hex mode"
                  >
                    <font-awesome-icon icon="code" />
                  </button>
                  <button 
                    @click="changeContentView('response', 'raw')"
                    :class="['btn', 'btn-xs', selectedEntry.response_view === 'raw' ? 'btn-primary' : 'btn-outline-secondary']"
                    title="Raw mode"
                  >
                    <font-awesome-icon icon="file-code" />
                  </button>
                </div>
                <button 
                  v-if="selectedEntry.id" 
                  @click="downloadFlowContent(selectedEntry.id, 'response')"
                  class="btn btn-xs btn-outline-secondary"
                  title="Download response content"
                >
                  <font-awesome-icon icon="download" />
                </button>
              </div>
            </div>
            <pre class="content-block" v-if="selectedEntry.response_content">{{ selectedEntry.response_content }}</pre>
            <div class="content-placeholder" v-else>
              <font-awesome-icon icon="info-circle" />
              <span>Response content unavailable or empty</span>
            </div>
          </div>

          <!-- Additional flow information -->
          <div class="detail-section" v-if="selectedEntry.detailed">
            <h6>Additional Information</h6>
            <div class="detail-grid">
              <div class="detail-item" v-if="selectedEntry.intercepted">
                <label>Intercepted:</label>
                <span class="badge badge-warning">Yes</span>
              </div>
              <div class="detail-item" v-if="selectedEntry.is_replay">
                <label>Replay:</label>
                <span class="badge badge-info">Yes</span>
              </div>
              <div class="detail-item" v-if="selectedEntry.modified">
                <label>Modified:</label>
                <span class="badge badge-warning">Yes</span>
              </div>
              <div class="detail-item" v-if="selectedEntry.marked">
                <label>Marked:</label>
                <span>{{ selectedEntry.marked }}</span>
              </div>
              <div class="detail-item" v-if="selectedEntry.comment">
                <label>Comment:</label>
                <span>{{ selectedEntry.comment }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading overlay -->
    <div class="loading-overlay" v-if="isLoading">
      <div class="spinner"></div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'TrafficMonitor',
  props: {
    deviceId: {
      type: String,
      required: true
    },
    websocket: {
      type: Object,
      default: null
    }
  },
  
  data() {
    return {
      isLoading: false,
      status: {
        proxy_running: false,
        cert_installed: false,
        su_available: false,
        device_ip: null,
        proxy_port: 8082,
        proxy_host: "0.0.0.0"
      },
      trafficData: [],
      securityReport: {
        issues: [],
        summary: { total: 0, high: 0, medium: 0, low: 0 }
      },
      selectedEntry: null,
      showDetailsModal: false,
      showExportMenu: false,
      currentPage: 1,
      itemsPerPage: 20,
      autoRefresh: true,
      refreshInterval: null,
      mitmproxyWebSocket: null
    }
  },

  computed: {
    proxyStatusText() {
      return this.status.proxy_running ? 'Running' : 'Stopped'
    },
    
    statusClass() {
      return this.status.proxy_running ? 'status-success' : 'status-error'
    },

    uniqueHosts() {
      const hosts = new Set(this.trafficData.map(entry => entry.host))
      return hosts.size
    },

    httpsCount() {
      return this.trafficData.filter(entry => entry.scheme === 'https').length
    },

    httpCount() {
      return this.trafficData.filter(entry => entry.scheme === 'http').length
    },

    totalPages() {
      return Math.ceil(this.trafficData.length / this.itemsPerPage)
    },

    paginatedTraffic() {
      const start = (this.currentPage - 1) * this.itemsPerPage
      const end = start + this.itemsPerPage
      return this.trafficData.slice(start, end)
    }
  },

  mounted() {
    this.checkStatus()
    this.openMitmproxyWebSocket()
    this.startAutoRefresh()
  },

  beforeUnmount() {
    this.closeMitmproxyWebSocket()
    this.stopAutoRefresh()
  },

  methods: {
    async checkStatus() {
      try {
        this.isLoading = true
        
        if (this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "get_state",
            device_id: this.deviceId
          }))
        } else {
          const response = await axios.get(`/api/v1/dynamic-testing/device/${encodeURIComponent(this.deviceId)}/mitmproxy/status`)
          this.status = response.data.data
        }
      } catch (error) {
        console.error('Error checking status:', error)
        this.$emit('error', 'Error getting proxy status')
      } finally {
        this.isLoading = false
      }
    },

    async startProxy() {
      try {
        this.isLoading = true
        
        if (this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "start_proxy",
            device_id: this.deviceId
          }))
        } else {
          const response = await axios.post(`/api/v1/dynamic-testing/device/${encodeURIComponent(this.deviceId)}/mitmproxy/start`)
          
          if (response.data.status === 'success') {
            this.status.proxy_running = true
            this.$emit('success', 'Proxy started successfully')
            await this.checkStatus()
          }
        }
      } catch (error) {
        console.error('Error starting proxy:', error)
        this.$emit('error', 'Error starting proxy: ' + (error.response?.data?.detail || error.message))
      } finally {
        this.isLoading = false
      }
    },

    async stopProxy() {
      try {
        this.isLoading = true
        
        if (this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "stop_proxy",
            device_id: this.deviceId
          }))
        } else {
          const response = await axios.post(`/api/v1/dynamic-testing/device/${encodeURIComponent(this.deviceId)}/mitmproxy/stop`)
          
          if (response.data.status === 'success') {
            this.status.proxy_running = false
            this.$emit('success', 'Proxy stopped successfully')
            await this.checkStatus()
          }
        }
      } catch (error) {
        console.error('Error stopping proxy:', error)
        this.$emit('error', 'Error stopping proxy: ' + (error.response?.data?.detail || error.message))
      } finally {
        this.isLoading = false
      }
    },

    async configureProxy() {
      try {
        this.isLoading = true
        
        if (this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "configure_proxy",
            device_id: this.deviceId
          }))
        } else {
          const response = await axios.post(`/api/v1/dynamic-testing/device/${encodeURIComponent(this.deviceId)}/mitmproxy/configure-proxy`)
          
          if (response.data.status === 'success') {
            this.$emit('success', 'Proxy configured on device')
          }
        }
      } catch (error) {
        console.error('Error configuring proxy:', error)
        this.$emit('error', 'Error configuring proxy: ' + (error.response?.data?.detail || error.message))
      } finally {
        this.isLoading = false
      }
    },

    async generateCertificate() {
      try {
        this.isLoading = true
        
        if (this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "generate_certificate",
            device_id: this.deviceId
          }))
        } else {
          const response = await axios.post(`/api/v1/dynamic-testing/device/${encodeURIComponent(this.deviceId)}/mitmproxy/generate-certificate`)
          
          if (response.data.status === 'success') {
            this.$emit('success', 'Certificate generated successfully')
          }
        }
      } catch (error) {
        console.error('Error generating certificate:', error)
        this.$emit('error', 'Error generating certificate: ' + (error.response?.data?.detail || error.message))
      } finally {
        this.isLoading = false
      }
    },

    async installCertificate() {
      try {
        this.isLoading = true
        
        if (this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "install_certificate",
            device_id: this.deviceId
          }))
        } else {
          const response = await axios.post(`/api/v1/dynamic-testing/device/${encodeURIComponent(this.deviceId)}/mitmproxy/install-certificate`)
          
          if (response.data.status === 'success') {
            this.status.cert_installed = true
            this.$emit('success', 'Certificate installed on device')
          }
        }
      } catch (error) {
        console.error('Error installing certificate:', error)
        this.$emit('error', 'Error installing certificate: ' + (error.response?.data?.detail || error.message))
      } finally {
        this.isLoading = false
      }
    },

    async downloadCertificate() {
      try {
        const url = `/api/v1/dynamic-testing/device/${this.deviceId}/mitmproxy/download-certificate`
        const link = document.createElement('a')
        link.href = url
        link.download = `mitmproxy-cert-${this.deviceId.replace(':', '_')}.pem`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        
        this.$emit('success', 'Certificate downloaded')
      } catch (error) {
        console.error('Error downloading certificate:', error)
        this.$emit('error', 'Error downloading certificate')
      }
    },

    async rebootDevice() {
      try {
        this.isLoading = true
        
        if (this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "reboot_device",
            device_id: this.deviceId
          }))
        } else {
          const response = await axios.post(`/api/v1/dynamic-testing/device/${encodeURIComponent(this.deviceId)}/mitmproxy/reboot-device`)
          
          if (response.data.status === 'success') {
            this.$emit('success', response.data.message)
            
            setTimeout(() => {
              this.checkStatus()
            }, 5000)
          }
        }
      } catch (error) {
        console.error('Error rebooting device:', error)
        this.$emit('error', 'Error rebooting device: ' + (error.response?.data?.detail || error.message))
      } finally {
        this.isLoading = false
      }
    },

    async refreshTraffic() {
      try {
        this.isLoading = true
        
        if (this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "get_flows",
            device_id: this.deviceId
          }))
        } else {
          try {
            const response = await axios.get(`/api/v1/mitmproxy/flows`, {
              params: {
                device_id: this.deviceId,
                detailed: true,
                limit: 200,
                offset: 0
              }
            })
            
            if (response.data && Array.isArray(response.data)) {
              this.trafficData = response.data.map(flow => this.convertFlowToTrafficEntry(flow))
            } else if (response.data.flows && Array.isArray(response.data.flows)) {
              this.trafficData = response.data.flows.map(flow => this.convertFlowToTrafficEntry(flow))
            } else {
              console.warn('Unexpected response format:', response.data)
              this.trafficData = []
            }
          } catch (error) {
            const fallbackResponse = await axios.get(`/api/v1/dynamic-testing/device/${this.deviceId}/mitmproxy/traffic?detailed=true`)
            if (fallbackResponse.data.status === 'success') {
              this.trafficData = fallbackResponse.data.data.traffic || []
            }
          }
        }
      } catch (error) {
        console.error('Error refreshing traffic:', error)
        this.$emit('error', 'Error refreshing traffic')
      } finally {
        this.isLoading = false
      }
    },

    async clearTraffic() {
      try {
        this.isLoading = true
        
        if (this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "clear_flows",
            device_id: this.deviceId
          }))
        } else {
          try {
            await axios.delete(`/api/v1/mitmproxy/flows`, {
              params: { device_id: this.deviceId }
            })
          } catch (error) {
            await axios.post(`/api/v1/dynamic-testing/device/${this.deviceId}/mitmproxy/clear-traffic`)
          }
        }
        
        this.trafficData = []
        this.securityReport = { issues: [], summary: { total: 0, high: 0, medium: 0, low: 0 } }
        this.$emit('success', 'Traffic cleared')
      } catch (error) {
        console.error('Error clearing traffic:', error)
        this.$emit('error', 'Error clearing traffic')
      } finally {
        this.isLoading = false
      }
    },

    async exportTraffic(format) {
      try {
        this.showExportMenu = false
        
        let response
        try {
          response = await axios.get(`/api/v1/mitmproxy/flows/dump`, {
            params: {
              device_id: this.deviceId,
              format: format
            }
          })
        } catch (error) {
          response = await axios.get(`/api/v1/dynamic-testing/device/${this.deviceId}/mitmproxy/export?format=${format}`)
        }
        
        let content, filename, mimeType
        
        if (format === 'json') {
          content = typeof response.data === 'string' ? response.data : JSON.stringify(response.data, null, 2)
          filename = `flows_${this.deviceId.replace(':', '_')}_${Date.now()}.json`
          mimeType = 'application/json'
        } else if (format === 'har') {
          content = typeof response.data === 'string' ? response.data : JSON.stringify(response.data, null, 2)
          filename = `flows_${this.deviceId.replace(':', '_')}_${Date.now()}.har`
          mimeType = 'application/json'
        } else {
          content = response.data
          filename = `flows_${this.deviceId.replace(':', '_')}_${Date.now()}.${format}`
          mimeType = format === 'csv' ? 'text/csv' : 'application/octet-stream'
        }
        
        const blob = new Blob([content], { type: mimeType })
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = filename
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
        
        this.$emit('success', `Traffic exported in ${format.toUpperCase()} format`)
      } catch (error) {
        console.error('Error exporting traffic:', error)
        this.$emit('error', 'Error exporting traffic')
      }
    },

    selectEntry(entry) {
      this.selectedEntry = entry
    },

    async viewDetails(entry) {
      try {
        this.isLoading = true
        
        if (entry.id) {
          const response = await axios.get(`/api/v1/mitmproxy/flows/${entry.id}`, {
            params: { device_id: this.deviceId }
          })
          
          if (response.data) {
            this.selectedEntry = this.convertFlowToTrafficEntry(response.data)
            this.selectedEntry.detailed = true
            
            this.selectedEntry.request_view = 'auto'
            this.selectedEntry.response_view = 'auto'
            
            const [requestContent, responseContent] = await Promise.allSettled([
              this.getFlowContent(entry.id, 'request', 'auto'),
              this.getFlowContent(entry.id, 'response', 'auto')
            ])
            
            if (requestContent.status === 'fulfilled' && requestContent.value) {
              this.selectedEntry.request_content = requestContent.value
            } else {
              console.warn('Could not load request content:', requestContent.reason)
              this.selectedEntry.request_content = 'Request content unavailable'
            }
            
            if (responseContent.status === 'fulfilled' && responseContent.value) {
              this.selectedEntry.response_content = responseContent.value
            } else {
              console.warn('Could not load response content:', responseContent.reason)
              this.selectedEntry.response_content = 'Response content unavailable'
            }
          } else {
            this.selectedEntry = entry
          }
        } else {
          this.selectedEntry = entry
        }
        
        this.showDetailsModal = true
      } catch (error) {
        console.error('Error getting flow details:', error)
        this.selectedEntry = entry
        this.showDetailsModal = true
      } finally {
        this.isLoading = false
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
        })
        
        if (typeof response.data === 'string') {
          return response.data
        } else if (response.data instanceof ArrayBuffer) {
          try {
            const decoder = new TextDecoder('utf-8')
            return decoder.decode(response.data)
          } catch (e) {
            return `[Binary data, size: ${response.data.byteLength} bytes]`
          }
        } else {
          return JSON.stringify(response.data, null, 2)
        }
      } catch (error) {
        console.error('Error getting flow content:', error)
        if (error.response?.status === 404) {
          return 'Content unavailable (404)'
        } else if (error.response?.status === 400) {
          return 'Bad request (400)'
        } else {
          return `Loading error: ${error.message}`
        }
      }
    },

    async downloadFlowContent(flowId, messageType) {
      try {
        const url = `/api/v1/mitmproxy/flows/${flowId}/${messageType}/content.data?device_id=${encodeURIComponent(this.deviceId)}`
        const link = document.createElement('a')
        link.href = url
        link.download = `${flowId}_${messageType}.data`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        
        this.$emit('success', `${messageType} content downloaded`)
      } catch (error) {
        console.error('Error downloading flow content:', error)
        this.$emit('error', 'Error downloading content')
      }
    },

    async resumeFlow(flowId) {
      try {
        if (this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "resume_flow",
            device_id: this.deviceId,
            flow_id: flowId
          }))
        } else {
          const response = await axios.post(`/api/v1/mitmproxy/flows/${flowId}/resume`, {
            device_id: this.deviceId
          })
          
          if (response.data.status === 'success') {
            this.$emit('success', 'Flow resumed')
            const index = this.trafficData.findIndex(entry => entry.id === flowId)
            if (index !== -1) {
              this.trafficData[index].intercepted = false
            }
          }
        }
      } catch (error) {
        console.error('Error resuming flow:', error)
        this.$emit('error', 'Error resuming flow: ' + (error.response?.data?.detail || error.message))
      }
    },

    async killFlow(flowId) {
      try {
        if (this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "kill_flow",
            device_id: this.deviceId,
            flow_id: flowId
          }))
        } else {
          const response = await axios.post(`/api/v1/mitmproxy/flows/${flowId}/kill`, {
            device_id: this.deviceId
          })
          
          if (response.data.status === 'success') {
            this.$emit('success', 'Flow stopped')
            const index = this.trafficData.findIndex(entry => entry.id === flowId)
            if (index !== -1) {
              this.trafficData.splice(index, 1)
            }
          }
        }
      } catch (error) {
        console.error('Error killing flow:', error)
        this.$emit('error', 'Error stopping flow: ' + (error.response?.data?.detail || error.message))
      }
    },

    async changeContentView(messageType, viewType) {
      if (!this.selectedEntry || !this.selectedEntry.id) {
        return
      }

      try {
        this.isLoading = true
        
        if (messageType === 'request') {
          this.selectedEntry.request_view = viewType
        } else if (messageType === 'response') {
          this.selectedEntry.response_view = viewType
        }
        
        const content = await this.getFlowContent(this.selectedEntry.id, messageType, viewType)
        
        if (content) {
          if (messageType === 'request') {
            this.selectedEntry.request_content = content
          } else if (messageType === 'response') {
            this.selectedEntry.response_content = content
          }
        }
      } catch (error) {
        console.error('Error changing content view:', error)
        this.$emit('error', 'Error changing content view')
      } finally {
        this.isLoading = false
      }
    },

    closeModal() {
      this.showDetailsModal = false
    },

    setupWebSocketHandlers() {
      if (this.websocket) {
        this.websocket.addEventListener('message', (event) => {
          try {
            const data = JSON.parse(event.data)
            if (data.type === 'mitmproxy') {
              this.handleWebSocketMessage(data)
            }
          } catch (error) {
            console.error('Error parsing websocket message:', error)
          }
        })
      }
    },

    handleWebSocketMessage(data) {
      console.log('Received mitmproxy message:', data)
      

      switch (data.action) {
        case 'ready':
          this.status = {
            proxy_running: false,
            cert_installed: data.cert_installed,
            su_available: data.su_available,
            device_ip: data.device_ip,
            proxy_port: data.proxy_port,
            proxy_host: data.proxy_host
          }
          break
          
        case 'state':
          if (data.data) {
            this.status = {
              proxy_running: data.data.is_running || false,
              cert_installed: data.data.cert_installed || false,
              su_available: data.data.su_available || false,
              device_ip: data.data.device_ip,
              proxy_port: data.data.proxy_port || 8082,
              proxy_host: data.data.proxy_host || "0.0.0.0",
              backend_ip: data.data.backend_ip
            }
          }
          break
          
        case 'flows':
          if (data.data && Array.isArray(data.data)) {
            this.trafficData = data.data.map(flow => this.convertFlowToTrafficEntry(flow))
          }
          break
          
        case 'clear_flows':
          if (data.success) {
            this.trafficData = []
            this.securityReport = { issues: [], summary: { total: 0, high: 0, medium: 0, low: 0 } }
            this.$emit('success', 'Traffic cleared')
          }
          break
          
        case 'proxy_start_result':
          this.status.proxy_running = data.success
          if (data.success) {
            this.$emit('success', 'Proxy started successfully')
            this.startAutoRefresh()
          } else {
            this.$emit('error', 'Error starting proxy')
          }
          break
          
        case 'proxy_stop_result':
          this.status.proxy_running = !data.success
          if (!this.status.proxy_running) {
            this.$emit('success', 'Proxy stopped successfully')
            this.stopAutoRefresh()
          } else {
            this.$emit('error', 'Error stopping proxy')
          }
          break
          
        case 'certificate_generated':
          if (data.success) {
            this.$emit('success', 'Certificate generated successfully')
          } else {
            this.$emit('error', 'Error generating certificate')
          }
          break
          
        case 'certificate_installed':
          this.status.cert_installed = data.success
          if (data.success) {
            this.$emit('success', 'Certificate installed on device')
          } else {
            this.$emit('error', 'Error installing certificate')
          }
          break
          
        case 'certificate_installed_reboot_needed':
          this.status.cert_installed = true
          this.$emit('info', data.message + ' Device reboot recommended.')
          break
          
        case 'certificate_warning':
          this.$emit('warning', data.message)
          break
          
        case 'certificate_error':
          this.$emit('error', data.message)
          break
          
        case 'proxy_configured':
          if (data.success) {
            this.$emit('success', 'Proxy configured on device')
          } else {
            this.$emit('error', 'Error configuring proxy')
          }
          break
          
        case 'proxy_port_updated':
          if (data.proxy_port) {
            this.status.proxy_port = data.proxy_port
          }
          if (data.backend_ip) {
            this.status.backend_ip = data.backend_ip
          }
          this.$emit('success', `Proxy configured: ${data.proxy_setting}`)
          break
          
        case 'device_rebooted':
          if (data.success) {
            this.$emit('success', data.message)
            setTimeout(() => {
              this.checkStatus()
            }, 3000)
          } else {
            this.$emit('error', data.message)
          }
          break
          
        case 'flow_resumed':
          if (data.success) {
            this.$emit('success', 'Flow resumed')
            const index = this.trafficData.findIndex(entry => entry.id === data.flow_id)
            if (index !== -1) {
              this.trafficData[index].intercepted = false
            }
          } else {
            this.$emit('error', 'Error resuming flow')
          }
          break
          
        case 'flow_killed':
          if (data.success) {
            this.$emit('success', 'Flow stopped')
            const index = this.trafficData.findIndex(entry => entry.id === data.flow_id)
            if (index !== -1) {
              this.trafficData.splice(index, 1)
            }
          } else {
            this.$emit('error', 'Error stopping flow')
          }
          break
          
        case 'flow_add':
        case 'flow_created': 
          if (data.flow && data.device_id === this.deviceId) {
            const flowSummary = this.convertFlowToTrafficEntry(data.flow)
            this.trafficData.unshift(flowSummary) 
            
            if (this.trafficData.length > 1000) {
              this.trafficData = this.trafficData.slice(0, 1000)
            }
          }
          break
          
        case 'flow_update':
        case 'flow_updated': 
          if (data.flow && data.device_id === this.deviceId) {
            const index = this.trafficData.findIndex(entry => entry.id === data.flow.id)
            if (index !== -1) {
              const updatedEntry = this.convertFlowToTrafficEntry(data.flow)
              this.trafficData.splice(index, 1, updatedEntry)
            } else {
              const flowSummary = this.convertFlowToTrafficEntry(data.flow)
              this.trafficData.unshift(flowSummary)
            }
          }
          break
          
        case 'flow_remove':
        case 'flow_deleted':
          if (data.flow && data.device_id === this.deviceId) {
            const index = this.trafficData.findIndex(entry => entry.id === data.flow.id)
            if (index !== -1) {
              this.trafficData.splice(index, 1)
              console.log(`Removed flow: ${data.flow.id}`)
            }
          }
          break
          
        case 'error':
          this.$emit('error', data.message || 'Unknown error')
          break
          
        default:
          console.log('Unknown mitmproxy action:', data.action)
      }
    },



    convertFlowToTrafficEntry(flow) {
      const request = flow.request || {}
      const response = flow.response || {}
      
      let duration = 0
      if (request.timestamp_start && request.timestamp_end) {
        duration = request.timestamp_end - request.timestamp_start
      }
      
              return {
          id: flow.id,
          timestamp: flow.timestamp_created || Date.now() / 1000,
          method: request.method || 'UNKNOWN',
          url: `${request.scheme || 'http'}://${request.host || ''}${request.path || ''}`,
          host: request.host || '',
          path: request.path || '',
          status_code: response.status_code || 0,
          request_size: request.contentLength || 0,
          response_size: response.contentLength || 0,
          duration: duration,
          scheme: request.scheme || 'http',
          port: request.port || 80,
          request_headers: Object.fromEntries(request.headers || []),
          response_headers: Object.fromEntries(response.headers || []),
          request_content: '', 
          response_content: '', 
          request_view: 'auto', 
          response_view: 'auto', 
          intercepted: flow.intercepted || false,
          is_replay: flow.is_replay || false,
          modified: flow.modified || false,
          marked: flow.marked || '',
          comment: flow.comment || '',
          type: flow.type || 'http',
          client_conn: flow.client_conn || null,
          server_conn: flow.server_conn || null,
          error: flow.error || null
        }
    },

    startAutoRefresh() {
      this.stopAutoRefresh()
      
      this.refreshInterval = setInterval(() => {
        if (this.status.proxy_running && this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "get_flows",
            device_id: this.deviceId
          }))
        }
      }, 5000) 
      
      this.autoRefresh = true
    },

    stopAutoRefresh() {
      if (this.refreshInterval) {
        clearInterval(this.refreshInterval)
        this.refreshInterval = null
      }
      this.autoRefresh = false
    },

    formatTime(timestamp) {
      return new Date(timestamp * 1000).toLocaleString('ru-RU')
    },

    formatSize(bytes) {
      if (bytes === 0) return '0 B'
      const k = 1024
      const sizes = ['B', 'KB', 'MB', 'GB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
    },

    formatDuration(duration) {
      if (duration < 1) {
        return Math.round(duration * 1000) + 'ms'
      }
      return duration.toFixed(2) + 's'
    },

    truncatePath(path) {
      return path.length > 50 ? path.substring(0, 50) + '...' : path
    },

    getStatusClass(statusCode) {
      if (statusCode >= 200 && statusCode < 300) return 'status-success'
      if (statusCode >= 300 && statusCode < 400) return 'status-warning'
      if (statusCode >= 400 && statusCode < 500) return 'status-error'
      if (statusCode >= 500) return 'status-critical'
      return 'status-unknown'
    },

    openMitmproxyWebSocket() {
      try {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const port = window.location.port || (window.location.protocol === 'https:' ? '443' : '80')
        const mitmproxyWsUrl = `${wsProtocol}//${window.location.hostname}:${port}/api/v1/dynamic-testing/ws/${encodeURIComponent(this.deviceId)}?action=mitmproxy`
        
        if (this.mitmproxyWebSocket) {
          this.mitmproxyWebSocket.close()
          this.mitmproxyWebSocket = null
        }
        
        this.mitmproxyWebSocket = new WebSocket(mitmproxyWsUrl)
        
        this.mitmproxyWebSocket.addEventListener('open', () => {
          console.log('Mitmproxy WebSocket connected')
          
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: 'mitmproxy',
            action: 'get_state',
            device_id: this.deviceId
          }))
        })
        
        this.mitmproxyWebSocket.addEventListener('message', (event) => {
          try {
            const message = JSON.parse(event.data)
            if (message.type === 'mitmproxy') {
              this.handleWebSocketMessage(message)
            }
          } catch (e) {
            console.error('Error parsing mitmproxy message:', e)
          }
        })
        
        this.mitmproxyWebSocket.addEventListener('close', (event) => {
          console.log('Mitmproxy WebSocket closed:', event.code, event.reason)
          
          if (event.code !== 1000) {
            setTimeout(() => {
              this.openMitmproxyWebSocket()
            }, 3000)
          }
        })
        
        this.mitmproxyWebSocket.addEventListener('error', (error) => {
          console.error('Mitmproxy WebSocket error:', error)
        })
        
      } catch (error) {
        console.error('Error opening mitmproxy WebSocket:', error)
      }
    },

    closeMitmproxyWebSocket() {
      if (this.mitmproxyWebSocket) {
        this.mitmproxyWebSocket.close()
        this.mitmproxyWebSocket = null
      }
    },


  }
}
</script>

<style scoped>
.traffic-monitor {
  max-width: 100%;
  background: #f8f9fa;
  border-radius: 8px;
  padding: 20px;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.traffic-monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 2px solid #e9ecef;
}

.traffic-monitor-header h3 {
  margin: 0;
  color: #333;
  font-weight: 600;
}

.status-section {
  display: flex;
  gap: 20px;
}

.status-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.status-label {
  font-size: 12px;
  color: #6c757d;
  margin-bottom: 4px;
}

.status-value {
  font-weight: 600;
  font-size: 14px;
}

.status-success {
  color: #28a745;
}

.status-error {
  color: #dc3545;
}

.control-section {
  margin-bottom: 25px;
}

.control-group {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
  flex-wrap: wrap;
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

.btn-danger {
  background: #dc3545;
  color: white;
}

.btn-warning {
  background: #ffc107;
  color: #212529;
}

.btn-info {
  background: #17a2b8;
  color: white;
}

.btn-success {
  background: #28a745;
  color: white;
}

.btn-secondary {
  background: #6c757d;
  color: white;
}

.btn-outline-primary {
  background: transparent;
  color: #007bff;
  border: 1px solid #007bff;
}

.btn-outline-danger {
  background: transparent;
  color: #dc3545;
  border: 1px solid #dc3545;
}

.btn-outline-secondary {
  background: transparent;
  color: #6c757d;
  border: 1px solid #6c757d;
}

.btn-outline-info {
  background: transparent;
  color: #17a2b8;
  border: 1px solid #17a2b8;
}

.btn-info {
  background: #17a2b8;
  color: white;
}

.btn-info:hover:not(:disabled) {
  background: #138496;
}

.btn-sm {
  padding: 4px 8px;
  font-size: 12px;
}

.btn-xs {
  padding: 2px 6px;
  font-size: 11px;
}

.traffic-section {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.traffic-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.traffic-header h4 {
  margin: 0;
  color: #333;
}

.traffic-controls {
  display: flex;
  gap: 10px;
  align-items: center;
}

.dropdown {
  position: relative;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  box-shadow: 0 4px 8px rgba(0,0,0,0.15);
  z-index: 1000;
  min-width: 120px;
}

.dropdown-item {
  display: block;
  padding: 8px 12px;
  color: #333;
  text-decoration: none;
  cursor: pointer;
}

.dropdown-item:hover {
  background: #f8f9fa;
}

.traffic-stats {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 6px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-label {
  font-size: 12px;
  color: #6c757d;
  margin-bottom: 4px;
}

.stat-value {
  font-weight: 600;
  font-size: 16px;
  color: #333;
}

.traffic-table-container {
  overflow-x: auto;
  margin-bottom: 20px;
}

.traffic-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.traffic-table th,
.traffic-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid #dee2e6;
}

.traffic-table th {
  background: #f8f9fa;
  font-weight: 600;
  color: #495057;
  position: sticky;
  top: 0;
}

.traffic-table tbody tr {
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.traffic-table tbody tr:hover {
  background: #f8f9fa;
}

.traffic-table tbody tr.selected {
  background: #e3f2fd;
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

.path-cell {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.no-traffic {
  text-align: center;
  padding: 40px 20px;
  color: #6c757d;
}

.no-traffic i {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 15px;
}

.pagination-info {
  font-size: 14px;
  color: #6c757d;
}

.security-section {
  background: white;
  border-radius: 8px;
  padding: 20px;
  margin-top: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.security-section h4 {
  margin: 0 0 20px 0;
  color: #333;
}

.security-stats {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
}

.security-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 15px;
  border-radius: 6px;
  min-width: 80px;
}

.security-stat.high {
  background: #f8d7da;
  color: #721c24;
}

.security-stat.medium {
  background: #fff3cd;
  color: #856404;
}

.security-stat.low {
  background: #d4edda;
  color: #155724;
}

.security-stat .count {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 4px;
}

.security-stat .label {
  font-size: 12px;
  font-weight: 500;
}

.security-issues {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.security-issue {
  padding: 15px;
  border-radius: 6px;
  border-left: 4px solid;
}

.security-issue.severity-high {
  background: #f8d7da;
  border-left-color: #dc3545;
}

.security-issue.severity-medium {
  background: #fff3cd;
  border-left-color: #ffc107;
}

.security-issue.severity-low {
  background: #d4edda;
  border-left-color: #28a745;
}

.issue-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.severity-badge {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 700;
}

.severity-badge.severity-high {
  background: #dc3545;
  color: white;
}

.severity-badge.severity-medium {
  background: #ffc107;
  color: #212529;
}

.severity-badge.severity-low {
  background: #28a745;
  color: white;
}

.issue-type {
  font-weight: 600;
  color: #333;
}

.issue-description {
  margin-bottom: 6px;
  color: #555;
}

.issue-url {
  font-size: 12px;
  color: #007bff;
  margin-bottom: 4px;
  word-break: break-all;
}

.issue-evidence {
  font-size: 11px;
  color: #6c757d;
  font-style: italic;
}

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

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(255,255,255,0.8);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
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

.action-buttons {
  display: flex;
  gap: 4px;
  align-items: center;
}

.action-buttons .btn {
  padding: 2px 6px;
  font-size: 10px;
  min-width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.action-buttons .btn i {
  font-size: 10px;
}

@media (max-width: 768px) {
  .traffic-monitor-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 15px;
  }
  
  .status-section {
    flex-direction: column;
    gap: 10px;
  }
  
  .control-group {
    flex-direction: column;
  }
  
  .traffic-controls {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  
  .security-stats {
    flex-direction: column;
    gap: 10px;
  }
  
  .modal-content {
    width: 95%;
    margin: 10px;
  }
}
</style>
