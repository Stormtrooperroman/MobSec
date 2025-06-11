<template>
  <div class="report-container">
    <!-- Navigation Sidebar -->
    <div class="report-nav">
      <div class="nav-section">
        <h3>Navigation</h3>
        <ul class="nav-list">
          <li>
            <a href="#file-info" class="nav-link">File Information</a>
          </li>
          <li>
            <a href="#file-hashes" class="nav-link">File Hashes</a>
          </li>
          <li v-if="hasAnyResults">
            <a href="#scan-overview" class="nav-link">Scan Overview</a>
          </li>
          <li class="nav-divider">Modules</li>
          <li v-for="(moduleData, moduleName) in processedModules" :key="moduleName">
            <a :href="`#module-${moduleName}`" class="nav-link">
              {{ formatModuleName(moduleName) }}
            </a>
          </li>
        </ul>
      </div>
    </div>

    <!-- Main Content -->
    <div class="report-main">
      <h1>App Analysis Report</h1>
      
      <div v-if="loading" class="loading-container">
        <div class="spinner"></div>
        <p>Loading report data...</p>
      </div>
      
      <div v-else-if="error" class="error-container">
        <h3>Error Loading Report</h3>
        <p>{{ error }}</p>
        <button @click="fetchReport" class="retry-button">Retry</button>
      </div>
      
      <div v-else class="report-content">
        <!-- Summary card with basic info -->
        <div id="file-info" class="summary-card">
          <div class="app-info">
            <h2>{{ reportData.file_info?.name || 'Unknown App' }}</h2>
            <div class="app-meta">
              <div><strong>Type:</strong> {{ reportData.file_info?.file_type?.toUpperCase() || 'Unknown' }}</div>
              <div><strong>Size:</strong> {{ formatFileSize(reportData.file_info?.size) }}</div>
              <div><strong>Uploaded:</strong> {{ formatDate(reportData.file_info?.upload_time) }}</div>
            </div>
          </div>
          
          <div class="scan-info">
            <div class="status-indicator">
              <div :class="['status-badge', getStatusClass()]">
                {{ reportData.scan_info?.status || 'Unknown' }}
              </div>
            </div>
            <div v-if="reportData.scan_info?.completed_at" class="scan-time">
              <div><strong>Duration:</strong> {{ reportData.scan_info?.duration }}</div>
              <div><strong>Completed:</strong> {{ formatDate(reportData.scan_info?.completed_at) }}</div>
            </div>
          </div>
        </div>
        
        <!-- File hash info -->
        <div id="file-hashes" class="hash-card">
          <h3>File Identifiers</h3>
          <div class="hash-grid">
            <div class="hash-item">
              <div class="hash-label">MD5:</div>
              <div class="hash-value">{{ reportData.file_info?.hashes?.md5 }}</div>
            </div>
            <div class="hash-item">
              <div class="hash-label">SHA1:</div>
              <div class="hash-value">{{ reportData.file_info?.hashes?.sha1 }}</div>
            </div>
            <div class="hash-item">
              <div class="hash-label">SHA256:</div>
              <div class="hash-value">{{ reportData.file_info?.hashes?.sha256 }}</div>
            </div>
          </div>
        </div>
        
        <!-- Scan Overview -->
        <div id="scan-overview" class="overview-card" v-if="hasAnyResults">
          <h3>Scan Overview</h3>
          <div class="severity-overview">
            <div 
              v-for="(count, severity) in totalSeverityCounts" 
              :key="severity"
              :class="['severity-badge', 'severity-' + severity.toLowerCase()]"
            >
              {{ severity }}: {{ count }}
            </div>
          </div>
        </div>
        
        <!-- All modules results displayed sequentially -->
        <div class="modules-container" v-if="reportData.modules">
          <h3>Scan Results</h3>
          
          <div v-if="Object.keys(processedModules).length === 0" class="no-results">
            <div class="empty-icon">📊</div>
            <h3>No Results Available</h3>
            <p>None of the scan modules produced any results.</p>
          </div>
          
          <div v-for="(moduleData, moduleName) in processedModules" 
               :key="moduleName" 
               :id="`module-${moduleName}`" 
               class="module-section">
            <component
              v-if="moduleData.customUI"
              :is="moduleData.customUI"
              :module-data="moduleData"
              :module-name="moduleName"
              :file-info="reportData.file_info"
            />
            <div v-else>
              <div class="module-header">
                <h3 class="module-title">{{ formatModuleName(moduleName) }} Results</h3>
                
                <!-- Show summary if available -->
                <div v-if="hasSummary(moduleData)" class="summary-section">
                  <h4 class="section-title">Summary</h4>
                  
                  <!-- Severity counts with improved visualization -->
                  <div v-if="hasSeverityCounts(moduleData)" class="summary-card">
                    <div class="summary-label">Findings by Severity</div>
                    <div class="severity-counts">
                      <div 
                        v-for="(count, severity) in moduleData.results.summary.severity_counts" 
                        :key="severity"
                        :class="['severity-badge', 'severity-' + severity.toLowerCase()]"
                      >
                        {{ severity }}: {{ count }}
                      </div>
                    </div>
                  </div>
                  
                  <!-- Category counts -->
                  <div v-if="hasCategoryCounts(moduleData)" class="summary-card">
                    <div class="summary-label">Findings by Category</div>
                    <div class="category-counts">
                      <div 
                        v-for="(count, category) in moduleData.results.summary.category_counts" 
                        :key="category"
                        class="category-badge"
                      >
                        {{ category }}: {{ count }}
                      </div>
                    </div>
                  </div>
                  
                  <!-- Other summary metrics -->
                  <div class="summary-metrics">
                    <div 
                      v-for="(value, key) in filteredSummaryItems(moduleData)" 
                      :key="key" 
                      class="summary-card"
                    >
                      <div class="summary-label">{{ formatKey(key) }}</div>
                      <div class="summary-value">{{ value }}</div>
                    </div>
                  </div>
                </div>
              </div>
              <!-- Show findings section only for non-APKiD modules -->
              <div v-if="moduleName !== 'apkid_module'" class="findings-section">
                <div class="findings-header">
                  <h4 class="section-title">Findings ({{ moduleData.results.findings.length }})</h4>
                  
                  <div class="findings-filters">
                    <div class="filter-group">
                      <label :for="`severity-filter-${moduleName}`">Severity:</label>
                      <select 
                        :id="`severity-filter-${moduleName}`" 
                        v-model="filters[moduleName].severity" 
                        class="filter-select"
                      >
                        <option value="">All Severities</option>
                        <option v-for="severity in getAvailableSeverities(moduleData)" :key="severity" :value="severity">
                          {{ severity }}
                        </option>
                      </select>
                    </div>
                    
                    <div class="filter-group" v-if="getAvailableCategories(moduleData).length > 0">
                      <label :for="`category-filter-${moduleName}`">Category:</label>
                      <select 
                        :id="`category-filter-${moduleName}`" 
                        v-model="filters[moduleName].category" 
                        class="filter-select"
                      >
                        <option value="">All Categories</option>
                        <option v-for="category in getAvailableCategories(moduleData)" :key="category" :value="category">
                          {{ category }}
                        </option>
                      </select>
                    </div>
                  </div>
                </div>
                
                <div class="findings-list">
                  <div 
                    v-for="(finding, index) in getFilteredFindings(moduleData, moduleName)" 
                    :key="index"
                    class="finding-card"
                  >
                    <div class="finding-header">
                      <div :class="['finding-severity', 'severity-' + finding.severity.toLowerCase()]">
                        {{ finding.severity }}
                      </div>
                      <div class="finding-rule">{{ finding.rule_id || 'Unknown Rule' }}</div>
                    </div>
                    
                    <div class="finding-message">{{ finding.message }}</div>
                    
                    <div v-if="finding.location" class="finding-location">
                      <div class="location-details">
                        <div class="location-file">
                          <span class="detail-label">File:</span> {{ getShortFilePath(finding.location.file) }}
                        </div>
                        <div class="location-lines">
                          <span class="detail-label">Lines:</span> {{ finding.location.start_line }} - {{ finding.location.end_line }}
                        </div>
                      </div>
                      
                      <div v-if="finding.location.code" class="location-code">
                        <pre><code>{{ finding.location.code }}</code></pre>
                      </div>
                    </div>
                    
                    <div v-if="finding.metadata && hasMetadata(finding.metadata)" class="finding-metadata">
                      <div v-for="(value, key) in finding.metadata" :key="key" class="metadata-item">
                        <template v-if="Array.isArray(value) && value.length > 0">
                          <span class="metadata-key">{{ formatKey(key) }}:</span> {{ value.join(', ') }}
                        </template>
                        <template v-else-if="value && !Array.isArray(value)">
                          <span class="metadata-key">{{ formatKey(key) }}:</span> {{ value }}
                        </template>
                      </div>
                    </div>
                  </div>
                  
                  <div v-if="getFilteredFindings(moduleData, moduleName).length === 0" class="no-findings">
                    <div class="empty-state">
                      <span class="empty-icon">🔍</span>
                      <p>No findings match your current filters.</p>
                    </div>
                  </div>
                </div>
              </div>
              
              <!-- Raw Results Section if no structured data is available -->
              <div v-if="!hasFindings(moduleData) && !hasSummary(moduleData)" class="raw-results">
                <h4 class="section-title">Raw Results</h4>
                <div class="code-container">
                  <pre><code>{{ JSON.stringify(moduleData.results, null, 2) }}</code></pre>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <div class="report-actions">
          <button @click="goBack" class="back-button">Back to Files</button>
          <button @click="fetchReport" class="refresh-button">Refresh Report</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { defineComponent } from 'vue'
import * as Vue from 'vue'

export default defineComponent({
  name: 'ReportView',
  props: {
    fileHash: {
      type: String,
      required: true
    }
  },
  data() {
    return {
      reportData: {},
      loading: true,
      error: null,
      filters: {},
      processedModules: {}
    };
  },
  computed: {
    nonEmptyModules() {
      if (!this.reportData.modules) return {};
      
      return Object.fromEntries(
        Object.entries(this.reportData.modules)
          .filter(([, moduleData]) => moduleData.results && 
            (this.hasFindings(moduleData) || this.hasSummary(moduleData) || 
            Object.keys(moduleData.results).length > 0)
          )
      );
    },
    hasAnyResults() {
      return Object.keys(this.nonEmptyModules).length > 0;
    },
    totalSeverityCounts() {
      const counts = {};
      
      Object.values(this.nonEmptyModules).forEach(moduleData => {
        if (this.hasSeverityCounts(moduleData)) {
          Object.entries(moduleData.results.summary.severity_counts).forEach(([severity, count]) => {
            counts[severity] = (counts[severity] || 0) + count;
          });
        }
      });
      
      return counts;
    }
  },
  mounted() {
    this.fetchReport();
  },
  methods: {
    async loadCustomModuleUIs() {
      if (!this.reportData.modules) return;
      
      try {
        const uiInfoResponse = await fetch('/api/v1/modules/module-ui-info');
        if (!uiInfoResponse.ok) {
          throw new Error('Failed to fetch module UI information');
        }
        const moduleUiInfo = await uiInfoResponse.json();
        
        const modules = Object.entries(this.nonEmptyModules);
        const modulesWithUI = await Promise.all(
          modules.map(async ([name, data]) => {
            const moduleKey = name.replace('_module', '').toLowerCase();
            
            if (moduleUiInfo[moduleKey]?.has_custom_ui) {
              try {
                const response = await fetch(`/api/v1/modules/module-ui-component/${moduleKey}`);
                if (!response.ok) {
                  console.debug(`Error fetching custom UI for module ${name}`);
                  return [name, { ...data, customUI: null }];
                }
                
                const { component_content, component_name } = await response.json();
                
                const { loadModule } = window['vue3-sfc-loader'];
                const options = {
                  moduleCache: {
                    vue: Vue
                  },
                  async getFile() {
                    return {
                      getContentData: async () => component_content
                    }
                  },
                  addStyle(textContent) {
                    const style = document.createElement('style');
                    style.textContent = textContent;
                    document.head.appendChild(style);
                  }
                };
                
                const customUI = await loadModule(`/${component_name}.vue`, options);
                return [name, { ...data, customUI }];
              } catch (error) {
                console.debug(`Error loading custom UI for module ${name}:`, error);
                return [name, { ...data, customUI: null }];
              }
            }
            
            return [name, { ...data, customUI: null }];
          })
        );
        
        this.processedModules = Object.fromEntries(modulesWithUI);
      } catch (error) {
        console.error('Error loading custom module UIs:', error);
        this.processedModules = this.nonEmptyModules;
      }
    },
    async fetchReport() {
      this.loading = true;
      this.error = null;
      
      try {
        const response = await fetch(`/api/v1/apps/report/${this.fileHash}`);
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }
        this.reportData = await response.json();
        
        if (this.reportData.modules) {
          Object.keys(this.reportData.modules).forEach(moduleName => {
            this.filters[moduleName] = { severity: '', category: '' };
          });
        }
      } catch (err) {
        console.error('Error fetching report:', err);
        this.error = err.message || 'Failed to load report data';
      } finally {
        this.loading = false;
      }
    },
    getStatusClass() {
      const status = this.reportData.scan_info?.status;
      if (!status) return 'status-unknown';
      
      switch (status.toLowerCase()) {
        case 'completed':
          return 'status-completed';
        case 'failed':
          return 'status-failed';
        case 'scanning':
          return 'status-scanning';
        case 'pending':
          return 'status-pending';
        default:
          return 'status-unknown';
      }
    },
    formatFileSize(bytes) {
      if (!bytes) return 'Unknown';
      
      const units = ['B', 'KB', 'MB', 'GB'];
      let size = bytes;
      let unitIndex = 0;
      
      while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
      }
      
      return `${size.toFixed(1)} ${units[unitIndex]}`;
    },
    formatDate(dateString) {
      if (!dateString) return 'N/A';
      
      try {
        const date = new Date(dateString);
        return date.toLocaleString();
      } catch (e) {
        return dateString;
      }
    },
    formatModuleName(name) {
      return name
        .replace('_module', '')
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
    },
    formatKey(key) {
      return key
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
    },
    hasSummary(moduleData) {
      return moduleData.results && moduleData.results.summary;
    },
    hasFindings(moduleData) {
      return moduleData.results && 
             moduleData.results.findings &&
             Array.isArray(moduleData.results.findings) &&
             moduleData.results.findings.length > 0;
    },
    hasSeverityCounts(moduleData) {
      return this.hasSummary(moduleData) && moduleData.results.summary.severity_counts;
    },
    hasCategoryCounts(moduleData) {
      return this.hasSummary(moduleData) && moduleData.results.summary.category_counts;
    },
    filteredSummaryItems(moduleData) {
      if (!this.hasSummary(moduleData)) return {};
      
      const exclude = ['severity_counts', 'category_counts'];
      return Object.fromEntries(
        Object.entries(moduleData.results.summary)
          .filter(([key]) => !exclude.includes(key))
      );
    },
    getAvailableSeverities(moduleData) {
      if (!this.hasFindings(moduleData)) return [];
      
      const severities = new Set();
      moduleData.results.findings.forEach(finding => {
        if (finding.severity) {
          severities.add(finding.severity);
        }
      });
      
      return Array.from(severities);
    },
    getAvailableCategories(moduleData) {
      if (!this.hasFindings(moduleData)) return [];
      
      const categories = new Set();
      moduleData.results.findings.forEach(finding => {
        if (finding.rule_id) {
          categories.add(finding.rule_id);
        }
        if (finding.metadata && finding.metadata.category) {
          categories.add(finding.metadata.category);
        }
      });
      
      return Array.from(categories).filter(c => c);
    },
    getFilteredFindings(moduleData, moduleName) {
      if (!this.hasFindings(moduleData)) return [];
      
      const { severity, category } = this.filters[moduleName] || { severity: '', category: '' };
      
      return moduleData.results.findings.filter(finding => {
        if (severity && finding.severity !== severity) {
          return false;
        }
        
        if (category) {
          const ruleCategory = finding.rule_id ? finding.rule_id : null;
          const metadataCategory = finding.metadata ? finding.metadata.category : null;
          
          if (ruleCategory !== category && metadataCategory !== category) {
            return false;
          }
        }
        
        return true;
      });
    },
    getShortFilePath(path) {
      if (!path) return 'Unknown';
      
      const parts = path.split('/');
      if (parts.length <= 2) return path;
      
      return '.../' + parts.slice(-2).join('/');
    },
    hasMetadata(metadata) {
      return Object.values(metadata).some(value => {
        if (Array.isArray(value)) return value.length > 0;
        return !!value;
      });
    },
    goBack() {
      this.$router.push('/apps');
    }
  },
  watch: {
    'reportData.modules': {
      immediate: true,
      handler() {
        this.loadCustomModuleUIs();
      }
    }
  }
});
</script>

<style scoped>
.report-container {
  display: flex;
  gap: 15px;
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.report-nav {
  position: sticky;
  top: 20px;
  width: 180px;
  height: fit-content;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  padding: 15px;
}

.nav-section h3 {
  margin: 0 0 12px 0;
  color: #2c3e50;
  font-size: 1rem;
}

.nav-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.nav-list li {
  margin-bottom: 6px;
}

.nav-divider {
  margin: 12px 0 8px 0;
  padding-top: 12px;
  border-top: 1px solid #eee;
  color: #666;
  font-weight: 600;
  font-size: 0.85rem;
}

.nav-link {
  display: block;
  padding: 6px 10px;
  color: #2c3e50;
  text-decoration: none;
  border-radius: 4px;
  transition: background-color 0.2s;
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.nav-link:hover {
  background-color: #f8f9fa;
  color: #0366d6;
}

.report-main {
  flex: 1;
  min-width: 0; /* Prevents flex item from overflowing */
}

/* Smooth scrolling for navigation */
html {
  scroll-behavior: smooth;
}

/* Offset for fixed headers if you have any */
.module-section {
  scroll-margin-top: 20px;
}

/* Responsive design */
@media (max-width: 1024px) {
  .report-container {
    flex-direction: column;
  }
  
  .report-nav {
    position: relative;
    width: auto;
    top: 0;
  }
  
  .nav-list {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }
  
  .nav-list li {
    margin: 0;
  }
  
  .nav-divider {
    width: 100%;
    margin: 10px 0;
  }
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.spinner {
  border: 4px solid rgba(0, 0, 0, 0.1);
  border-radius: 50%;
  border-top: 4px solid #3498db;
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin-bottom: 20px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error-container {
  padding: 20px;
  background-color: #ffeeee;
  border-radius: 8px;
  text-align: center;
}

.summary-card, .hash-card, .overview-card, .module-section {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  padding: 20px;
  margin-bottom: 20px;
}

.summary-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
}

.app-info {
  flex: 2;
  min-width: 250px;
}

.app-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.scan-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  min-width: 200px;
  margin-top: 10px;
}

.status-badge {
  padding: 8px 16px;
  border-radius: 16px;
  text-transform: uppercase;
  font-weight: bold;
  font-size: 14px;
  margin-bottom: 12px;
}

.hash-grid {
  display: grid;
  gap: 10px;
}

.hash-item {
  display: flex;
  align-items: center;
}

.hash-label {
  width: 70px;
  font-weight: bold;
}

.hash-value {
  font-family: monospace;
  word-break: break-all;
}

.overview-card {
  padding: 20px;
}

.severity-overview {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 10px;
}

.modules-container {
  margin-top: 30px;
}

.no-results {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
  color: #6c757d;
  background-color: #f8f9fa;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  margin-top: 20px;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.module-section {
  margin-top: 30px;
  border-left: 5px solid #3498db;
}

.module-header {
  margin-bottom: 24px;
}

.module-title {
  font-size: 1.5rem;
  color: #212529;
  margin-bottom: 16px;
  font-weight: 600;
}

.section-title {
  font-size: 1.25rem;
  color: #343a40;
  margin-bottom: 12px;
  font-weight: 600;
}

.summary-section {
  background-color: #f8f9fa;
  border-radius: 8px;
  padding: 20px;
  margin-top: 10px;
}

.summary-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.summary-card {
  background-color: #fff;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.summary-label {
  font-weight: 600;
  margin-bottom: 8px;
  color: #495057;
  font-size: 0.9rem;
}

.summary-value {
  font-size: 1.1rem;
  font-weight: 500;
}

.severity-counts, .category-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.severity-badge, .category-badge {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 0.85rem;
  font-weight: 600;
}

.severity-error, .severity-high {
  background-color: #f8d7da;
  color: #721c24;
}

.severity-warning, .severity-medium {
  background-color: #fff3cd;
  color: #856404;
}

.severity-info, .severity-low {
  background-color: #d1ecf1;
  color: #0c5460;
}

.category-badge {
  background-color: #e2e3e5;
  color: #383d41;
}

.findings-section {
  margin-top: 24px;
}

.findings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.findings-filters {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-group label {
  font-weight: 600;
  color: #495057;
  font-size: 0.9rem;
}

.filter-select {
  padding: 6px 12px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  background-color: white;
  font-size: 0.9rem;
  color: #495057;
}

.findings-list {
  display: grid;
  gap: 16px;
}

.finding-card {
  background-color: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  border-left: 4px solid transparent;
}

.finding-card:nth-child(odd) {
  background-color: #f9f9f9;
}

.finding-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  align-items: center;
}

.finding-severity {
  padding: 4px 12px;
  border-radius: 16px;
  font-size: 0.8rem;
  font-weight: 600;
}

.finding-rule {
  font-size: 0.9rem;
  color: #6c757d;
  font-weight: 500;
}

.finding-message {
  font-size: 1rem;
  margin-bottom: 16px;
  line-height: 1.5;
}

.finding-location {
  background-color: #f8f9fa;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 16px;
  font-size: 0.9rem;
}

.location-details {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 8px;
}

.detail-label {
  font-weight: 600;
  color: #495057;
}

.location-code {
  margin-top: 12px;
  background-color: #f1f3f5;
  border-radius: 4px;
  padding: 12px;
  overflow-x: auto;
  max-width: 100%; /* Ensure it doesn't exceed parent width */
}

.location-code pre {
  margin: 0;
  white-space: pre-wrap; /* This is already set correctly */
  word-wrap: break-word; /* Add this to force long words to break */
  word-break: break-word; /* Modern browsers will respect this */
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 0.85rem;
  line-height: 1.6;
  max-width: 100%; /* Ensure content respects container limits */
}

.location-code code {
  display: block;
  max-width: 100%; /* Ensure content respects container limits */
}

.finding-metadata {
  background-color: #f8f9fa;
  border-radius: 6px;
  padding: 16px;
  font-size: 0.9rem;
}

.metadata-item {
  margin-bottom: 8px;
  line-height: 1.5;
}

.metadata-item:last-child {
  margin-bottom: 0;
}

.metadata-key {
  font-weight: 600;
  color: #495057;
}

.no-findings {
  padding: 32px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  color: #6c757d;
}

.empty-state .empty-icon {
  font-size: 32px;
  margin-bottom: 12px;
}

.raw-results {
  margin-top: 24px;
}

.code-container {
  background-color: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
  overflow-x: auto;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.code-container pre {
  margin: 0;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 0.85rem;
  line-height: 1.6;
}

.report-actions {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

button {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.back-button {
  background-color: #6c757d;
  color: white;
}

.refresh-button {
  background-color: #28a745;
  color: white;
}

.status-completed {
  background-color: #d4edda;
  color: #155724;
}

.status-failed {
  background-color: #f8d7da;
  color: #721c24;
}

.status-scanning {
  background-color: #cce5ff;
  color: #004085;
}

.status-pending {
  background-color: #fff3cd;
  color: #856404;
}

.status-unknown {
  background-color: #e2e3e5;
  color: #383d41;
}

/* Responsive styles */
@media (max-width: 768px) {
  .summary-card {
    flex-direction: column;
  }
  
  .scan-info {
    align-items: flex-start;
    margin-top: 20px;
  }
  
  .findings-header {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .findings-filters {
    margin-top: 12px;
    width: 100%;
  }
  
  .filter-group {
    width: 100%;
  }
  
  .filter-select {
    flex-grow: 1;
  }
  
  .summary-metrics {
    grid-template-columns: 1fr;
  }
}
</style>