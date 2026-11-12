/**
 * Yjs WebSocket provider for WORLDWEAVE collaborative documents.
 *
 * The provider speaks the protocol implemented by
 * ``backend/modules/collaboration/manager.py``:
 *
 * - a short-lived, HMAC-signed ticket is fetched over the authenticated REST
 *   session before every connection attempt;
 * - Yjs sync messages are exchanged on the ``yjs-websocket-v1`` channel;
 * - a binary control channel (message type ``3``) carries JSON events, notably
 *   ``permission`` and ``durable_ack``;
 * - an acknowledgement means the update is committed in PostgreSQL, not merely
 *   received by the server.
 *
 * Tickets are bound to a document ``collab_generation``. A revision restore
 * discards the old CRDT state and increments the generation, so a provider
 * that observes a different generation must stop and let the page rebuild the
 * editor from a fresh Y.Doc. Reusing the previous Y.Doc would resurrect
 * operations that the restore deliberately removed.
 */

import * as decoding from 'lib0/decoding';
import * as encoding from 'lib0/encoding';
import { Awareness, applyAwarenessUpdate, encodeAwarenessUpdate, removeAwarenessStates } from 'y-protocols/awareness';
import * as syncProtocol from 'y-protocols/sync';
import * as Y from 'yjs';
import {
  getCollaborationTicket,
  type CollaborationTicketResponse,
} from '@workspace/api-client-react';

const MESSAGE_SYNC = 0;
const MESSAGE_AWARENESS = 1;
const MESSAGE_CONTROL = 3;

const SYNC_STEP1 = 0;
const SYNC_STEP2 = 1;

const CLOSE_ROOM_RESET = 4001;
const CLOSE_FORBIDDEN = 4403;
const CLOSE_NOT_FOUND = 4404;

const HEARTBEAT_INTERVAL_MS = 20_000;
const MAX_RECONNECT_DELAY_MS = 15_000;

export type CollaborationStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'synced'
  | 'offline'
  | 'error'
  | 'reset';

export interface CollaborationState {
  status: CollaborationStatus;
  canWrite: boolean;
  role: string;
  displayName: string;
  /** Local operations not yet acknowledged by a committed database write. */
  pendingUpdates: number;
  lastAckSequence: number;
  /** Remote participants currently publishing awareness state. */
  collaborators: number;
  errorMessage: string | null;
}

export interface CollaborationProviderOptions {
  universeId: string;
  documentId: string;
  user: { name: string; color: string };
  /**
   * Called when the server invalidates the room (revision restore, invalid
   * CRDT projection, or a ticket issued for a different generation). The page
   * must refetch the document and mount a new provider with a fresh Y.Doc.
   */
  onReset?: (reason: string) => void;
}

const INITIAL_STATE: CollaborationState = {
  status: 'idle',
  canWrite: false,
  role: 'viewer',
  displayName: '',
  pendingUpdates: 0,
  lastAckSequence: 0,
  collaborators: 0,
  errorMessage: null,
};

type Ticket = CollaborationTicketResponse;

function isStateVectorSubset(
  candidate: Map<number, number>,
  reference: Map<number, number>
): boolean {
  for (const [client, clock] of candidate) {
    if ((reference.get(client) ?? 0) < clock) return false;
  }
  return true;
}

function toUint8Array(value: ArrayBuffer | ArrayBufferView): Uint8Array {
  if (value instanceof Uint8Array) return value;
  if (ArrayBuffer.isView(value)) {
    return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  }
  return new Uint8Array(value);
}

export class CollaborationProvider {
  readonly doc: Y.Doc;
  readonly awareness: Awareness;

  private readonly universeId: string;
  private readonly documentId: string;
  private readonly onReset?: (reason: string) => void;

  private readonly listeners = new Set<() => void>();
  private state: CollaborationState = INITIAL_STATE;

  private socket: WebSocket | null = null;
  private ticketAbort: AbortController | null = null;
  private reconnectTimer: number | null = null;
  private heartbeatTimer: number | null = null;
  private reconnectAttempts = 0;
  private generation: number | null = null;
  private stopped = false;
  private connecting = false;
  private resetNotified = false;

  constructor(options: CollaborationProviderOptions) {
    this.universeId = options.universeId;
    this.documentId = options.documentId;
    this.onReset = options.onReset;

    this.doc = new Y.Doc();
    this.awareness = new Awareness(this.doc);
    this.awareness.setLocalStateField('user', options.user);

    this.doc.on('update', this.handleDocumentUpdate);
    this.awareness.on('update', this.handleAwarenessUpdate);
  }

  // -------------------------------------------------------------------------
  // External store interface
  // -------------------------------------------------------------------------

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = (): CollaborationState => this.state;

  // -------------------------------------------------------------------------
  // Lifecycle
  // -------------------------------------------------------------------------

  connect(): void {
    if (this.stopped || this.socket || this.connecting) return;
    this.update({
      status: this.state.lastAckSequence > 0 ? 'connected' : 'connecting',
      errorMessage: null,
    });
    void this.openSocket();
  }

  destroy(): void {
    if (this.stopped) return;
    this.stopped = true;
    this.clearReconnectTimer();
    this.stopHeartbeat();
    this.ticketAbort?.abort();
    this.ticketAbort = null;

    this.doc.off('update', this.handleDocumentUpdate);
    this.awareness.off('update', this.handleAwarenessUpdate);

    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
      if (socket.readyState === WebSocket.OPEN) {
        const local = this.doc.clientID;
        removeAwarenessStates(this.awareness, [local], this);
        try {
          socket.send(this.encodeAwarenessUpdate([local]));
        } catch {
          // The socket may already be closing; the server expires awareness.
        }
        socket.close(1000, 'client_destroyed');
      } else if (socket.readyState === WebSocket.CONNECTING) {
        socket.close();
      }
    }

    this.update({ status: 'idle', collaborators: 0 });
    this.awareness.destroy();
    this.doc.destroy();
    this.listeners.clear();
  }

  // -------------------------------------------------------------------------
  // Connection
  // -------------------------------------------------------------------------

  private async openSocket(): Promise<void> {
    if (this.stopped || this.connecting || this.socket) return;
    this.connecting = true;
    const abort = new AbortController();
    this.ticketAbort = abort;

    let ticket: Ticket;
    try {
      ticket = await getCollaborationTicket(
        this.universeId,
        this.documentId,
        { signal: abort.signal }
      );
    } catch (error) {
      this.connecting = false;
      if (this.stopped) return;
      if (abort.signal.aborted) return;
      this.update({
        status: 'offline',
        errorMessage:
          'The collaboration ticket could not be issued. Retrying…',
      });
      this.scheduleReconnect();
      return;
    } finally {
      if (this.ticketAbort === abort) this.ticketAbort = null;
    }

    this.connecting = false;
    if (this.stopped) return;

    if (this.generation === null) {
      this.generation = ticket.collab_generation;
    } else if (ticket.collab_generation !== this.generation) {
      // The durable room was reset while this provider was disconnected. The
      // local Y.Doc still contains the discarded generation's operations.
      this.notifyReset('generation_changed');
      return;
    }

    this.update({
      canWrite: ticket.can_write,
      role: ticket.role,
      displayName: ticket.display_name,
      status: 'connecting',
      errorMessage: null,
    });

    const socket = new WebSocket(this.websocketUrl(ticket));
    socket.binaryType = 'arraybuffer';
    socket.onopen = () => this.handleOpen(socket);
    socket.onmessage = (event) => {
      void this.handleMessage(socket, event.data);
    };
    socket.onerror = () => {
      // ``onclose`` performs the actual retry bookkeeping.
    };
    socket.onclose = (event) => this.handleClose(socket, event);
    this.socket = socket;
  }

  private websocketUrl(ticket: Ticket): string {
    const path = ticket.websocket_path;
    const separator = path.includes('?') ? '&' : '?';
    const query = `${separator}ticket=${encodeURIComponent(ticket.ticket)}`;
    if (/^wss?:\/\//i.test(path)) return `${path}${query}`;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}${path}${query}`;
  }

  private handleOpen(socket: WebSocket): void {
    if (this.socket !== socket || this.stopped) return;
    this.reconnectAttempts = 0;
    this.update({ status: 'connected', errorMessage: null });

    // Announce the local state vector. The server replies with a step-2 diff
    // containing everything this client is missing.
    this.sendSyncStep1();
    this.sendAwareness([this.doc.clientID]);
    this.startHeartbeat();
  }

  private handleClose(socket: WebSocket, event: CloseEvent): void {
    if (this.socket !== socket) return;
    this.socket = null;
    this.stopHeartbeat();

    const remoteClients = Array.from(this.awareness.getStates().keys()).filter(
      (client) => client !== this.doc.clientID
    );
    if (remoteClients.length > 0) {
      removeAwarenessStates(this.awareness, remoteClients, this);
    }

    if (this.stopped) return;

    if (event.code === CLOSE_ROOM_RESET) {
      this.notifyReset(event.reason || 'room_reset');
      return;
    }
    if (
      event.code === 4401 ||
      event.code === CLOSE_FORBIDDEN ||
      event.code === CLOSE_NOT_FOUND
    ) {
      this.update({
        status: 'error',
        errorMessage:
          event.code === 4401
            ? 'The collaboration session expired. Reload the page to sign in again.'
            : 'You no longer have access to this document.',
      });
      return;
    }

    this.update({
      status: 'offline',
      errorMessage:
        event.reason === 'server_shutdown'
          ? 'The collaboration server restarted. Reconnecting…'
          : 'Connection lost. Your edits are kept locally and will sync when the connection returns.',
    });
    this.scheduleReconnect();
  }

  private notifyReset(reason: string): void {
    if (this.resetNotified || this.stopped) return;
    this.resetNotified = true;
    this.clearReconnectTimer();
    this.update({
      status: 'reset',
      errorMessage:
        reason === 'generation_changed'
          ? 'This document was restored or repaired elsewhere. Reloading its collaborative state…'
          : 'The collaborative state was reset. Reloading the document…',
    });
    this.onReset?.(reason);
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.reconnectTimer !== null) return;
    const attempt = this.reconnectAttempts;
    this.reconnectAttempts = Math.min(attempt + 1, 8);
    const base = Math.min(1000 * 2 ** attempt, MAX_RECONNECT_DELAY_MS);
    const jitter = Math.floor(Math.random() * 250);
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.stopped) void this.openSocket();
    }, base + jitter);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  // -------------------------------------------------------------------------
  // Yjs sync protocol
  // -------------------------------------------------------------------------

  private sendSyncStep1(): void {
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeSyncStep1(encoder, this.doc);
    this.sendBinary(encoding.toUint8Array(encoder));
  }

  private handleDocumentUpdate = (update: Uint8Array, origin: unknown): void => {
    if (origin === this) return; // remote update just applied
    if (!this.sendBinary(this.encodeUpdate(update))) {
      // Offline edits stay in the Y.Doc and converge during the next sync.
    }
    this.update({ pendingUpdates: this.state.pendingUpdates + 1 });
  };

  private encodeUpdate(update: Uint8Array): Uint8Array {
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeUpdate(encoder, update);
    return encoding.toUint8Array(encoder);
  }

  private async handleMessage(
    socket: WebSocket,
    data: ArrayBuffer | Blob | string
  ): Promise<void> {
    if (this.socket !== socket || this.stopped) return;
    if (typeof data === 'string') return; // protocol is binary only

    let payload: Uint8Array;
    try {
      payload =
        data instanceof Blob
          ? new Uint8Array(await data.arrayBuffer())
          : toUint8Array(data);
    } catch {
      return;
    }
    if (this.stopped || this.socket !== socket || payload.length === 0) return;

    const decoder = decoding.createDecoder(payload);
    let messageType: number;
    try {
      messageType = decoding.readVarUint(decoder);
    } catch {
      return;
    }

    if (messageType === MESSAGE_SYNC) {
      this.handleSyncMessage(payload);
      return;
    }
    if (messageType === MESSAGE_AWARENESS) {
      try {
        applyAwarenessUpdate(
          this.awareness,
          decoding.readVarUint8Array(decoder),
          this
        );
      } catch {
        // Ignore malformed awareness frames instead of dropping the room.
      }
      return;
    }
    if (messageType === MESSAGE_CONTROL) {
      this.handleControlMessage(payload.subarray(1));
    }
  }

  private handleSyncMessage(payload: Uint8Array): void {
    const subtype = payload[1];
    const decoder = decoding.createDecoder(payload.subarray(1));
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);

    try {
      syncProtocol.readSyncMessage(decoder, encoder, this.doc, this);
    } catch {
      return;
    }

    if (encoding.length(encoder) > 1) {
      this.sendBinary(encoding.toUint8Array(encoder));
    }

    if (subtype === SYNC_STEP1) {
      // The server announced its state vector. If it only contains clocks we
      // already have, no step-2 reply will follow and the room is in sync.
      try {
        const vectorDecoder = decoding.createDecoder(payload.subarray(2));
        const serverVector = Y.decodeStateVector(
          decoding.readVarUint8Array(vectorDecoder)
        );
        const localVector = Y.decodeStateVector(
          Y.encodeStateVector(this.doc)
        );
        if (isStateVectorSubset(serverVector, localVector)) {
          this.markSynced();
        }
      } catch {
        // A malformed vector is not fatal: the step-2 reply still converges.
      }
      return;
    }

    if (subtype === SYNC_STEP2) {
      this.markSynced();
    }
  }

  private markSynced(): void {
    if (this.state.status !== 'synced') {
      this.reconnectAttempts = 0;
      this.update({
        status: 'synced',
        // Once a full sync round-trip completes, anything local is either
        // already durable on the server or has just been sent again.
        pendingUpdates: 0,
        errorMessage: null,
      });
    }
  }

  private handleControlMessage(payload: Uint8Array): void {
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(new TextDecoder().decode(payload)) as Record<
        string,
        unknown
      >;
    } catch {
      return;
    }

    switch (message.type) {
      case 'permission':
        this.update({
          canWrite: Boolean(message.canWrite),
          role: typeof message.role === 'string' ? message.role : this.state.role,
          displayName:
            typeof message.displayName === 'string'
              ? message.displayName
              : this.state.displayName,
        });
        break;
      case 'durable_ack': {
        const sequence =
          typeof message.sequence === 'number' ? message.sequence : null;
        this.update({
          lastAckSequence: sequence ?? this.state.lastAckSequence,
          pendingUpdates: Math.max(0, this.state.pendingUpdates - 1),
        });
        break;
      }
      case 'error':
        if (message.code === 'read_only') {
          this.update({
            canWrite: false,
            errorMessage:
              'Your write access was revoked. The document is now read-only.',
          });
        } else if (message.code === 'invalid_update') {
          this.update({
            errorMessage:
              'An edit could not be synchronized. The editor will recover on the next save.',
          });
        }
        break;
      default:
        break;
    }
  }

  // -------------------------------------------------------------------------
  // Awareness
  // -------------------------------------------------------------------------

  private handleAwarenessUpdate = (
    changes: { added: number[]; updated: number[]; removed: number[] },
    origin: unknown
  ): void => {
    const collaborators = Math.max(0, this.awareness.getStates().size - 1);
    if (collaborators !== this.state.collaborators) {
      this.update({ collaborators });
    }
    if (origin === this) return;

    const local = this.doc.clientID;
    const changed = [
      ...changes.added,
      ...changes.updated,
      ...changes.removed,
    ];
    if (!changed.includes(local)) return;
    this.sendAwareness(changed);
  };

  private encodeAwarenessUpdate(clients: number[]): Uint8Array {
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_AWARENESS);
    encoding.writeVarUint8Array(
      encoder,
      encodeAwarenessUpdate(this.awareness, clients)
    );
    return encoding.toUint8Array(encoder);
  }

  private sendAwareness(clients: number[]): void {
    this.sendBinary(this.encodeAwarenessUpdate(clients));
  }

  // -------------------------------------------------------------------------
  // Transport
  // -------------------------------------------------------------------------

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = window.setInterval(() => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;
      const payload = new TextEncoder().encode(
        JSON.stringify({ type: 'ping' })
      );
      const frame = new Uint8Array(payload.length + 1);
      frame[0] = MESSAGE_CONTROL;
      frame.set(payload, 1);
      this.sendBinary(frame);
    }, HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private sendBinary(payload: Uint8Array): boolean {
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    try {
      socket.send(payload);
      return true;
    } catch {
      return false;
    }
  }

  // -------------------------------------------------------------------------
  // Store updates
  // -------------------------------------------------------------------------

  private update(partial: Partial<CollaborationState>): void {
    const next = { ...this.state, ...partial };
    const changed = (
      Object.keys(next) as Array<keyof CollaborationState>
    ).some((key) => next[key] !== this.state[key]);
    if (!changed) return;
    this.state = next;
    for (const listener of this.listeners) listener();
  }
}
