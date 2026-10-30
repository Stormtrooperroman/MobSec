<template>
  <div ref="editorContainer" class="monaco-editor-container"></div>
</template>

<script>
import * as monaco from 'monaco-editor';

function severityLevel(severity) {
  const s = String(severity || '').toLowerCase();
  if (['critical', 'high', 'error'].includes(s)) return 'high';
  if (['medium', 'warning', 'warn'].includes(s)) return 'medium';
  return 'low';
}

function escapeMarkdown(text) {
  return String(text || '').replace(/[\\`*_{}\[\]()#+!|<>~]/g, '\\$&');
}

export default {
  name: 'MonacoEditor',
  props: {
    value: {
      type: String,
      default: '',
    },
    language: {
      type: String,
      default: 'plaintext',
    },
    theme: {
      type: String,
      default: 'vs-dark',
    },
    readOnly: {
      type: Boolean,
      default: false,
    },
    options: {
      type: Object,
      default: () => ({}),
    },
  },
  emits: ['update:value', 'change'],
  mounted() {
    this.editor = monaco.editor.create(this.$refs.editorContainer, {
      value: this.value,
      language: this.language,
      theme: this.theme,
      readOnly: this.readOnly,
      automaticLayout: true,
      glyphMargin: true,
      minimap: { enabled: true },
      scrollBeyondLastLine: false,
      fontSize: 13,
      ...this.options,
    });

    this.editor.onDidChangeModelContent(() => {
      const current = this.editor.getValue();
      if (current !== this.value) {
        this.$emit('update:value', current);
        this.$emit('change', current);
      }
    });
  },
  beforeUnmount() {
    if (this.editor) {
      const model = this.editor.getModel();
      this.editor.dispose();
      if (model) {
        model.dispose();
      }
    }
  },
  watch: {
    value(newValue) {
      if (this.editor && newValue !== this.editor.getValue()) {
        this.editor.setValue(newValue);
      }
    },
    language(newLanguage) {
      if (this.editor) {
        const model = this.editor.getModel();
        if (model) {
          monaco.editor.setModelLanguage(model, newLanguage);
        }
      }
    },
    theme(newTheme) {
      if (this.editor) {
        monaco.editor.setTheme(newTheme);
      }
    },
    readOnly(newReadOnly) {
      if (this.editor) {
        this.editor.updateOptions({ readOnly: newReadOnly });
      }
    },
  },
  methods: {
    highlightRange({ startLine, endLine, severity, title, message, select = true } = {}) {
      if (!this.editor) return;
      const model = this.editor.getModel();
      if (!model) return;

      const lineCount = model.getLineCount();
      const start = parseInt(startLine, 10);
      if (!start || start > lineCount) {
        this.clearHighlight();
        return;
      }
      const end = Math.min(Math.max(parseInt(endLine, 10) || start, start), lineCount);
      const level = severityLevel(severity);

      const hoverParts = [];
      if (title) hoverParts.push(`**${escapeMarkdown(title)}**`);
      if (message) hoverParts.push(escapeMarkdown(message));

      const decorations = [
        {
          range: new monaco.Range(start, 1, end, 1),
          options: {
            isWholeLine: true,
            className: `finding-hl-line finding-hl-line--${level}`,
            linesDecorationsClassName: `finding-hl-bar finding-hl-bar--${level}`,
          },
        },
        {
          range: new monaco.Range(start, 1, start, 1),
          options: {
            glyphMarginClassName: `finding-hl-glyph finding-hl-glyph--${level}`,
            glyphMarginHoverMessage: hoverParts.length ? { value: hoverParts.join('\n\n') } : undefined,
          },
        },
      ];

      if (this.highlightCollection) {
        this.highlightCollection.set(decorations);
      } else {
        this.highlightCollection = this.editor.createDecorationsCollection(decorations);
      }

      const range = new monaco.Range(start, 1, end, model.getLineMaxColumn(end));
      const lineHeight = this.editor.getOption(monaco.editor.EditorOption.lineHeight);
      const visibleLines = Math.floor(this.editor.getLayoutInfo().height / lineHeight);
      if (end - start + 1 > visibleLines) {
        this.editor.revealLineInCenter(start);
      } else {
        this.editor.revealRangeInCenter(range);
      }

      if (select) {
        this.editor.setSelection(range);
      } else {
        this.editor.setPosition({ lineNumber: start, column: 1 });
      }
      this.editor.focus();
    },
    clearHighlight() {
      if (this.highlightCollection) {
        this.highlightCollection.clear();
      }
    },
    goToLine(lineNumber) {
      if (this.editor && lineNumber) {
        this.editor.revealLineInCenter(lineNumber);
        this.editor.setPosition({ lineNumber, column: 1 });
        this.editor.focus();
      }
    },
    getEditor() {
      return this.editor;
    },
  },
};
</script>

<style scoped>
.monaco-editor-container {
  width: 100%;
  height: 100%;
  min-height: 300px;
}
</style>

<!-- Not scoped: Monaco injects decoration elements into its own DOM -->
<style>
.finding-hl-line--high {
  background-color: rgba(244, 135, 113, 0.15);
}
.finding-hl-line--medium {
  background-color: rgba(204, 167, 0, 0.15);
}
.finding-hl-line--low {
  background-color: rgba(55, 148, 255, 0.15);
}

.finding-hl-bar {
  width: 3px !important;
  margin-left: 3px;
}
.finding-hl-bar--high {
  background-color: #f48771;
}
.finding-hl-bar--medium {
  background-color: #cca700;
}
.finding-hl-bar--low {
  background-color: #3794ff;
}

.finding-hl-glyph {
  background-repeat: no-repeat;
  background-position: center;
  background-size: 14px;
  cursor: pointer;
}
.finding-hl-glyph--high {
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><circle cx='8' cy='8' r='7' fill='%23f48771'/><rect x='7.2' y='3.5' width='1.6' height='5.5' fill='white'/><rect x='7.2' y='10.5' width='1.6' height='1.8' fill='white'/></svg>");
}
.finding-hl-glyph--medium {
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><circle cx='8' cy='8' r='7' fill='%23cca700'/><rect x='7.2' y='3.5' width='1.6' height='5.5' fill='white'/><rect x='7.2' y='10.5' width='1.6' height='1.8' fill='white'/></svg>");
}
.finding-hl-glyph--low {
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><circle cx='8' cy='8' r='7' fill='%233794ff'/><rect x='7.2' y='7' width='1.6' height='5.5' fill='white'/><rect x='7.2' y='3.5' width='1.6' height='1.8' fill='white'/></svg>");
}
</style>
