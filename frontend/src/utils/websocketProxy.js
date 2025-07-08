/**
 * WebSocket Proxy Utilities
 *
 * This module provides utilities for working with WebSocket proxies over ADB,
 * similar to the TypeScript WebsocketProxyOverAdb functionality.
 */

/**
 * Process WebSocket proxy request and validate parameters
 * Similar to TypeScript processRequest method
 *
 * @param {string} deviceUdid - Device UDID
 * @param {string} remote - Remote address (e.g., "tcp:8886")
 * @param {string} path - WebSocket path (default: "/")
 * @returns {Object|null} Proxy configuration or null if invalid
 */
export function processProxyRequest(deviceUdid, remote, path = '/') {
  // Validate parameters (similar to TypeScript validation)
  if (!remote || typeof remote !== 'string') {
    console.error('[WebSocketProxy] Invalid value for "remote" parameter:', remote);
    return null;
  }

  if (!deviceUdid || typeof deviceUdid !== 'string') {
    console.error('[WebSocketProxy] Invalid value for "udid" parameter:', deviceUdid);
    return null;
  }

  if (path && typeof path !== 'string') {
    console.error('[WebSocketProxy] Invalid value for "path" parameter:', path);
    return null;
  }

  // Create proxy configuration
  return createProxyOverAdb(deviceUdid, remote, path);
}

/**
 * Create proxy over ADB configuration
 * Similar to TypeScript createProxyOverAdb method
 *
 * @param {string} deviceUdid - Device UDID
 * @param {string} remote - Remote address
 * @param {string} path - WebSocket path
 * @returns {Object} Proxy configuration
 */
export function createProxyOverAdb(deviceUdid, remote, path = '/') {
  // Parse remote to get device port
  let devicePort;
  try {
    if (remote.startsWith('tcp:')) {
      devicePort = parseInt(remote.split(':')[1]);
    } else {
      devicePort = parseInt(remote);
    }
  } catch (error) {
    console.error('[WebSocketProxy] Invalid remote format:', remote);
    throw new Error(`Invalid remote format: ${remote}`);
  }

  return {
    deviceUdid,
    devicePort,
    path,
    // Generate WebSocket URL (will be populated when proxy is started)
    getWebSocketUrl: function (hostPort) {
      if (!hostPort) {
        throw new Error('Proxy not started yet');
      }
      return `ws://127.0.0.1:${hostPort}${this.path}`;
    },
  };
}

/**
 * Create WebSocket connection using proxy configuration
 *
 * @param {Object} proxyConfig - Proxy configuration from createProxyOverAdb
 * @param {string} websocketUrl - Full WebSocket URL from backend
 * @returns {WebSocket} WebSocket instance
 */
export function createWebSocketConnection(proxyConfig, websocketUrl) {
  if (!websocketUrl) {
    throw new Error('No WebSocket URL provided');
  }

  console.log('[WebSocketProxy] Creating connection to:', websocketUrl);

  const ws = new WebSocket(websocketUrl);
  ws.binaryType = 'arraybuffer';

  return ws;
}

/**
 * Validates the connection information received from the server
 * @param {Object} connectionInfo - The connection information object
 * @returns {boolean} - Whether the connection information is valid
 */
export function validateConnectionInfo(connectionInfo) {
  if (!connectionInfo) {
    console.error('No connection info provided');
    return false;
  }

  // Check required fields
  const requiredFields = ['serial', 'state', 'websocket_url'];
  for (const field of requiredFields) {
    if (!connectionInfo[field]) {
      console.error(`Missing required field: ${field}`);
      return false;
    }
  }

  // Validate WebSocket URL
  try {
    new URL(connectionInfo.websocket_url);
  } catch (e) {
    console.error('Invalid WebSocket URL:', e);
    return false;
  }

  // Validate device state
  if (connectionInfo.state !== 'device') {
    console.error('Device is not in ready state:', connectionInfo.state);
  return false;
  }

  return true;
}

/**
 * Get WebSocket URL from connection info
 *
 * @param {Object} connectionInfo - Connection info from backend
 * @returns {string} WebSocket URL
 */
export function getWebSocketUrl(connectionInfo) {
  if (!connectionInfo) {
    throw new Error('No connection information available');
  }

  // Prefer websocket_url (on-demand proxy approach)
  if (connectionInfo.websocket_url) {
    return connectionInfo.websocket_url;
  }

  // Fallback to legacy ip/port format
  if (connectionInfo.ip && connectionInfo.port) {
    return `ws://${connectionInfo.ip}:${connectionInfo.port}`;
  }

  throw new Error('No valid connection information available');
}

/**
 * Creates a binary message for touch events
 * @param {number} type - Message type (e.g., TYPE_TOUCH = 2)
 * @param {number} action - Touch action (DOWN = 0, UP = 1, MOVE = 2)
 * @param {number} pointerId - Touch pointer ID
 * @param {number} x - X coordinate
 * @param {number} y - Y coordinate
 * @param {number} screenWidth - Screen width
 * @param {number} screenHeight - Screen height
 * @param {number} pressure - Touch pressure (0.0 to 1.0)
 * @param {number} buttons - Button state
 * @returns {ArrayBuffer} - Binary message ready to send
 */
export function createTouchMessage(
  type,
  action,
  pointerId,
  x,
  y,
  screenWidth,
  screenHeight,
  pressure = 1.0,
  buttons = 1
) {
  const buffer = new ArrayBuffer(29);
  const view = new DataView(buffer);
  let offset = 0;

  view.setUint8(offset++, type);
  view.setUint8(offset++, action);
  view.setUint32(offset, 0, false); // pointerId high (big endian)
  offset += 4;
  view.setUint32(offset, pointerId, false); // pointerId low (big endian)
  offset += 4;
  view.setUint32(offset, x, false); // x coordinate (big endian)
  offset += 4;
  view.setUint32(offset, y, false); // y coordinate (big endian)
  offset += 4;
  view.setUint16(offset, screenWidth, false); // screen width (big endian)
  offset += 2;
  view.setUint16(offset, screenHeight, false); // screen height (big endian)
  offset += 2;
  view.setUint16(offset, Math.round(pressure * 65535), false); // pressure (big endian)
  offset += 2;
  view.setUint32(offset, buttons, false); // buttons (big endian)

  return buffer;
}

// Touch event constants
export const TouchConstants = {
  TYPE_TOUCH: 2,
  ACTION_DOWN: 0,
  ACTION_UP: 1,
  ACTION_MOVE: 2,
  BUTTON_PRIMARY: 1 << 0
};
