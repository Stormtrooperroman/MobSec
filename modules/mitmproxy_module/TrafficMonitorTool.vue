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

          <a 
            @click="exportTraffic('json')"
            class="control-btn"
          >
            <font-awesome-icon icon="download" />  Export
        </a>
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

    <!-- Traffic Details Modal -->
    <TrafficDetailsModal
      :show="showDetailsModal"
      :entry="selectedEntry"
      :device-id="deviceId"
      @close="closeModal"
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
import TrafficDetailsModal from './TrafficDetailsModal.vue'

export default {
  name: 'TrafficMonitorTool',
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
      selectedEntry: null,
      showDetailsModal: false,
      currentPage: 1,
      itemsPerPage: 20,
      autoRefresh: true,
      refreshInterval: null,
      mitmproxyWebSocket: null,
      closingWebSocket: false,
      reconnectTimer: null,
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
    this.openMitmproxyWebSocket()
    this.startAutoRefresh()
    this.applyFilters()
    
    this.selectedMethods = []
    this.selectedStatuses = []
    
    document.addEventListener('click', this.handleClickOutside)
  },

  beforeUnmount() {
    this.closingWebSocket = true
    this.closeMitmproxyWebSocket()
    this.stopAutoRefresh()
    
    document.removeEventListener('click', this.handleClickOutside)
  },

  methods: {
    sendMitmproxyAction(action, payload = {}) {
      if (!this.mitmproxyWebSocket || this.mitmproxyWebSocket.readyState !== WebSocket.OPEN) {
        this.$emit('error', 'Mitmproxy WebSocket is disconnected')
        return false
      }

      this.mitmproxyWebSocket.send(JSON.stringify({
        type: 'mitmproxy',
        action,
        device_id: this.deviceId,
        ...payload
      }))
      return true
    },

    applyFilters() {
      let filtered = [...this.trafficData]
      
      if (this.filters.host) {
        filtered = filtered.filter(entry => 
          entry.host.toLowerCase().includes(this.filters.host.toLowerCase())
        )
      }
      
      if (this.filters.method) {
        if (this.filters.method.includes(',')) {
          const methods = this.filters.method.split(',')
          filtered = filtered.filter(entry => methods.includes(entry.method))
        } else {
          filtered = filtered.filter(entry => entry.method === this.filters.method)
        }
      }
      
      if (this.filters.status) {
        if (this.filters.status.includes(',')) {
          const statuses = this.filters.status.split(',')
          filtered = filtered.filter(entry => {
            const statusCode = Math.floor(entry.status_code / 100)
            return statuses.some(status => parseInt(status.charAt(0)) === statusCode)
          })
        } else {
          const statusCode = parseInt(this.filters.status.charAt(0))
          filtered = filtered.filter(entry => 
            Math.floor(entry.status_code / 100) === statusCode
          )
        }
      }
      
      this.applySorting(filtered)
      
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
        this.sortBy = currentDirection === 'asc' ? `${field}_desc` : `${field}_asc`
      } else {
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
      if (!event.target.closest('.filterable-header')) {
        this.showMethodDropdown = false
        this.showStatusDropdown = false
        this.showHostDropdown = false
      }
    },

    sendWebSocketAction(action, payload = {}) {
      if (!this.mitmproxyWebSocket || this.mitmproxyWebSocket.readyState !== WebSocket.OPEN) {
        this.$emit('error', 'Mitmproxy WebSocket is not connected')
        return false
      }

      this.mitmproxyWebSocket.send(JSON.stringify({
        type: 'mitmproxy',
        action,
        device_id: this.deviceId,
        ...payload
      }))
      return true
    },

    checkStatus() {
      this.sendWebSocketAction('get_state')
    },

    startProxy() {
      this.isLoading = this.sendWebSocketAction('start_proxy')
    },

    stopProxy() {
      this.isLoading = this.sendWebSocketAction('stop_proxy')
    },

    configureProxy() {
      this.isLoading = this.sendWebSocketAction('configure_proxy')
    },

    disableProxy() {
      this.isLoading = this.sendWebSocketAction('disable_proxy')
    },

    generateCertificate() {
      this.isLoading = this.sendWebSocketAction('generate_certificate')
    },

    installCertificate() {
      this.isLoading = this.sendWebSocketAction('install_certificate')
    },

    downloadCertificate() {
      this.sendWebSocketAction('download_certificate')
    },

    rebootDevice() {
      this.isLoading = this.sendWebSocketAction('reboot_device')
    },

    refreshTraffic() {
      this.isLoading = this.sendWebSocketAction('get_flows')
    },

    clearTraffic() {
      this.isLoading = this.sendWebSocketAction('clear_flows')
    },

    exportTraffic(format) {
      this.showExportMenu = false
      this.isLoading = this.sendWebSocketAction('export_flows', { format })
    },

    killFlow(flowId) {
      this.isLoading = this.sendWebSocketAction('kill_flow', { flow_id: flowId })
    },

    downloadBase64File(data) {
      const binary = window.atob(data.content || '')
      const bytes = new Uint8Array(binary.length)
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index)
      }
      const blob = new Blob([bytes], { type: data.mime_type || 'application/octet-stream' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = data.filename || 'mitmproxy-download'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    },

    selectEntry(entry) {
      this.selectedEntry = entry
    },

    async viewDetails(entry) {
      try {
        this.isLoading = true
        
        this.selectedEntry = { ...entry }
        this.selectedEntry.request_view = 'auto'
        this.selectedEntry.response_view = 'auto'
        this.showDetailsModal = true
      } catch (error) {
        console.error('Error opening flow details:', error)
        this.selectedEntry = { ...entry }
        this.showDetailsModal = true
      } finally {
        this.isLoading = false
      }
    },



    killFlow(flowId) {
      this.isLoading = this.sendWebSocketAction('kill_flow', { flow_id: flowId })
    },



    closeModal() {
      this.showDetailsModal = false
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
          this.isLoading = false
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
          this.isLoading = false
          if (data.data && Array.isArray(data.data)) {
            if (data.data.length > 0 || this.trafficData.length === 0) {
              this.trafficData = data.data.map(flow => this.convertFlowToTrafficEntry(flow))
              this.applyFilters()
            }
          }
          break
          
        case 'clear_flows':
          this.isLoading = false
          if (data.success) {
            this.trafficData = []
            this.filteredTraffic = []
            this.$emit('success', 'Traffic cleared')
          }
          break
          
        case 'proxy_start_result':
          this.isLoading = false
          this.status.proxy_running = data.success
          if (data.success) {
            this.$emit('success', 'Proxy started successfully')
            this.startAutoRefresh()
          } else {
            this.$emit('error', 'Error starting proxy')
          }
          break
          
        case 'proxy_stop_result':
          this.isLoading = false
          this.status.proxy_running = !data.success
          if (!this.status.proxy_running) {
            this.$emit('success', 'Proxy stopped successfully')
            this.stopAutoRefresh()
          } else {
            this.$emit('error', 'Error stopping proxy')
          }
          break
          
        case 'certificate_generated':
          this.isLoading = false
          if (data.success) {
            this.$emit('success', 'Certificate generated successfully')
          } else {
            this.$emit('error', 'Error generating certificate')
          }
          break
          
        case 'certificate_installed':
          this.isLoading = false
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
          this.isLoading = false
          this.status.proxy_configured = data.success
          if (data.success) {
            this.$emit('success', 'Proxy configured on device')
          } else {
            this.$emit('error', 'Error configuring proxy')
          }
          break
          
        case 'proxy_disabled':
          this.isLoading = false
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
          this.isLoading = false
          if (data.success) {
            this.$emit('success', data.message)
            setTimeout(() => {
              this.checkStatus()
            }, 3000)
          } else {
            this.$emit('error', data.message)
          }
          break
          
        case 'certificate_download':
        case 'flows_export':
          this.isLoading = false
          if (data.success && data.content) {
            this.downloadBase64File(data)
            this.$emit('success', data.message || 'Download ready')
          } else {
            this.$emit('error', data.message || 'Download failed')
          }
          break

        case 'flow_killed':
          this.isLoading = false
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
          request_content: request.content || '',
          response_content: response.content || '',
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
          
          if (event.code !== 1000 && !this.closingWebSocket) {
            this.reconnectTimer = setTimeout(() => {
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
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer)
        this.reconnectTimer = null
      }
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
}
</style>
