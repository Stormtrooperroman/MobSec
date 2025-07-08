import { ManagerClient } from './ManagerClient';
import { Message } from '../../types/Message';
import { MessageError, MessageHosts, MessageType } from '../../common/HostTrackerMessage';
import { ACTION } from '../../common/Action';
import { DeviceTracker as GoogDeviceTracker } from '../googDevice/client/DeviceTracker';
import { DeviceTracker as ApplDeviceTracker } from '../applDevice/client/DeviceTracker';
import { ParamsBase } from '../../types/ParamsBase';
import { HostItem } from '../../types/Configuration';
import { ChannelCode } from '../../common/ChannelCode';
import { TypedEmitter } from '../../common/TypedEmitter';

const TAG = '[HostTracker]';

export interface HostTrackerParams {
  action: ACTION;
  hostname: string;
  port: number;
  pathname: string;
  secure: boolean;
  useProxy: boolean;
  type?: 'android' | 'ios';
}

export interface HostTrackerEvents {
  'device': (tracker: GoogDeviceTracker | ApplDeviceTracker) => void;
  'device-list': (trackers: Array<GoogDeviceTracker | ApplDeviceTracker>) => void;
  'device-remove': (tracker: GoogDeviceTracker | ApplDeviceTracker) => void;
  'disconnected': CloseEvent;
  'error': string;
}

export class HostTracker extends ManagerClient<HostTrackerParams, HostTrackerEvents> {
  private static instance?: HostTracker;
  private static defaultParams: HostTrackerParams = {
    action: ACTION.LIST_HOSTS,
    hostname: window.location.hostname,
    port: window.location.port ? parseInt(window.location.port) : (window.location.protocol === 'https:' ? 443 : 80),
    pathname: '/api/v1/dynamic-testing/ws',
    secure: window.location.protocol === 'https:',
    useProxy: false,
    type: 'android'
  };

  public static start(): void {
    this.getInstance();
  }

  public static getInstance(): HostTracker {
    if (!this.instance) {
      this.instance = new HostTracker(this.defaultParams);
    }
    return this.instance;
  }

  private trackers: Array<GoogDeviceTracker | ApplDeviceTracker> = [];

  private constructor(params: HostTrackerParams) {
    super(params);
    this.openNewConnection();
    if (this.ws) {
      this.ws.binaryType = 'arraybuffer';
    }
  }

  protected onSocketOpen(event: Event): void {
    console.log(TAG, 'WS opened');
  }

  protected onSocketMessage(event: MessageEvent): void {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'device') {
        this.emit('device', data.device);
      } else if (data.type === 'device-list') {
        this.emit('device-list', data.devices);
      } else if (data.type === 'device-remove') {
        this.emit('device-remove', data.device);
      }
    } catch (error) {
      console.error(TAG, 'Failed to parse message:', error);
      this.emit('error', error instanceof Error ? error.message : String(error));
    }
  }

  protected onSocketClose(event: CloseEvent): void {
    console.log(TAG, 'WS closed');
    this.emit('disconnected', event);
  }

  private startTracker(hostItem: HostItem): void {
    switch (hostItem.type) {
      case 'android':
        this.trackers.push(GoogDeviceTracker.start(hostItem));
        break;
      case 'ios':
        this.trackers.push(ApplDeviceTracker.start(hostItem));
        break;
      default:
        console.warn(TAG, `Unsupported host type: "${hostItem.type}"`);
    }
  }

  public destroy(): void {
    super.destroy();
    this.trackers.forEach(tracker => {
      tracker.destroy();
    });
    this.trackers.length = 0;
  }

  protected supportMultiplexing(): boolean {
    return true;
  }

  protected getChannelInitData(): Uint8Array {
    const buffer = new Uint8Array(4);
    const encoder = new TextEncoder();
    encoder.encodeInto(ChannelCode.HSTS, buffer);
    return buffer;
  }

  protected getHostName(): string {
    return this.params.hostname;
  }

  protected getPort(): number {
    return this.params.port;
  }

  protected getPathname(): string {
    return this.params.pathname;
  }

  protected isSecure(): boolean {
    return this.params.secure || false;
  }

  protected getQueryString(): string {
    return `?action=${this.params.action}`;
  }
}
