<template>
  <div class="trufflehog-report">
    <div v-if="!hasResults" class="module-empty">
      <div class="empty-icon">🔍</div>
      <h3>Secret Scanner</h3>
      <p>No secrets found in the analyzed files.</p>
    </div>

    <div v-else class="findings-container">
      <div class="module-header">
        <h3 class="module-title">Secret Detection Results</h3>
        
        <!-- Summary Cards -->
        <div class="summary-grid">
          <div class="summary-card">
            <div class="card-value">{{ totalSecrets }}</div>
            <div class="card-label">Total Secrets Found</div>
          </div>
          <div class="summary-card">
            <div class="card-value">{{ uniqueDetectors.length }}</div>
            <div class="card-label">Types of Secrets</div>
          </div>
        </div>

        <!-- Findings List -->
        <div class="findings-section">
          <div class="filters">
            <select v-model="currentDetector" class="filter-select">
              <option value="all">All Detectors</option>
              <option v-for="detector in uniqueDetectors" 
                      :key="detector" 
                      :value="detector">
                {{ detector }}
              </option>
            </select>
          </div>

          <div class="findings-list">
            <div v-for="(finding, index) in filteredFindings" 
                 :key="index"
                 class="finding-card">
              <div class="finding-header">
                <h4>{{ finding.name }}</h4>
                <div class="badge badge-error">{{ finding.severity }}</div>
              </div>
              <div class="finding-content">
                <div class="finding-location" v-if="finding.location">
                  <div class="location-item">
                    <strong>File:</strong> {{ finding.location.file }}
                  </div>
                  <div class="location-item">
                    <strong>Line:</strong> {{ finding.location.line }}
                  </div>
                  <div class="location-item">
                    <strong>Path:</strong> {{ finding.location.path }}
                  </div>
                </div>
                <div class="finding-details">
                  <div class="detail-row">
                    <strong>Detector:</strong> {{ finding.metadata.detector }}
                  </div>
                  <div class="detail-row">
                    <strong>Entropy:</strong> {{ finding.metadata.entropy.toFixed(2) }}
                  </div>
                  <div class="detail-row">
                    <strong>Verified:</strong> 
                    <span :class="finding.metadata.verified ? 'verified' : 'unverified'">
                      {{ finding.metadata.verified ? 'Yes' : 'No' }}
                    </span>
                  </div>
                  <div class="secret-value">
                    <strong>Secret Value:</strong>
                    <div class="secret-container">
                      <code>{{ finding.metadata.secret_value }}</code>
                    </div>
                  </div>
                  <div class="finding-description">{{ finding.metadata.description }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'TrufflehogReport',
  props: {
    moduleData: {
      type: Object,
      required: true
    }
  },
  data() {
    return {
      currentDetector: 'all'
    }
  },
  computed: {
    hasResults() {
      return !!this.moduleData?.results?.length;
    },
    totalSecrets() {
      return this.moduleData?.results?.length || 0;
    },
    uniqueDetectors() {
      if (!this.moduleData?.results) return [];
      return [...new Set(this.moduleData.results.map(r => r.metadata.detector))];
    },
    filteredFindings() {
      if (!this.moduleData?.results) return [];
      if (this.currentDetector === 'all') return this.moduleData.results;
      return this.moduleData.results.filter(
        f => f.metadata.detector === this.currentDetector
      );
    }
  }
}
</script>

<style scoped>
.trufflehog-report {
  width: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', sans-serif;
  color: #333;
}

.module-empty {
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
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
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

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin: 20px 0;
}

.summary-card {
  background-color: #f8f9fa;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  text-align: center;
}

.card-value {
  font-size: 24px;
  font-weight: bold;
  color: #dc3545;
}

.card-label {
  color: #6c757d;
  margin-top: 8px;
  font-size: 0.9rem;
}

.findings-section {
  margin-top: 30px;
}

.filters {
  margin-bottom: 20px;
}

.filter-select {
  padding: 8px 12px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  background-color: white;
  font-size: 0.9rem;
  color: #495057;
  width: 200px;
}

.finding-card {
  background-color: white;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  margin-bottom: 15px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.finding-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 15px;
  background-color: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
}

.finding-header h4 {
  margin: 0;
  font-size: 1.1rem;
  color: #212529;
}

.badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 600;
}

.badge-error {
  background-color: #f8d7da;
  color: #721c24;
}

.finding-content {
  padding: 15px;
}

.finding-location {
  margin-bottom: 15px;
  padding: 12px;
  background-color: #f8f9fa;
  border-radius: 6px;
  font-size: 0.9rem;
}

.location-item {
  margin: 5px 0;
  color: #495057;
}

.location-item strong {
  margin-right: 8px;
  color: #495057;
  font-weight: 600;
}

.finding-details {
  font-size: 0.9rem;
  color: #495057;
}

.detail-row {
  margin: 8px 0;
}

.detail-row strong {
  margin-right: 8px;
  color: #495057;
  font-weight: 600;
}

.secret-value {
  margin: 15px 0;
}

.secret-container {
  margin-top: 8px;
  padding: 12px;
  background-color: #f1f3f5;
  border-radius: 4px;
  overflow-x: auto;
}

.secret-container code {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 0.85rem;
  color: #e83e8c;
  line-height: 1.6;
}

.finding-description {
  margin-top: 10px;
  padding: 8px;
  background-color: #f8f9fa;
  border-radius: 4px;
  color: #6c757d;
  font-size: 0.9rem;
}

.verified {
  color: #28a745;
  font-weight: 500;
}

.unverified {
  color: #ffc107;
  font-weight: 500;
}

@media (max-width: 768px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }
  
  .filter-select {
    width: 100%;
  }
  
  .finding-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  
  .finding-location {
    flex-direction: column;
  }
}
</style> 