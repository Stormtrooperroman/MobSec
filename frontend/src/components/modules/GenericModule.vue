<template>
  <div class="generic-module">
    <div v-if="!moduleData.results" class="module-empty">
      <div class="empty-icon">📊</div>
      <h3>No Results Available</h3>
      <p>This module did not produce any results or is still processing.</p>
    </div>

    <div v-else class="module-results">
      <!-- Module header with basic info -->
      <div class="module-header">
        <h3 class="module-title">{{ formatModuleName(moduleName) }} Results</h3>

        <!-- Show summary if available -->
        <div v-if="hasSummary" class="summary-section">
          <h4 class="section-title">Summary</h4>

          <!-- Severity counts with improved visualization -->
          <div v-if="hasSeverityCounts" class="summary-card">
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
          <div v-if="hasCategoryCounts" class="summary-card">
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
            <div v-for="(value, key) in filteredSummaryItems" :key="key" class="summary-card">
              <div class="summary-label">{{ formatKey(key) }}</div>
              <div class="summary-value">{{ value }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Findings section -->
      <div v-if="hasFindings" class="findings-section">
        <div class="findings-header">
          <h4 class="section-title">Findings ({{ moduleData.results.findings.length }})</h4>

          <div class="findings-filters">
            <div class="filter-group">
              <label for="severity-filter">Severity:</label>
              <select id="severity-filter" v-model="severityFilter" class="filter-select">
                <option value="">All Severities</option>
                <option v-for="severity in availableSeverities" :key="severity" :value="severity">
                  {{ severity }}
                </option>
              </select>
            </div>

            <div class="filter-group" v-if="availableCategories.length > 0">
              <label for="category-filter">Category:</label>
              <select id="category-filter" v-model="categoryFilter" class="filter-select">
                <option value="">All Categories</option>
                <option v-for="category in availableCategories" :key="category" :value="category">
                  {{ category }}
                </option>
              </select>
            </div>
          </div>
        </div>

        <div class="findings-list">
          <div v-for="(finding, index) in filteredFindings" :key="index" class="finding-card">
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
                  <span class="detail-label">Lines:</span> {{ finding.location.start_line }} -
                  {{ finding.location.end_line }}
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

          <div v-if="filteredFindings.length === 0" class="no-findings">
            <div class="empty-state">
              <span class="empty-icon">🔍</span>
              <p>No findings match your current filters.</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Raw Results Section -->
      <div v-if="!hasFindings && !hasSummary" class="raw-results">
        <h4 class="section-title">Raw Results</h4>
        <div class="code-container">
          <pre><code>{{ JSON.stringify(moduleData.results, null, 2) }}</code></pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'GenericModule',
  props: {
    moduleData: {
      type: Object,
      required: true,
    },
    moduleName: {
      type: String,
      required: true,
    },
    fileInfo: {
      type: Object,
      default: () => ({}),
    },
  },
  data() {
    return {
      severityFilter: '',
      categoryFilter: '',
    };
  },
  computed: {
    hasSummary() {
      return this.moduleData.results && this.moduleData.results.summary;
    },
    hasFindings() {
      return (
        this.moduleData.results &&
        this.moduleData.results.findings &&
        Array.isArray(this.moduleData.results.findings) &&
        this.moduleData.results.findings.length > 0
      );
    },
    hasSeverityCounts() {
      return this.hasSummary && this.moduleData.results.summary.severity_counts;
    },
    hasCategoryCounts() {
      return this.hasSummary && this.moduleData.results.summary.category_counts;
    },
    filteredSummaryItems() {
      if (!this.hasSummary) return {};

      // Filter out special summary items that are displayed separately
      const exclude = ['severity_counts', 'category_counts'];
      return Object.fromEntries(
        Object.entries(this.moduleData.results.summary).filter(([key]) => !exclude.includes(key)),
      );
    },
    availableSeverities() {
      if (!this.hasFindings) return [];

      const severities = new Set();
      this.moduleData.results.findings.forEach(finding => {
        if (finding.severity) {
          severities.add(finding.severity);
        }
      });

      return Array.from(severities);
    },
    availableCategories() {
      if (!this.hasFindings) return [];

      const categories = new Set();
      this.moduleData.results.findings.forEach(finding => {
        if (finding.rule_id) {
          categories.add(finding.rule_id.split('-')[0]);
        }
        if (finding.metadata && finding.metadata.category) {
          categories.add(finding.metadata.category);
        }
      });

      return Array.from(categories).filter(c => c);
    },
    filteredFindings() {
      if (!this.hasFindings) return [];

      return this.moduleData.results.findings.filter(finding => {
        // Filter by severity if set
        if (this.severityFilter && finding.severity !== this.severityFilter) {
          return false;
        }

        // Filter by category if set
        if (this.categoryFilter) {
          const ruleCategory = finding.rule_id ? finding.rule_id.split('-')[0] : null;
          const metadataCategory = finding.metadata ? finding.metadata.category : null;

          if (ruleCategory !== this.categoryFilter && metadataCategory !== this.categoryFilter) {
            return false;
          }
        }

        return true;
      });
    },
  },
  methods: {
    formatModuleName(name) {
      return name
        .replace('_module', '')
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
    },
    formatKey(key) {
      // Convert snake_case to Title Case
      return key
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
    },
    getShortFilePath(path) {
      if (!path) return 'Unknown';

      // Try to get the file name only, or the shortest relevant path
      const parts = path.split('/');
      if (parts.length <= 2) return path;

      // Return the last two path components
      return '.../' + parts.slice(-2).join('/');
    },
    hasMetadata(metadata) {
      return Object.values(metadata).some(value => {
        if (Array.isArray(value)) return value.length > 0;
        return !!value;
      });
    },
  },
};
</script>

<style scoped>
.generic-module {
  width: 100%;
  font-family:
    -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', sans-serif;
  color: #333;
}

/* Empty state styling */
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

/* Module header styling */
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

/* Summary section styling */
.summary-section {
  background-color: #fff;
  border-radius: 8px;
  padding: 20px;
  margin-top: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.summary-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.summary-card {
  background-color: #f8f9fa;
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

.severity-counts,
.category-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.severity-badge,
.category-badge {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 0.85rem;
  font-weight: 600;
}

.severity-error,
.severity-high {
  background-color: #f8d7da;
  color: #721c24;
}

.severity-warning,
.severity-medium {
  background-color: #fff3cd;
  color: #856404;
}

.severity-info,
.severity-low {
  background-color: #d1ecf1;
  color: #0c5460;
}

.category-badge {
  background-color: #e2e3e5;
  color: #383d41;
}

/* Findings section styling */
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

/* Finding card styling */
.findings-list {
  display: grid;
  gap: 16px;
}

.finding-card {
  background-color: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
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
}

.location-code pre {
  margin: 0;
  white-space: pre-wrap;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 0.85rem;
  line-height: 1.6;
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

/* Empty findings state */
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

/* Raw results styling */
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

@media (max-width: 768px) {
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
