<template>
  <div class="modal-backdrop" v-if="show" @click.self="closeModal">
    <div class="modal-container">
      <header class="modal-header">
        <h2>{{ title }}</h2>
        <button class="close-button" @click="closeModal">&times;</button>
      </header>

      <div class="modal-body">
        <div v-if="loading" class="loading">Loading...</div>
        <div v-if="error" class="error-message">{{ error }}</div>

        <form v-if="!loading" @submit.prevent="runProcess">
          <!-- Mode Selection -->
          <div class="form-group">
            <label class="form-label">Run Type:</label>
            <div class="radio-group">
              <label class="radio-label">
                <input type="radio" v-model="runType" value="module" />
                Module
              </label>
              <label class="radio-label">
                <input type="radio" v-model="runType" value="chain" />
                Chain
              </label>
            </div>
          </div>

          <!-- Module Selection -->
          <div v-if="runType === 'module'" class="form-group">
            <label class="form-label">Select Module:</label>
            <select v-model="selectedModule" class="form-select" required>
              <option value="" disabled>-- Select a module --</option>
              <optgroup label="Internal Modules">
                <option
                  v-for="module in internalModules"
                  :key="module.id"
                  :value="module.id"
                  :disabled="!module.active"
                >
                  {{ module.name }} {{ !module.active ? '(inactive)' : '' }}
                </option>
              </optgroup>
              <optgroup v-if="externalModules.length > 0" label="External Modules">
                <option
                  v-for="module in externalModules"
                  :key="module.id"
                  :value="module.id"
                  :disabled="!module.active"
                >
                  {{ module.name }} {{ !module.active ? '(inactive)' : '' }}
                </option>
              </optgroup>
            </select>
          </div>

          <!-- Chain Selection -->
          <div v-if="runType === 'chain'" class="form-group">
            <label class="form-label">Select Chain:</label>
            <select v-model="selectedChain" class="form-select" required>
              <option value="" disabled>-- Select a chain --</option>
              <option v-for="chain in chains" :key="chain.name" :value="chain.name">
                {{ chain.name }}
              </option>
            </select>
          </div>

          <!-- Task Options -->
          <div class="form-group">
            <label class="form-label">Application:</label>
            <select v-model="selectedApp" class="form-select" required>
              <option value="" disabled>-- Select an application --</option>
              <option v-for="app in apps" :key="app.file_hash" :value="app.file_hash">
                {{ app.original_name }}
              </option>
            </select>
          </div>

          <!-- Run Button -->
          <div class="form-actions">
            <button type="submit" class="submit-button" :disabled="isSubmitDisabled">
              Run {{ runType === 'module' ? 'Module' : 'Chain' }}
            </button>
          </div>
        </form>

        <!-- Results -->
        <div v-if="taskResult" class="result-section">
          <h3>Task Submitted</h3>
          <div class="result-info">
            <p><strong>Task ID:</strong> {{ taskResult.task_id }}</p>
            <p><strong>Status:</strong> {{ taskResult.status }}</p>
            <p>{{ taskResult.message }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'RunModuleModal',
  props: {
    show: {
      type: Boolean,
      default: false,
    },
    appData: {
      type: Object,
      default: null,
    },
    preselectedModule: {
      type: Object,
      default: null,
    },
  },
  data() {
    return {
      runType: 'module',
      internalModules: [],
      externalModules: [],
      chains: [],
      apps: [],
      selectedModule: '',
      selectedChain: '',
      selectedApp: '',
      loading: false,
      error: null,
      taskResult: null,
      externalModuleId: null,
    };
  },
  computed: {
    title() {
      return this.runType === 'module' ? 'Run Module' : 'Run Chain';
    },
    isSubmitDisabled() {
      if (this.runType === 'module') {
        return !this.selectedModule || !this.selectedApp;
      } else {
        return !this.selectedChain || !this.selectedApp;
      }
    },
  },
  watch: {
    show(newVal) {
      if (newVal) {
        this.initialize();
      }
    },
    appData(newVal) {
      if (newVal && newVal.file_hash) {
        this.selectedApp = newVal.file_hash;
      }
    },
    preselectedModule(newVal) {
      if (newVal) {
        if (newVal.isExternal) {
          this.externalModuleId = newVal.id;
        } else {
          this.selectedModule = newVal.id;
        }
      }
    },
  },
  methods: {
    initialize() {
      this.resetForm();
      this.fetchModules();
      this.fetchChains();
      this.fetchApps();

      if (this.appData && this.appData.file_hash) {
        this.selectedApp = this.appData.file_hash;
      }

      if (this.preselectedModule) {
        if (this.preselectedModule.isExternal) {
          this.externalModuleId = this.preselectedModule.id;
        } else {
          this.selectedModule = this.preselectedModule.id;
        }
      }
    },
    resetForm() {
      this.selectedModule = '';
      this.selectedChain = '';
      this.error = null;
      this.taskResult = null;
      this.externalModuleId = null;
    },
    async fetchModules() {
      try {
        this.loading = true;
        const response = await fetch('/api/v1/modules/all');
        if (!response.ok) throw new Error('Failed to fetch modules');
        const allModules = await response.json();

        this.internalModules = allModules.filter(m => !m.is_external);
        this.externalModules = allModules.filter(m => m.is_external);
      } catch (err) {
        this.error = 'Error loading modules: ' + err.message;
        console.error('Error fetching modules:', err);
      } finally {
        this.loading = false;
      }
    },
    async fetchChains() {
      try {
        this.loading = true;
        const response = await fetch('/api/v1/chains');
        if (!response.ok) throw new Error('Failed to fetch chains');
        this.chains = await response.json();
      } catch (err) {
        this.error = 'Error loading chains: ' + err.message;
        console.error('Error fetching chains:', err);
      } finally {
        this.loading = false;
      }
    },
    async fetchApps() {
      try {
        this.loading = true;
        const response = await fetch('/api/v1/apps?limit=100');
        if (!response.ok) throw new Error('Failed to fetch apps');
        const data = await response.json();
        this.apps = data.apps || [];
      } catch (err) {
        this.error = 'Error loading applications: ' + err.message;
        console.error('Error fetching apps:', err);
      } finally {
        this.loading = false;
      }
    },
    async runProcess() {
      this.error = null;
      this.taskResult = null;

      try {
        this.loading = true;

        if (this.runType === 'module') {
          await this.runModule();
        } else {
          await this.runChain();
        }
      } catch (err) {
        this.error = `Error running ${this.runType}: ${err.message}`;
        console.error(`Error running ${this.runType}:`, err);
      } finally {
        this.loading = false;
      }
    },
    async runModule() {
      if (!this.selectedModule) {
        throw new Error('No module selected');
      }

      const selectedModule = [...this.internalModules, ...this.externalModules].find(m => m.id === this.selectedModule);
      if (!selectedModule) {
        throw new Error('Selected module not found');
      }

      const url = `/api/v1/modules/${selectedModule.id}/run`;
      const requestBody = {
        file_hash: this.selectedApp,
        is_external: selectedModule.is_external,
      };

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to run module');
      }

      this.taskResult = await response.json();
      this.$emit('task-submitted', this.taskResult);
    },
    async runChain() {
      const url = `/api/v1/chains/${this.selectedChain}/run`;
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ file_hash: this.selectedApp }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to run chain');
      }

      this.taskResult = await response.json();
      this.$emit('task-submitted', this.taskResult);
    },
    closeModal() {
      this.$emit('close');
    },
  },
};
</script>

<style>
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-container {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid #e5e7eb;
}

.modal-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.close-button {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6b7280;
}

.modal-body {
  padding: 24px;
}

.loading {
  display: flex;
  justify-content: center;
  padding: 20px;
  font-weight: 500;
}

.error-message {
  color: #dc2626;
  background-color: #fee2e2;
  padding: 12px;
  border-radius: 4px;
  margin-bottom: 16px;
}

.form-group {
  margin-bottom: 20px;
}

.form-label {
  display: block;
  font-weight: 500;
  margin-bottom: 8px;
}

.radio-group {
  display: flex;
  gap: 16px;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.form-select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background-color: white;
  font-size: 14px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 24px;
}

.submit-button {
  background-color: #4f46e5;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
}

.submit-button:hover {
  background-color: #4338ca;
}

.submit-button:disabled {
  background-color: #9ca3af;
  cursor: not-allowed;
}

.result-section {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

.result-info {
  background-color: #f3f4f6;
  border-radius: 4px;
  padding: 16px;
}

.result-info p {
  margin: 8px 0;
}
</style>
