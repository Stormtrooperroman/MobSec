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
              <div class="badge badge-info">{{ libraries.length }}</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <h4>Debug Symbols</h4>
              <div
                :class="[
                  'badge',
                  hasDebugSymbols ? 'badge-warning' : 'badge-success',
                ]"
              >
                {{ debugSymbolsCount }} Found
              </div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <h4>Architectures</h4>
              <div class="badge badge-primary">{{ architectureCount }}</div>
            </div>
            <div v-if="architectureCount" class="arch-breakdown">
              <span
                v-for="(count, arch) in architectures"
                :key="arch"
                class="arch-chip"
                :class="archChipClass(arch)"
              >
                {{ arch }} · {{ count }}
              </span>
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
                <div
                  v-for="lib in libraries"
                  :key="lib.name"
                  class="lib-item"
                  :class="{ 'has-debug': lib.has_debug_symbols }"
                >
                  <div class="lib-header">
                    <div class="lib-name">{{ formatLibName(lib.name) }}</div>
                    <div
                      v-if="lib.architecture"
                      class="badge badge-arch"
                      :class="archChipClass(lib.architecture)"
                    >
                      {{ lib.architecture }}
                    </div>
                  </div>
                  <div class="lib-details">
                    <div class="detail-item">
                      <span class="detail-label">Symbols:</span>
                      <span class="detail-value">{{ lib.symbols }}</span>
                    </div>
                    <div class="detail-item">
                      <span class="detail-label">Imported Functions:</span>
                      <span class="detail-value">{{
                        lib.imported_functions
                      }}</span>
                    </div>
                    <div class="detail-item">
                      <span class="detail-label">Sections:</span>
                      <span class="detail-value">{{ lib.sections }}</span>
                    </div>
                    <div class="detail-item">
                      <span class="detail-label">Debug Symbols:</span>
                      <span
                        :class="[
                          'detail-value',
                          lib.has_debug_symbols
                            ? 'text-warning'
                            : 'text-success',
                        ]"
                      >
                        {{ lib.has_debug_symbols ? "Present" : "Not Present" }}
                      </span>
                    </div>
                    <div
                      v-if="lib.imported_libraries?.length"
                      class="detail-item-full"
                    >
                      <span class="detail-label">Imported Libraries:</span>
                      <div class="detail-list">
                        <span
                          v-for="impLib in lib.imported_libraries"
                          :key="impLib"
                          class="detail-tag"
                        >
                          {{ impLib }}
                        </span>
                      </div>
                    </div>
                    <div
                      v-if="lib.exported_functions?.length"
                      class="detail-item detail-item-fit"
                    >
                      <span class="detail-label">Exported Functions:</span>
                      <button
                        type="button"
                        class="fn-count-btn"
                        @click="openFunctions(lib)"
                      >
                        {{ lib.exported_functions.length }} · View all
                      </button>
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

    <div
      v-if="activeLib"
      ref="overlay"
      class="modal-overlay"
      tabindex="-1"
      @click.self="closeFunctions"
      @keydown.esc="closeFunctions"
    >
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-header">
          <div class="modal-heading">
            <h5>Exported Functions</h5>
            <div class="modal-sub" :title="activeLib.name">
              {{ formatLibName(activeLib.name) }} ·
              {{ filteredFunctions.length }} of
              {{ activeLib.exported_functions.length }}
            </div>
          </div>
          <button
            type="button"
            class="modal-close"
            aria-label="Close"
            @click="closeFunctions"
          >
            ×
          </button>
        </div>

        <div class="modal-search">
          <input
            v-model.trim="search"
            type="text"
            placeholder="Filter functions…"
            @keydown.esc.stop="closeFunctions"
          />
        </div>

        <div class="modal-body">
          <ul v-if="filteredFunctions.length" class="fn-list">
            <li v-for="fn in filteredFunctions" :key="fn">
              <button
                type="button"
                class="fn-item"
                :title="'Click to copy: ' + fn"
                @click="copyName(fn)"
              >
                {{ fn }}
              </button>
            </li>
          </ul>
          <p v-else class="no-items">No matching functions</p>
        </div>

        <div class="modal-footer">
          <span class="modal-hint">Click a function to copy its name</span>
          <transition name="fade">
            <span v-if="toast" class="copy-toast" :class="toast.type">
              {{ toast.text }}
            </span>
          </transition>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: "NativeLibsReport",
  props: {
    moduleData: {
      type: Object,
      required: true,
    },
  },
  data() {
    return {
      activeLib: null,
      search: "",
      toast: null,
      toastTimer: null,
    };
  },
  beforeUnmount() {
    clearTimeout(this.toastTimer);
  },

  computed: {
    filteredFunctions() {
      const list = this.activeLib?.exported_functions || [];
      const q = this.search.toLowerCase();
      return q ? list.filter((fn) => fn.toLowerCase().includes(q)) : list;
    },
    hasResults() {
      return this.moduleData?.results !== undefined;
    },
    summary() {
      return (
        this.moduleData?.results?.summary || {
          total_libs: 0,
          architectures: {},
        }
      );
    },
    architectures() {
      return this.summary.architectures || {};
    },
    architectureCount() {
      return Object.keys(this.architectures).length;
    },
    libraries() {
      return this.moduleData?.results?.libraries || [];
    },
    hasDebugSymbols() {
      return this.libraries.some((lib) => lib.has_debug_symbols);
    },
    debugSymbolsCount() {
      return this.libraries.filter((lib) => lib.has_debug_symbols).length;
    },
  },
  methods: {
    openFunctions(lib) {
      this.activeLib = lib;
      this.search = "";
      this.toast = null;
      this.$nextTick(() => this.$refs.overlay?.focus());
    },
    closeFunctions() {
      this.activeLib = null;
      this.search = "";
      this.toast = null;
      clearTimeout(this.toastTimer);
    },
    async copyName(name) {
      try {
        if (navigator.clipboard?.writeText && window.isSecureContext) {
          await navigator.clipboard.writeText(name);
        } else {
          const ta = document.createElement("textarea");
          ta.value = name;
          ta.style.position = "fixed";
          ta.style.opacity = "0";
          document.body.appendChild(ta);
          ta.select();
          const ok = document.execCommand("copy");
          document.body.removeChild(ta);
          if (!ok) throw new Error("copy failed");
        }
        this.showToast(`Copied: ${name}`, "ok");
      } catch (e) {
        this.showToast("Failed to copy", "error");
      }
    },
    showToast(text, type) {
      clearTimeout(this.toastTimer);
      this.toast = { text, type };
      this.toastTimer = setTimeout(() => {
        this.toast = null;
      }, 2000);
    },
    formatLibName(name) {
      return name.split("/").pop();
    },
    archChipClass(arch) {
      const known = ["arm64-v8a", "armeabi-v7a", "x86", "x86_64", "armeabi"];
      return known.includes(arch) ? `arch-${arch}` : "arch-unknown";
    },
  },
};
</script>

<style scoped>
.native-libs-report {
  font-family:
    -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
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

.arch-breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.arch-chip {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 12px;
  background-color: #e9ecef;
  color: #495057;
}

.arch-arm64-v8a {
  background-color: #d4edda;
  color: #155724;
}
.arch-armeabi-v7a {
  background-color: #d1ecf1;
  color: #0c5460;
}
.arch-x86_64 {
  background-color: #fff3cd;
  color: #856404;
}
.arch-x86 {
  background-color: #f8d7da;
  color: #721c24;
}
.arch-armeabi {
  background-color: #e2d9f3;
  color: #4b2e83;
}
.arch-unknown {
  background-color: #e9ecef;
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
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
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

.badge-arch {
  font-size: 0.75rem;
  padding: 3px 8px;
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
  justify-content: center;
  align-items: center;
  padding: 5px 0;
}

.detail-label {
  color: #6c757d;
  font-size: 0.9rem;
  margin-right: 0.5rem;
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
  max-width: 100%;
  overflow-wrap: anywhere;
}

.lib-name {
  min-width: 0;
  overflow-wrap: anywhere;
  margin-right: 10px;
}

.lib-header .badge-arch {
  flex-shrink: 0;
}

.detail-item-fit {
  grid-column: 1 / -1;
  justify-self: start;
  width: max-content;
  max-width: 100%;
  flex-wrap: wrap;
  gap: 4px 0;
}

.fn-count-btn {
  border: none;
  cursor: pointer;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
  background-color: #007bff;
  color: white;
  transition: background-color 0.15s;
  height: 2.6em;
}

.fn-count-btn:hover {
  background-color: #0069d9;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(0, 0, 0, 0.45);
  outline: none;
}

.modal {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 720px;
  max-height: 80vh;
  background: white;
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 15px;
  border-bottom: 1px solid #e9ecef;
}

.modal-heading {
  min-width: 0;
}

.modal-heading h5 {
  margin: 0;
  font-size: 1.1rem;
  color: #2c3e50;
}

.modal-sub {
  margin-top: 4px;
  font-size: 0.85rem;
  color: #6c757d;
  overflow-wrap: anywhere;
}

.modal-close {
  border: none;
  background: none;
  font-size: 1.6rem;
  line-height: 1;
  cursor: pointer;
  color: #6c757d;
}

.modal-close:hover {
  color: #2c3e50;
}

.modal-search {
  padding: 10px 15px;
  border-bottom: 1px solid #e9ecef;
}

.modal-search input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid #ced4da;
  border-radius: 6px;
  font-size: 0.9rem;
}

.modal-search input:focus {
  outline: none;
  border-color: #007bff;
}

.modal-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 15px;
}

.fn-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fn-item {
  display: block;
  width: 100%;
  text-align: left;
  border: none;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 4px;
  background-color: #f8f9fa;
  color: #495057;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.85rem;
  overflow-wrap: anywhere;
  word-break: break-all;
}

.fn-item:hover {
  background-color: #e2e6ea;
}

.modal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  min-height: 44px;
  padding: 10px 15px;
  border-top: 1px solid #e9ecef;
  font-size: 0.85rem;
}

.modal-hint {
  color: #6c757d;
}

.copy-toast {
  max-width: 60%;
  padding: 3px 10px;
  border-radius: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.copy-toast.ok {
  background-color: #d4edda;
  color: #155724;
}

.copy-toast.error {
  background-color: #f8d7da;
  color: #721c24;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}

.fade-enter-from,
.fade-enter,
.fade-leave-to {
  opacity: 0;
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
