<template>
  <div class="file-manager-section">
    <div class="file-manager-header">
      <span>
        File Manager
        <span class="user-info">
          [{{ fileManagerData.currentUser }}]
        </span>
      </span>
    </div>
    
    <div class="file-manager-path">
      <div class="current-path">
        <span class="path-label">Current Path:</span>
        <span class="path-value">{{ fileManagerData.currentPath }}</span>
      </div>
    </div>
    
    <div class="file-manager-toolbar">
      <button @click="goToParentDirectory" :disabled="fileManagerData.currentPath === '/'">
        <font-awesome-icon icon="level-up-alt" /> Parent
      </button>
      <button @click="goToQuickPath('/')">
        <font-awesome-icon icon="folder" /> Root
      </button>
      <button @click="goToQuickPath('/data/local/tmp')">
        <font-awesome-icon icon="folder" /> Temp
      </button>
      <button @click="goToQuickPath('/storage')">
        <font-awesome-icon icon="folder" /> Storage
      </button>
      <button @click="refreshFileList">
        <font-awesome-icon icon="sync" /> Refresh
      </button>
      <button @click="createDirectory">
        <font-awesome-icon icon="folder-plus" /> New Folder
      </button>
      <input type="file" @change="uploadFile" style="display: none" ref="fileInput">
      <button @click="$refs.fileInput.click()">
        <font-awesome-icon icon="upload" /> Upload File
      </button>
      
      <!-- Simple button to toggle role -->
      <div class="user-controls" v-if="fileManagerData.suAvailable || fileManagerData.currentUser !== 'unknown'">
        <button 
          @click="toggleSu" 
          :class="['role-toggle-btn', { 'root-mode': fileManagerData.useSu }]"
          :disabled="!fileManagerData.suAvailable"
        >
          <font-awesome-icon :icon="fileManagerData.useSu ? 'user' : 'lock'" />
          {{ fileManagerData.useSu ? 'Switch to User' : 'Switch to Root' }}
        </button>
      </div>
    </div>
    
    <div class="file-manager-content">
      <table class="file-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Size</th>
            <th>Modified</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in fileManagerData.entries" :key="entry.name" class="file-row">
            <td class="file-name">
              <span 
                :class="['file-icon', getFileIconClass(entry)]"
                @click="handleFileClick(entry)"
              >
                <font-awesome-icon 
                  :icon="getFileIcon(entry)" 
                  class="file-type-icon"
                />
                {{ entry.name }}
                <span v-if="entry.type === 'symlink' && entry.target" class="symlink-target">
                  → {{ entry.target }}
                </span>
              </span>
            </td>
            <td>{{ entry.type }}</td>
            <td>{{ entry.is_directory ? '-' : formatFileSize(entry.size) }}</td>
            <td>{{ entry.modified }}</td>
            <td class="file-actions">
              <button v-if="!entry.is_directory && entry.type !== 'symlink'" @click="downloadFile(entry.name)" class="action-btn">
                <font-awesome-icon icon="download" />
                Download
              </button>
              <button @click="deleteFile(entry.name)" class="action-btn delete-btn">
                <font-awesome-icon icon="trash" />
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script>
export default {
  name: 'FileManager',
  props: {
    deviceId: {
      type: String,
      required: true
    }
  },
  data() {
    return {
      currentFileManagerClient: null,
      fileManagerScrollHandler: null,
      fileManagerData: {
        currentPath: '/data/local/tmp',
        entries: [],
        selectedFiles: [],
        suAvailable: false,
        useSu: false,
        currentUser: 'unknown'
      }
    };
  },
  async mounted() {
    await this.openFileManager();
  },
  beforeUnmount() {
    this.closeFileManager();
  },
  methods: {
    async openFileManager() {
      try {
        if (this.currentFileManagerClient && this.currentFileManagerClient.readyState === WebSocket.OPEN) {
          return;
        }
        
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host;
        
        await this.$nextTick();
        
        const fileManagerContent = this.$el.querySelector('.file-manager-content');
        if (fileManagerContent) {
          this.fileManagerScrollHandler = (event) => {
            const { scrollTop, scrollHeight, clientHeight } = fileManagerContent;
            const isAtTop = scrollTop === 0;
            const isAtBottom = scrollTop + clientHeight >= scrollHeight;
            
            if (event.deltaY < 0 && isAtTop) {
              event.preventDefault();
              event.stopPropagation();
            } else if (event.deltaY > 0 && isAtBottom) {
              event.preventDefault();
              event.stopPropagation();
            } else if (!isAtTop && !isAtBottom) {
              event.stopPropagation();
            }
          };
          
          fileManagerContent.addEventListener('wheel', this.fileManagerScrollHandler, { passive: false });
        }
        
        const port = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
        const fileManagerWsUrl = `${wsProtocol}//${window.location.hostname}:${port}/api/v1/dynamic-testing/ws/${encodeURIComponent(this.deviceId)}?action=file_manager`;
        
        if (this.currentFileManagerClient) {
          this.currentFileManagerClient.close();
          this.currentFileManagerClient = null;
        }
        
        const fileManagerWs = new WebSocket(fileManagerWsUrl);
        
        fileManagerWs.addEventListener('open', () => {
          console.log('File Manager WebSocket connected');
          
          // Request initial status and file list
          fileManagerWs.send(JSON.stringify({
            type: 'file_manager',
            action: 'list',
            path: '/data/local/tmp'
          }));
        });
        
        fileManagerWs.addEventListener('message', (event) => {
          try {
            const message = JSON.parse(event.data);
            if (message.type === 'file_manager') {
              this.handleFileManagerMessage(message);
            }
          } catch (e) {
            console.error('Error parsing file manager message:', e);
          }
        });
        
        fileManagerWs.addEventListener('close', (event) => {
          console.log('File Manager WebSocket closed:', event.code, event.reason);
          
          if (event.code !== 1000) {
            setTimeout(() => {
              this.openFileManager();
            }, 3000);
          }
        });
        
        fileManagerWs.addEventListener('error', (error) => {
          console.error('File Manager WebSocket error:', error);
        });
        
        this.currentFileManagerClient = fileManagerWs;

      } catch (error) {
        console.error('Error opening file manager:', error);
      }
    },

    closeFileManager() {
      if (this.currentFileManagerClient) {
        this.currentFileManagerClient.close();
        this.currentFileManagerClient = null;
      }
      
      if (this.fileManagerScrollHandler) {
        const fileManagerContent = this.$el?.querySelector('.file-manager-content');
        if (fileManagerContent) {
          fileManagerContent.removeEventListener('wheel', this.fileManagerScrollHandler);
        }
        this.fileManagerScrollHandler = null;
      }
      
      // Reset file manager data
      this.fileManagerData.entries = [];
      this.fileManagerData.selectedFiles = [];
      this.fileManagerData.currentUser = 'unknown';
      this.fileManagerData.useSu = false;
      this.fileManagerData.suAvailable = false;
    },

    handleFileManagerMessage(message) {
      console.log('File Manager message:', message);
      
      if (message.action === 'ready') {
        console.log('Ready message received:', {
          current_path: message.current_path,
          su_available: message.su_available,
          use_su: message.use_su,
          current_user: message.current_user
        });
        this.fileManagerData.currentPath = message.current_path;
        this.fileManagerData.suAvailable = message.su_available || false;
        this.fileManagerData.useSu = message.use_su || false;
        this.fileManagerData.currentUser = message.current_user || 'unknown';
        console.log('Updated fileManagerData:', this.fileManagerData);
        
        // Force Vue to update the UI
        this.$nextTick(() => {
          this.$forceUpdate();
        });
      } else if (message.action === 'list') {
        this.fileManagerData.currentPath = message.path;
        this.fileManagerData.entries = message.entries || [];
      } else if (message.action === 'su_toggled') {
        this.fileManagerData.useSu = message.use_su;
        this.fileManagerData.suAvailable = message.su_available;
        this.fileManagerData.currentUser = message.current_user || 'unknown';
        
        // Force Vue to update the UI
        this.$nextTick(() => {
          this.$forceUpdate();
        });
      } else if (message.action === 'error') {
        console.error('File Manager error:', message.message);
        alert(`Error: ${message.message}`);
      } else if (message.action === 'download') {
        this.handleFileDownload(message);
      } else if (message.action === 'upload' || message.action === 'delete' || message.action === 'mkdir') {
        this.refreshFileList();
      }
    },

    handleFileDownload(message) {
      try {
        const binaryString = atob(message.data);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }
        
        const blob = new Blob([bytes]);
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = message.filename;
        link.click();
        URL.revokeObjectURL(url);
      } catch (error) {
        console.error('Error downloading file:', error);
        alert('Error downloading file');
      }
    },

    navigateToDirectory(path) {
      if (this.currentFileManagerClient && this.currentFileManagerClient.readyState === WebSocket.OPEN) {
        let normalizedPath = path.replace(/\/+/g, '/');
        if (normalizedPath !== '/' && normalizedPath.endsWith('/')) {
          normalizedPath = normalizedPath.slice(0, -1);
        }
        
        this.currentFileManagerClient.send(JSON.stringify({
          type: 'file_manager',
          action: 'list',
          path: normalizedPath
        }));
      }
    },

    downloadFile(filename) {
      const fullPath = this.fileManagerData.currentPath + '/' + filename;
      if (this.currentFileManagerClient && this.currentFileManagerClient.readyState === WebSocket.OPEN) {
        this.currentFileManagerClient.send(JSON.stringify({
          type: 'file_manager',
          action: 'download',
          path: fullPath
        }));
      }
    },

    deleteFile(filename) {
      if (confirm(`Are you sure you want to delete ${filename}?`)) {
        const fullPath = this.fileManagerData.currentPath + '/' + filename;
        if (this.currentFileManagerClient && this.currentFileManagerClient.readyState === WebSocket.OPEN) {
          this.currentFileManagerClient.send(JSON.stringify({
            type: 'file_manager',
            action: 'delete',
            path: fullPath
          }));
        }
      }
    },

    createDirectory() {
      const dirName = prompt('Enter directory name:');
      if (dirName) {
        const fullPath = this.fileManagerData.currentPath + '/' + dirName;
        if (this.currentFileManagerClient && this.currentFileManagerClient.readyState === WebSocket.OPEN) {
          this.currentFileManagerClient.send(JSON.stringify({
            type: 'file_manager',
            action: 'mkdir',
            path: fullPath
          }));
        }
      }
    },

    refreshFileList() {
      if (this.currentFileManagerClient && this.currentFileManagerClient.readyState === WebSocket.OPEN) {
        this.currentFileManagerClient.send(JSON.stringify({
          type: 'file_manager',
          action: 'list',
          path: this.fileManagerData.currentPath
        }));
      }
    },

    uploadFile(event) {
      const file = event.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
          const arrayBuffer = e.target.result;
          const bytes = new Uint8Array(arrayBuffer);
          let binaryString = '';
          for (let i = 0; i < bytes.length; i++) {
            binaryString += String.fromCharCode(bytes[i]);
          }
          const base64Data = btoa(binaryString);
          
          const fullPath = this.fileManagerData.currentPath + '/' + file.name;
          if (this.currentFileManagerClient && this.currentFileManagerClient.readyState === WebSocket.OPEN) {
            this.currentFileManagerClient.send(JSON.stringify({
              type: 'file_manager',
              action: 'upload',
              path: fullPath,
              data: base64Data
            }));
          }
        };
        reader.readAsArrayBuffer(file);
      }
    },

    goToParentDirectory() {
      const currentPath = this.fileManagerData.currentPath;
      if (currentPath !== '/') {
        const parentPath = currentPath.substring(0, currentPath.lastIndexOf('/')) || '/';
        this.navigateToDirectory(parentPath);
      }
    },

    goToQuickPath(path) {
      this.navigateToDirectory(path);
    },

    toggleSu() {
      if (this.currentFileManagerClient && this.currentFileManagerClient.readyState === WebSocket.OPEN) {
        this.currentFileManagerClient.send(JSON.stringify({
          type: 'file_manager',
          action: 'toggle_su'
        }));
      }
    },

    formatFileSize(bytes) {
      if (bytes === 0) return '0 B';
      const k = 1024;
      const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    getFileIconClass(entry) {
      if (entry.is_directory) {
        return 'folder';
      } else if (entry.type === 'symlink') {
        return 'symlink';
      } else {
        return 'file';
      }
    },

    getFileIcon(entry) {
      if (entry.is_directory) {
        return 'folder';
      } else if (entry.type === 'symlink') {
        return 'link';
      } else {
        return 'file';
      }
    },

    handleFileClick(entry) {
      if (entry.is_directory) {
        const newPath = this.fileManagerData.currentPath === '/' 
          ? '/' + entry.name 
          : this.fileManagerData.currentPath + '/' + entry.name;
        this.navigateToDirectory(newPath);
      } else if (entry.type === 'symlink') {
        if (entry.target) {
          const targetPath = entry.target.startsWith('/') 
            ? entry.target 
            : this.fileManagerData.currentPath + '/' + entry.target;
          this.navigateToDirectory(targetPath);
        }
      }
    }
  }
};
</script>

<style scoped>
.file-manager-section {
  margin-top: 0;
  margin-bottom: 0;
  background: #f5f5f5;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.file-manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 15px;
  background: #2d2d2d;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
  color: #ffffff;
}

.file-manager-path {
  padding: 10px 15px;
  background: #f8f9fa;
  border-bottom: 1px solid #e0e0e0;
}

.current-path {
  display: flex;
  align-items: center;
  gap: 10px;
}

.path-label {
  font-weight: 600;
  color: #333;
  font-size: 14px;
}

.path-value {
  font-family: monospace;
  background: #fff;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid #ddd;
  color: #555;
  font-size: 13px;
  word-break: break-all;
}

.file-manager-toolbar {
  display: flex;
  gap: 10px;
  padding: 10px 15px;
  background: #e0e0e0;
  border-bottom: 1px solid #ccc;
}

.file-manager-toolbar button {
  padding: 5px 10px;
  border: 1px solid #ccc;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.file-manager-toolbar button:hover:not(:disabled) {
  background: #f0f0f0;
}

.file-manager-toolbar button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.file-manager-content {
  flex: 1;
  padding: 15px;
  background: #fff;
  overflow-y: auto;
  max-height: 250px;
}

.file-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.file-table th,
.file-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid #eee;
}

.file-table th {
  background: #f8f9fa;
  font-weight: 600;
  color: #333;
}

.file-row:hover {
  background: #f8f9fa;
}

.file-name {
  cursor: pointer;
}

.file-icon {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}

.file-icon.folder {
  color: #1976d2;
  cursor: pointer;
}

.file-icon.folder:hover {
  background: #e3f2fd;
}

.file-icon.file {
  color: #424242;
}

.file-icon.symlink {
  color: #ff9800;
  cursor: pointer;
}

.file-icon.symlink:hover {
  background: #fff3e0;
}

.file-type-icon {
  margin-right: 6px;
}

.symlink-target {
  color: #666;
  font-size: 0.9em;
  font-style: italic;
}

.file-actions {
  white-space: nowrap;
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

.user-info {
  color: #666;
  font-size: 0.9em;
  margin-left: 8px;
}

.user-controls {
  margin-left: auto;
  display: flex;
  align-items: center;
}

.role-toggle-btn {
  padding: 5px 10px;
  border: 1px solid #ccc;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s ease;
}

.role-toggle-btn:hover:not(:disabled) {
  background: #f0f0f0;
}

.role-toggle-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.role-toggle-btn.root-mode {
  background-color: #4caf50;
  color: white;
  border-color: #4caf50;
}

.role-toggle-btn.root-mode:hover:not(:disabled) {
  background-color: #45a049;
  border-color: #45a049;
  color: white;
}

@media (max-width: 1024px) {
  .file-manager-section {
    max-height: 350px;
  }
  
  .file-manager-content {
    max-height: 250px;
  }
}

@media (max-width: 768px) {
  .file-manager-section {
    max-height: 300px;
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
  }
  
  .file-manager-content {
    max-height: 200px;
  }
}
</style> 