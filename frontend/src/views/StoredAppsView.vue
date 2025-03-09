<template>
  <div class="apps-container">
    <div class="apps-header">
      <h2 class="apps-title">Stored Applications</h2>
    </div>

    <div v-if="loading" class="loading-container">
      <div class="spinner"></div>
      <p>Loading applications...</p>
    </div>
    
    <div v-if="error" class="error-container">
      <div class="error-icon">!</div>
      <p>{{ error }}</p>
      <button @click="fetchApps" class="retry-button">Retry</button>
    </div>

    <div v-if="!loading && !error && apps.length === 0" class="empty-state">
      <div class="empty-icon">📁</div>
      <h3>No Applications Found</h3>
      <p>Upload your first application to begin analysis</p>
      <router-link to="/" class="upload-empty-button">Upload Application</router-link>
    </div>

    <div v-else-if="!loading && !error" class="table-wrapper">
      <div class="table-container">
        <table class="apps-table">
          <thead>
            <tr>
              <th class="table-header">App Name</th>
              <th class="table-header">File Type</th>
              <th class="table-header">Uploaded At</th>
              <th class="table-header">Status</th>
              <th class="table-header">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="app in apps" :key="app.file_hash" class="table-row">
              <td class="table-cell app-name">
                <div class="app-icon">{{ app.original_name.charAt(0).toUpperCase() }}</div>
                <span>{{ app.original_name }}</span>
              </td>
              <td class="table-cell file-type">
                {{ app.file_type || 'Unknown' }}
              </td>
              <td class="table-cell">{{ formatDate(app.timestamp) }}</td>
              <td class="table-cell">
                <span :class="['status-badge', getStatusClass(app.scan_status)]">
                  <span class="status-dot"></span>
                  {{ app.scan_status }}
                </span>
              </td>
              <td class="table-cell actions-cell">
                <button @click="runAnalysis(app)" class="action-button run-button">
                  <span class="action-icon">▶</span>
                  Analyze
                </button>
                <button 
                  @click="viewReport(app.file_hash)" 
                  class="action-button report-button"
                  :disabled="app.scan_status === 'N/A'">
                  <span class="action-icon">📊</span>
                  View Report
                </button>
                <button @click="deleteApp(app.file_hash)" class="action-button delete-button">
                  <span class="action-icon">🗑️</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pagination">
        <button @click="prevPage" :disabled="skip === 0" class="page-button">
          <span class="page-arrow">←</span> Previous
        </button>
        <div class="page-info">
          <span class="current-page">Page {{ currentPage }}</span>
          <span class="page-count">of {{ Math.ceil(total / limit) || 1 }}</span>
        </div>
        <button @click="nextPage" :disabled="apps.length < limit" class="page-button">
          Next <span class="page-arrow">→</span>
        </button>
      </div>
    </div>
    
    <!-- Run Module/Chain Modal -->
    <RunModuleModal 
      :show="showRunModal" 
      :appData="selectedApp"
      @close="showRunModal = false"
      @task-submitted="handleTaskSubmitted"
    />
  </div>
</template>

<script>
import RunModuleModal from './RunModuleModal.vue';

export default {
  name: 'StoredAppsView',
  components: {
    RunModuleModal
  },
  data() {
    return {
      apps: [],
      total: 0,
      skip: 0,
      limit: 10,
      loading: false,
      error: null,
      showRunModal: false,
      selectedApp: null
    };
  },
  computed: {
    currentPage() {
      return Math.floor(this.skip / this.limit) + 1;
    }
  },
  methods: {
    formatDate(date) {
      if (!date) return "N/A";
      const options = { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      };
      return new Date(date).toLocaleString(undefined, options);
    },
    getStatusClass(status) {
      const classes = {
        'completed': 'status-complete',
        'pending': 'status-progress',
        'failed': 'status-failed'
      };
      return classes[status] || 'status-default';
    },
    async fetchApps() {
      this.loading = true;
      this.error = null;
      try {
        const response = await fetch(`/api/v1/apps?skip=${this.skip}&limit=${this.limit}`);
        const data = await response.json();
        this.apps = data.apps || [];
        this.total = data.total || 0;
      } catch (error) {
        this.error = 'Error fetching applications. Please try again.';
        console.error(error);
      } finally {
        this.loading = false;
      }
    },
    runAnalysis(app) {
      this.selectedApp = app;
      this.showRunModal = true;
    },
    handleTaskSubmitted(result) {
      // You could show a notification or update the app status
      console.log('Task submitted:', result);
      
      // Optionally close the modal after submission
      setTimeout(() => {
        this.showRunModal = false;
        // Refresh the apps list to show updated status
        this.fetchApps();
      }, 2000);
    },
    async viewReport(fileHash) {
      try {
        this.$router.push(`/apps/report/${fileHash}`);
      } catch (error) {
        console.error('Error fetching report:', error);
      }
    },
    async deleteApp(fileHash) {
      if (confirm('Are you sure you want to delete this app?')) {
        try {
          await fetch(`/api/v1/apps/${fileHash}`, { method: 'DELETE' });
          this.fetchApps();  // Refresh list after deletion
        } catch (error) {
          console.error('Error deleting app:', error);
        }
      }
    },
    nextPage() {
      if (this.apps.length >= this.limit) {
        this.skip += this.limit;
        this.fetchApps();
      }
    },
    prevPage() {
      if (this.skip > 0) {
        this.skip -= this.limit;
        this.fetchApps();
      }
    }
  },
  mounted() {
    this.fetchApps();
  }
};
</script>

<style>
.apps-container {
  background-color: #ffffff;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  padding: 28px;
  max-width: 1200px;
  margin: 0 auto;
}

.apps-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.apps-title {
  font-size: 24px;
  font-weight: 700;
  color: #1a202c;
  margin: 0;
}

.upload-empty-button {
  margin-top: 20px;
  padding: 10px 20px;
  background-color: #4f46e5;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s;
}

.upload-empty-button:hover {
  background-color: #4338ca;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
}

.spinner {
  border: 3px solid rgba(0, 0, 0, 0.1);
  border-radius: 50%;
  border-top: 3px solid #4f46e5;
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 0;
  color: #dc2626;
}

.error-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background-color: #fee2e2;
  color: #dc2626;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: bold;
  margin-bottom: 16px;
}

.retry-button {
  margin-top: 16px;
  padding: 8px 16px;
  background-color: #f3f4f6;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 0;
  color: #6b7280;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state h3 {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: #4b5563;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.table-wrapper {
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  overflow: hidden;
}

.table-container {
  overflow-x: auto;
}

.apps-table {
  width: 100%;
  border-collapse: collapse;
}

.table-header {
  padding: 14px 20px;
  text-align: left;
  font-size: 13px;
  font-weight: 600;
  color: #4b5563;
  background-color: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.table-row {
  transition: background-color 0.2s;
}

.table-row:hover {
  background-color: #f9fafb;
}

.table-cell {
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  font-size: 14px;
  color: #1f2937;
  vertical-align: middle;
}

.app-name {
  display: flex;
  align-items: center;
}

.app-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background-color: #e5e7eb;
  margin-right: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #4b5563;
  font-weight: 600;
}

.file-type {
  font-family: monospace;
  font-size: 1.5em;
  color: #4b5563;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 500;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}

.status-complete {
  background-color: #ecfdf5;
  color: #065f46;
}

.status-complete .status-dot {
  background-color: #10b981;
}

.status-progress {
  background-color: #fffbeb;
  color: #92400e;
}

.status-progress .status-dot {
  background-color: #f59e0b;
}

.status-failed {
  background-color: #fef2f2;
  color: #b91c1c;
}

.status-failed .status-dot {
  background-color: #ef4444;
}

.status-default {
  background-color: #f3f4f6;
  color: #1f2937;
}

.status-default .status-dot {
  background-color: #9ca3af;
}

.actions-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-button {
  display: flex;
  align-items: center;
  background: none;
  border: none;
  font-size: 14px;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  font-weight: 500;
}

.action-icon {
  margin-right: 6px;
}

.run-button {
  color: #059669;
  background-color: #ecfdf5;
}

.run-button:hover {
  background-color: #d1fae5;
}

.report-button {
  color: #1d4ed8;
  background-color: #eff6ff;
}

.report-button:hover:not(:disabled) {
  background-color: #dbeafe;
}

.report-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background-color: #f3f4f6;
  color: #9ca3af;
}

.delete-button {
  color: #dc2626;
  background-color: #fef2f2;
  padding: 6px;
}

.delete-button:hover {
  background-color: #fee2e2;
}

.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background-color: #f9fafb;
  border-top: 1px solid #e5e7eb;
}

.page-button {
  display: flex;
  align-items: center;
  padding: 8px 14px;
  border: 1px solid #d1d5db;
  background-color: white;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: #4b5563;
  transition: all 0.2s;
}

.page-button:hover:not(:disabled) {
  background-color: #f3f4f6;
  border-color: #9ca3af;
}

.page-button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
  background-color: #f3f4f6;
}

.page-arrow {
  font-size: 16px;
}

.page-info {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.current-page {
  font-weight: 600;
  color: #1f2937;
  font-size: 14px;
}

.page-count {
  font-size: 12px;
  color: #6b7280;
  margin-top: 2px;
}

@media (max-width: 768px) {
  .apps-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  
  .actions-cell {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }
  
  .table-header, .table-cell {
    padding: 12px 16px;
  }
  
  .table-container {
    overflow-x: auto;
  }
  
  .file-type {
    max-width: 150px;
  }
}
</style>