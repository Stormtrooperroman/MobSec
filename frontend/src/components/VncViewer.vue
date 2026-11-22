<template>
  <div class="device-streamer">
    <div v-if="error" class="error-message">{{ error }}</div>
    <div v-if="!error && !vncConnected" class="connecting-message">Connecting to device...</div>

    <div v-show="!error" class="container">
      <div class="main-layout">
        <!-- Tools Section (Left) -->
        <div class="tools-section">
          <div class="tools-tabs">
            <div class="tab-headers">
              <button :class="['tab-header', { active: activeTab === 'terminal' }]" @click="setActiveTab('terminal')">
                <span class="tab-icon">
                  <font-awesome-icon icon="terminal" />
                </span>
                <span class="tab-title">Terminal</span>
              </button>
              <button
                :class="['tab-header', { active: activeTab === 'file_manager' }]"
                @click="setActiveTab('file_manager')"
              >
                <span class="tab-icon">
                  <font-awesome-icon icon="folder" />
                </span>
                <span class="tab-title">File Manager</span>
              </button>
            </div>

            <div class="tab-content">
              <!-- Terminal Tab -->
              <div v-show="activeTab === 'terminal'" class="tab-pane terminal-tab-pane active">
                <div class="terminal-header">
                  <span>SSH Terminal</span>
                  <div class="terminal-controls">
                    <button @click="restartTerminal" class="terminal-restart-btn" title="Restart terminal">
                      <font-awesome-icon icon="refresh" />
                    </button>
                    <span class="terminal-status" :class="{ connected: terminalConnected }">
                      <font-awesome-icon
                        icon="circle"
                        :class="terminalConnected ? 'status-connected' : 'status-disconnected'"
                      />
                    </span>
                  </div>
                </div>
                <div class="terminal-container" ref="terminalContainer"></div>
              </div>

              <!-- File Manager Tab -->
              <div v-if="activeTab === 'file_manager'" class="tab-pane active">
                <FileManager :device-id="deviceId" :device="device" />
              </div>
            </div>
          </div>
        </div>

        <!-- VNC Screen (Right) -->
        <div class="device-screen-area" ref="deviceScreenArea">
          <div id="vnc-canvas" class="vnc-canvas" ref="vncCanvas"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';
import RFB from '@novnc/novnc';

import FileManager from './tools/FileManager.vue';

export default {
  name: 'VncViewer',
  components: {
    FileManager,
  },
  props: {
    device: {
      type: Object,
      required: true,
    },
    deviceId: {
      type: String,
      required: true,
    },
  },
  emits: ['error'],
  setup(props, { emit }) {
    const vncCanvas = ref(null);
    const deviceScreenArea = ref(null);
    const terminalContainer = ref(null);
    const rfbClient = ref(null);
    const error = ref('');
    const vncConnected = ref(false);
    const vncUrl = ref('');
    const activeTab = ref('terminal');

    // Terminal state
    const terminal = ref(null);
    const fitAddon = ref(null);
    const terminalConnected = ref(false);
    const terminalWs = ref(null);
    const resizeObserver = ref(null);

    const setActiveTab = tabName => {
      activeTab.value = tabName;
    };

    const getVncUrl = async () => {
      try {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host;
        vncUrl.value = `${wsProtocol}//${wsHost}/api/v1/dynamic-testing/ws/${encodeURIComponent(
          props.deviceId,
        )}?action=vnc&os_type=aurora`;
      } catch (err) {
        console.error('Error constructing VNC URL', err);
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host;
        vncUrl.value = `${wsProtocol}//${wsHost}/api/v1/dynamic-testing/ws/${encodeURIComponent(
          props.deviceId,
        )}?action=vnc&os_type=aurora`;
      }
    };

    const initVnc = async () => {
      try {
        if (!vncCanvas.value) {
          console.warn('Canvas ref not ready yet, waiting...');
          await new Promise(resolve => setTimeout(resolve, 100));
          if (!vncCanvas.value) {
            throw new Error('Canvas not available');
          }
        }

        rfbClient.value = new RFB(vncCanvas.value, vncUrl.value, {
          credentials: { username: '', password: '' },
        });

        rfbClient.value.scaleViewport = true;
        rfbClient.value.resizeSession = false;

        rfbClient.value.addEventListener('connect', () => {
          console.log('VNC Connected');
          vncConnected.value = true;
          error.value = '';
          // Apply scaling after connection
          setTimeout(() => {
            if (rfbClient.value && vncCanvas.value) {
              rfbClient.value.scaleViewport = true;
              // Trigger resize to apply scaling
              const event = new Event('resize');
              window.dispatchEvent(event);
            }
          }, 500);
        });

        rfbClient.value.addEventListener('disconnect', () => {
          console.log('VNC Disconnected');
          vncConnected.value = false;
        });

        rfbClient.value.addEventListener('error', evt => {
          console.error('VNC Error:', evt);
          error.value = evt.detail?.message || 'VNC Connection Error';
          emit('error', error.value);
        });
      } catch (err) {
        error.value = err.message || 'Failed to initialize VNC';
        emit('error', error.value);
        console.error('VNC initialization error:', err);
      }
    };

    const initTerminal = async () => {
      if (!terminalContainer.value || terminal.value) {
        return;
      }

      terminal.value = new Terminal({
        cursorBlink: true,
        fontSize: 14,
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
        theme: {
          background: '#1e1e1e',
          foreground: '#d4d4d4',
        },
        scrollback: 10000,
      });

      fitAddon.value = new FitAddon();
      terminal.value.loadAddon(fitAddon.value);
      terminal.value.open(terminalContainer.value);

      const safeFit = () => {
        try {
          if (!fitAddon.value || !terminal.value || !terminalContainer.value) return;

          // Check if container is actually visible
          const containerWidth = terminalContainer.value.offsetWidth;
          const containerHeight = terminalContainer.value.offsetHeight;
          if (containerWidth <= 0 || containerHeight <= 0) return;

          fitAddon.value.fit();

          const cols = Math.max(1, Math.floor(terminal.value.cols || 80));
          const rows = Math.max(1, Math.floor(terminal.value.rows || 30));

          if (cols > 0 && rows > 0 && Number.isInteger(cols) && Number.isInteger(rows)) {
            terminal.value.resize(cols, rows);
          }
        } catch (e) {
          // Silently ignore errors during fit (happens during tab switching)
          if (e.message !== 'This API only accepts integers') {
            console.error('Error fitting terminal:', e);
          }
        }
      };

      // Defer initial fit to allow terminal to fully initialize
      await new Promise(resolve => setTimeout(resolve, 50));
      safeFit();

      resizeObserver.value = new ResizeObserver(() => {
        if (fitAddon.value && terminal.value) {
          safeFit();
          sendTerminalResize();
        }
      });

      resizeObserver.value.observe(terminalContainer.value);

      await connectTerminalWebSocket();
    };

    const connectTerminalWebSocket = async () => {
      const encodedDeviceId = encodeURIComponent(props.deviceId);
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsHost = window.location.host;
      const wsUrl = `${wsProtocol}//${wsHost}/api/v1/dynamic-testing/ws/${encodedDeviceId}?action=shell&os_type=aurora`;

      terminalWs.value = new WebSocket(wsUrl);

      terminalWs.value.onopen = () => {
        console.log('Terminal WebSocket connected');
        terminalConnected.value = true;
        sendTerminalResize();
      };

      terminalWs.value.onmessage = event => {
        try {
          if (event.data instanceof Blob) {
            const reader = new FileReader();
            reader.onload = () => {
              const text = new TextDecoder().decode(reader.result);
              terminal.value.write(text);
            };
            reader.readAsArrayBuffer(event.data);
          } else if (typeof event.data === 'string') {
            try {
              const data = JSON.parse(event.data);
              if (data.type === 'output' && data.data) {
                terminal.value.write(data.data);
              } else if (data.type === 'error') {
                terminal.value.write(`\r\n\x1b[31mError: ${data.message}\x1b[0m\r\n`);
              }
            } catch {
              terminal.value.write(event.data);
            }
          }
        } catch (err) {
          console.error('Error parsing terminal message:', err);
        }
      };

      terminalWs.value.onerror = err => {
        console.error('Terminal WebSocket error:', err);
        terminalConnected.value = false;
      };

      terminalWs.value.onclose = () => {
        console.log('Terminal WebSocket closed');
        terminalConnected.value = false;
      };

      terminal.value.onData(data => {
        if (terminalWs.value && terminalWs.value.readyState === WebSocket.OPEN) {
          terminalWs.value.send(data);
        }
      });
    };

    const sendTerminalResize = () => {
      if (!terminal.value || !terminalWs.value || terminalWs.value.readyState !== WebSocket.OPEN) {
        return;
      }

      const rows = Math.floor(terminal.value.rows);
      const cols = Math.floor(terminal.value.cols);

      terminalWs.value.send(
        JSON.stringify({
          type: 'resize',
          rows: rows,
          cols: cols,
        }),
      );
    };

    const restartTerminal = async () => {
      closeTerminal();
      await initTerminal();
    };

    const closeTerminal = () => {
      if (terminalWs.value) {
        terminalWs.value.close();
        terminalWs.value = null;
      }

      if (resizeObserver.value) {
        resizeObserver.value.disconnect();
        resizeObserver.value = null;
      }

      if (terminal.value) {
        terminal.value.dispose();
        terminal.value = null;
      }

      terminalConnected.value = false;
    };

    onMounted(async () => {
      await getVncUrl();
      if (vncUrl.value) {
        await initVnc();
      }
      await initTerminal();
    });

    onUnmounted(() => {
      if (rfbClient.value) {
        rfbClient.value.disconnect();
      }
      closeTerminal();
    });

    return {
      vncCanvas,
      deviceScreenArea,
      terminalContainer,
      error,
      vncConnected,
      activeTab,
      setActiveTab,
      terminalConnected,
      restartTerminal,
    };
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

.tools-section {
  padding: 0;
  background-color: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  flex: 1;
  min-width: 300px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tools-tabs {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
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
  min-height: 0;
  display: flex;
  flex-direction: column;
  background-color: #fff;
  border-bottom-left-radius: 8px;
  border-bottom-right-radius: 8px;
  overflow: hidden;
}

.tab-pane {
  display: none;
  padding: 1rem;
  overflow: auto;
}

.tab-pane.active {
  display: block;
}

.tab-pane.terminal-tab-pane {
  padding: 0;
}

.tab-pane.terminal-tab-pane.active {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
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

.terminal-container {
  flex: 1;
  padding: 10px;
  background: #1e1e1e;
  border-bottom-left-radius: 8px;
  border-bottom-right-radius: 8px;
  overflow: hidden;
  min-height: 400px;
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
}

.terminal-container .xterm-viewport::-webkit-scrollbar-thumb:hover {
  background: #888;
}

.device-screen-area {
  width: fit-content;
  min-width: 300px;
  height: 600px;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #f8f9fa;
  border-radius: 8px;
  padding: 1rem;
  overflow: auto;
}

.vnc-canvas {
  width: 100%;
  height: 100%;
  max-width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

.vnc-canvas > div {
  display: flex;
  width: 100%;
  height: 100%;
  justify-content: center;
  align-items: center;
}

::v-deep .vnc-canvas canvas {
  width: auto !important;
  height: auto !important;
  max-height: 100% !important;
  max-width: 100% !important;
  object-fit: contain !important;
}

@media (max-width: 1024px) {
  .main-layout {
    flex-direction: column;
  }

  .tools-section {
    flex: none;
    width: 100%;
    max-height: 350px;
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
