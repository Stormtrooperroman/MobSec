<template>
  <div class="device-streamer">
    <div v-if="error" class="error-message">
      {{ error }}
    </div>
    <div v-else-if="!isConnected && !error" class="connecting-message">
      Connecting to device...
    </div>


    <div class="tools-section" v-if="availableTools.length > 0">
      <h3>Available Tools:</h3>
      <div class="tools-list">
        <div v-for="tool in availableTools" :key="tool.ACTION" class="tool-item" @click="openTool(tool)">
          <span class="tool-name">{{ tool.title || tool.ACTION }}</span>
          <span class="tool-action">{{ tool.ACTION }}</span>
        </div>
      </div>
    </div>

    <div v-if="showTerminal" class="terminal-section">
      <div class="terminal-header">
        <span>Shell Terminal</span>
        <button @click="closeTerminal" class="close-button">×</button>
      </div>
      <div class="terminal-container" ref="terminalContainer"></div>
    </div>

    <!-- File Manager -->
    <div v-if="showFileManager" class="file-manager-section">
      <div class="file-manager-header">
        <span>
          File Manager
          <span class="user-info">
            [{{ fileManagerData.currentUser }}]
          </span>
        </span>
        <button @click="closeFileManager" class="close-button">×</button>
      </div>
      
      <div class="file-manager-path">
        <div class="current-path">
          <span class="path-label">Current Path:</span>
          <span class="path-value">{{ fileManagerData.currentPath }}</span>
        </div>
      </div>
      
      <div class="file-manager-toolbar">
        <button @click="goToParentDirectory" :disabled="fileManagerData.currentPath === '/'">
          ↖️ Parent
        </button>
        <button @click="goToQuickPath('/')">📁 Root</button>
        <button @click="goToQuickPath('/data/local/tmp')">📁 Temp</button>
        <button @click="goToQuickPath('/storage')">📁 Storage</button>
        <button @click="refreshFileList">🔄 Refresh</button>
        <button @click="createDirectory">📁 New Folder</button>
        <input type="file" @change="uploadFile" style="display: none" ref="fileInput">
        <button @click="$refs.fileInput.click()">📤 Upload File</button>
        
        <!-- Simple button to toggle role -->
        <div class="user-controls" v-if="fileManagerData.suAvailable">
          <button 
            @click="toggleSu" 
            :class="['role-toggle-btn', { 'root-mode': fileManagerData.useSu }]"
          >
            {{ fileManagerData.useSu ? '👤 Switch to User' : '🔐 Switch to Root' }}
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
                  📥 Download
                </button>
                <button @click="deleteFile(entry.name)" class="action-btn delete-btn">
                  🗑️ Delete
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script>
import '@/assets/app.css';
import '@/ws-scrcpy/style/morebox.css';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';

import { StreamClientScrcpy } from '@/ws-scrcpy/app/googDevice/client/StreamClientScrcpy';
import { ACTION } from '@/ws-scrcpy/common/Action';

import { MsePlayer } from '@/ws-scrcpy/app/player/MsePlayer';
import { WebCodecsPlayer } from '@/ws-scrcpy/app/player/WebCodecsPlayer';
import { TinyH264Player } from '@/ws-scrcpy/app/player/TinyH264Player';
import { BroadwayPlayer } from '@/ws-scrcpy/app/player/BroadwayPlayer';

import { ShellClient } from '@/ws-scrcpy/app/googDevice/client/ShellClient';
import { FileListingClient } from '@/ws-scrcpy/app/googDevice/client/FileListingClient';

// Register available players
StreamClientScrcpy.registerPlayer(TinyH264Player);
StreamClientScrcpy.registerPlayer(MsePlayer);
StreamClientScrcpy.registerPlayer(WebCodecsPlayer);
StreamClientScrcpy.registerPlayer(BroadwayPlayer);

export default {
  name: 'DeviceStreamer',
  props: {
    deviceId: {
      type: String,
      required: true
    }
  },
  data() {
    return {
      isConnected: false,
      availableTools: [],
      streamClient: null,
      error: null,
      showTerminal: false,
      terminal: null,
      currentShellClient: null,
      fitAddon: null,
      resizeHandler: null,
      showFileManager: false,
      currentFileManagerClient: null,
      fileManagerData: {
        currentPath: '/data/local/tmp',
        entries: [],
        selectedFiles: [],
        suAvailable: false,
        useSu: false,
        currentUser: 'unknown'
      },
    };
  },
  async mounted() {
    // Check WebAssembly support before initializing
    if (typeof WebAssembly !== 'object' || typeof WebAssembly.instantiate !== 'function') {
              this.error = 'WebAssembly is not supported in this browser';
      return;
    }
    
    await this.initializeComponents();
  },
  beforeUnmount() {
    if (this.streamClient) {
      this.streamClient.stop();
    }
    this.closeTerminal();
    this.closeFileManager();
    if (this.resizeHandler) {
      window.removeEventListener('resize', this.resizeHandler);
    }
  },
  methods: {
    async initializeComponents() {
      try {
        let retries = 3;
        let response;
        
        while (retries > 0) {
          try {
            response = await fetch(`/api/v1/dynamic-testing/device/${this.deviceId}/start`, {
              method: 'POST',
              signal: AbortSignal.timeout(10000)
            });
            
            if (response.ok) {
              break;
            }
          } catch (error) {
            console.error('Error starting device server:', error);
            retries--;
            if (retries > 0) {
              await new Promise(resolve => setTimeout(resolve, 2000));
              continue;
            }
            throw error;
          }
        }
        
        if (!response?.ok) {
          throw new Error('Failed to start device server');
        }

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host;
        const wsUrl = `${wsProtocol}//${wsHost}/api/v1/dynamic-testing/ws/${encodeURIComponent(this.deviceId)}?action=stream`;
        
        let playerName = 'tinyh264';
        
        if (typeof MediaSource !== 'undefined' && MediaSource.isTypeSupported) {
          if (MediaSource.isTypeSupported('video/mp4; codecs="avc1.42E01E"')) {
            playerName = 'mse';
            console.log('Using MSE player (preferred)');
          }
        }
        
        if (typeof VideoDecoder !== 'undefined') {
          playerName = 'webcodecs';
          console.log('Using WebCodecs player (best performance)');
        }
        
        console.log('Selected player:', playerName);
        
        const urlParams = new URLSearchParams();
        urlParams.set('action', ACTION.STREAM_SCRCPY);
        urlParams.set('udid', this.deviceId);
        urlParams.set('player', playerName);
        urlParams.set('ws', wsUrl);

        console.log('Starting StreamClientScrcpy with WebSocket URL:', wsUrl);

        const players = StreamClientScrcpy.getPlayers();
        console.log('Registered players:', players.map(p => p.playerCodeName));
        
        if (players.length === 0) {
          throw new Error('No video players registered');
        }

        await this.$nextTick();
        
        this.streamClient = StreamClientScrcpy.start(urlParams);

        if (this.streamClient && this.streamClient.streamReceiver) {
          this.streamClient.streamReceiver.on('connected', () => {
            console.log('StreamReceiver connected successfully');
          });
          
          this.streamClient.streamReceiver.on('disconnected', (event) => {
            console.error('StreamReceiver disconnected:', event);
            if (event.code !== 1000) {
              this.error = 'Connection to device lost';
              this.isConnected = false;
            }
          });
          
        }
        
        if (this.streamClient && this.streamClient.player) {
          console.log('Player state:', this.streamClient.player.getState());
          console.log('Player type:', this.streamClient.player.constructor.name);
        }

        this.availableTools = [
          {
            title: 'Shell',
            ACTION: 'shell',
            client: ShellClient
          },
          {
            title: 'File Manager',
            ACTION: ACTION.FILE_LISTING,
            client: FileListingClient
          }
        ];

        this.isConnected = true;
        console.log('StreamClientScrcpy started successfully');

      } catch (error) {
        console.error('Failed to initialize components:', error);
        this.error = error.message || 'Failed to initialize video stream';
      }
    },



    async openTool(tool) {
      try {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host;
        
        if (tool.ACTION === 'shell') {
          this.showTerminal = true;
          await this.$nextTick();
          
          this.terminal = new Terminal({
            cursorBlink: true,
            fontSize: 14,
            theme: {
              background: '#1e1e1e',
              foreground: '#ffffff'
            },
            convertEol: true,
            fontFamily: 'monospace',
            rows: 20,
            cols: 100,
            scrollback: 10000,
            allowTransparency: true,
            tabStopWidth: 4,
            screenReaderMode: 'off',
            windowsMode: false,
            scrollSensitivity: 1,
            fastScrollSensitivity: 5,
            fastScrollModifier: 'alt',
            scrollOnUserInput: true,
            scrollOnOutput: true,
            rightClickSelectsWord: false,
            fastScrollModifier: 'alt',
            macOptionIsMeta: false,
            macOptionClickForcesSelection: false
          });

          this.fitAddon = new FitAddon();
          this.terminal.loadAddon(this.fitAddon);
          
          this.terminal.open(this.$refs.terminalContainer);
          this.fitAddon.fit();

            setTimeout(() => {
              this.fitAddon.fit();
              this.terminal.scrollToBottom();
            }, 100);

            setTimeout(() => {
              this.terminal.scrollToBottom();
            }, 100);

            this.terminal.onKey(({ key, domEvent }) => {
              
              if (key === '\t') {
                domEvent.preventDefault();
                if (shellWs.readyState === WebSocket.OPEN) {
                  shellWs.send(key);
                  setTimeout(() => {
                    this.terminal.scrollToBottom();
                  }, 10);
                }
              } else {
                setTimeout(() => {
                  this.terminal.scrollToBottom();
                }, 10);
              }
            });

            const resizeHandler = () => {
              if (!this.terminal || !this.fitAddon) return;
              
              try {
                this.fitAddon.fit();
                const { rows, cols } = this.terminal;
                
                if (this.currentShellClient && this.currentShellClient.readyState === WebSocket.OPEN) {
                  this.currentShellClient.send(JSON.stringify({
                    type: 'shell',
                    data: {
                      type: 'resize',
                      rows,
                      cols
                    }
                  }));
                }
                
                setTimeout(() => {
                  this.terminal.scrollToBottom();
                }, 50);
              } catch (error) {
                console.warn('Error in resize handler:', error);
              }
            };

            window.addEventListener('resize', resizeHandler);
            this.resizeHandler = resizeHandler;

          const port = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
          const shellWsUrl = `${wsProtocol}//${window.location.hostname}:${port}/api/v1/dynamic-testing/ws/${encodeURIComponent(this.deviceId)}?action=shell`;
          
          if (this.currentShellClient) {
            this.currentShellClient.close();
            this.currentShellClient = null;
          }
          
          const shellWs = new WebSocket(shellWsUrl);
          shellWs.binaryType = 'arraybuffer';

          shellWs.addEventListener('open', () => {
            this.terminal.clear();
            
            const { rows, cols } = this.terminal;
            shellWs.send(JSON.stringify({
              type: 'shell',
              data: {
                type: 'start',
                rows,
                cols
              }
            }));
            
            this.terminal.onData((data) => {
              if (shellWs.readyState === WebSocket.OPEN) {
                
                shellWs.send(data);
                setTimeout(() => {
                  this.terminal.scrollToBottom();
                }, 10);
              } else {
                console.error('WebSocket not open, state:', shellWs.readyState);
              }
            });
            
            shellWs.addEventListener('message', (event) => {
              if (event.data instanceof ArrayBuffer) {
                const decoder = new TextDecoder();
                const text = decoder.decode(event.data);
                this.terminal.write(text);
                setTimeout(() => {
                  this.terminal.scrollToBottom();
                }, 10);
                this.terminal.focus();
              } else {
                try {
                  const message = JSON.parse(event.data);
                  if (message.type === 'shell' && message.data && message.data.output) {
                    this.terminal.write(message.data.output);
                    setTimeout(() => {
                      this.terminal.scrollToBottom();
                    }, 10);
                    this.terminal.focus();
                  }
                } catch (e) {
                  this.terminal.write(event.data);
                  setTimeout(() => {
                    this.terminal.scrollToBottom();
                  }, 10);
                  this.terminal.focus();
                }
              }
            });
            
            this.terminal.focus();
          });

          shellWs.addEventListener('close', (event) => {
            console.log('Shell WebSocket closed:', event.code, event.reason);
            if (this.terminal) {
              this.terminal.write('\r\n\x1b[31mConnection closed. Press Enter to reconnect.\x1b[0m\r\n');
            }

            if (event.code !== 1000 && this.showTerminal) {
              setTimeout(() => {
                if (this.showTerminal) {
                  this.openTool({ ACTION: 'shell', title: 'Shell' });
                }
              }, 3000);
            }
          });

          shellWs.addEventListener('error', (error) => {
            console.error('Shell WebSocket error:', error);
            this.terminal.write('\r\n\x1b[31mConnection error. Press Enter to reconnect.\x1b[0m\r\n');
          });

          this.currentShellClient = shellWs;

        } else if (tool.ACTION === ACTION.FILE_LISTING || tool.title === 'File Manager') {
          this.showFileManager = true;
          await this.$nextTick();
          
          const port = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
          const fileManagerWsUrl = `${wsProtocol}//${window.location.hostname}:${port}/api/v1/dynamic-testing/ws/${encodeURIComponent(this.deviceId)}?action=file_manager`;
          
          if (this.currentFileManagerClient) {
            this.currentFileManagerClient.close();
            this.currentFileManagerClient = null;
          }
          
          const fileManagerWs = new WebSocket(fileManagerWsUrl);
          
          fileManagerWs.addEventListener('open', () => {
            console.log('File Manager WebSocket connected');
            
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
            
            if (event.code !== 1000 && this.showFileManager) {
              setTimeout(() => {
                if (this.showFileManager) {
                  this.openTool({ ACTION: ACTION.FILE_LISTING, title: 'File Manager' });
                }
              }, 3000);
            }
          });
          
          fileManagerWs.addEventListener('error', (error) => {
            console.error('File Manager WebSocket error:', error);
          });
          
          this.currentFileManagerClient = fileManagerWs;

        } else {
          const params = {
            action: tool.ACTION,
            useProxy: true,
            secure: window.location.protocol === 'https:',
            port: window.location.port ? parseInt(window.location.port) : (window.location.protocol === 'https:' ? 443 : 80),
            hostname: window.location.hostname,
            pathname: `/api/v1/dynamic-testing/ws/${encodeURIComponent(this.deviceId)}`,
            udid: this.deviceId,
            type: 'android',
            ...(tool.ACTION === ACTION.FILE_LISTING && { path: '/data/local/tmp' })
          };
          tool.client.start(params);
        }

      } catch (error) {
        console.error(`Error opening tool ${tool.title}:`, error);
        if (this.terminal) {
          this.terminal.write(`\r\nError: ${error.message}\r\n`);
        }
      }
    },

    closeTerminal() {
      if (this.currentShellClient) {
        this.currentShellClient.close();
        this.currentShellClient = null;
      }
      
      if (this.resizeHandler) {
        window.removeEventListener('resize', this.resizeHandler);
        this.resizeHandler = null;
      }
      
      
      this.showTerminal = false;
    },

    closeFileManager() {
      if (this.currentFileManagerClient) {
        this.currentFileManagerClient.close();
        this.currentFileManagerClient = null;
      }
      
      this.showFileManager = false;
      this.fileManagerData.entries = [];
      this.fileManagerData.selectedFiles = [];
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
      } else if (message.action === 'list') {
        this.fileManagerData.currentPath = message.path;
        this.fileManagerData.entries = message.entries || [];
      } else if (message.action === 'su_toggled') {
        this.fileManagerData.useSu = message.use_su;
        this.fileManagerData.suAvailable = message.su_available;
        this.fileManagerData.currentUser = message.current_user || 'unknown';
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
    },
    
    async refreshDevice() {
      try {
        if (this.streamClient) {
          this.streamClient.stop();
          this.streamClient = null;
        }
        this.isConnected = false;
        await new Promise(resolve => setTimeout(resolve, 1000));
        await this.initializeComponents();
      } catch (error) {
        console.error('Error refreshing device:', error);
        this.error = 'Failed to refresh device connection';
      }
    },
  },
};
</script>

<style scoped>
.device-streamer {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.error-message {
  color: #ff5722;
  padding: 1rem;
  text-align: center;
  background-color: #fff3e0;
  border-radius: 4px;
  margin: 1rem;
  border: 1px solid #ffcc80;
}

.connecting-message {
  padding: 1rem;
  text-align: center;
  color: #666;
  font-size: 1.1rem;
}

.video-section {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 400px;
  background-color: #f5f5f5;
  border-radius: 8px;
  margin: 1rem;
  overflow: hidden;
}

.device-view {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #000;
  border-radius: 8px;
  position: relative;
}

.device-view canvas {
  max-width: 100%;
  max-height: 100%;
}

.device-view .video {
  display: block !important;
  width: auto !important;
  height: auto !important;
  max-width: 100%;
  max-height: 100%;
}

.tools-section {
  padding: 1rem;
  background-color: #f8f9fa;
  border-top: 1px solid #dee2e6;
  margin: 1rem;
  border-radius: 8px;
}

.tools-list {
  display: flex;
  flex-direction: row;
  gap: 1rem;
  margin: 1rem 0;
  flex-wrap: wrap;
}

.tool-item {
  display: flex;
  align-items: center;
  padding: 0.5rem 1rem;
  border: 1px solid #dee2e6;
  cursor: pointer;
  border-radius: 4px;
  color: #333;
  transition: background-color 0.2s ease;
  background-color: #fff;
}

.tool-item:hover {
  background-color: #e9ecef;
}

.tool-name {
  font-weight: bold;
  margin-right: 0.5rem;
}

.tool-action {
  color: #666;
}

.terminal-section {
  margin-top: 1rem;
  background: #1e1e1e;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 15px;
  background: #2d2d2d;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
  color: #ffffff;
}

.close-button {
  background: none;
  border: none;
  color: #ffffff;
  font-size: 20px;
  cursor: pointer;
  padding: 0 5px;
}

.close-button:hover {
  color: #ff4444;
}

.terminal-container {
  flex: 1;
  padding: 10px;
  background: #1e1e1e;
  border-bottom-left-radius: 8px;
  border-bottom-right-radius: 8px;
  overflow: hidden;
  min-height: 400px;
  max-height: 400px;
  display: flex;
  flex-direction: column;
}

.terminal-container .xterm {
  height: 100%;
  width: 100%;
  flex: 1;
  overflow: hidden;
}

.terminal-container .xterm-viewport {
  overflow-y: scroll !important;
  overflow-x: hidden !important;
  scrollbar-width: thin;
  scrollbar-color: #666 #333;
}

.terminal-container .xterm-viewport::-webkit-scrollbar {
  width: 12px;
}

.terminal-container .xterm-viewport::-webkit-scrollbar-track {
  background: #333;
}

.terminal-container .xterm-viewport::-webkit-scrollbar-thumb {
  background: #666;
  border-radius: 6px;
}

.terminal-container .xterm-viewport::-webkit-scrollbar-thumb:hover {
  background: #888;
}

.terminal-container .xterm-screen {
  height: 100% !important;
  width: 100% !important;
}

.terminal-container .xterm-text-layer {
  width: 100% !important;
  height: 100% !important;
}

.terminal-container .xterm-text-layer canvas {
  width: 100% !important;
  height: 100% !important;
}

.terminal-container .xterm-selection-layer {
  width: 100% !important;
  height: 100% !important;
}

.terminal-container .xterm-link-layer {
  width: 100% !important;
  height: 100% !important;
}

.terminal-container .xterm-cursor-layer {
  width: 100% !important;
  height: 100% !important;
}

.file-manager-section {
  margin-top: 1rem;
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

.su-indicator {
  color: #ff5722;
  font-weight: bold;
  margin-left: 8px;
  padding: 2px 6px;
  background: rgba(255, 87, 34, 0.2);
  border-radius: 3px;
  font-size: 0.9em;
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

.su-toggle {
  margin-left: auto;
  display: flex;
  align-items: center;
}

.su-toggle-label {
  display: flex;
  align-items: center;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
}

.su-checkbox {
  margin-right: 5px;
  cursor: pointer;
}

.su-text {
  color: #d32f2f;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.su-toggle-label:hover .su-text {
  color: #b71c1c;
}

.file-manager-content {
  flex: 1;
  padding: 15px;
  background: #fff;
  overflow-y: auto;
  max-height: 400px;
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

.file-icon.folder:before {
  content: "📁 ";
  margin-right: 4px;
}

.file-icon.file {
  color: #424242;
}

.file-icon.file:before {
  content: "📄 ";
  margin-right: 4px;
}

.file-icon.symlink {
  color: #ff9800;
  cursor: pointer;
}

.file-icon.symlink:hover {
  background: #fff3e0;
}

.file-icon.symlink:before {
  content: "🔗 ";
  margin-right: 4px;
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
}

.action-btn:hover {
  background: #f0f0f0;
}

.delete-btn {
  color: #d32f2f;
  border-color: #d32f2f;
}

.delete-btn:hover {
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
}
</style>
