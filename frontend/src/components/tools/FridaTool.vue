<template>
  <div class="frida-section">
    <div class="frida-header">
      <span>
        Frida Tool
        <span class="frida-status-indicator" :class="{ 'installed': fridaInstalled, 'running': fridaRunning }">
          <font-awesome-icon v-if="fridaRunning" icon="circle" class="status-icon running" />
          <font-awesome-icon v-else-if="fridaInstalled" icon="circle" class="status-icon installed" />
          <font-awesome-icon v-else icon="circle" class="status-icon not-installed" />
          {{ fridaRunning ? 'Running' : fridaInstalled ? 'Installed' : 'Not Installed' }}
        </span>
      </span>
      <div class="frida-controls">
        <button @click="refreshFridaStatus" class="frida-refresh-btn" title="Обновить статус" :disabled="fridaRefreshing">
          <font-awesome-icon v-if="fridaRefreshing" icon="spinner" spin />
          <font-awesome-icon v-else icon="refresh" />
        </button>
      </div>
    </div>
    
    <div class="frida-toolbar">
      <button @click="installFrida" :disabled="fridaInstalled || fridaInstalling" class="frida-btn">
        <font-awesome-icon v-if="fridaInstalling" icon="spinner" spin />
        <font-awesome-icon v-else icon="download" />
        Install Frida
      </button>
      <button @click="startFridaServer" :disabled="!fridaInstalled || fridaRunning || fridaStarting" class="frida-btn">
        <font-awesome-icon v-if="fridaStarting" icon="spinner" spin />
        <font-awesome-icon v-else icon="play" />
        Start Server
      </button>
      <button @click="stopFridaServer" :disabled="!fridaRunning || fridaStopping" class="frida-btn">
        <font-awesome-icon v-if="fridaStopping" icon="spinner" spin />
        <font-awesome-icon v-else icon="stop" />
        Stop Server
      </button>
      <button @click="listProcesses" :disabled="!fridaRunning || fridaProcessesLoading" class="frida-btn">
        <font-awesome-icon v-if="fridaProcessesLoading" icon="spinner" spin />
        <font-awesome-icon v-else icon="list" />
        List Processes
      </button>
    </div>
    
    <div class="frida-content">
      <div class="frida-scripts">
        <div class="script-section">
          <h4>Scripts</h4>
          <div class="script-actions">
            <input type="file" @change="loadScriptFile" accept=".js" style="display: none" ref="scriptFileInput">
            <button @click="$refs.scriptFileInput.click()" class="script-btn">
              <font-awesome-icon icon="folder-open" />
              Load Script
            </button>
            <button @click="createNewScript" class="script-btn">
              <font-awesome-icon icon="plus" />
              New Script
            </button>
            <button @click="stopCurrentScript" :disabled="isStopButtonDisabled" class="script-btn stop-btn">
              <font-awesome-icon v-if="fridaStopping" icon="spinner" spin />
              <font-awesome-icon v-else icon="stop" />
              Stop Script
            </button>
          </div>
          
          <div class="scripts-list">
            <div v-for="(script, name) in fridaScripts" :key="name" class="script-item">
              <span class="script-name">{{ name }}</span>
              <div class="script-item-actions">
                <button @click="editScript(name)" class="action-btn">
                  <font-awesome-icon icon="edit" />
                  Edit
                </button>
                <button @click="runScript(name)" :disabled="isRunButtonDisabled" class="action-btn">
                  <font-awesome-icon icon="play" />
                  Run
                </button>
                <button @click="deleteScript(name)" class="action-btn delete-btn">
                  <font-awesome-icon icon="trash" />
                  Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <div class="frida-processes" v-if="fridaProcesses.length > 0">
        <h4>Processes</h4>
        <div class="processes-list">
          <div v-for="process in fridaProcesses" :key="process.pid" class="process-item">
            <span class="process-name">{{ process.name }}</span>
            <span class="process-pid">PID: {{ process.pid }}</span>
          </div>
        </div>
      </div>
      
      <div class="frida-output" v-if="fridaOutput.length > 0">
        <h4>Output</h4>
        <div class="output-content" ref="fridaOutputContent">
          <div v-for="(output, index) in fridaOutput" :key="index" class="output-line">
            <span class="output-timestamp">{{ output.timestamp }}</span>
            <span class="output-stream" :class="output.stream">{{ output.stream }}</span>
            <span class="output-text">{{ output.text }}</span>
          </div>
        </div>
        <div class="output-controls">
          <button @click="clearOutput" class="output-btn">
            <font-awesome-icon icon="trash" />
            Clear
          </button>
        </div>
      </div>
    </div>
    
    <!-- Script Editor Modal -->
    <div v-if="showScriptEditor" class="modal-overlay" @click="closeScriptEditor">
      <div class="modal-container script-editor-modal" @click.stop>
        <div class="modal-header">
          <h3>{{ editingScriptName ? 'Edit Script' : 'New Script' }}: {{ editingScriptName || newScriptName }}</h3>
          <button @click="closeScriptEditor" class="modal-close-btn">&times;</button>
        </div>
        <div class="modal-body">
          <div class="script-editor-container">
            <textarea 
              v-model="scriptContent" 
              class="script-editor"
              placeholder="Enter your Frida script here..."
              spellcheck="false"
              @keydown.tab.prevent="insertTab"
            ></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button @click="closeScriptEditor" class="modal-btn cancel-btn">Cancel</button>
          <button @click="saveScript" class="modal-btn save-btn">Save</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'FridaTool',
  props: {
    deviceId: {
      type: String,
      required: true
    }
  },
  data() {
    return {
      fridaInstalled: false,
      fridaRunning: false,
      fridaScripts: {},
      fridaProcesses: [],
      fridaOutput: [],
      currentFridaClient: null,
      isScriptRunning: false,
      currentRunningScript: null,
      showScriptEditor: false,
      editingScriptName: null,
      newScriptName: '',
      scriptContent: '',
      fridaInstalling: false,
      fridaStarting: false,
      fridaStopping: false,
      fridaRefreshing: false,
      fridaProcessesLoading: false,
    };
  },
  computed: {
    isRunButtonDisabled() {
      const disabled = !this.fridaRunning || this.isScriptRunning;
      return disabled;
    },
    isStopButtonDisabled() {
      const disabled = !this.isScriptRunning;
      return disabled;
    }
  },
  watch: {
    isScriptRunning(newValue, oldValue) {
      console.log('Script state changed:', oldValue ? 'running' : 'stopped', '=>', newValue ? 'running' : 'stopped');
    }
  },
  async mounted() {
    await this.openFridaTool();
  },
  beforeUnmount() {
    this.closeFridaTool();
  },
  methods: {
    async openFridaTool() {
      try {
        if (this.currentFridaClient) {
          return;
        }
        
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host;
        const port = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
        const fridaWsUrl = `${wsProtocol}//${window.location.hostname}:${port}/api/v1/dynamic-testing/ws/${encodeURIComponent(this.deviceId)}?action=frida`;
        
        const fridaWs = new WebSocket(fridaWsUrl);
        
        fridaWs.addEventListener('open', () => {
          console.log('Frida WebSocket connected');
          
          // Request status
          fridaWs.send(JSON.stringify({
            type: 'frida',
            action: 'status'
          }));
        });
        
        fridaWs.addEventListener('message', (event) => {
          try {
            const message = JSON.parse(event.data);
            if (message.type === 'frida') {
              this.handleFridaMessage(message);
            }
          } catch (e) {
            console.error('Error parsing Frida message:', e);
          }
        });
        
        fridaWs.addEventListener('close', (event) => {
          console.log('Frida WebSocket closed:', event.code, event.reason);
          
          if (event.code !== 1000) {
            setTimeout(() => {
              this.openFridaTool();
            }, 3000);
          }
        });
        
        fridaWs.addEventListener('error', (error) => {
          console.error('Frida WebSocket error:', error);
        });
        
        this.currentFridaClient = fridaWs;

      } catch (error) {
        console.error('Error opening Frida tool:', error);
      }
    },

    closeFridaTool() {
      if (this.currentFridaClient) {
        this.currentFridaClient.close();
        this.currentFridaClient = null;
      }
      
      // Reset Frida data
      this.fridaInstalled = false;
      this.fridaRunning = false;
      this.fridaScripts = {};
      this.fridaProcesses = [];
      this.fridaOutput = [];
      this.isScriptRunning = false;
      this.currentRunningScript = null;
      this.fridaInstalling = false;
      this.fridaStarting = false;
      this.fridaStopping = false;
      this.fridaRefreshing = false;
      this.fridaProcessesLoading = false;
    },

    handleFridaMessage(message) {
      switch (message.action) {
        case 'ready':
        case 'status':
          this.fridaInstalled = message.frida_installed;
          this.fridaRunning = message.frida_running;
          this.fridaRefreshing = false;
          break;
        case 'install_progress':
          // Handle installation progress
          break;
        case 'install_complete':
          this.fridaInstalled = true;
          this.fridaInstalling = false;
          break;
        case 'server_status':
          this.fridaRunning = message.running;
          this.fridaStarting = false;
          this.fridaStopping = false;
          break;
        case 'script_loaded':
          break;
        case 'script_started':
          this.updateScriptState(true, message.script_name);
          console.log('Script started:', message.script_name, 'against', message.target_process);
          break;
        case 'script_stopped':
          this.updateScriptState(false);
          console.log('Script stopped:', message.script_name);
          break;
        case 'script_completed':
          this.updateScriptState(false);
          console.log('Script completed:', message.script_name, 'with return code:', message.return_code);
          
          // Add completion message to output
          this.fridaOutput.push({
            timestamp: new Date().toLocaleTimeString(),
            text: `Script '${message.script_name}' completed (code: ${message.return_code}) - ${message.message}`,
            stream: message.return_code === 0 ? 'stdout' : 'stderr'
          });
          this.scrollToFridaOutput();
          break;
        case 'script_output':
          this.fridaOutput.push({
            timestamp: new Date().toLocaleTimeString(),
            text: message.output,
            stream: message.stream || 'stdout'
          });
          this.scrollToFridaOutput();
          break;
        case 'processes_list':
          this.fridaProcesses = message.processes;
          this.fridaProcessesLoading = false;
          break;

        case 'error':
          console.error('Frida error:', message.message);
          this.updateScriptState(false);
          this.fridaInstalling = false;
          this.fridaStarting = false;
          this.fridaStopping = false;
          this.fridaRefreshing = false;
          this.fridaProcessesLoading = false;
          alert('Frida error: ' + message.message);
          break;
      }
    },

    // Frida action methods
    installFrida() {
      if (this.currentFridaClient && this.currentFridaClient.readyState === WebSocket.OPEN) {
        this.fridaInstalling = true;
        this.currentFridaClient.send(JSON.stringify({
          type: 'frida',
          action: 'install'
        }));
      }
    },

    startFridaServer() {
      if (this.currentFridaClient && this.currentFridaClient.readyState === WebSocket.OPEN) {
        this.fridaStarting = true;
        this.currentFridaClient.send(JSON.stringify({
          type: 'frida',
          action: 'start_server'
        }));
      }
    },

    stopFridaServer() {
      if (this.currentFridaClient && this.currentFridaClient.readyState === WebSocket.OPEN) {
        this.fridaStopping = true;
        this.currentFridaClient.send(JSON.stringify({
          type: 'frida',
          action: 'stop_server'
        }));
      }
    },

    refreshFridaStatus() {
      if (this.currentFridaClient && this.currentFridaClient.readyState === WebSocket.OPEN) {
        this.fridaRefreshing = true;
        this.currentFridaClient.send(JSON.stringify({
          type: 'frida',
          action: 'status'
        }));
      }
    },

    listProcesses() {
      if (this.currentFridaClient && this.currentFridaClient.readyState === WebSocket.OPEN) {
        this.fridaProcessesLoading = true;
        this.currentFridaClient.send(JSON.stringify({
          type: 'frida',
          action: 'list_processes'
        }));
      }
    },

    loadScriptFile(event) {
      const file = event.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
          const scriptContent = e.target.result;
          const scriptName = file.name.replace('.js', '');
          
          this.fridaScripts[scriptName] = scriptContent;
          
          if (this.currentFridaClient && this.currentFridaClient.readyState === WebSocket.OPEN) {
            this.currentFridaClient.send(JSON.stringify({
              type: 'frida',
              action: 'load_script',
              script_name: scriptName,
              script_content: scriptContent
            }));
          }
        };
        reader.readAsText(file);
      }
    },

    createNewScript() {
      this.newScriptName = prompt('Enter script name:');
      if (this.newScriptName) {
        this.editingScriptName = null;
        this.scriptContent = `// ${this.newScriptName}
console.log('Script ${this.newScriptName} started');

Java.perform(function() {
    // Your code here
    console.log('Java.perform called');
});`;
        this.showScriptEditor = true;
      }
    },

    editScript(scriptName) {
      this.editingScriptName = scriptName;
      this.scriptContent = this.fridaScripts[scriptName];
      this.showScriptEditor = true;
    },

    closeScriptEditor() {
      this.showScriptEditor = false;
      this.editingScriptName = null;
      this.newScriptName = '';
      this.scriptContent = '';
    },

    saveScript() {
      const scriptName = this.editingScriptName || this.newScriptName;
      if (scriptName && this.scriptContent) {
        this.fridaScripts[scriptName] = this.scriptContent;
        
        if (this.currentFridaClient && this.currentFridaClient.readyState === WebSocket.OPEN) {
          this.currentFridaClient.send(JSON.stringify({
            type: 'frida',
            action: 'load_script',
            script_name: scriptName,
            script_content: this.scriptContent
          }));
        }
        
        this.closeScriptEditor();
      }
    },

    insertTab(event) {
      // Handle tab key in textarea
      const textarea = event.target;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      
      this.scriptContent = this.scriptContent.substring(0, start) + '    ' + this.scriptContent.substring(end);
      
      this.$nextTick(() => {
        textarea.selectionStart = textarea.selectionEnd = start + 4;
      });
    },

    stopCurrentScript() {
      if (this.currentRunningScript && this.currentFridaClient && this.currentFridaClient.readyState === WebSocket.OPEN) {
        this.currentFridaClient.send(JSON.stringify({
          type: 'frida',
          action: 'stop_script',
          script_name: this.currentRunningScript
        }));
        
        // Add stop message to output
        this.fridaOutput.push({
          timestamp: new Date().toLocaleTimeString(),
          text: `Stopping script '${this.currentRunningScript}'...`,
          stream: 'stdout'
        });
        this.scrollToFridaOutput();
      }
    },

    clearOutput() {
      this.fridaOutput = [];
    },

    deleteScript(scriptName) {
      if (confirm(`Are you sure you want to delete script "${scriptName}"?`)) {
        delete this.fridaScripts[scriptName];
      }
    },

    runScript(scriptName) {
      const targetProcess = prompt('Enter target process name:');
      if (targetProcess) {
        if (this.currentFridaClient && this.currentFridaClient.readyState === WebSocket.OPEN) {
          this.currentFridaClient.send(JSON.stringify({
            type: 'frida',
            action: 'run_script',
            script_name: scriptName,
            target_process: targetProcess
          }));
          
          // Add start message to output
          this.fridaOutput.push({
            timestamp: new Date().toLocaleTimeString(),
            text: `Starting script '${scriptName}' against '${targetProcess}'...`,
            stream: 'stdout'
          });
          this.scrollToFridaOutput();
        }
      }
    },

    scrollToFridaOutput() {
      // Auto-scroll to bottom of Frida output
      this.$nextTick(() => {
        const outputContent = this.$refs.fridaOutputContent;
        if (outputContent) {
          outputContent.scrollTop = outputContent.scrollHeight;
        }
      });
    },

    updateScriptState(isRunning, scriptName = null) {
      this.isScriptRunning = isRunning;
      this.currentRunningScript = scriptName;
      
      // Force Vue to update UI
      this.$nextTick(() => {
        this.$forceUpdate();
      });
    }
  }
};
</script>

<style scoped>
.frida-section {
  margin-top: 0;
  margin-bottom: 0;
  background: #f5f5f5;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.frida-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 15px;
  background: #2d2d2d;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
  color: #ffffff;
  border-bottom: 1px solid #444;
}

.frida-status-indicator {
  margin-left: 10px;
  font-size: 14px;
  font-weight: 500;
}

.status-icon {
  margin-right: 5px;
  font-size: 12px;
}

.status-icon.running {
  color: #4caf50;
}

.status-icon.installed {
  color: #ffc107;
}

.status-icon.not-installed {
  color: #f44336;
}

.frida-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.frida-refresh-btn {
  background: #4a4a4a;
  border: 1px solid #666;
  color: #ffffff;
  border-radius: 4px;
  padding: 6px 8px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  height: 28px;
}

.frida-refresh-btn:hover:not(:disabled) {
  background: #5a5a5a;
  border-color: #777;
}

.frida-refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.frida-toolbar {
  display: flex;
  gap: 10px;
  padding: 10px 15px;
  background: #e0e0e0;
  border-bottom: 1px solid #ccc;
  flex-wrap: wrap;
}

.frida-btn {
  padding: 6px 12px;
  border: 1px solid #ccc;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 6px;
}

.frida-btn:hover:not(:disabled) {
  background: #f0f0f0;
}

.frida-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.frida-content {
  flex: 1;
  padding: 15px;
  background: #fff;
  border-bottom-left-radius: 8px;
  border-bottom-right-radius: 8px;
  overflow-y: auto;
}

.frida-scripts {
  margin-bottom: 20px;
}

.script-section h4 {
  margin: 0 0 10px 0;
  color: #333;
}

.script-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}

.script-btn {
  padding: 6px 12px;
  border: 1px solid #007bff;
  background: #007bff;
  color: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 6px;
}

.script-btn:hover:not(:disabled) {
  background: #0056b3;
  border-color: #0056b3;
}

.script-btn.stop-btn {
  border-color: #f44336;
  background: #f44336;
}

.script-btn.stop-btn:hover:not(:disabled) {
  background: #d32f2f;
  border-color: #d32f2f;
}

.script-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #ccc;
  border-color: #ccc;
}

.scripts-list {
  background: #fff;
  border-radius: 4px;
  border: 1px solid #ddd;
  max-height: 200px;
  overflow-y: auto;
}

.script-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 15px;
  border-bottom: 1px solid #eee;
}

.script-item:last-child {
  border-bottom: none;
}

.script-name {
  font-weight: 500;
  color: #333;
}

.script-item-actions {
  display: flex;
  gap: 5px;
}

.action-btn {
  padding: 4px 8px;
  margin-right: 5px;
  border: 1px solid #ccc;
  background: #fff;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.action-btn:hover:not(:disabled) {
  background: #f0f0f0;
}

.delete-btn {
  color: #d32f2f;
  border-color: #d32f2f;
}

.delete-btn:hover:not(:disabled) {
  background: #ffebee;
}

.frida-processes {
  margin-bottom: 20px;
}

.frida-processes h4 {
  margin: 0 0 10px 0;
  color: #333;
}

.processes-list {
  background: #fff;
  border-radius: 4px;
  border: 1px solid #ddd;
  max-height: 300px;
  overflow-y: auto;
}

.process-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid #eee;
}

.process-item:last-child {
  border-bottom: none;
}

.process-name {
  font-weight: 500;
  color: #333;
}

.process-pid {
  font-size: 12px;
  color: #666;
}

.frida-output {
  margin-top: 20px;
}

.frida-output h4 {
  margin: 0 0 10px 0;
  color: #333;
}

.output-content {
  background: #1e1e1e;
  color: #ffffff;
  font-family: monospace;
  font-size: 13px;
  line-height: 1.4;
  padding: 10px;
  border: 1px solid #444;
  border-radius: 4px;
  max-height: 350px;
  overflow-y: auto;
}

.output-content::-webkit-scrollbar {
  width: 8px;
}

.output-content::-webkit-scrollbar-track {
  background: #333;
  border-radius: 4px;
}

.output-content::-webkit-scrollbar-thumb {
  background: #666;
  border-radius: 4px;
}

.output-content::-webkit-scrollbar-thumb:hover {
  background: #888;
}

.output-line {
  margin-bottom: 3px;
  word-wrap: break-word;
}

.output-timestamp {
  color: #888;
  font-size: 11px;
  margin-right: 8px;
}

.output-stream {
  color: #007bff; /* Default color for stdout */
  font-weight: bold;
  margin-right: 5px;
  font-size: 11px;
  text-transform: uppercase;
}

.output-stream.stderr {
  color: #f44336; /* Red for stderr */
}

.output-text {
  color: #ffffff;
}

.output-controls {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}

.output-btn {
  padding: 5px 10px;
  border: 1px solid #ccc;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 5px;
}

.output-btn:hover:not(:disabled) {
  background: #f0f0f0;
}

.output-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

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
  background-color: #2d2d2d;
  border-radius: 8px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: #ffffff;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 20px;
  background-color: #333;
  border-bottom: 1px solid #444;
}

.modal-header h3 {
  margin: 0;
  font-size: 1.2em;
  color: #ffffff;
}

.modal-close-btn {
  background: none;
  border: none;
  color: #ffffff;
  font-size: 24px;
  cursor: pointer;
  padding: 0 5px;
  line-height: 1;
}

.modal-close-btn:hover {
  color: #ff4444;
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex-grow: 1;
}

.script-editor-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.script-editor {
  width: 100%;
  height: 100%;
  background-color: #1e1e1e;
  color: #ffffff;
  font-family: monospace;
  font-size: 14px;
  line-height: 1.5;
  padding: 10px;
  border: 1px solid #444;
  border-radius: 4px;
  resize: none;
  outline: none;
  box-sizing: border-box;
  white-space: pre-wrap;
  word-wrap: break-word;
  caret-color: #ffffff;
  -webkit-text-fill-color: #ffffff;
  caret-shape: block;
  tab-size: 4;
}

.script-editor::-webkit-scrollbar {
  width: 10px;
}

.script-editor::-webkit-scrollbar-track {
  background: #333;
  border-radius: 5px;
}

.script-editor::-webkit-scrollbar-thumb {
  background: #666;
  border-radius: 5px;
}

.script-editor::-webkit-scrollbar-thumb:hover {
  background: #888;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 15px 20px;
  background-color: #333;
  border-top: 1px solid #444;
}

.modal-btn {
  padding: 8px 15px;
  border: 1px solid #007bff;
  background: #007bff;
  color: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
}

.modal-btn:hover:not(:disabled) {
  background: #0056b3;
  border-color: #0056b3;
}

.modal-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #444;
  border-color: #444;
}

.modal-btn.cancel-btn {
  border-color: #666;
  background: #444;
}

.modal-btn.cancel-btn:hover:not(:disabled) {
  background: #555;
  border-color: #555;
}

.modal-btn.save-btn {
  border-color: #4caf50;
  background: #4caf50;
}

.modal-btn.save-btn:hover:not(:disabled) {
  background: #388e3c;
  border-color: #388e3c;
}

.modal-container.script-editor-modal {
  width: 95%;
  max-width: 900px;
  height: 80vh;
  max-height: 80vh;
}

.modal-container.script-editor-modal .modal-body {
  display: flex;
  flex-direction: column;
  height: calc(100% - 120px);
}

.modal-container.script-editor-modal .script-editor {
  height: 400px;
  min-height: 300px;
  flex-grow: 1;
}

@media (max-width: 1024px) {
  .frida-section {
    max-height: 350px;
  }
  
  .frida-content {
    max-height: 250px;
  }
}

@media (max-width: 768px) {
  .frida-section {
    max-height: 300px;
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
  }
  
  .frida-content {
    max-height: 200px;
  }
  
  .frida-btn {
    flex-direction: column;
    gap: 2px;
    font-size: 10px;
    min-height: 40px;
  }
  
  .script-btn {
    flex-direction: column;
    gap: 2px;
    font-size: 10px;
    min-height: 36px;
  }
}
</style> 