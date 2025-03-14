<template>
  <div class="modules-container">
    <div class="header">
      <h2>Available Modules</h2>
    </div>
    <div class="modules-grid">
      <div v-for="module in modules" :key="module.id" class="module-card">
        <div class="module-header">
          <h3>{{ module.name }}</h3>
          <div class="status-container">
            <span :class="['status-badge', module.active ? 'active' : 'inactive']">
              <i :class="['fas', module.active ? 'fa-check-circle' : 'fa-times-circle']"></i>
              {{ module.active ? 'Active' : 'Inactive' }}
            </span>
          </div>
        </div>
        <p class="module-description">{{ module.description }}</p>
        <div class="button-container">
          <button 
            @click="toggleModule(module)"
            :class="['action-button', module.active ? 'warning' : 'success']"
            :disabled="module.isLoading"
          >
            <i :class="['fas', module.isLoading ? 'fa-spinner fa-spin' : module.active ? 'fa-stop' : 'fa-play']"></i>
            {{ module.active ? 'Deactivate' : 'Activate' }}
          </button>
          <button 
            @click="rebuildModule(module)"
            class="action-button rebuild"
            :disabled="module.isRebuilding || !module.active"
          >
            <i :class="['fas', module.isRebuilding ? 'fa-spinner fa-spin' : 'fa-sync']"></i>
            Rebuild
          </button>
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
      modules: []
    }
  },
  methods: {
    async fetchModules() {
      try {
        const response = await fetch('/api/v1/modules');
        const data = await response.json();
        this.modules = data.map(module => ({
          ...module,
          isLoading: false,
          isRebuilding: false
        }));
      } catch (error) {
        console.error('Error fetching modules:', error);
      }
    },
    async toggleModule(module) {
      if (module.isLoading) return;
      
      module.isLoading = true;
      try {
        const response = await fetch(`/api/v1/modules/${module.id}/toggle`, {
          method: 'POST'
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
          method: 'POST'
        });
        if (response.ok) {
          // Refresh the module status after rebuild
          await this.fetchModules();
        }
      } catch (error) {
        console.error('Error rebuilding module:', error);
      } finally {
        module.isRebuilding = false;
      }
    }
  },
  mounted() {
    this.fetchModules();
  }
}
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
}

.module-card {
  background-color: white;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 24px;
  transition: all 0.2s ease;
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
  margin-top: 20px;
}

.action-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
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
  background-color: #eff6ff;
  color: #2563eb;
  border-color: #bfdbfe;
}

.action-button.rebuild:hover {
  background-color: #dbeafe;
}

.action-button.rebuild:disabled {
  background-color: #f3f4f6;
  color: #9ca3af;
  border-color: #e5e7eb;
}

@media (max-width: 768px) {
  .modules-container {
    padding: 20px;
    border-radius: 8px;
  }

  .header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
    text-align: center;
  }

  .modules-grid {
    grid-template-columns: 1fr;
  }

  .button-container {
    flex-direction: column;
  }

  .action-button {
    width: 100%;
    justify-content: center;
  }
}
</style>