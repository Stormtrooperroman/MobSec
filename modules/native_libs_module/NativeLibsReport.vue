<template>
  <div class="native-libs-report">
    <div v-if="!hasResults" class="module-empty">
      <div class="empty-icon">🔧</div>
      <h3>Native Libraries Analysis</h3>
      <p>No native libraries data available for this APK.</p>
    </div>

    <div v-else class="native-libs-results">
      <div class="module-header">
        <h3 class="module-title">Native Libraries Analysis</h3>
        
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-header">
              <h4>Total Libraries</h4>
              <div class="badge badge-info">{{ metrics.total_libs }}</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <h4>Debug Symbols</h4>
              <div :class="['badge', hasDebugSymbols ? 'badge-warning' : 'badge-success']">
                {{ debugSymbolsCount }} Found
              </div>
            </div>
          </div>
        </div>

        <div class="analysis-grid">
          <div class="analysis-card">
            <div class="card-header">
              <h5>Library Details</h5>
              <div class="badge badge-info">{{ libraries.length }} Total</div>
            </div>
            <div class="card-content">
              <div v-if="libraries.length" class="lib-list">
                <div v-for="lib in libraries" 
                     :key="lib.name" 
                     class="lib-item"
                     :class="{ 'has-debug': lib.has_debug_symbols }">
                  <div class="lib-header">
                    <div class="lib-name">{{ formatLibName(lib.name) }}</div>
                  </div>
                  <div class="lib-details">
                    <div class="detail-item">
                      <span class="detail-label">Symbols:</span>
                      <span class="detail-value">{{ lib.symbols }}</span>
                    </div>
                    <div class="detail-item">
                      <span class="detail-label">Imported Functions:</span>
                      <span class="detail-value">{{ lib.imported_functions }}</span>
                    </div>
                    <div class="detail-item">
                      <span class="detail-label">Sections:</span>
                      <span class="detail-value">{{ lib.sections }}</span>
                    </div>
                    <div class="detail-item">
                      <span class="detail-label">Debug Symbols:</span>
                      <span :class="['detail-value', lib.has_debug_symbols ? 'text-warning' : 'text-success']">
                        {{ lib.has_debug_symbols ? 'Present' : 'Not Present' }}
                      </span>
                    </div>
                    <div v-if="lib.imported_libraries?.length" class="detail-item-full">
                      <span class="detail-label">Imported Libraries:</span>
                      <div class="detail-list">
                        <span v-for="impLib in lib.imported_libraries" 
                              :key="impLib" 
                              class="detail-tag">
                          {{ impLib }}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <p v-else class="no-items">No libraries found</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'NativeLibsReport',
  props: {
    moduleData: {
      type: Object,
      required: true
    }
  },
  computed: {
    hasResults() {
      return this.moduleData?.results !== undefined;
    },
    metrics() {
      return this.moduleData?.results?.metrics || {
        total_libs: 0,
        architectures: {}
      };
    },
    libraries() {
      return this.moduleData?.results?.libraries || [];
    },
    hasDebugSymbols() {
      return this.libraries.some(lib => lib.has_debug_symbols);
    },
    debugSymbolsCount() {
      return this.libraries.filter(lib => lib.has_debug_symbols).length;
    }
  },
  methods: {
    formatLibName(name) {
      return name.split('/').pop();
    }
  }
};
</script>

<style scoped>
.native-libs-report {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #333;
}

.module-header {
  background-color: #f4f6f9;
  padding: 20px;
  border-radius: 8px;
}

.module-title {
  font-size: 1.5rem;
  margin-bottom: 20px;
  color: #2c3e50;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 15px;
  margin-bottom: 20px;
}

.stat-card {
  background: white;
  padding: 15px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.stat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-header h4 {
  margin: 0;
  font-size: 1rem;
  color: #495057;
}

.analysis-grid {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.analysis-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  width: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px;
  border-bottom: 1px solid #e9ecef;
}

.card-header h5 {
  margin: 0;
  font-size: 1.1rem;
  color: #2c3e50;
}

.card-content {
  padding: 15px;
}

.badge {
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}

.badge-warning {
  background-color: #ffc107;
  color: #212529;
}

.badge-success {
  background-color: #28a745;
  color: white;
}

.badge-info {
  background-color: #17a2b8;
  color: white;
}

.badge-primary {
  background-color: #007bff;
  color: white;
}

.lib-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.lib-item {
  padding: 15px;
  border-radius: 6px;
  background-color: #f8f9fa;
  border-left: 4px solid #17a2b8;
}

.lib-item.has-debug {
  border-left-color: #ffc107;
}

.lib-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.lib-name {
  font-weight: 600;
  color: #2c3e50;
}

.lib-details {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px;
}

.detail-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 0;
}

.detail-label {
  color: #6c757d;
  font-size: 0.9rem;
}

.detail-value {
  font-weight: 500;
  color: #2c3e50;
}

.text-warning {
  color: #ffc107;
}

.text-success {
  color: #28a745;
}

.no-items {
  color: #666;
  font-style: italic;
}

.module-empty {
  text-align: center;
  padding: 40px;
  color: #6c757d;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.detail-item-full {
  grid-column: 1 / -1;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #e9ecef;
}

.detail-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.detail-tag {
  background-color: #e9ecef;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.9rem;
  color: #495057;
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
  
  .lib-details {
    grid-template-columns: 1fr;
  }
}
</style> 