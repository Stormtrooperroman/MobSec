<template>
  <div class="modules-container">
    <div class="header">
      <h2>Available Modules</h2>
    </div>

    <div v-if="externalModules.length > 0" class="modules-section">
      <h3 class="section-title">External Modules</h3>
      <div class="modules-grid">
        <div v-for="module in externalModules" :key="module.module_id" class="module-card external-module-card">
          <div class="module-content">
            <div class="module-header">
              <h3>
                {{ module.config.name }}
                <span class="external-badge">External</span>
              </h3>
              <div class="status-container">
                <span :class="['status-badge', module.status === 'active' ? 'active' : 'inactive']">
                  <font-awesome-icon :icon="module.status === 'active' ? 'check-circle' : 'times-circle'" />
                  {{ module.status === 'active' ? 'Active' : 'Inactive' }}
                </span>
              </div>
            </div>
            <p class="module-description">{{ module.config.description }}</p>
            <div class="module-details">
              <div class="detail-item">
                <span class="detail-label">ID:</span>
                <span class="detail-value">{{ module.module_id }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Version:</span>
                <span class="detail-value">{{ module.config.version }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Formats:</span>
                <span class="detail-value">{{ module.config.input_formats.join(', ') }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="modules-section">
      <h3 v-if="externalModules.length > 0" class="section-title">Internal Modules</h3>
      <div class="modules-grid">
        <div v-for="module in modules" :key="module.id" class="module-card">
          <div class="module-content">
            <div class="module-header">
              <h3>{{ module.name }}</h3>
              <div class="status-container">
                <span :class="['status-badge', module.active ? 'active' : 'inactive']">
                  <font-awesome-icon :icon="module.active ? 'check-circle' : 'times-circle'" />
                  {{ module.active ? 'Active' : 'Inactive' }}
                </span>
              </div>
            </div>
            <p class="module-description">{{ module.description }}</p>
            <div class="module-details">
              <div class="detail-item">
                <span class="detail-label">ID:</span>
                <span class="detail-value">{{ module.id }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Version:</span>
                <span class="detail-value">{{ module.version || 'N/A' }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Formats:</span>
                <span class="detail-value">{{ module.input_formats ? module.input_formats.join(', ') : 'All' }}</span>
              </div>
            </div>
          </div>
          <div class="button-container">
            <button
              class="action-button"
              :class="module.active ? 'warning' : 'success'"
              @click="toggleModule(module)"
              :disabled="module.isLoading"
            >
              <font-awesome-icon
                :icon="module.isLoading ? 'spinner' : module.active ? 'stop' : 'play'"
                :spin="module.isLoading"
              />
              {{ module.active ? 'Deactivate' : 'Activate' }}
            </button>
            <button class="action-button rebuild" @click="rebuildModule(module)" :disabled="module.isRebuilding">
              <font-awesome-icon icon="sync" :spin="module.isRebuilding" />
              Rebuild
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="modules-section">
      <h3 class="section-title">Emulators</h3>
      <div class="modules-grid">
        <div v-for="emulator in emulators" :key="emulator.name" class="module-card emulator-card">
          <div class="module-content">
            <div class="module-header">
              <h3>{{ emulator.name }}</h3>
              <div class="status-container">
                <span :class="['status-badge', emulator.status === 'running' ? 'active' : 'inactive']">
                  <font-awesome-icon :icon="emulator.status === 'running' ? 'check-circle' : 'times-circle'" />
                  {{ emulator.status === 'running' ? 'Running' : 'Stopped' }}
                </span>
              </div>
            </div>
            <div class="module-details">
              <div class="detail-item">
                <span class="detail-label">Name:</span>
                <span class="detail-value">{{ emulator.name }}</span>
              </div>
              <div class="detail-item" v-if="emulator.config && emulator.config.description">
                <span class="detail-label">Description:</span>
                <span class="detail-value">{{ emulator.config.description }}</span>
              </div>
              <div class="detail-item" v-if="emulator.ports && Object.keys(emulator.ports).length > 0">
                <span class="detail-label">Ports:</span>
                <span class="detail-value">
                  <span v-for="(port, protocol) in emulator.ports" :key="protocol" class="port-badge">
                    {{ protocol }}: {{ port }}
                  </span>
                </span>
              </div>
              <div class="detail-item" v-if="emulator.container_id">
                <span class="detail-label">Container:</span>
                <span class="detail-value">{{ emulator.container_id.substring(0, 12) }}</span>
              </div>
              <div class="detail-item" v-if="emulator.status === 'running'">
                <span class="detail-label">Status:</span>
                <span class="detail-value">{{ emulator.status }}</span>
              </div>
            </div>
          </div>
          <div class="button-container">
            <button
              class="action-button"
              :class="emulator.status === 'running' ? 'warning' : 'success'"
              @click="toggleEmulator(emulator)"
              :disabled="emulator.isLoading"
            >
              <font-awesome-icon
                :icon="emulator.isLoading ? 'spinner' : emulator.status === 'running' ? 'stop' : 'play'"
                :spin="emulator.isLoading"
              />
              {{ emulator.status === 'running' ? 'Stop' : 'Start' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ModulesView',
  data() {
    return {
      modules: [],
      externalModules: [],
      emulators: [],
    };
  },
  methods: {
    async fetchModules() {
      try {
        const response = await fetch('/api/v1/modules');
        const data = await response.json();
        this.modules = data.map(module => ({
          ...module,
          isLoading: false,
          isRebuilding: false,
        }));
      } catch (error) {
        console.error('Error fetching modules:', error);
      }
    },
    async fetchExternalModules() {
      try {
        const response = await fetch('/api/v1/external-modules');
        const data = await response.json();
        this.externalModules = data;
      } catch (error) {
        console.error('Error fetching external modules:', error);
      }
    },
    async toggleModule(module) {
      if (module.isLoading) return;

      module.isLoading = true;
      try {
        const response = await fetch(`/api/v1/modules/${module.id}/toggle`, {
          method: 'POST',
        });
        if (response.ok) {
          module.active = !module.active;
        }
      } catch (error) {
        console.error('Error toggling module:', error);
      } finally {
        module.isLoading = false;
      }
    },
    async rebuildModule(module) {
      if (module.isRebuilding) return;

      module.isRebuilding = true;
      try {
        const response = await fetch(`/api/v1/modules/${module.id}/rebuild`, {
          method: 'POST',
        });
        if (response.ok) {
          await this.fetchModules();
        }
      } catch (error) {
        console.error('Error rebuilding module:', error);
      } finally {
        module.isRebuilding = false;
      }
    },
    async fetchEmulators() {
      try {
        const response = await fetch('/api/v1/emulators/list');
        const data = await response.json();
        this.emulators = data.emulators.map(emulator => ({
          ...emulator,
          isLoading: false,
        }));
      } catch (error) {
        console.error('Error fetching emulators:', error);
      }
    },
    async toggleEmulator(emulator) {
      if (emulator.isLoading) return;

      emulator.isLoading = true;
      try {
        const endpoint = emulator.status === 'running' ? '/api/v1/emulators/stop' : '/api/v1/emulators/start';
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ name: emulator.name }),
        });
        
        if (response.ok) {
          await this.fetchEmulators();
        } else {
          const error = await response.json();
          console.error('Error toggling emulator:', error);
        }
      } catch (error) {
        console.error('Error toggling emulator:', error);
      } finally {
        emulator.isLoading = false;
      }
    },
  },
  mounted() {
    this.fetchModules();
    this.fetchExternalModules();
    this.fetchEmulators();
    

  },
};
</script>

<style>
.modules-container {
  background-color: white;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  padding: 32px;
  max-width: 1400px;
  margin: 0 auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding-bottom: 16px;
  border-bottom: 2px solid #f3f4f6;
}

.header h2 {
  font-size: 28px;
  font-weight: 700;
  color: #1f2937;
  margin: 0;
}

.modules-grid {
  display: grid;
  gap: 24px;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  align-items: start;
}

.module-card {
  background-color: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 24px;
  transition: all 0.2s ease;
  border-left: 4px solid #2563eb;
  background-color: #eff6ff;
  display: flex;
  flex-direction: column;
  min-height: 350px;
}

.module-content {
  flex: 1 0 auto;
}

.module-card:hover {
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  transform: translateY(-2px);
}

.module-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.module-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.module-description {
  color: #6b7280;
  margin: 12px 0 20px 0;
  line-height: 1.6;
  font-size: 15px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.status-badge.active {
  background-color: #dcfce7;
  color: #166534;
}

.status-badge.inactive {
  background-color: #f3f4f6;
  color: #374151;
}

.button-container {
  display: flex;
  gap: 12px;
  margin-top: auto;
  padding-top: 20px;
  border-top: 1px solid #e5e7eb;
}

.action-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
  min-width: 120px;
}

.action-button.success {
  background-color: #ecfdf5;
  color: #059669;
  border-color: #a7f3d0;
}

.action-button.success:hover {
  background-color: #d1fae5;
}

.action-button.warning {
  background-color: #fef2f2;
  color: #dc2626;
  border-color: #fecaca;
}

.action-button.warning:hover {
  background-color: #fee2e2;
}

.action-button:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.action-button:disabled:hover {
  background-color: inherit;
  transform: none;
}

.action-button.rebuild {
  background-color: #475569;
  color: white;
  border-color: #334155;
}

.action-button.rebuild:hover {
  background-color: #334155;
}

/* Styles for external modules */
.modules-section {
  margin-bottom: 40px;
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e5e7eb;
}

.external-module-card {
  border-left: 4px solid #7c3aed;
  background-color: #f5f3ff;
}

.external-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 500;
  background-color: #7c3aed;
  color: white;
  border-radius: 9999px;
  vertical-align: middle;
}

.module-details {
  margin: 16px 0;
  font-size: 14px;
}

.detail-item {
  display: flex;
  margin-bottom: 6px;
}

.detail-label {
  font-weight: 500;
  color: #4b5563;
  width: 100px;
}

.detail-value {
  color: #1f2937;
}

/* Emulator specific styles */
.emulator-card {
  border-left: 4px solid #f59e0b;
  background-color: #fffbeb;
}

.port-badge {
  display: inline-block;
  margin-right: 8px;
  padding: 2px 8px;
  font-size: 12px;
  background-color: #dbeafe;
  color: #1d4ed8;
  border-radius: 4px;
  font-weight: 500;
}


</style>
