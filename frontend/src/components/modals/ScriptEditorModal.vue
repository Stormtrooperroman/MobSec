<template>
  <div v-if="show" class="modal-overlay" @click="closeModal">
    <div class="modal-container script-editor-modal" @click.stop>
      <div class="modal-header">
        <h3>{{ editingScriptName ? 'Edit Script' : 'New Script' }}: {{ editingScriptName || newScriptName }}</h3>
        <button @click="closeModal" class="modal-close-btn">&times;</button>
      </div>
      <div class="modal-body">
        <div class="script-editor-container">
          <textarea 
            v-model="content" 
            class="script-editor"
            placeholder="Enter your Frida script here..."
            spellcheck="false"
            @keydown.tab.prevent="insertTab"
          ></textarea>
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
export default {
  name: 'ScriptEditorModal',
  props: {
    show: {
      type: Boolean,
      default: false
    },
    editingScriptName: {
      type: String,
      default: ''
    },
    newScriptName: {
      type: String,
      default: ''
    },
    scriptContent: {
      type: String,
      default: ''
    }
  },
  emits: ['close', 'save'],
  data() {
    return {
      content: ''
    };
  },
  watch: {
    scriptContent(newVal) {
      this.content = newVal;
    },
    show(newVal) {
      if (newVal) {
        this.content = this.scriptContent;
      }
    }
  },
  methods: {
    closeModal() {
      this.$emit('close');
    },

    saveScript() {
      this.$emit('save', this.content);
    },

    insertTab(event) {
      const textarea = event.target;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      
      this.content = this.content.substring(0, start) + '\t' + this.content.substring(end);
      
      this.$nextTick(() => {
        textarea.selectionStart = textarea.selectionEnd = start + 1;
      });
    }
  }
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
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.script-editor {
  flex: 1;
  background: #1e1e1e;
  color: #e0e0e0;
  border: none;
  padding: 20px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  outline: none;
  tab-size: 2;
  white-space: pre;
  overflow-wrap: normal;
  overflow-x: auto;
  min-height: 400px;
}

.script-editor::placeholder {
  color: #666;
}

.script-editor:focus {
  background: #252525;
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
  background: #4CAF50;
  color: white;
}

.modal-btn.save-btn:hover:not(:disabled) {
  background: #45a049;
}

.modal-container.script-editor-modal {
  width: 80%;
  height: 70%;
  max-width: 1000px;
  max-height: 800px;
}

.modal-container.script-editor-modal .modal-body {
  flex: 1;
  overflow: hidden;
}

.modal-container.script-editor-modal .script-editor {
  width: 100%;
  height: 100%;
  min-height: unset;
}

@media (max-width: 768px) {
  .modal-container.script-editor-modal {
    width: 95%;
    height: 80%;
  }
  
  .modal-header h3 {
    font-size: 14px;
  }
  
  .script-editor {
    font-size: 12px;
    padding: 15px;
  }
}
</style> 