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
                <font-awesome-icon 
                  icon="circle" 
                  :class="terminalConnected ? 'status-connected' : 'status-disconnected'" 
                />
              </span>
            </div>
          </div>
          <div class="terminal-container" ref="terminalContainer"></div>
        </div>

        <div class="device-screen-area" ref="deviceScreenArea">
        </div>
      </div>

      <div class="tools-section" v-if="availableTools.length > 0">
        <div class="tools-tabs">
          <div class="tab-headers">
            <button 
              v-for="tool in availableTools" 
              :key="tool.ACTION"
              :class="['tab-header', { 'active': activeTab === tool.ACTION }]"
              @click="setActiveTab(tool.ACTION)"
            >
              <span class="tab-icon">
                <font-awesome-icon 
                  :icon="getToolIcon(tool.ACTION)" 
                  v-if="getToolIcon(tool.ACTION)"
                />
              </span>
              <span class="tab-title">{{ tool.title || tool.ACTION }}</span>
            </button>
          </div>
          
          <div class="tab-content">
            <!-- File Manager Tab -->
            <div v-if="activeTab === 'file_manager'" class="tab-pane active">
              <FileManager :device-id="deviceId" />
            </div>
            
            <!-- Frida Tab -->
            <div v-if="activeTab === 'frida'" class="tab-pane active">
              <FridaTool :device-id="deviceId" />
            </div>
          </div>
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

import { FileListingClient } from '@/ws-scrcpy/app/googDevice/client/FileListingClient';

import FileManager from './tools/FileManager.vue';
import FridaTool from './tools/FridaTool.vue';

// Register available players
StreamClientScrcpy.registerPlayer(TinyH264Player);
StreamClientScrcpy.registerPlayer(MsePlayer);
StreamClientScrcpy.registerPlayer(WebCodecsPlayer);
StreamClientScrcpy.registerPlayer(BroadwayPlayer);

export default {
  name: 'DeviceStreamer',
  components: {
    FileManager,
    FridaTool
  },
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
      deviceViewObserver: null,
      activeTab: 'file_manager',
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
    setActiveTab(tabName) {
      this.activeTab = tabName;
    },

    getToolIcon(action) {
      const icons = {
        'file_manager': 'folder',
        'frida': 'bug'
      };
      return icons[action] || 'tool';
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
            ACTION: 'file_manager',
            client: FileListingClient
          },
          {
            title: 'Frida',
            ACTION: 'frida',
            client: null
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
  padding: 0;
  background-color: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  margin-top: 1rem;
  margin-bottom: 1rem;
}

.tools-tabs {
  display: flex;
  flex-direction: column;
}

.tab-headers {
  display: flex;
  background-color: #e9ecef;
  border-bottom: 1px solid #dee2e6;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
}

.tab-header {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  border: none;
  background: none;
  cursor: pointer;
  color: #495057;
  font-weight: 500;
  transition: all 0.2s ease;
  border-bottom: 2px solid transparent;
}

.tab-header:hover {
  background-color: #f8f9fa;
  color: #212529;
}

.tab-header.active {
  background-color: #fff;
  color: #495057;
  border-bottom-color: #007bff;
}

.tab-icon {
  margin-right: 0.5rem;
}

.tab-title {
  font-weight: 500;
}

.tab-content {
  flex: 1;
  background-color: #fff;
  border-bottom-left-radius: 8px;
  border-bottom-right-radius: 8px;
}

.tab-pane {
  display: none;
  padding: 1rem;
}

.tab-pane.active {
  display: block;
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

.status-connected {
  color: #4caf50 !important;
}

.status-disconnected {
  color: #f44336 !important;
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

.terminal-container .xterm-viewport {
  overflow-y: scroll !important;
  -webkit-overflow-scrolling: touch;
}

.terminal-container .xterm-viewport {
  scrollbar-width: thin !important;
  scrollbar-color: #666 #333 !important;
}

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
}
</style>
