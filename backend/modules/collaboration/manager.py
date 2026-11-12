"""In-process Yjs room manager for FastAPI WebSockets.

Design decisions mirror the frozen M0 collaboration specification:

* updates are acknowledged only after the database transaction commits;
* snapshots are verified to reproduce the room state vector before the update
  log they cover is pruned;
* authorization is re-read from durable state while a room is open;
* presence is relayed but never persisted or used as authorship evidence;
* the TipTap JSON projection is regenerated from the CRDT, never from a
  client-supplied copy of the document.

The manager owns one ``pycrdt.Doc`` per open document. It is intended for the
single-worker deployment described in the operational guide. Multi-worker
deployments need sticky room routing or an external pub/sub layer, because Yjs
awareness and room state are deliberately in-memory.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from pycrdt import (
    Doc,
    create_sync_message,
    create_update_message,
    handle_sync_message,
    read_message,
)
from starlette.concurrency import run_in_threadpool

from backend.core.config import Settings
from backend.core.errors import ApiError
from backend.modules.chronicle.content import ContentValidationError
from backend.modules.collaboration.repository import (
    SessionFactory,
    StaleRoomError,
    load_room_payload,
    materialize_room,
    persist_baseline_snapshot,
    persist_snapshot_and_prune,
    persist_update_batch,
    reset_room_state,
)
from backend.modules.collaboration.service import (
    CollaborationAccessError,
    load_access,
)
from backend.modules.collaboration.tickets import TicketError, decode_ticket
from backend.modules.collaboration.ydoc import (
    get_fragment,
    snapshot_is_consistent,
    tiptap_to_ydoc,
    ydoc_to_tiptap,
)

logger = logging.getLogger("worldweave.collaboration")

MESSAGE_SYNC = 0
MESSAGE_AWARENESS = 1
MESSAGE_CONTROL = 3
SYNC_STEP1 = 0
SYNC_STEP2 = 1
SYNC_UPDATE = 2

MAX_SYNC_MESSAGE_BYTES = 8 * 1024 * 1024
MAX_AWARENESS_BYTES = 256 * 1024
MAX_BATCH_UPDATES = 128
REVALIDATE_INTERVAL_SECONDS = 2.0
REAPER_INTERVAL_SECONDS = 15.0


def _load_access_in_session(
    session_factory: SessionFactory,
    *,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
):
    with session_factory() as db:
        return load_access(
            db,
            universe_id=universe_id,
            document_id=document_id,
            user_id=user_id,
            session_id=session_id,
        )

CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404
CLOSE_CONFLICT = 4409
CLOSE_ROOM_RESET = 4001
CLOSE_GOING_AWAY = 1012
CLOSE_TOO_LARGE = 1009


@dataclass(eq=False, slots=True)
class Connection:
    websocket: WebSocket
    user_id: uuid.UUID
    session_id: uuid.UUID
    universe_id: uuid.UUID
    document_id: uuid.UUID
    role: str
    display_name: str
    can_write: bool
    generation: int
    last_validated: float = 0.0
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass(slots=True)
class UpdateItem:
    connection: Connection
    update: bytes
    role: str


@dataclass(eq=False, slots=True)
class Room:
    universe_id: uuid.UUID
    document_id: uuid.UUID
    document: Doc
    generation: int
    owner_id: uuid.UUID
    last_sequence: int
    queue: asyncio.Queue[UpdateItem | None]
    writer_task: asyncio.Task[None] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    compaction_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    connections: set[Connection] = field(default_factory=set)
    awareness_frames: dict[Connection, bytes] = field(default_factory=dict)
    updates_since_snapshot: int = 0
    bytes_since_snapshot: int = 0
    last_materialized_at: float = 0.0
    last_revision_at: float = 0.0
    last_actor_id: uuid.UUID | None = None
    last_actor_role: str = "viewer"
    materialize_task: asyncio.Task[None] | None = None
    idle_task: asyncio.Task[None] | None = None
    stopped: bool = False


class CollaborationManager:
    def __init__(
        self, *, settings: Settings, session_factory: SessionFactory
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self._rooms: dict[uuid.UUID, Room] = {}
        self._creation_locks: dict[uuid.UUID, asyncio.Lock] = {}
        self._reaper_task: asyncio.Task[None] | None = None
        self._shutting_down = False

    async def start(self) -> None:
        if self._reaper_task is None:
            self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def shutdown(self) -> None:
        self._shutting_down = True
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass
            self._reaper_task = None
        rooms = list(self._rooms.values())
        await asyncio.gather(
            *(self._shutdown_room(room) for room in rooms),
            return_exceptions=True,
        )
        self._rooms.clear()

    async def handle_websocket(
        self, websocket: WebSocket, *, document_id: uuid.UUID, ticket: str
    ) -> None:
        if self._shutting_down:
            await websocket.close(code=CLOSE_GOING_AWAY)
            return

        try:
            claims = decode_ticket(
                ticket, secret=self.settings.collaboration_ticket_secret
            )
        except TicketError:
            await websocket.close(code=CLOSE_UNAUTHORIZED, reason="invalid_ticket")
            return

        if claims.document_id != document_id:
            await websocket.close(code=CLOSE_FORBIDDEN, reason="document_mismatch")
            return

        try:
            access = await run_in_threadpool(
                _load_access_in_session,
                self.session_factory,
                universe_id=claims.universe_id,
                document_id=document_id,
                user_id=claims.user_id,
                session_id=claims.session_id,
            )
        except CollaborationAccessError as exc:
            await websocket.close(
                code=CLOSE_UNAUTHORIZED
                if exc.status_code == 401
                else CLOSE_NOT_FOUND,
                reason=exc.code,
            )
            return
        except Exception:
            logger.exception("collaboration_access_failed")
            await websocket.close(code=1011, reason="authorization_failed")
            return

        if claims.collab_generation != access.document.collab_generation:
            # The ticket was issued for a CRDT generation that a revision
            # restore (or content repair) has since invalidated. Reconnecting
            # with the stale local state would resurrect discarded operations.
            await websocket.close(code=CLOSE_ROOM_RESET, reason="room_reset")
            return

        await websocket.accept()

        try:
            room = await self._get_room(
                claims.universe_id,
                document_id,
                access.document.collab_generation,
            )
        except CollaborationAccessError:
            await websocket.close(code=CLOSE_NOT_FOUND, reason="document_not_found")
            return
        except StaleRoomError:
            await websocket.close(code=CLOSE_ROOM_RESET, reason="room_reset")
            return
        except Exception:
            logger.exception("collaboration_room_load_failed")
            await websocket.close(code=1011, reason="room_load_failed")
            return

        if room.idle_task is not None:
            room.idle_task.cancel()
            room.idle_task = None

        connection = Connection(
            websocket=websocket,
            user_id=access.user.id,
            session_id=access.session.id,
            universe_id=claims.universe_id,
            document_id=document_id,
            role=access.membership.role,
            display_name=access.user.display_name,
            can_write=access.can_write,
            generation=room.generation,
            last_validated=time.monotonic(),
        )
        room.connections.add(connection)

        try:
            async with room.lock:
                initial = create_sync_message(room.document)
            await self._send_bytes(connection, initial)
            await self._send_permission(connection)
            # Presence is ephemeral, but a late joiner should not wait up to
            # 15 seconds for every existing participant's awareness tick.
            # Each connection keeps a single last-known frame; replaying them
            # reconstructs the current room presence immediately.
            for other, frame in list(room.awareness_frames.items()):
                if other is not connection:
                    await self._send_bytes(connection, frame)
            await self._receive_loop(connection, room)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "collaboration_connection_failed",
                extra={"document_id": str(document_id)},
            )
        finally:
            room.connections.discard(connection)
            room.awareness_frames.pop(connection, None)
            await self._schedule_idle_close(room)

    async def _receive_loop(self, connection: Connection, room: Room) -> None:
        while True:
            message = await connection.websocket.receive()
            message_type = message.get("type")
            if message_type == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data is not None:
                await self._handle_binary(connection, room, data)
                continue
            text = message.get("text")
            if text is not None:
                await self._handle_text(connection, text)

    async def _handle_binary(
        self, connection: Connection, room: Room, data: bytes
    ) -> None:
        if not data:
            return
        if len(data) > MAX_SYNC_MESSAGE_BYTES:
            await connection.websocket.close(
                code=CLOSE_TOO_LARGE, reason="message_too_large"
            )
            return

        message_type = data[0]
        if message_type == MESSAGE_SYNC:
            if len(data) < 2:
                return
            await self._handle_sync(connection, room, data)
            return
        if message_type == MESSAGE_AWARENESS:
            if len(data) > MAX_AWARENESS_BYTES:
                await connection.websocket.close(
                    code=CLOSE_TOO_LARGE, reason="awareness_too_large"
                )
                return
            room.awareness_frames[connection] = data
            await self._broadcast(room, data, exclude=connection)
            return
        if message_type == MESSAGE_CONTROL:
            await self._handle_text(connection, data[1:].decode("utf-8", "ignore"))

    async def _handle_sync(
        self, connection: Connection, room: Room, data: bytes
    ) -> None:
        subtype = data[1]
        try:
            if subtype == SYNC_STEP1:
                async with room.lock:
                    reply = handle_sync_message(data[1:], room.document)
                if reply is not None:
                    await self._send_bytes(connection, reply)
                return
            if subtype not in {SYNC_STEP2, SYNC_UPDATE}:
                return
            update = read_message(data[2:])
        except Exception:
            await self._send_control(
                connection,
                {"type": "error", "code": "invalid_update"},
            )
            return

        if update == b"\x00\x00":
            return
        if not await self._ensure_writable(connection, room):
            return
        await room.queue.put(
            UpdateItem(
                connection=connection,
                update=update,
                role=connection.role,
            )
        )

    async def _handle_text(self, connection: Connection, text: str) -> None:
        if len(text) > 4096:
            return
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        if payload.get("type") == "ping":
            await self._send_control(connection, {"type": "pong"})

    async def _ensure_writable(
        self, connection: Connection, room: Room
    ) -> bool:
        if (
            time.monotonic() - connection.last_validated
            >= REVALIDATE_INTERVAL_SECONDS
        ):
            if not await self._revalidate(connection, room):
                return False
        if not connection.can_write:
            await self._send_control(
                connection,
                {
                    "type": "error",
                    "code": "read_only",
                    "message": "This document is read-only for your session.",
                },
            )
            return False
        return True

    async def _revalidate(self, connection: Connection, room: Room) -> bool:
        try:
            access = await run_in_threadpool(
                _load_access_in_session,
                self.session_factory,
                universe_id=connection.universe_id,
                document_id=connection.document_id,
                user_id=connection.user_id,
                session_id=connection.session_id,
            )
        except CollaborationAccessError as exc:
            await connection.websocket.close(
                code=CLOSE_UNAUTHORIZED
                if exc.status_code == 401
                else CLOSE_NOT_FOUND,
                reason=exc.code,
            )
            return False
        except Exception:
            logger.exception("collaboration_revalidation_failed")
            return False

        connection.last_validated = time.monotonic()
        connection.role = access.membership.role
        connection.display_name = access.user.display_name
        if access.document.collab_generation != room.generation:
            await connection.websocket.close(
                code=CLOSE_ROOM_RESET, reason="room_reset"
            )
            return False
        if access.can_write != connection.can_write:
            connection.can_write = access.can_write
            await self._send_permission(connection)
        return True

    async def _send_permission(self, connection: Connection) -> None:
        await self._send_control(
            connection,
            {
                "type": "permission",
                "canWrite": connection.can_write,
                "role": connection.role,
                "displayName": connection.display_name,
            },
        )

    async def _send_control(
        self, connection: Connection, payload: dict[str, Any]
    ) -> bool:
        encoded = (
            bytes([MESSAGE_CONTROL])
            + json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        return await self._send_bytes(connection, encoded)

    async def _send_bytes(
        self, connection: Connection, payload: bytes
    ) -> bool:
        try:
            async with connection.send_lock:
                await connection.websocket.send_bytes(payload)
            return True
        except (RuntimeError, OSError):
            return False
        except Exception:
            return False

    async def _broadcast(
        self, room: Room, payload: bytes, *, exclude: Connection | None = None
    ) -> None:
        stale: list[Connection] = []
        for connection in list(room.connections):
            if connection is exclude:
                continue
            if not await self._send_bytes(connection, payload):
                stale.append(connection)
        for connection in stale:
            room.connections.discard(connection)
            room.awareness_frames.pop(connection, None)

    async def _get_room(
        self,
        universe_id: uuid.UUID,
        document_id: uuid.UUID,
        generation: int,
    ) -> Room:
        room = self._rooms.get(document_id)
        if room is not None:
            if room.generation != generation:
                await self._close_room(
                    room,
                    code=CLOSE_ROOM_RESET,
                    reason="room_reset",
                )
            else:
                return room

        lock = self._creation_locks.setdefault(document_id, asyncio.Lock())
        async with lock:
            room = self._rooms.get(document_id)
            if room is not None and room.generation == generation:
                return room
            if room is not None:
                await self._close_room(
                    room, code=CLOSE_ROOM_RESET, reason="room_reset"
                )

            payload = await run_in_threadpool(
                load_room_payload,
                self.session_factory,
                universe_id=universe_id,
                document_id=document_id,
            )
            if payload["collab_generation"] != generation:
                raise StaleRoomError("collaboration generation changed")

            if payload["has_snapshot"]:
                document = Doc()
                document.apply_update(payload["snapshot_state"])
            else:
                document = tiptap_to_ydoc(payload["content_json"])
                await run_in_threadpool(
                    persist_baseline_snapshot,
                    self.session_factory,
                    universe_id=universe_id,
                    document_id=document_id,
                    ydoc_state=document.get_update(),
                    state_vector=document.get_state(),
                    expected_generation=generation,
                )

            for _, update, _actor in payload["updates"]:
                document.apply_update(update)

            room = Room(
                universe_id=universe_id,
                document_id=document_id,
                document=document,
                generation=generation,
                owner_id=uuid.UUID(str(payload["owner_id"])),
                last_sequence=int(payload["max_sequence"]),
                queue=asyncio.Queue(),
            )
            room.updates_since_snapshot = len(payload["updates"])
            room.bytes_since_snapshot = sum(
                len(update) for _, update, _ in payload["updates"]
            )
            room.writer_task = asyncio.create_task(
                self._writer_loop(room), name=f"collab-writer-{document_id}"
            )
            self._rooms[document_id] = room
            return room

    async def _writer_loop(self, room: Room) -> None:
        while True:
            item = await room.queue.get()
            if item is None:
                return
            batch = [item]
            while len(batch) < MAX_BATCH_UPDATES:
                try:
                    candidate = room.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if candidate is None:
                    return
                batch.append(candidate)

            accepted: list[tuple[UpdateItem, int]] = []
            async with room.lock:
                for pending in batch:
                    if not pending.connection.can_write:
                        await self._send_control(
                            pending.connection,
                            {
                                "type": "error",
                                "code": "read_only",
                                "message": "Write permission was revoked.",
                            },
                        )
                        continue
                    try:
                        room.document.apply_update(pending.update)
                    except Exception:
                        await self._send_control(
                            pending.connection,
                            {
                                "type": "error",
                                "code": "invalid_update",
                                "message": "The CRDT update could not be applied.",
                            },
                        )
                        continue
                    accepted.append(
                        (pending, room.last_sequence + 1 + len(accepted))
                    )

                if not accepted:
                    continue

                rows = [
                    {
                        "sequence": sequence,
                        "update": pending.update,
                        "client_id": None,
                        "actor_id": pending.connection.user_id,
                    }
                    for pending, sequence in accepted
                ]

                try:
                    await run_in_threadpool(
                        persist_update_batch,
                        self.session_factory,
                        universe_id=room.universe_id,
                        document_id=room.document_id,
                        expected_generation=room.generation,
                        rows=rows,
                    )
                except StaleRoomError:
                    await self._close_room(
                        room, code=CLOSE_ROOM_RESET, reason="room_reset"
                    )
                    return
                except Exception:
                    logger.exception(
                        "collaboration_persist_failed",
                        extra={"document_id": str(room.document_id)},
                    )
                    await self._close_room(
                        room,
                        code=1011,
                        reason="persistence_failed",
                    )
                    return

                room.last_sequence = accepted[-1][1]
                room.updates_since_snapshot += len(accepted)
                room.bytes_since_snapshot += sum(
                    len(pending.update) for pending, _ in accepted
                )
                latest = accepted[-1][0]
                room.last_actor_id = latest.connection.user_id
                room.last_actor_role = latest.role

                state_vector = base64.b64encode(
                    room.document.get_state()
                ).decode("ascii")
                for pending, sequence in accepted:
                    await self._send_control(
                        pending.connection,
                        {
                            "type": "durable_ack",
                            "sequence": sequence,
                            "stateVector": state_vector,
                        },
                    )
                    await self._broadcast(
                        room,
                        create_update_message(pending.update),
                        exclude=pending.connection,
                    )

            self._schedule_materialization(room)

            if (
                room.updates_since_snapshot
                >= self.settings.collaboration_snapshot_update_threshold
                or room.bytes_since_snapshot
                >= self.settings.collaboration_snapshot_byte_threshold
            ):
                await self._compact(room)

    def _schedule_materialization(self, room: Room) -> None:
        if room.materialize_task is not None and not room.materialize_task.done():
            return
        room.materialize_task = asyncio.create_task(
            self._delayed_materialize(room),
            name=f"collab-materialize-{room.document_id}",
        )

    async def _delayed_materialize(self, room: Room) -> None:
        try:
            await asyncio.sleep(
                max(
                    0.05,
                    self.settings.collaboration_materialize_delay_ms / 1000,
                )
            )
            await self._materialize(room)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "collaboration_materialize_failed",
                extra={"document_id": str(room.document_id)},
            )

    async def _materialize(self, room: Room) -> None:
        if room.stopped or room.last_actor_id is None:
            return
        async with room.lock:
            content = ydoc_to_tiptap(room.document)
        now = time.monotonic()
        create_revision = (
            now - room.last_revision_at
            >= self.settings.collaboration_revision_interval_seconds
        )
        try:
            result = await run_in_threadpool(
                materialize_room,
                self.session_factory,
                universe_id=room.universe_id,
                document_id=room.document_id,
                expected_generation=room.generation,
                actor_id=room.last_actor_id,
                role=room.last_actor_role,
                content_json=content,
                create_revision=create_revision,
            )
        except (ContentValidationError, ApiError):
            logger.exception(
                "collaboration_content_rejected",
                extra={"document_id": str(room.document_id)},
            )
            await self._poison_room(room)
            return
        except Exception:
            logger.exception(
                "collaboration_materialize_failed",
                extra={"document_id": str(room.document_id)},
            )
            return
        if result is None:
            return
        room.last_materialized_at = now
        if result.get("revision_number"):
            room.last_revision_at = now

    async def _poison_room(self, room: Room) -> None:
        """Discard CRDT state that cannot be projected into the schema."""

        try:
            await run_in_threadpool(
                reset_room_state,
                self.session_factory,
                universe_id=room.universe_id,
                document_id=room.document_id,
            )
        except Exception:
            logger.exception("collaboration_reset_failed")
        await self._close_room(
            room, code=CLOSE_ROOM_RESET, reason="invalid_document_state"
        )

    async def _compact(self, room: Room, *, reason: str = "compaction") -> None:
        async with room.compaction_lock:
            if room.updates_since_snapshot <= 0:
                return
            async with room.lock:
                snapshot = room.document.get_update()
                state_vector = room.document.get_state()
                if not snapshot_is_consistent(room.document, snapshot):
                    logger.error(
                        "collaboration_snapshot_verification_failed",
                        extra={"document_id": str(room.document_id)},
                    )
                    return
                last_sequence = room.last_sequence
                update_count = room.updates_since_snapshot
                created_by = room.last_actor_id

            try:
                await run_in_threadpool(
                    persist_snapshot_and_prune,
                    self.session_factory,
                    universe_id=room.universe_id,
                    document_id=room.document_id,
                    expected_generation=room.generation,
                    ydoc_state=snapshot,
                    state_vector=state_vector,
                    last_update_sequence=last_sequence,
                    update_count=update_count,
                    created_by=created_by,
                    reason=reason,
                )
            except StaleRoomError:
                return
            except Exception:
                logger.exception(
                    "collaboration_snapshot_failed",
                    extra={"document_id": str(room.document_id)},
                )
                return

            if room.last_sequence == last_sequence:
                room.updates_since_snapshot = 0
                room.bytes_since_snapshot = 0

    async def _schedule_idle_close(self, room: Room) -> None:
        if room.connections or room.stopped:
            return
        if room.idle_task is not None and not room.idle_task.done():
            return
        room.idle_task = asyncio.create_task(
            self._idle_close(room),
            name=f"collab-idle-{room.document_id}",
        )

    async def _idle_close(self, room: Room) -> None:
        try:
            await asyncio.sleep(
                self.settings.collaboration_idle_close_seconds
            )
        except asyncio.CancelledError:
            return
        if room.connections or room.stopped:
            return
        try:
            await self._materialize(room)
            await self._compact(room, reason="idle")
        finally:
            room.stopped = True
            await room.queue.put(None)
            if self._rooms.get(room.document_id) is room:
                self._rooms.pop(room.document_id, None)

    async def _close_room(
        self, room: Room, *, code: int, reason: str
    ) -> None:
        room.stopped = True
        if self._rooms.get(room.document_id) is room:
            self._rooms.pop(room.document_id, None)
        for connection in list(room.connections):
            try:
                await connection.websocket.close(code=code, reason=reason)
            except Exception:
                pass
        room.connections.clear()
        room.awareness_frames.clear()
        await room.queue.put(None)

    async def _reaper_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(REAPER_INTERVAL_SECONDS)
                rooms = list(self._rooms.values())
                for room in rooms:
                    for connection in list(room.connections):
                        if room.stopped:
                            break
                        if not await self._revalidate(connection, room):
                            room.connections.discard(connection)
                    if not room.connections:
                        await self._schedule_idle_close(room)
        except asyncio.CancelledError:
            raise

    async def _shutdown_room(self, room: Room) -> None:
        room.stopped = True
        for connection in list(room.connections):
            try:
                await connection.websocket.close(
                    code=CLOSE_GOING_AWAY, reason="server_shutdown"
                )
            except Exception:
                pass
        room.connections.clear()
        try:
            await self._materialize(room)
            await self._compact(room, reason="shutdown")
        finally:
            await room.queue.put(None)
            if room.materialize_task is not None:
                room.materialize_task.cancel()
