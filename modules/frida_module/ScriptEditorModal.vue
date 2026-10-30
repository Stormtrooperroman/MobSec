<template>
  <div v-if="show" class="modal-overlay" @click="closeModal">
    <div class="modal-container script-editor-modal" @click.stop>
      <div class="modal-header">
        <h3>
          {{ editingScriptName ? "Edit Script" : "New Script" }}:
          {{ editingScriptName || newScriptName }}
        </h3>
        <button @click="closeModal" class="modal-close-btn">&times;</button>
      </div>
      <div class="modal-body">
        <div class="script-editor-container">
          <div ref="editorContainer" class="monaco-editor-host"></div>
        </div>
      </div>
      <div class="modal-footer">
        <button @click="closeModal" class="modal-btn cancel-btn">Cancel</button>
        <button @click="saveScript" class="modal-btn save-btn">Save</button>
      </div>
    </div>
  </div>
</template>

<script>
import * as monaco from "monaco-editor";

export default {
  name: "ScriptEditorModal",
  props: {
    show: {
      type: Boolean,
      default: false,
    },
    editingScriptName: {
      type: String,
      default: "",
    },
    newScriptName: {
      type: String,
      default: "",
    },
    scriptContent: {
      type: String,
      default: "",
    },
  },
  emits: ["close", "save"],
  data() {
    return {
      content: "",
    };
  },
  watch: {
    scriptContent(newVal) {
      this.content = newVal;
      if (this.editor && newVal !== this.editor.getValue()) {
        this.editor.setValue(newVal);
      }
    },
    show(newVal) {
      if (newVal) {
        this.content = this.scriptContent;
        this.$nextTick(() => this.ensureEditor());
      } else {
        this.disposeEditor();
      }
    },
  },
  mounted() {
    if (this.show) {
      this.content = this.scriptContent;
      this.$nextTick(() => this.ensureEditor());
    }
  },
  beforeUnmount() {
    this.disposeEditor();
  },
  methods: {
    ensureEditor() {
      if (!this.$refs.editorContainer) return;

      this.disposeEditor();

      this.editor = monaco.editor.create(this.$refs.editorContainer, {
        value: this.content,
        language: "javascript",
        theme: "vs-dark",
        automaticLayout: true,
        fontSize: 14,
        tabSize: 2,
        minimap: { enabled: true },
        scrollBeyondLastLine: false,
      });

      this.editor.onDidChangeModelContent(() => {
        this.content = this.editor.getValue();
      });
    },

    disposeEditor() {
      if (this.editor) {
        const model = this.editor.getModel();
        this.editor.dispose();
        this.editor = null;
        if (model) {
          model.dispose();
        }
      }
    },

    closeModal() {
      this.$emit("close");
    },

    saveScript() {
      this.$emit("save", this.content);
    },
  },
};
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.7);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-container {
  background: #1e1e1e;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
  max-width: 90%;
  max-height: 90%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 20px;
  border-bottom: 1px solid #333;
  background: #2d2d2d;
}

.modal-header h3 {
  margin: 0;
  color: #e0e0e0;
  font-size: 16px;
}

.modal-close-btn {
  background: none;
  border: none;
  color: #888;
  font-size: 20px;
  cursor: pointer;
  padding: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-close-btn:hover {
  color: #fff;
}

.modal-body {
  flex: 1;
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.script-editor-container {
  flex: 1;
  position: relative;
  min-height: 0;
  overflow: hidden;
}

.monaco-editor-host {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 15px 20px;
  border-top: 1px solid #333;
  background: #2d2d2d;
}

.modal-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s ease;
}

.modal-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.modal-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.modal-btn.cancel-btn {
  background: #666;
  color: white;
}

.modal-btn.cancel-btn:hover:not(:disabled) {
  background: #777;
}

.modal-btn.save-btn {
  background: #4caf50;
  color: white;
}

.modal-btn.save-btn:hover:not(:disabled) {
  background: #45a049;
}

.modal-container.script-editor-modal {
  width: 80%;
  height: 100%;
  max-width: 1000px;
  max-height: 100%;
  border-radius: 0;
}

.modal-container.script-editor-modal .modal-body {
  flex: 1;
  overflow: hidden;
}

@media (max-width: 768px) {
  .modal-container.script-editor-modal {
    width: 100%;
    height: 100%;
  }

  .modal-header h3 {
    font-size: 14px;
  }
}
</style>
