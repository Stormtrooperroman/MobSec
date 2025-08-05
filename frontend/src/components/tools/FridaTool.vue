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
        <button @click="refreshFridaStatus" class="frida-refresh-btn" title="Refresh status" :disabled="fridaRefreshing">
          <font-awesome-icon v-if="fridaRefreshing" icon="spinner" spin />
          <font-awesome-icon v-else icon="refresh" />
        </button>
      </div>
    </div>
    
    <div class="frida-toolbar">
      <div class="frida-toolbar-left">
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
      
      <div class="frida-toolbar-right">
        <div class="process-input-group">
          <input 
            v-model="targetProcessName" 
            type="text" 
            placeholder="Enter process name"
            class="process-input"
            @keyup.enter="runSelectedScript"
            :disabled="!fridaRunning || isScriptRunning"
          />
          <div v-if="showProcessError" class="process-error-overlay">
            <div class="process-error">
              <font-awesome-icon icon="exclamation-triangle" />
              Please select a process before running a script
            </div>
          </div>
        </div>
      </div>
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
            <button @click="loadScriptsFromAPI" :disabled="scriptsLoading" class="script-btn">
              <font-awesome-icon v-if="scriptsLoading" icon="spinner" spin />
              <font-awesome-icon v-else icon="refresh" />
              Refresh Scripts
            </button>
            <button @click="stopCurrentScript" :disabled="isStopButtonDisabled" class="script-btn stop-btn">
              <font-awesome-icon v-if="fridaStopping" icon="spinner" spin />
              <font-awesome-icon v-else icon="stop" />
              Stop Script
            </button>
          </div>
          
          <div class="scripts-list">
            <div v-for="(script, name) in fridaScripts" :key="name" class="script-item" :data-script="name">
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
          <div v-for="process in fridaProcesses" :key="process.pid" class="process-item" @click="selectProcess(process.name)">
            <div class="process-info">
              <div class="process-name">{{ process.name }}</div>
              <div class="process-pid">PID: {{ process.pid }}</div>
            </div>
            <div class="process-icon">
              <font-awesome-icon icon="chevron-right" />
            </div>
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
      selectedScriptName: null,
      newScriptName: '',
      scriptContent: '',
      targetProcessName: '',
      fridaInstalling: false,
      fridaStarting: false,
      fridaStopping: false,
      fridaRefreshing: false,
      fridaProcessesLoading: false,
      scriptsLoading: false,
      showProcessError: false,
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
    await this.loadScriptsFromAPI();
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

    async loadScriptFile(event) {
      const file = event.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = async (e) => {
          const scriptContent = e.target.result;
          const scriptName = file.name.replace('.js', '');
          
          try {
            await this.createScriptAPI(scriptName, scriptContent);
          } catch (error) {
            this.fridaOutput.push({
              timestamp: new Date().toLocaleTimeString(),
              text: `Error loading script '${scriptName}': ${error.message}`,
              stream: 'stderr'
            });
          }
          this.scrollToFridaOutput();
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

    selectScript(scriptName) {
      this.selectedScriptName = scriptName;
      
      // Highlight the selected script
      this.$nextTick(() => {
        const scriptItems = document.querySelectorAll('.script-item');
        scriptItems.forEach(item => {
          item.classList.remove('selected');
        });
        const selectedItem = document.querySelector(`[data-script="${scriptName}"]`);
        if (selectedItem) {
          selectedItem.classList.add('selected');
        }
      });
    },

    runScript(scriptName) {
      if (!this.targetProcessName.trim()) {
        // Show error and highlight process input
        this.showProcessError = true;
        this.highlightProcessInput();
        
        // Hide error after 3 seconds
        setTimeout(() => {
          this.showProcessError = false;
        }, 3000);
        
        return;
      }
      
      // Run the script
      if (this.currentFridaClient && this.currentFridaClient.readyState === WebSocket.OPEN) {
        this.currentFridaClient.send(JSON.stringify({
          type: 'frida',
          action: 'run_script',
          script_name: scriptName,
          target_process: this.targetProcessName.trim()
        }));
      }
    },

    highlightProcessInput() {
      const processInput = document.querySelector('.process-input');
      if (processInput) {
        processInput.classList.add('error-highlight');
        processInput.focus();
        
        // Remove highlight after animation
        setTimeout(() => {
          processInput.classList.remove('error-highlight');
        }, 2000);
      }
    },

    selectProcess(processName) {
      this.targetProcessName = processName;
      this.showProcessError = false; // Hide error when process is selected
    },

    runSelectedScript() {
      if (this.targetProcessName.trim() && this.selectedScriptName) {
        if (this.currentFridaClient && this.currentFridaClient.readyState === WebSocket.OPEN) {
          this.currentFridaClient.send(JSON.stringify({
            type: 'frida',
            action: 'run_script',
            script_name: this.selectedScriptName,
            target_process: this.targetProcessName.trim()
          }));
        }
      } else if (!this.selectedScriptName) {
        alert('Please select a script first');
      } else if (!this.targetProcessName.trim()) {
        alert('Please enter a process name');
      }
    },

    async saveScript() {
      const scriptName = this.editingScriptName || this.newScriptName;
      if (scriptName && this.scriptContent) {
        try {
          if (this.editingScriptName) {
            // Update existing script
            await this.updateScriptAPI(scriptName, this.scriptContent);
          } else {
            // Create new script
            await this.createScriptAPI(scriptName, this.scriptContent);
          }
          this.scrollToFridaOutput();
        } catch (error) {
          this.fridaOutput.push({
            timestamp: new Date().toLocaleTimeString(),
            text: `Error saving script '${scriptName}': ${error.message}`,
            stream: 'stderr'
          });
          this.scrollToFridaOutput();
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
      }
    },

    clearOutput() {
      this.fridaOutput = [];
    },

    async deleteScript(scriptName) {
      if (confirm(`Are you sure you want to delete script "${scriptName}"?`)) {
        try {
          await this.deleteScriptAPI(scriptName);
        } catch (error) {
          this.fridaOutput.push({
            timestamp: new Date().toLocaleTimeString(),
            text: `Error deleting script '${scriptName}': ${error.message}`,
            stream: 'stderr'
          });
        }
        this.scrollToFridaOutput();
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
    },

    // API methods for script management
    async loadScriptsFromAPI() {
      try {
        this.scriptsLoading = true;
        const response = await fetch('/api/v1/frida/scripts');
        if (response.ok) {
          const scripts = await response.json();
          this.fridaScripts = {};
          for (const script of scripts) {
            // Load script content
            const contentResponse = await fetch(`/api/v1/frida/scripts/${script.name}/content`);
            if (contentResponse.ok) {
              const contentData = await contentResponse.json();
              this.fridaScripts[script.name] = contentData.content;
            }
          }
        }
      } catch (error) {
        console.error('Error loading scripts from API:', error);
      } finally {
        this.scriptsLoading = false;
      }
    },

    async createScriptAPI(name, content) {
      try {
        const response = await fetch('/api/v1/frida/scripts', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            name: name,
            content: content
          })
        });
        
        if (response.ok) {
          this.fridaScripts[name] = content;
          return true;
        } else {
          const error = await response.json();
          throw new Error(error.detail || 'Failed to create script');
        }
      } catch (error) {
        console.error('Error creating script:', error);
        throw error;
      }
    },

    async updateScriptAPI(name, content) {
      try {
        const response = await fetch(`/api/v1/frida/scripts/${name}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            content: content
          })
        });
        
        if (response.ok) {
          this.fridaScripts[name] = content;
          return true;
        } else {
          const error = await response.json();
          throw new Error(error.detail || 'Failed to update script');
        }
      } catch (error) {
        console.error('Error updating script:', error);
        throw error;
      }
    },

    async deleteScriptAPI(name) {
      try {
        const response = await fetch(`/api/v1/frida/scripts/${name}`, {
          method: 'DELETE'
        });
        
        if (response.ok) {
          delete this.fridaScripts[name];
          return true;
        } else {
          const error = await response.json();
          throw new Error(error.detail || 'Failed to delete script');
        }
      } catch (error) {
        console.error('Error deleting script:', error);
        throw error;
      }
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
  position: relative;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 15px;
  padding: 10px 15px;
  background: #e0e0e0;
  border-bottom: 1px solid #ccc;
  flex-wrap: wrap;
}

.frida-toolbar-left {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.frida-toolbar-right {
  display: flex;
  align-items: center;
}

.process-input-group {
  position: relative;
  display: flex;
  align-items: center;
  min-width: 250px;
}

.process-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #ccc;
  background: #fff;
  border-radius: 4px;
  font-size: 12px;
  outline: none;
  transition: all 0.2s ease;
  min-width: 150px;
}

.process-input:focus {
  border-color: #007bff;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
}

.process-input:disabled {
  background: #f5f5f5;
  color: #999;
  cursor: not-allowed;
}

.process-input.error-highlight {
  border-color: #f44336;
  box-shadow: 0 0 0 2px rgba(244, 67, 54, 0.25);
  animation: shake 0.5s ease-in-out;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-5px); }
  75% { transform: translateX(5px); }
}

.process-error-overlay {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 1000;
  margin-top: 5px;
}

.process-error {
  padding: 8px 12px;
  background: #ffebee;
  border: 1px solid #f44336;
  border-radius: 4px;
  color: #d32f2f;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  animation: fadeIn 0.3s ease-in;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  white-space: nowrap;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
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
  transition: all 0.2s ease;
}

.script-item:hover {
  background: #f8f9fa;
}

.script-item.selected {
  background: #e3f2fd;
  border-left: 3px solid #007bff;
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
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  max-height: 300px;
  overflow-y: auto;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.process-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: all 0.2s ease;
  background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
}

.process-item:hover {
  background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%);
  transform: translateX(2px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.process-item:last-child {
  border-bottom: none;
}

.process-item:active {
  transform: translateX(1px);
  background: linear-gradient(135deg, #bbdefb 0%, #e1bee7 100%);
}

.process-info {
  flex: 1;
}

.process-name {
  font-weight: 600;
  color: #2c3e50;
  font-size: 14px;
  margin-bottom: 2px;
}

.process-pid {
  font-size: 12px;
  color: #7f8c8d;
  font-weight: 500;
}

.process-icon {
  color: #3498db;
  font-size: 14px;
  opacity: 0.7;
  transition: all 0.2s ease;
}

.process-item:hover .process-icon {
  opacity: 1;
  transform: translateX(2px);
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
  
  .frida-toolbar {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  
  .process-input-group {
    min-width: auto;
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
  
  .process-input-group {
    flex-direction: column;
    align-items: stretch;
  }
}
</style> 