<template>
  <div class="device-streamer">
    <div v-if="error" class="error-message">
      {{ error }}
    </div>
    <div v-else-if="!isConnected && !error" class="connecting-message">
      Connecting to device...
    </div>
    
        <div v-else class="container">
      <div class="main-layout">
        <div class="terminal-section">
          <div class="terminal-header">
            <span>Shell Terminal</span>
            <div class="terminal-controls">
              <button @click="restartTerminal" class="terminal-restart-btn" title="Перезапустить терминал">
                <font-awesome-icon icon="refresh" />
              </button>
              <span class="terminal-status" :class="{ 'connected': terminalConnected }">
                {{ terminalConnected ? '🟢' : '🔴' }}
              </span>
            </div>
          </div>
          <div class="terminal-container" ref="terminalContainer"></div>
        </div>

        <div class="device-screen-area" ref="deviceScreenArea">
        </div>
      </div>

      <div class="tools-section" v-if="availableTools.length > 0">
        <h3>Available Tools:</h3>
        <div class="tools-list">
          <div v-for="tool in availableTools" :key="tool.ACTION" 
               :class="['tool-item', { 'disabled': isToolDisabled(tool) }]" 
               @click="!isToolDisabled(tool) && openTool(tool)">
            <span class="tool-name">{{ tool.title || tool.ACTION }}</span>
          </div>
        </div>
      </div>

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
  </div>
</template>

<script>
import '@/assets/app.css';
import '@/assets/devicelist.css';
import '@/ws-scrcpy/style/morebox.css';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { AttachAddon } from 'xterm-addon-attach';
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
      terminal: null,
      currentShellClient: null,
      fitAddon: null,
      resizeHandler: null,
      preventPageScrollHandler: null,
      terminalCopyHandler: null,
      terminalInitializing: false,
      terminalConnected: false,
      showFileManager: false,
      currentFileManagerClient: null,
      fileManagerScrollHandler: null,
      fileManagerData: {
        currentPath: '/data/local/tmp',
        entries: [],
        selectedFiles: [],
        suAvailable: false,
        useSu: false,
        currentUser: 'unknown'
      },
      deviceViewObserver: null,
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
      if (this.streamClient.streamReceiver) {
        this.streamClient.streamReceiver.stop();
      }
      if (this.streamClient.player) {
        this.streamClient.player.stop();
      }
      this.cleanupStreamElements();
    }
    this.closeTerminal();
    this.closeFileManager();
    if (this.resizeHandler) {
      window.removeEventListener('resize', this.resizeHandler);
      this.resizeHandler = null;
    }
    if (this.deviceViewObserver) {
      this.deviceViewObserver.disconnect();
      this.deviceViewObserver = null;
    }
    this.terminalInitializing = false;
  },
  methods: {
    isToolDisabled(tool) {
      if (tool.ACTION === 'file_manager' || tool.title === 'File Manager') {
        return this.showFileManager;
      }
      return false;
    },
    
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

        setTimeout(() => {
          this.moveExistingDeviceViews();
        }, 0);

        if (this.streamClient && this.streamClient.streamReceiver) {
          this.streamClient.streamReceiver.on('connected', () => {
            setTimeout(() => {
              this.moveExistingDeviceViews();
            }, 100);
            setTimeout(() => {
              this.moveExistingDeviceViews();
            }, 500);
            setTimeout(() => {
              this.moveExistingDeviceViews();
            }, 1000);
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
            title: 'File Manager',
            ACTION: ACTION.FILE_LISTING,
            client: FileListingClient
          }
        ];

        this.isConnected = true;
        console.log('StreamClientScrcpy started successfully');

        await this.$nextTick();
        this.initializeTerminal();

        this.setupDeviceViewObserver();

      } catch (error) {
        console.error('Failed to initialize components:', error);
        this.error = error.message || 'Failed to initialize video stream';
      }
    },

    setupDeviceViewObserver() {
      this.moveExistingDeviceViews();

      this.deviceViewObserver = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          mutation.addedNodes.forEach((node) => {
            if (node.nodeType === Node.ELEMENT_NODE) {
              if (node.classList && node.classList.contains('device-view')) {
                this.moveDeviceViewToContainer(node);
              }
              const childDeviceViews = node.querySelectorAll && node.querySelectorAll('.device-view');
              if (childDeviceViews && childDeviceViews.length > 0) {
                childDeviceViews.forEach((childView) => {
                  this.moveDeviceViewToContainer(childView);
                });
              }
            }
          });
        });
      });

      this.deviceViewObserver.observe(this.$el, {
        childList: true,
        subtree: true
      });

      setTimeout(() => {
        this.moveExistingDeviceViews();
      }, 100);

      setTimeout(() => {
        this.moveExistingDeviceViews();
      }, 1000);
    },

    moveExistingDeviceViews() {
      const deviceViews = this.$el.querySelectorAll('.device-view');
      
      deviceViews.forEach((deviceView) => {
        if (deviceView.parentNode !== this.$refs.deviceScreenArea) {
          this.moveDeviceViewToContainer(deviceView);
        }
      });
    },

    moveDeviceViewToContainer(deviceView) {
      if (this.$refs.deviceScreenArea && deviceView.parentNode && deviceView.parentNode !== this.$refs.deviceScreenArea) {
        try {
          this.$refs.deviceScreenArea.appendChild(deviceView);
        } catch (error) {
          console.error('Error moving device-view:', error);
        }
      }
    },

    async initializeTerminal() {
      try {
        if (this.terminalInitializing || this.currentShellClient) {
          return;
        }
        
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host;
        const port = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
        const shellWsUrl = `${wsProtocol}//${window.location.hostname}:${port}/api/v1/dynamic-testing/ws/${encodeURIComponent(this.deviceId)}?action=shell`;
        
        this.terminalInitializing = true;
        
        if (this.currentShellClient) {
          this.currentShellClient.close();
          this.currentShellClient = null;
        }
        
        const shellWs = new WebSocket(shellWsUrl);
        shellWs.binaryType = 'arraybuffer';

        shellWs.addEventListener('open', () => {
          try {
            if (!this.$refs.terminalContainer) {
              console.error('Terminal container not found');
              return;
            }
            
            this.$refs.terminalContainer.innerHTML = '';
            
            this.terminal = new Terminal({
              cursorBlink: true,
              fontSize: 12,
              theme: {
                background: '#1e1e1e',
                foreground: '#ffffff'
              },
              convertEol: true,
              fontFamily: 'monospace',
              rows: 30,
              cols: 80,
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
              macOptionIsMeta: false,
              macOptionClickForcesSelection: false,
              scrollbarWidth: 8
            });

            try {
              if (shellWs.readyState === WebSocket.OPEN) {
                const attachAddon = new AttachAddon(shellWs);
                attachAddon.activate(this.terminal);
              } else {
                console.warn('WebSocket not ready for AttachAddon');
              }
            } catch (error) {
              console.warn('Error loading AttachAddon:', error);
            }
            
            this.fitAddon = new FitAddon();
            this.fitAddon.activate(this.terminal);
            
            this.terminal.open(this.$refs.terminalContainer);
            
            if (this.fitAddon) {
              this.fitAddon.fit();
            }
            
            this.terminalConnected = true;
            
          } catch (error) {
            console.error('Error initializing terminal:', error);
            this.terminalInitializing = false;
            this.terminalConnected = false;
            return;
          }
          
          this.terminalInitializing = false;
          
          const terminalContainer = this.$refs.terminalContainer;
          this.preventPageScrollHandler = (event) => {
            const viewport = terminalContainer.querySelector('.xterm-viewport');
            if (!viewport) return;
            
            const { scrollTop, scrollHeight, clientHeight } = viewport;
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
          
          terminalContainer.addEventListener('wheel', this.preventPageScrollHandler, { passive: false });
          
          const { rows, cols } = this.terminal;
          shellWs.send(JSON.stringify({
            type: 'shell',
            data: {
              type: 'start',
              rows,
              cols
            }
          }));
          
          this.terminal.focus();
          
          this.terminalCopyHandler = (event) => {
            if (event.ctrlKey && event.shiftKey && event.key === 'C') {
              event.preventDefault();
              event.stopPropagation();
              
              const selection = this.terminal.getSelection();
              if (selection) {
                navigator.clipboard.writeText(selection).then(() => {
                  // Text copied successfully
                }).catch(() => {
                  const textArea = document.createElement('textarea');
                  textArea.value = selection;
                  document.body.appendChild(textArea);
                  textArea.select();
                  document.execCommand('copy');
                  document.body.removeChild(textArea);
                });
              }
            } else if (event.ctrlKey && event.shiftKey && event.key === 'V') {
              event.preventDefault();
              event.stopPropagation();
              
              navigator.clipboard.readText().then(text => {
                if (text && this.currentShellClient && this.currentShellClient.readyState === WebSocket.OPEN) {
                  this.terminal.write(text);
                }
              }).catch(() => {
                // Failed to read clipboard
              });
            }
          };
          
          terminalContainer.addEventListener('keydown', this.terminalCopyHandler);
          
          const resizeHandler = () => {
            if (!this.terminal || !this.fitAddon) return;
            
            try {
              this.fitAddon.fit();
              const { rows, cols } = this.terminal;
              
              if (shellWs.readyState === WebSocket.OPEN) {
                shellWs.send(JSON.stringify({
                  type: 'shell',
                  data: {
                    type: 'resize',
                    rows,
                    cols
                  }
                }));
              }
            } catch (error) {
              console.warn('Error in resize handler:', error);
            }
          };

          window.addEventListener('resize', resizeHandler);
          this.resizeHandler = resizeHandler;
        });

        shellWs.addEventListener('close', (event) => {
          console.log('Shell WebSocket closed:', event.code, event.reason);
          this.terminalConnected = false;
          if (this.terminal && !this.terminal.isDisposed) {
            this.terminal.write('\r\n\x1b[31mConnection closed. Reconnecting...\x1b[0m\r\n');
            setTimeout(() => {
              this.initializeTerminal();
            }, 2000);
          }
        });

        shellWs.addEventListener('error', (error) => {
          console.error('Shell WebSocket error:', error);
          this.terminalConnected = false;
          if (this.terminal && !this.terminal.isDisposed) {
            this.terminal.write('\r\n\x1b[31mConnection error. Reconnecting...\x1b[0m\r\n');
          }
        });

        this.currentShellClient = shellWs;
        
      } catch (error) {
        console.error('Error initializing terminal:', error);
        this.terminalInitializing = false;
        this.terminalConnected = false;
      }
    },

    async openTool(tool) {
      try {
        if (this.isToolDisabled(tool)) {
          return;
        }
        
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host;
        
        if (tool.ACTION === 'shell') {
          if (this.terminal) {
            this.terminal.focus();
          }
        } else if (tool.ACTION === ACTION.FILE_LISTING || tool.title === 'File Manager') {
          this.showFileManager = true;
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
        if (this.terminal && !this.terminal.isDisposed) {
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
      
      if (this.preventPageScrollHandler && this.$refs.terminalContainer) {
        this.$refs.terminalContainer.removeEventListener('wheel', this.preventPageScrollHandler);
        this.preventPageScrollHandler = null;
      }
      
      if (this.terminalCopyHandler && this.$refs.terminalContainer) {
        this.$refs.terminalContainer.removeEventListener('keydown', this.terminalCopyHandler);
        this.terminalCopyHandler = null;
      }
      
      if (this.terminal) {
        try {
          this.terminal.clear();
          this.terminal.dispose();
        } catch (error) {
          console.warn('Error disposing terminal:', error);
        }
        this.terminal = null;
      }
      
      this.fitAddon = null;
      
      if (this.$refs.terminalContainer) {
        this.$refs.terminalContainer.innerHTML = '';
        while (this.$refs.terminalContainer.firstChild) {
          this.$refs.terminalContainer.removeChild(this.$refs.terminalContainer.firstChild);
        }
      }
      
      this.terminalInitializing = false;
      this.terminalConnected = false;
    },

    async restartTerminal() {
      try {
        console.log('Restarting terminal...');
        this.closeTerminal();
        await this.$nextTick();
        await new Promise(resolve => setTimeout(resolve, 500));
        this.initializeTerminal();
      } catch (error) {
        console.error('Error restarting terminal:', error);
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
    
    cleanupStreamElements() {
      const container = this.$el || document.querySelector('.dynamic-testing');
      if (!container) return;
      
      const deviceViews = container.querySelectorAll('.device-view');
      deviceViews.forEach(element => {
        if (element.parentElement) {
          element.parentElement.removeChild(element);
        }
      });
      
      const moreBoxes = container.querySelectorAll('.more-box');
      moreBoxes.forEach(element => {
        if (element.parentElement) {
          element.parentElement.removeChild(element);
        }
      });
      
      const bodyDeviceViews = document.body.querySelectorAll('.device-view');
      bodyDeviceViews.forEach(element => {
        const nameBox = element.querySelector('.text-with-shadow');
        if (nameBox && nameBox.textContent && nameBox.textContent.includes(this.deviceId)) {
          if (element.parentElement) {
            element.parentElement.removeChild(element);
          }
        }
      });
    },

    async refreshDevice() {
      try {
        if (this.streamClient) {
          if (this.streamClient.streamReceiver) {
            this.streamClient.streamReceiver.stop();
          }
          if (this.streamClient.player) {
            this.streamClient.player.stop();
          }
          this.cleanupStreamElements();
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

.container {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.main-layout {
  display: flex;
  flex-direction: row;
  flex: 1;
  gap: 1rem;
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
  border: 1px solid #dee2e6;
  border-radius: 8px;
  margin-top: 1rem;
  margin-bottom: 1rem;
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
  padding: 0.5rem 0.5rem;
  border: 1px solid #dee2e6;
  cursor: pointer;
  border-radius: 4px;
  color: #333;
  transition: background-color 0.2s ease;
  background-color: #fff;
}

.tool-item:hover:not(.disabled) {
  background-color: #e9ecef;
}

.tool-item.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background-color: #f8f9fa;
}

.tool-name {
  font-weight: bold;
}

.tool-action {
  color: #666;
}

.terminal-section {
  flex: 1;
  background: #1e1e1e;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 300px;
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

.terminal-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.terminal-restart-btn {
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

.terminal-restart-btn:hover {
  background: #5a5a5a;
  border-color: #777;
}

.terminal-restart-btn:active {
  background: #3a3a3a;
  transform: scale(0.95);
}

.terminal-status {
  font-size: 14px;
  margin-left: 10px;
}

.terminal-status.connected {
  color: #4caf50;
}

.terminal-status:not(.connected) {
  color: #f44336;
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
  max-height: 600px;
  display: flex;
  flex-direction: column;
  position: relative;
}

.terminal-container .xterm {
  height: 100%;
  width: 100%;
  flex: 1;
  overflow: hidden;
}

.terminal-container .xterm .xterm-screen {
  scrollbar-width: thin;
  scrollbar-color: #666 #333;
}

.terminal-container .xterm-viewport {
  overflow-y: scroll !important;
  overflow-x: hidden !important;
  scrollbar-width: thin;
  scrollbar-color: #666 #333;
  scrollbar-gutter: stable;
}

.terminal-container .xterm-viewport::-webkit-scrollbar {
  width: 12px;
  visibility: visible !important;
  display: block !important;
}

.terminal-container .xterm-viewport::-webkit-scrollbar-track {
  background: #333;
  border-radius: 6px;
}

.terminal-container .xterm-viewport::-webkit-scrollbar-thumb {
  background: #666;
  border-radius: 6px;
  min-height: 30px;
}

.terminal-container .xterm-viewport::-webkit-scrollbar-thumb:hover {
  background: #888;
}

.terminal-container .xterm-viewport::-webkit-scrollbar-thumb:active {
  background: #999;
}

/* Принудительное отображение полосы прокрутки */
.terminal-container .xterm-viewport {
  overflow-y: scroll !important;
  -webkit-overflow-scrolling: touch;
}

/* Для Firefox */
.terminal-container .xterm-viewport {
  scrollbar-width: thin !important;
  scrollbar-color: #666 #333 !important;
}

/* Дополнительные стили для всегда видимой полосы прокрутки */
.terminal-container .xterm-viewport::-webkit-scrollbar-corner {
  background: #333;
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
  margin-bottom: 1rem;
  background: #f5f5f5;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  max-height: 400px;
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

.device-screen-area {
  flex: 0 0 auto;
  display: flex;
  justify-content: center;
  min-height: 400px;
  background: #f8f9fa;
  border-radius: 8px;
  padding: 1rem;
  overflow: hidden;
  width: fit-content;
}

.device-screen-area .device-view {
  width: auto;
  height: auto;
  background: transparent;
  border-radius: 0;
}

@media (max-width: 1024px) {
  .main-layout {
    flex-direction: column;
  }
  
  .terminal-section {
    flex: none;
    width: 100%;
    max-height: 300px;
  }
  
  .terminal-container {
    min-height: 250px;
    max-height: 300px;
  }
  
  .device-screen-area {
    min-height: 300px;
    width: 100%;
    flex: 0 0 auto;
  }
  
  .file-manager-section {
    max-height: 350px;
  }
  
  .file-manager-content {
    max-height: 250px;
  }
}

@media (max-width: 768px) {
  .main-layout {
    gap: 0.5rem;
  }
  
  .tools-section {
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
  }
  
  .device-screen-area {
    min-height: 250px;
    width: 100%;
  }
  
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
