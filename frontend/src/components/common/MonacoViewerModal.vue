<template>
  <div v-if="show" class="modal-overlay" @click="close">
    <div class="modal-container monaco-viewer-modal" @click.stop>
      <div class="modal-header">
        <h3 class="modal-title" :title="filePath">{{ displayTitle }}</h3>
        <div class="modal-header-actions">
          <span v-if="lineLabel" class="modal-line-badge">{{ lineLabel }}</span>
          <button @click="close" class="modal-close-btn">&times;</button>
        </div>
      </div>
      <div class="modal-body">
        <div v-if="loading" class="viewer-state">Loading file content...</div>
        <div v-else-if="error" class="viewer-state viewer-error">{{ error }}</div>
        <MonacoEditor v-else ref="editor" :value="content" :language="resolvedLanguage" :read-only="true" />
      </div>
    </div>
  </div>
</template>

<script>
import MonacoEditor from './MonacoEditor.vue';

const EXTENSION_LANGUAGE_MAP = {
  java: 'java',
  kt: 'kotlin',
  kts: 'kotlin',
  js: 'javascript',
  mjs: 'javascript',
  ts: 'typescript',
  json: 'json',
  xml: 'xml',
  html: 'xml',
  smali: 'plaintext',
  sh: 'shell',
  bash: 'shell',
  yaml: 'yaml',
  yml: 'yaml',
  c: 'cpp',
  cpp: 'cpp',
  cc: 'cpp',
  h: 'cpp',
  hpp: 'cpp',
  txt: 'plaintext',
};

export default {
  name: 'MonacoViewerModal',
  components: {
    MonacoEditor,
  },
  props: {
    show: {
      type: Boolean,
      default: false,
    },
    filePath: {
      type: String,
      default: '',
    },
    content: {
      type: String,
      default: '',
    },
    language: {
      type: String,
      default: '',
    },
    line: {
      type: [Number, String],
      default: null,
    },
    endLine: {
      type: [Number, String],
      default: null,
    },
    severity: {
      type: String,
      default: '',
    },
    ruleId: {
      type: String,
      default: '',
    },
    message: {
      type: String,
      default: '',
    },
    loading: {
      type: Boolean,
      default: false,
    },
    error: {
      type: String,
      default: '',
    },
  },
  emits: ['close'],
  computed: {
    displayTitle() {
      if (!this.filePath) return 'File Viewer';
      const parts = this.filePath.split('/');
      return parts[parts.length - 1] || this.filePath;
    },
    lineLabel() {
      const start = parseInt(this.line, 10);
      if (!start) return '';
      const end = parseInt(this.endLine, 10);
      return end && end !== start ? `Lines ${start}-${end}` : `Line ${start}`;
    },
    resolvedLanguage() {
      if (this.language) return this.language;
      const match = this.filePath.match(/\.([^.]+)$/);
      const ext = match ? match[1].toLowerCase() : '';
      return EXTENSION_LANGUAGE_MAP[ext] || 'plaintext';
    },
  },
  watch: {
    show(visible) {
      if (visible) {
        this.$nextTick(() => this.revealLine());
      }
    },
    content() {
      if (this.show) {
        this.$nextTick(() => this.revealLine());
      }
    },
  },
  methods: {
    revealLine() {
      const startLine = parseInt(this.line, 10);
      if (!this.$refs.editor || !startLine) return;

      this.$refs.editor.highlightRange({
        startLine,
        endLine: parseInt(this.endLine, 10) || startLine,
        severity: this.severity,
        title: [this.severity.toUpperCase(), this.ruleId].filter(Boolean).join(' · '),
        message: this.message,
      });
    },
    close() {
      this.$emit('close');
    },
  },
};
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1050;
}

.monaco-viewer-modal {
  background-color: #1e1e1e;
  border-radius: 8px;
  width: 90%;
  max-width: 1100px;
  height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background-color: #252526;
  border-bottom: 1px solid #333;
}

.modal-title {
  margin: 0;
  font-size: 1rem;
  color: #e0e0e0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.modal-line-badge {
  font-size: 0.8rem;
  color: #9cdcfe;
  background-color: #2d2d2d;
  padding: 2px 8px;
  border-radius: 4px;
}

.modal-close-btn {
  background: none;
  border: none;
  color: #ccc;
  font-size: 1.5rem;
  line-height: 1;
  cursor: pointer;
}

.modal-close-btn:hover {
  color: #fff;
}

.modal-body {
  flex: 1;
  min-height: 0;
  display: flex;
}

.modal-body > * {
  flex: 1;
}

.viewer-state {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  color: #ccc;
  font-size: 0.95rem;
}

.viewer-error {
  color: #f48771;
}
</style>
