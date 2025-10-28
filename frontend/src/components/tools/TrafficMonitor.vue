<template>
  <div class="traffic-monitor">
    <div class="traffic-monitor-header">
      <span>
        Network Traffic Monitoring
        <span class="user-info">
          [{{ status.proxy_running ? 'Active' : 'Inactive' }}]
        </span>
      </span>
    </div>
    
    <div class="traffic-monitor-path">
      <div class="current-path">
        <span class="path-label">Proxy Status:</span>
        <span class="path-value" :class="statusClass">{{ proxyStatusText }}</span>
      </div>
      <div class="current-path" v-if="status.device_ip">
        <span class="path-label">Device IP:</span>
        <span class="path-value">{{ status.device_ip }}</span>
      </div>
      <div class="current-path" v-if="status.backend_ip">
        <span class="path-label">Backend IP:</span>
        <span class="path-value">{{ status.backend_ip }}</span>
      </div>
      <div class="current-path">
        <span class="path-label">Proxy Port:</span>
        <span class="path-value">{{ status.proxy_port || 8082 }}</span>
      </div>
    </div>

    <div class="traffic-monitor-toolbar">
      <button 
        @click="startProxy" 
        v-if="!status.proxy_running"
        :disabled="isLoading"
        class="toolbar-btn"
      >
        <font-awesome-icon icon="play" /> Start Proxy
      </button>
      
      <button 
        @click="stopProxy" 
        v-if="status.proxy_running"
        :disabled="isLoading"
        class="toolbar-btn"
      >
        <font-awesome-icon icon="stop" /> Stop Proxy
      </button>
      
      <button 
        @click="configureProxy" 
        v-if="!status.proxy_configured"
        :disabled="!status.proxy_running || isLoading"
        class="toolbar-btn"
      >
        <font-awesome-icon icon="cog" /> Configure on Device
      </button>
      
      <button 
        @click="disableProxy" 
        v-if="status.proxy_configured"
        :disabled="isLoading"
        class="toolbar-btn"
      >
        <font-awesome-icon icon="unlink" /> Disable Proxy
      </button>
      
      <button 
        @click="generateCertificate" 
        :disabled="isLoading"
        class="toolbar-btn"
      >
        <font-awesome-icon icon="certificate" /> Generate Certificate
      </button>
      
      <button 
        @click="installCertificate" 
        :disabled="isLoading"
        class="toolbar-btn"
      >
        <font-awesome-icon icon="download" /> Install Certificate
      </button>
      
      <button 
        @click="downloadCertificate" 
        :disabled="isLoading"
        class="toolbar-btn"
      >
        <font-awesome-icon icon="file-download" /> Download Certificate
      </button>
      
      <button 
        @click="rebootDevice" 
        :disabled="isLoading"
        class="toolbar-btn"
        title="Reboot device to apply certificates"
      >
        <font-awesome-icon icon="power-off" /> Reboot Device
      </button>
    </div>

    <div class="traffic-monitor-content">
      <div class="traffic-header">
        <h4>Captured Traffic</h4>
        <div class="traffic-controls">
          <button 
            @click="refreshTraffic" 
            :disabled="isLoading"
            class="control-btn"
          >
            <font-awesome-icon icon="sync" /> Refresh
          </button>
          
          <button 
            @click="clearTraffic" 
            :disabled="isLoading"
            class="control-btn"
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

      <div class="traffic-stats">
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
        <table class="traffic-table">
          <thead>
            <tr>
              <th class="sortable-header" @click="toggleSort('timestamp')">
                <div class="header-content">
                  <span>Time</span>
                  <span class="sort-indicator" :class="getSortClass('timestamp')">
                    <font-awesome-icon icon="sort" />
                  </span>
                </div>
              </th>
              <th class="sortable-header filterable-header" @click="toggleMethodFilter">
                <div class="header-content">
                  <span>Method</span>
                  <span class="filter-indicator" :class="{ 'active': filters.method }">
                    <font-awesome-icon icon="filter" />
                  </span>
                </div>
                <div class="header-dropdown" v-show="showMethodDropdown">
                  <div class="dropdown-content">
                    <label v-for="method in availableMethods" :key="method" class="dropdown-item">
                      <input 
                        type="checkbox" 
                        :value="method" 
                        :checked="selectedMethods.includes(method)"
                        @click.stop="toggleMethod(method)"
                      />
                      <span>{{ method }}</span>
                    </label>
                    <div class="dropdown-actions">
                      <button @click="clearMethodFilter" class="clear-btn">Clear</button>
                    </div>
                  </div>
                </div>
              </th>
              <th class="sortable-header filterable-header" @click="toggleHostFilter">
                <div class="header-content">
                  <span>Host</span>
                  <div class="header-controls">
                    <span class="sort-indicator" :class="getSortClass('host')" @click.stop="toggleSort('host')">
                      <font-awesome-icon icon="sort" />
                    </span>
                    <span class="filter-indicator" :class="{ 'active': filters.host }">
                      <font-awesome-icon icon="filter" />
                    </span>
                  </div>
                </div>
                <div class="header-dropdown" v-show="showHostDropdown">
                  <div class="dropdown-content">
                    <div class="host-filter-input">
                      <input 
                        v-model="filters.host" 
                        type="text" 
                        placeholder="Enter hostname..."
                        class="filter-input"
                        @input="applyFilters"
                        @click.stop
                      />
                    </div>
                    <div class="dropdown-actions">
                      <button @click="clearHostFilter" class="clear-btn">Clear</button>
                    </div>
                  </div>
                </div>
              </th>
              <th>Path</th>
              <th class="sortable-header filterable-header" @click="toggleStatusFilter">
                <div class="header-content">
                  <span>Status</span>
                  <span class="filter-indicator" :class="{ 'active': filters.status }">
                    <font-awesome-icon icon="filter" />
                  </span>
                </div>
                <div class="header-dropdown" v-show="showStatusDropdown">
                  <div class="dropdown-content">
                    <label v-for="status in availableStatuses" :key="status.value" class="dropdown-item">
                      <input 
                        type="checkbox" 
                        :value="status.value" 
                        :checked="selectedStatuses.includes(status.value)"
                        @click.stop="toggleStatus(status.value)"
                      />
                      <span>{{ status.label }}</span>
                    </label>
                    <div class="dropdown-actions">
                      <button @click="clearStatusFilter" class="clear-btn">Clear</button>
                    </div>
                  </div>
                </div>
              </th>
              <th>Size</th>
              <th class="sortable-header" @click="toggleSort('duration')">
                <div class="header-content">
                  <span>Duration</span>
                  <span class="sort-indicator" :class="getSortClass('duration')">
                    <font-awesome-icon icon="sort" />
                  </span>
                </div>
              </th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody v-if="filteredTraffic.length > 0">
            <tr 
              v-for="(entry, index) in paginatedTraffic" 
              :key="index"
              @click="selectEntry(entry)"
              :class="{ 'selected': selectedEntry === entry }"
              class="traffic-row"
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
                    class="action-btn"
                    title="View details"
                  >
                    <font-awesome-icon icon="eye" />
                  </button>
                  <button 
                    @click.stop="killFlow(entry.id)" 
                    class="action-btn delete-btn"
                    title="Stop flow"
                  >
                    <font-awesome-icon icon="times" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
          <tbody v-else>
            <tr>
              <td colspan="8" class="no-traffic">
                <font-awesome-icon icon="inbox" />
                <p v-if="trafficData.length === 0">No traffic captured</p>
                <p v-else>No traffic matches current filters</p>
                <small v-if="trafficData.length === 0">Start proxy and configure device to capture traffic</small>
                <small v-else>Try adjusting your filters or <a @click="clearFilters" class="clear-filters-link">clear all filters</a></small>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pagination" v-if="totalPages > 1">
        <button 
          @click="currentPage--" 
          :disabled="currentPage === 1"
          class="control-btn"
        >
          <font-awesome-icon icon="chevron-left" />
        </button>
        
        <span class="pagination-info">
          Page {{ currentPage }} of {{ totalPages }}
          <span v-if="filteredTraffic.length !== trafficData.length" class="pagination-note">
            ({{ filteredTraffic.length }} filtered)
          </span>
        </span>
        
        <button 
          @click="currentPage++" 
          :disabled="currentPage === totalPages"
          class="control-btn"
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
    <TrafficDetailsModal
      :show="showDetailsModal"
      :entry="selectedEntry"
      :device-id="deviceId"
      @close="closeModal"
      @content-changed="handleContentChanged"
      @success="handleModalSuccess"
      @error="handleModalError"
    />

    <!-- Loading overlay -->
    <div class="loading-overlay" v-if="isLoading">
      <div class="spinner"></div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'
import TrafficDetailsModal from '@/components/modals/TrafficDetailsModal.vue'

export default {
  name: 'TrafficMonitor',
  components: {
    TrafficDetailsModal
  },
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
        proxy_host: "0.0.0.0",
        proxy_configured: false
      },
      trafficData: [],
      filteredTraffic: [],
      securityReport: {
        issues: [],
        summary: { total: 0, high: 0, medium: 0, low: 0 }
      },
      selectedEntry: null,
      showDetailsModal: false,
      currentPage: 1,
      itemsPerPage: 20,
      autoRefresh: true,
      refreshInterval: null,
      mitmproxyWebSocket: null,
      filters: {
        host: '',
        method: '',
        status: ''
      },
      sortBy: 'timestamp_desc',
      showExportMenu: false,
      showMethodDropdown: false,
      showStatusDropdown: false,
      showHostDropdown: false,
      selectedMethods: [],
      selectedStatuses: [],
      availableMethods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'],
      availableStatuses: [
        { value: '2xx', label: '2xx Success' },
        { value: '3xx', label: '3xx Redirect' },
        { value: '4xx', label: '4xx Client Error' },
        { value: '5xx', label: '5xx Server Error' }
      ]
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

    httpCountFiltered() {
      return this.filteredTraffic.filter(entry => entry.scheme === 'http').length
    },

    totalPages() {
      return Math.ceil(this.filteredTraffic.length / this.itemsPerPage)
    },

    paginatedTraffic() {
      const start = (this.currentPage - 1) * this.itemsPerPage
      const end = start + this.itemsPerPage
      return this.filteredTraffic.slice(start, end)
    }
  },

  mounted() {
    this.checkStatus()
    this.openMitmproxyWebSocket()
    this.startAutoRefresh()
    this.applyFilters()
    
    // Ensure arrays are properly initialized
    this.selectedMethods = []
    this.selectedStatuses = []
    
    // Add click outside listener to close dropdowns
    document.addEventListener('click', this.handleClickOutside)
  },

  beforeUnmount() {
    this.closeMitmproxyWebSocket()
    this.stopAutoRefresh()
    
    // Remove click outside listener
    document.removeEventListener('click', this.handleClickOutside)
  },

  methods: {
    applyFilters() {
      let filtered = [...this.trafficData]
      
      // Apply host filter
      if (this.filters.host) {
        filtered = filtered.filter(entry => 
          entry.host.toLowerCase().includes(this.filters.host.toLowerCase())
        )
      }
      
      // Apply method filter
      if (this.filters.method) {
        if (this.filters.method.includes(',')) {
          // Multiple methods selected
          const methods = this.filters.method.split(',')
          filtered = filtered.filter(entry => methods.includes(entry.method))
        } else {
          // Single method selected
          filtered = filtered.filter(entry => entry.method === this.filters.method)
        }
      }
      
      // Apply status filter
      if (this.filters.status) {
        if (this.filters.status.includes(',')) {
          // Multiple statuses selected
          const statuses = this.filters.status.split(',')
          filtered = filtered.filter(entry => {
            const statusCode = Math.floor(entry.status_code / 100)
            return statuses.some(status => parseInt(status.charAt(0)) === statusCode)
          })
        } else {
          // Single status selected
          const statusCode = parseInt(this.filters.status.charAt(0))
          filtered = filtered.filter(entry => 
            Math.floor(entry.status_code / 100) === statusCode
          )
        }
      }
      
      // Apply sorting
      this.applySorting(filtered)
      
      // Reset to first page when filters change
      this.currentPage = 1
    },

    applySorting(data = null) {
      const dataToSort = data || this.filteredTraffic
      if (!Array.isArray(dataToSort)) {
        console.error('applySorting: dataToSort is not an array:', dataToSort)
        return
      }
      let sorted = [...dataToSort]
      
      const [field, direction] = this.sortBy.split('_')
      
      sorted.sort((a, b) => {
        let aVal, bVal
        
        switch (field) {
          case 'timestamp':
            aVal = a.timestamp
            bVal = b.timestamp
            break
          case 'host':
            aVal = a.host.toLowerCase()
            bVal = b.host.toLowerCase()
            break
          case 'method':
            aVal = a.method.toLowerCase()
            bVal = b.method.toLowerCase()
            break
          case 'status':
            aVal = a.status_code
            bVal = b.status_code
            break
          case 'duration':
            aVal = a.duration || 0
            bVal = b.duration || 0
            break
          default:
            return 0
        }
        
        if (direction === 'asc') {
          return aVal > bVal ? 1 : aVal < bVal ? -1 : 0
        } else {
          return aVal < bVal ? 1 : aVal > bVal ? -1 : 0
        }
      })
      
      this.filteredTraffic = sorted
    },

    clearFilters() {
      this.filters = {
        host: '',
        method: '',
        status: ''
      }
      this.sortBy = 'timestamp_desc'
      this.selectedMethods = []
      this.selectedStatuses = []
      this.showMethodDropdown = false
      this.showStatusDropdown = false
      this.showHostDropdown = false
      this.applyFilters()
    },

    toggleSort(field) {
      const [currentField, currentDirection] = this.sortBy.split('_')
      
      if (currentField === field) {
        // Toggle direction if same field
        this.sortBy = currentDirection === 'asc' ? `${field}_desc` : `${field}_asc`
      } else {
        // Set new field with default direction
        this.sortBy = `${field}_desc`
      }
      
      this.applySorting()
    },

    getSortClass(field) {
      const [currentField, currentDirection] = this.sortBy.split('_')
      if (currentField === field) {
        return currentDirection === 'asc' ? 'sort-asc' : 'sort-desc'
      }
      return ''
    },

    toggleMethodFilter() {
      this.showMethodDropdown = !this.showMethodDropdown
      this.showStatusDropdown = false
      this.showHostDropdown = false
    },

    toggleStatusFilter() {
      this.showStatusDropdown = !this.showStatusDropdown
      this.showMethodDropdown = false
      this.showHostDropdown = false
    },

    toggleHostFilter() {
      this.showHostDropdown = !this.showHostDropdown
      this.showMethodDropdown = false
      this.showStatusDropdown = false
    },

    clearHostFilter() {
      this.filters.host = ''
      this.applyFilters()
    },

    toggleMethod(method) {
      console.log('toggleMethod called with:', method)
      const index = this.selectedMethods.indexOf(method)
      if (index > -1) {
        this.selectedMethods.splice(index, 1)
      } else {
        this.selectedMethods.push(method)
      }
      console.log('selectedMethods after toggle:', this.selectedMethods)
      this.applyMethodFilter()
    },

    toggleStatus(status) {
      console.log('toggleStatus called with:', status)
      const index = this.selectedStatuses.indexOf(status)
      if (index > -1) {
        this.selectedStatuses.splice(index, 1)
      } else {
        this.selectedStatuses.push(status)
      }
      console.log('selectedStatuses after toggle:', this.selectedStatuses)
      this.applyStatusFilter()
    },

    applyMethodFilter() {
      console.log('applyMethodFilter called, selectedMethods:', this.selectedMethods)
      if (this.selectedMethods.length === 0) {
        this.filters.method = ''
      } else {
        this.filters.method = this.selectedMethods.join(',')
      }
      console.log('filters.method set to:', this.filters.method)
      this.applyFilters()
    },

    applyStatusFilter() {
      console.log('applyStatusFilter called, selectedStatuses:', this.selectedStatuses)
      if (this.selectedStatuses.length === 0) {
        this.filters.status = ''
      } else {
        this.filters.status = this.selectedStatuses.join(',')
      }
      console.log('filters.status set to:', this.filters.status)
      this.applyFilters()
    },

    clearMethodFilter() {
      this.selectedMethods = []
      this.filters.method = ''
      this.applyFilters()
    },

    clearStatusFilter() {
      this.selectedStatuses = []
      this.filters.status = ''
      this.applyFilters()
    },

    handleClickOutside(event) {
      // Close dropdowns if clicking outside
      if (!event.target.closest('.filterable-header')) {
        this.showMethodDropdown = false
        this.showStatusDropdown = false
        this.showHostDropdown = false
      }
    },

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
            this.status.proxy_configured = true
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

    async disableProxy() {
      try {
        this.isLoading = true
        
        if (this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
          this.mitmproxyWebSocket.send(JSON.stringify({
            type: "mitmproxy",
            action: "disable_proxy",
            device_id: this.deviceId
          }))
        } else {
          const response = await axios.post(`/api/v1/dynamic-testing/device/${encodeURIComponent(this.deviceId)}/mitmproxy/disable-proxy`)
          
          if (response.data.status === 'success') {
            this.status.proxy_configured = false
            this.$emit('success', 'Proxy disabled on device')
          }
        }
      } catch (error) {
        console.error('Error disabling proxy:', error)
        this.$emit('error', 'Error disabling proxy: ' + (error.response?.data?.detail || error.message))
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
            this.applyFilters()
          } catch (error) {
            const fallbackResponse = await axios.get(`/api/v1/dynamic-testing/device/${this.deviceId}/mitmproxy/traffic?detailed=true`)
            if (fallbackResponse.data.status === 'success') {
              this.trafficData = fallbackResponse.data.data.traffic || []
              this.applyFilters()
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
        this.filteredTraffic = []
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
        let useBlobResponse = false
        
        try {
          // Try primary endpoint with blob response
          response = await axios.get(`/api/v1/mitmproxy/flows/dump`, {
            params: {
              device_id: this.deviceId,
              format: format
            },
            responseType: 'blob'
          })
          useBlobResponse = true
        } catch (error) {
          // Fallback to alternative endpoint
          try {
            response = await axios.get(`/api/v1/dynamic-testing/device/${this.deviceId}/mitmproxy/export?format=${format}`, {
              responseType: 'blob'
            })
            useBlobResponse = true
          } catch (fallbackError) {
            // Last resort: try without blob response
            response = await axios.get(`/api/v1/mitmproxy/flows/dump`, {
              params: {
                device_id: this.deviceId,
                format: format
              }
            })
            useBlobResponse = false
          }
        }
        
        // Determine filename and mime type
        let filename, mimeType
        
        if (format === 'json') {
          filename = `flows_${this.deviceId.replace(':', '_')}_${Date.now()}.json`
          mimeType = 'application/json'
        } else if (format === 'har') {
          filename = `flows_${this.deviceId.replace(':', '_')}_${Date.now()}.har`
          mimeType = 'application/json'
        } else {
          filename = `flows_${this.deviceId.replace(':', '_')}_${Date.now()}.${format}`
          mimeType = format === 'csv' ? 'text/csv' : 'application/octet-stream'
        }
        
        // Handle different response types
        let blob
        
        if (useBlobResponse && response.data instanceof Blob) {
          // Check if Blob contains JSON
          if (mimeType === 'application/json') {
            // Read blob as text for JSON data
            const text = await response.data.text()
            blob = new Blob([text], { type: mimeType })
          } else {
            // Binary data - use blob as is
            blob = response.data
          }
        } else if (useBlobResponse && typeof response.data === 'string') {
          // String from blob response
          blob = new Blob([response.data], { type: mimeType })
        } else if (typeof response.data === 'string') {
          // Direct string response
          blob = new Blob([response.data], { type: mimeType })
        } else if (typeof response.data === 'object') {
          // JSON object - stringify it
          const content = JSON.stringify(response.data, null, 2)
          blob = new Blob([content], { type: mimeType })
        } else {
          // Fallback: wrap in Blob
          blob = new Blob([response.data], { type: mimeType })
        }
        
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
        this.$emit('error', 'Error exporting traffic: ' + (error.response?.data?.detail || error.message))
      }
    },

    selectEntry(entry) {
      this.selectedEntry = entry
    },

    async viewDetails(entry) {
      try {
        this.isLoading = true
        
        // Use local entry data instead of fetching (flows might be cleared)
        this.selectedEntry = { ...entry }
        this.selectedEntry.request_view = 'auto'
        this.selectedEntry.response_view = 'auto'
        
        // Content will be loaded in the modal component
        this.selectedEntry.request_content = null
        this.selectedEntry.response_content = null
        
        this.showDetailsModal = true
      } catch (error) {
        console.error('Error opening flow details:', error)
        this.selectedEntry = { ...entry }
        this.showDetailsModal = true
      } finally {
        this.isLoading = false
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



    closeModal() {
      this.showDetailsModal = false
    },

    handleContentChanged(data) {
      if (data.messageType === 'request') {
        this.selectedEntry.request_content = data.content;
        this.selectedEntry.request_view = data.viewType;
      } else if (data.messageType === 'response') {
        this.selectedEntry.response_content = data.content;
        this.selectedEntry.response_view = data.viewType;
      }
    },

    handleModalSuccess(message) {
      this.$emit('success', message);
    },

    handleModalError(message) {
      this.$emit('error', message);
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
            proxy_host: data.proxy_host,
            proxy_configured: data.proxy_configured || false
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
              backend_ip: data.data.backend_ip,
              proxy_configured: data.data.proxy_configured || false
            }
          }
          break
          
        case 'flows':
          if (data.data && Array.isArray(data.data)) {
            // Don't replace if empty array received (might be temporary)
            if (data.data.length > 0 || this.trafficData.length === 0) {
              this.trafficData = data.data.map(flow => this.convertFlowToTrafficEntry(flow))
              this.applyFilters()
            }
          }
          break
          
        case 'clear_flows':
          if (data.success) {
            this.trafficData = []
            this.filteredTraffic = []
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
          this.status.proxy_configured = data.success
          if (data.success) {
            this.$emit('success', 'Proxy configured on device')
          } else {
            this.$emit('error', 'Error configuring proxy')
          }
          break
          
        case 'proxy_disabled':
          this.status.proxy_configured = !data.success
          if (data.success) {
            this.$emit('success', 'Proxy disabled on device')
          } else {
            this.$emit('error', 'Error disabling proxy')
          }
          break
          
        case 'proxy_port_updated':
          if (data.proxy_port) {
            this.status.proxy_port = data.proxy_port
          }
          if (data.backend_ip) {
            this.status.backend_ip = data.backend_ip
          }
          this.status.proxy_configured = true
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
            // Add new traffic to the end by default (unless sorted differently)
            this.trafficData.push(flowSummary) 
            
            if (this.trafficData.length > 1000) {
              this.trafficData = this.trafficData.slice(0, 1000)
            }
            
            this.applyFilters()
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
              this.trafficData.push(flowSummary)
            }
            this.applyFilters()
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
            // Reapply filters after removal
            this.applyFilters()
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
          type: flow.type || 'http',
          client_conn: flow.client_conn || null,
          server_conn: flow.server_conn || null,
          error: flow.error || null
        }
    },

    startAutoRefresh() {
      this.stopAutoRefresh()
      
      // Don't periodically request flows - rely on WebSocket events (flow_add, flow_update)
      // Only request initial state once
      if (this.status.proxy_running && this.mitmproxyWebSocket && this.mitmproxyWebSocket.readyState === WebSocket.OPEN) {
        this.mitmproxyWebSocket.send(JSON.stringify({
          type: "mitmproxy",
          action: "get_state",
          device_id: this.deviceId
        }))
      }
      
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
        const wsHost = window.location.host
        const mitmproxyWsUrl = `${wsProtocol}//${wsHost}/api/v1/dynamic-testing/ws/${encodeURIComponent(this.deviceId)}?action=mitmproxy`
        
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
  margin-top: 0;
  margin-bottom: 0;
  background: #f5f5f5;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.traffic-monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 15px;
  background: #2d2d2d;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
  color: #ffffff;
}

.traffic-monitor-header span {
  font-weight: 600;
  font-size: 16px;
}

.user-info {
  color: #666;
  font-size: 0.9em;
  margin-left: 8px;
}

.traffic-monitor-path {
  padding: 10px 15px;
  background: #f8f9fa;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
}

.current-path {
  display: flex;
  align-items: center;
  gap: 10px;
}

.path-label {
  font-weight: 600;
  color: #333;
  font-size: 14px;
}

.path-value {
  font-family: monospace;
  background: #fff;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid #ddd;
  color: #555;
  font-size: 13px;
  word-break: break-all;
}

.path-value.status-success {
  color: #28a745;
  border-color: #28a745;
}

.path-value.status-error {
  color: #dc3545;
  border-color: #dc3545;
}

.traffic-monitor-toolbar {
  display: flex;
  gap: 10px;
  padding: 10px 15px;
  background: #e0e0e0;
  border-bottom: 1px solid #ccc;
  flex-wrap: wrap;
}

.toolbar-btn {
  padding: 5px 10px;
  border: 1px solid #ccc;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s ease;
}

.toolbar-btn:hover:not(:disabled) {
  background: #f0f0f0;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.toolbar-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.traffic-monitor-content {
  flex: 1;
  padding: 15px;
  background: #fff;
  overflow-y: auto;
  min-height: 400px;
  max-height: 600px;
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
  font-size: 16px;
}

.traffic-controls {
  display: flex;
  gap: 10px;
  align-items: center;
}

.traffic-filters {
  background: #f8f9fa;
  border-radius: 6px;
  padding: 15px;
  margin-bottom: 15px;
  border: 1px solid #e9ecef;
}

.filter-row {
  display: flex;
  gap: 15px;
  align-items: end;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.filter-group label {
  font-size: 12px;
  font-weight: 600;
  color: #495057;
  margin: 0;
}

.filter-input,
.filter-select {
  padding: 6px 10px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 13px;
  background: white;
  transition: border-color 0.15s ease-in-out, box-shadow 0.15s ease-in-out;
}

.filter-input:focus,
.filter-select:focus {
  outline: 0;
  border-color: #80bdff;
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
}

.clear-filters-btn {
  background: #dc3545;
  color: white;
  border-color: #dc3545;
  margin-left: auto;
}

.clear-filters-btn:hover:not(:disabled) {
  background: #c82333;
  border-color: #bd2130;
}

.control-btn {
  padding: 4px 8px;
  border: 1px solid #ccc;
  background: #fff;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.2s ease;
}

.control-btn:hover:not(:disabled) {
  background: #f0f0f0;
}

.control-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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

.stat-note {
  font-size: 11px;
  color: #6c757d;
  font-weight: normal;
  margin-left: 5px;
}

.filter-active {
  color: #dc3545 !important;
  font-weight: 700;
}

.traffic-table-container {
  overflow-x: auto;
  margin-bottom: 20px;
  min-height: 200px;
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
  border-bottom: 1px solid #eee;
}

.traffic-table th {
  background: #f8f9fa;
  font-weight: 600;
  color: #333;
  position: sticky;
  top: 0;
}

.sortable-header {
  cursor: pointer;
  user-select: none;
  position: relative;
  transition: background-color 0.2s ease;
}

.sortable-header:hover {
  background: #e9ecef;
}

.filterable-header {
  position: relative;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 4px;
}

.host-filter-input {
  padding: 8px 12px;
}

.host-filter-input .filter-input {
  margin: 0;
}

.sort-indicator,
.filter-indicator {
  opacity: 0.5;
  transition: opacity 0.2s ease;
}

.sort-indicator.sort-asc {
  opacity: 1;
  color: #007bff;
}

.sort-indicator.sort-desc {
  opacity: 1;
  color: #007bff;
  transform: rotate(180deg);
}

.filter-indicator.active {
  opacity: 1;
  color: #dc3545;
}

.header-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  box-shadow: 0 4px 8px rgba(0,0,0,0.15);
  z-index: 1000;
  overflow-y: auto;
  white-space: nowrap;
}

.dropdown-content {
  padding: 8px 0;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.dropdown-item:hover {
  background: #f8f9fa;
}

.dropdown-item input[type="checkbox"] {
  margin: 0;
  cursor: pointer;
  pointer-events: auto;
}

.dropdown-item label {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin: 0;
}

.dropdown-actions {
  border-top: 1px solid #dee2e6;
  padding: 8px 12px;
}

.clear-btn {
  background: #dc3545;
  color: white;
  border: none;
  padding: 4px 8px;
  border-radius: 3px;
  font-size: 12px;
  cursor: pointer;
}

.clear-btn:hover {
  background: #c82333;
}

.traffic-row {
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.traffic-row:hover {
  background: #f8f9fa;
}

.traffic-row.selected {
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

td.no-traffic {
  display: table-cell;
  text-align: center;
  vertical-align: middle;
}

td.no-traffic > * {
  display: block;
  margin: 8px auto;
}

td.no-traffic p {
  margin: 8px 0 4px 0;
}

td.no-traffic small {
  display: block;
  text-align: center;
}

.clear-filters-link {
  color: #007bff;
  text-decoration: underline;
  cursor: pointer;
}

.clear-filters-link:hover {
  color: #0056b3;
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

.pagination-note {
  font-size: 12px;
  color: #999;
  margin-left: 8px;
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

.action-buttons {
  display: flex;
  gap: 4px;
  align-items: center;
}

.action-btn {
  padding: 2px 6px;
  margin-right: 5px;
  border: 1px solid #ccc;
  background: #fff;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 24px;
  height: 24px;
  justify-content: center;
}

.action-btn:hover:not(:disabled) {
  background: #f0f0f0;
}

.action-btn.delete-btn {
  color: #d32f2f;
  border-color: #d32f2f;
}

.action-btn.delete-btn:hover:not(:disabled) {
  background: #ffebee;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #3498db;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@media (max-width: 1024px) {
  .traffic-monitor {
    max-height: 700px;
  }
  
  .traffic-monitor-content {
    max-height: 450px;
  }
}

@media (max-width: 768px) {
  .traffic-monitor {
    max-height: 450px;
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
  }
  
  .traffic-monitor-content {
    max-height: 300px;
  }
  
  .traffic-monitor-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  
  .traffic-monitor-path {
    flex-direction: column;
    gap: 10px;
  }
  
  .traffic-monitor-toolbar {
    flex-direction: column;
  }
  
  .traffic-controls {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  
  .traffic-filters {
    padding: 10px;
  }
  
  .filter-row {
    flex-direction: column;
    gap: 10px;
  }
  
  .filter-group {
    min-width: auto;
    width: 100%;
  }
  
  .clear-filters-btn {
    margin-left: 0;
    width: 100%;
  }
  
  .security-stats {
    flex-direction: column;
    gap: 10px;
  }
}
</style>
