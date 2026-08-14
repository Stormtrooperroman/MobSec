<template>
  <div v-if="show" class="attach-modal-overlay" @click.self="close">
    <div class="attach-modal">
      <div class="attach-modal-header">
        <span>
          <font-awesome-icon icon="crosshairs" />
          Select Target
        </span>
        <button class="attach-modal-close" @click="close" title="Close">
          <font-awesome-icon icon="times" />
        </button>
      </div>

      <div class="attach-modal-tabs">
        <button
          class="attach-tab"
          :class="{ active: activeTab === 'attach' }"
          @click="switchTab('attach')"
        >
          <font-awesome-icon icon="link" />
          Attach to Running
        </button>
        <button
          class="attach-tab"
          :class="{ active: activeTab === 'start' }"
          @click="switchTab('start')"
        >
          <font-awesome-icon icon="rocket" />
          Start Application
        </button>
      </div>

      <div class="attach-modal-search">
        <font-awesome-icon icon="search" class="search-icon" />
        <input
          v-model="searchQuery"
          type="text"
          class="attach-search-input"
          :placeholder="activeTab === 'attach' ? 'Filter running processes...' : 'Filter installed apps...'"
        />
        <button
          class="attach-refresh-btn"
          @click="refresh"
          :disabled="isLoading"
          title="Refresh list"
        >
          <font-awesome-icon v-if="isLoading" icon="spinner" spin />
          <font-awesome-icon v-else icon="refresh" />
        </button>
      </div>

      <div class="attach-modal-body">
        <!-- Attach to running process -->
        <div v-if="activeTab === 'attach'">
          <div v-if="processesLoading" class="attach-empty-state">
            <font-awesome-icon icon="spinner" spin />
            Loading processes...
          </div>
          <div v-else-if="filteredProcesses.length === 0" class="attach-empty-state">
            <font-awesome-icon icon="inbox" />
            No running processes found
          </div>
          <div v-else class="attach-list">
            <div
              v-for="process in filteredProcesses"
              :key="process.pid"
              class="attach-item"
              :class="{ selected: selectedTarget === String(process.pid) }"
              @click="selectProcess(process)"
              @dblclick="selectProcess(process); confirm()"
            >
              <div class="attach-item-icon">
                <font-awesome-icon icon="microchip" />
              </div>
              <div class="attach-item-info">
                <div class="attach-item-name">{{ process.name }}</div>
                <div class="attach-item-meta">PID: {{ process.pid }}</div>
              </div>
              <div class="attach-item-action">
                <font-awesome-icon v-if="selectedTarget === String(process.pid)" icon="check-circle" class="selected-icon" />
                <font-awesome-icon v-else icon="chevron-right" />
              </div>
            </div>
          </div>
        </div>

        <!-- Start / spawn application -->
        <div v-else>
          <div v-if="appsLoading" class="attach-empty-state">
            <font-awesome-icon icon="spinner" spin />
            Loading applications...
          </div>
          <div v-else-if="filteredApps.length === 0" class="attach-empty-state">
            <font-awesome-icon icon="inbox" />
            No applications found
          </div>
          <div v-else class="attach-list">
            <div
              v-for="app in filteredApps"
              :key="app.identifier"
              class="attach-item"
              :class="{ selected: selectedTarget === ('package:' + app.identifier) }"
              @click="selectApp(app)"
              @dblclick="selectApp(app); confirm()"
            >
              <div class="attach-item-icon">
                <img
                  v-if="app.icon"
                  :src="app.icon"
                  :alt="app.name"
                  class="attach-item-icon-img"
                />
                <font-awesome-icon v-else icon="mobile-alt" />
              </div>
              <div class="attach-item-info">
                <div class="attach-item-name">{{ app.name }}</div>
                <div class="attach-item-meta">{{ app.identifier }}</div>
              </div>
              <div class="attach-item-pid">
                <span v-if="app.pid" class="pid-badge pid-running">
                  <span class="pid-dot"></span>PID {{ app.pid }}
                </span>
                <span v-else class="pid-badge pid-stopped">&mdash;</span>
              </div>
              <div class="attach-item-action">
                <font-awesome-icon v-if="selectedTarget === ('package:' + app.identifier)" icon="check-circle" class="selected-icon" />
                <font-awesome-icon v-else icon="chevron-right" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="activeTab === 'start'" class="attach-modal-manual">
        <span class="attach-manual-label">Or enter manually:</span>
        <input
          v-model="manualTarget"
          type="text"
          class="attach-manual-input"
          placeholder="Package name, e.g. com.example.app"
          @keyup.enter="confirmManual"
        />
      </div>

      <div class="attach-modal-footer">
        <div class="attach-selected-preview" v-if="currentSelectionLabel">
          <font-awesome-icon icon="check-circle" />
          Selected: <strong>{{ currentSelectionLabel }}</strong>
        </div>
        <div v-else class="attach-selected-preview attach-selected-empty">
          No target selected
        </div>
        <div class="attach-modal-actions">
          <button class="attach-btn attach-btn-cancel" @click="close">Cancel</button>
          <button
            class="attach-btn attach-btn-confirm"
            :disabled="!canConfirm"
            @click="confirm"
          >
            <font-awesome-icon :icon="activeTab === 'start' ? 'rocket' : 'link'" />
            {{ activeTab === 'start' ? 'Start & Attach' : 'Attach' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'AttachModal',
  props: {
    show: {
      type: Boolean,
      default: false
    },
    processes: {
      type: Array,
      default: () => []
    },
    apps: {
      type: Array,
      default: () => []
    },
    processesLoading: {
      type: Boolean,
      default: false
    },
    appsLoading: {
      type: Boolean,
      default: false
    }
  },
  emits: ['close', 'confirm', 'refresh-processes', 'refresh-apps'],
  data() {
    return {
      activeTab: 'attach',
      searchQuery: '',
      selectedTarget: null,
      selectedLabel: '',
      manualTarget: '',
    };
  },
  computed: {
    isLoading() {
      return this.activeTab === 'attach' ? this.processesLoading : this.appsLoading;
    },
    filteredProcesses() {
      const q = this.searchQuery.trim().toLowerCase();
      if (!q) return this.processes;
      return this.processes.filter(p =>
        (p.name || '').toLowerCase().includes(q) || String(p.pid).includes(q)
      );
    },
    filteredApps() {
      const q = this.searchQuery.trim().toLowerCase();
      if (!q) return this.apps;
      return this.apps.filter(a =>
        (a.identifier || '').toLowerCase().includes(q) ||
        (a.name || '').toLowerCase().includes(q)
      );
    },
    canConfirm() {
      return !!(this.selectedTarget || this.manualTarget.trim());
    },
    currentSelectionLabel() {
      if (this.selectedTarget) return this.selectedLabel;
      if (this.manualTarget.trim()) return this.manualTarget.trim();
      return '';
    }
  },
  watch: {
    show(newValue) {
      if (newValue) {
        this.resetState();
        this.$emit('refresh-processes');
      }
    },
    manualTarget(newValue) {
      if (newValue) {
        this.selectedTarget = null;
        this.selectedLabel = '';
      }
    }
  },
  methods: {
    resetState() {
      this.searchQuery = '';
      this.selectedTarget = null;
      this.selectedLabel = '';
      this.manualTarget = '';
      this.activeTab = 'attach';
    },
    switchTab(tab) {
      if (this.activeTab === tab) return;
      this.activeTab = tab;
      this.searchQuery = '';
      this.selectedTarget = null;
      this.selectedLabel = '';
      this.manualTarget = '';
      if (tab === 'start' && this.apps.length === 0) {
        this.$emit('refresh-apps');
      }
    },
    refresh() {
      if (this.activeTab === 'attach') {
        this.$emit('refresh-processes');
      } else {
        this.$emit('refresh-apps');
      }
    },
    selectProcess(process) {
      this.selectedTarget = String(process.pid);
      this.selectedLabel = `${process.name} (PID ${process.pid})`;
      this.manualTarget = '';
    },
    selectApp(app) {
      this.selectedTarget = `package:${app.identifier}`;
      this.selectedLabel = app.name || app.identifier;
      this.manualTarget = '';
    },
    confirmManual() {
      if (this.manualTarget.trim()) {
        this.confirm();
      }
    },
    confirm() {
      let target = this.selectedTarget;
      let label = this.selectedLabel;

      if (!target && this.manualTarget.trim()) {
        const manual = this.manualTarget.trim();
        target = this.activeTab === 'start' && !manual.startsWith('package:')
          ? `package:${manual}`
          : manual;
        label = manual;
      }

      if (!target) return;

      this.$emit('confirm', {
        target,
        mode: this.activeTab,
        label: label || target,
      });
      this.close();
    },
    close() {
      this.$emit('close');
    }
  }
};
</script>

<style scoped>
.attach-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.attach-modal {
  width: 520px;
  max-width: 92vw;
  max-height: 85vh;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.attach-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #2d2d2d;
  color: #ffffff;
  font-weight: 500;
  font-size: 15px;
  border-bottom: 1px solid #444;
}

.attach-modal-header span {
  display: flex;
  align-items: center;
  gap: 8px;
}

.attach-modal-close {
  background: transparent;
  border: none;
  color: #ffffff;
  cursor: pointer;
  font-size: 16px;
  padding: 4px 6px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.attach-modal-close:hover {
  background: rgba(255, 255, 255, 0.15);
}

.attach-modal-tabs {
  display: flex;
  background: #e0e0e0;
  border-bottom: 1px solid #ccc;
}

.attach-tab {
  flex: 1;
  padding: 10px 12px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: #555;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-bottom: 2px solid transparent;
  transition: all 0.2s ease;
}

.attach-tab:hover {
  background: rgba(0, 0, 0, 0.04);
}

.attach-tab.active {
  color: #007bff;
  border-bottom-color: #007bff;
  background: #fff;
  font-weight: 600;
}

.attach-modal-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid #eee;
  background: #fafafa;
}

.search-icon {
  color: #999;
  font-size: 13px;
}

.attach-search-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 13px;
  outline: none;
}

.attach-search-input:focus {
  border-color: #007bff;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.2);
}

.attach-refresh-btn {
  background: #4a4a4a;
  border: 1px solid #666;
  color: #fff;
  border-radius: 4px;
  padding: 6px 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 30px;
}

.attach-refresh-btn:hover:not(:disabled) {
  background: #5a5a5a;
}

.attach-refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.attach-modal-body {
  flex: 1;
  overflow-y: auto;
  min-height: 200px;
  max-height: 360px;
  padding: 8px 12px;
}

.attach-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 10px;
  color: #999;
  font-size: 13px;
}

.attach-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.attach-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.15s ease;
  background: #fff;
}

.attach-item:hover {
  background: #f5f8ff;
}

.attach-item.selected {
  background: #e3f2fd;
  border-color: #007bff;
}

.attach-item-icon {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: #f0f0f0;
  color: #555;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.attach-item.selected .attach-item-icon {
  background: #007bff;
  color: #fff;
}

.attach-item-icon-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 6px;
}

.attach-item-info {
  flex: 1;
  min-width: 0;
}

.attach-item-name {
  font-weight: 500;
  color: #2c3e50;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attach-item-meta {
  font-size: 11px;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attach-item-pid {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.pid-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10.5px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 10px;
  white-space: nowrap;
}

.pid-badge.pid-running {
  background: #e6f7ee;
  color: #1b8a5a;
}

.pid-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #2ecc71;
  flex-shrink: 0;
}

.pid-badge.pid-stopped {
  background: #f0f0f0;
  color: #aaa;
  font-weight: 400;
  padding: 3px 9px;
}

.attach-item-action {
  color: #007bff;
  font-size: 14px;
  flex-shrink: 0;
}

.selected-icon {
  color: #007bff;
}

.attach-modal-manual {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-top: 1px solid #eee;
  background: #fafafa;
}

.attach-manual-label {
  font-size: 12px;
  color: #777;
  white-space: nowrap;
}

.attach-manual-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 12px;
  outline: none;
}

.attach-manual-input:focus {
  border-color: #007bff;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.2);
}

.attach-modal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-top: 1px solid #ddd;
  background: #f5f5f5;
  flex-wrap: wrap;
}

.attach-selected-preview {
  font-size: 12px;
  color: #333;
  display: flex;
  align-items: center;
  gap: 6px;
}

.attach-selected-preview strong {
  color: #007bff;
}

.attach-selected-empty {
  color: #999;
}

.attach-modal-actions {
  display: flex;
  gap: 10px;
  margin-left: auto;
}

.attach-btn {
  padding: 7px 14px;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid #ccc;
  background: #fff;
}

.attach-btn-cancel:hover {
  background: #f0f0f0;
}

.attach-btn-confirm {
  background: #007bff;
  border-color: #007bff;
  color: #fff;
}

.attach-btn-confirm:hover:not(:disabled) {
  background: #0056b3;
  border-color: #0056b3;
}

.attach-btn-confirm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #ccc;
  border-color: #ccc;
}

@media (max-width: 600px) {
  .attach-modal {
    width: 100%;
    max-height: 90vh;
  }

  .attach-modal-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .attach-modal-actions {
    margin-left: 0;
    justify-content: flex-end;
  }
}
</style>
