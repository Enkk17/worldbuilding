import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import type { JSONContent } from '@tiptap/core';
import { useQueryClient } from '@tanstack/react-query';
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  Clock,
  FileText,
  Feather,
  History,
  Layers,
  Library,
  Link2,
  MessageSquare,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Settings2,
  StickyNote,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import {
  useCreateDocument,
  useCreateDocumentComment,
  useDeleteDocument,
  useDeleteDocumentComment,
  useGetCurrentAccount,
  useGetDocument,
  useGetDocumentRevision,
  useGetDocumentTree,
  useListDocumentComments,
  useListDocumentRevisions,
  useListEntities,
  useListEntityDocuments,
  useRestoreDocumentRevision,
  useUpdateDocument,
  useUpdateDocumentComment,
  getGetDocumentQueryKey,
  getGetDocumentTreeQueryKey,
  type CommentResponse,
  type DocumentResponse,
  type DocumentRevisionResponse,
  type DocumentSummary,
  type DocumentTreeNode,
} from '@workspace/api-client-react';
import { RichTextEditor } from '@/components/RichTextEditor';
import {
  CollaborationProvider,
  type CollaborationState,
} from '@/lib/collaboration-provider';

type UniverseRole = 'owner' | 'admin' | 'editor' | 'contributor' | 'viewer';

const DOCUMENT_TYPES = [
  'collection',
  'work',
  'part',
  'chapter',
  'scene',
  'note',
] as const;
const DOCUMENT_STATUSES = ['draft', 'review', 'published', 'archived'] as const;
const DOCUMENT_VISIBILITIES = [
  'universe',
  'restricted',
  'draft',
  'private',
] as const;

const ALLOWED_CHILD_TYPES: Record<string, readonly string[]> = {
  collection: ['work', 'part', 'chapter', 'note'],
  work: ['part', 'chapter', 'note'],
  part: ['chapter', 'note'],
  chapter: ['scene', 'note'],
  scene: ['note'],
  note: [],
};

const TYPE_ICON: Record<string, typeof Library> = {
  collection: Library,
  work: BookOpen,
  part: Layers,
  chapter: FileText,
  scene: Feather,
  note: StickyNote,
};

const EMPTY_CONTENT: JSONContent = {
  type: 'doc',
  content: [{ type: 'paragraph' }],
};

const COLLABORATOR_COLORS = [
  '#9b4a36',
  '#294238',
  '#64856b',
  '#b18b4d',
  '#5d6f9b',
  '#7a5c8a',
  '#a05a2c',
  '#3f6d7a',
] as const;

const EMPTY_COLLAB_STATE: CollaborationState = {
  status: 'idle',
  canWrite: false,
  role: 'viewer',
  displayName: '',
  pendingUpdates: 0,
  lastAckSequence: 0,
  collaborators: 0,
  errorMessage: null,
};

const emptyCollabSubscribe = () => () => undefined;
const getEmptyCollabState = () => EMPTY_COLLAB_STATE;
const ignoreContentChange = () => undefined;

function collaboratorColor(seed: string): string {
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash * 31 + seed.charCodeAt(index)) >>> 0;
  }
  return COLLABORATOR_COLORS[hash % COLLABORATOR_COLORS.length];
}

function collaborationSummary(state: CollaborationState): {
  tone: 'ok' | 'warn' | 'error' | 'muted';
  text: string;
  animated: boolean;
} {
  switch (state.status) {
    case 'synced':
      if (!state.canWrite) {
        return {
          tone: 'muted',
          text: 'Live read-only · changes appear as collaborators type',
          animated: false,
        };
      }
      return state.pendingUpdates > 0
        ? {
            tone: 'warn',
            text: `Saving ${state.pendingUpdates} change${
              state.pendingUpdates === 1 ? '' : 's'
            }…`,
            animated: true,
          }
        : {
            tone: 'ok',
            text: 'Live collaboration · all changes saved',
            animated: false,
          };
    case 'connected':
      return {
        tone: 'muted',
        text: 'Connected · synchronizing shared content…',
        animated: true,
      };
    case 'connecting':
      return {
        tone: 'muted',
        text: 'Connecting live collaboration…',
        animated: true,
      };
    case 'offline':
      return {
        tone: 'warn',
        text:
          state.errorMessage ??
          'Offline · edits are kept locally and will sync when the connection returns.',
        animated: true,
      };
    case 'reset':
      return {
        tone: 'warn',
        text: state.errorMessage ?? 'Reloading collaborative state…',
        animated: true,
      };
    case 'error':
      return {
        tone: 'error',
        text: state.errorMessage ?? 'Collaboration is unavailable.',
        animated: false,
      };
    default:
      return {
        tone: 'muted',
        text: 'Preparing live collaboration…',
        animated: true,
      };
  }
}

const COLLAB_TONE_CLASS: Record<
  'ok' | 'warn' | 'error' | 'muted',
  { container: string; dot: string; text: string }
> = {
  ok: {
    container: 'border-[#64856b]/40 bg-[#eef4ef]',
    dot: 'bg-[#64856b]',
    text: 'text-[#2e4c35]',
  },
  warn: {
    container: 'border-[#b18b4d]/50 bg-[#faf3e4]',
    dot: 'bg-[#b18b4d]',
    text: 'text-[#6b5327]',
  },
  error: {
    container: 'border-[#a4523b]/50 bg-[#fdf2ef]',
    dot: 'bg-[#a4523b]',
    text: 'text-[#7d3e30]',
  },
  muted: {
    container: 'border-[#d9d1c2] bg-[#faf7ef]',
    dot: 'bg-[#899087]',
    text: 'text-[#53655b]',
  },
};

function CollaborationStatusBar({
  state,
  onRetry,
}: {
  state: CollaborationState;
  onRetry?: () => void;
}) {
  const summary = collaborationSummary(state);
  const tone = COLLAB_TONE_CLASS[summary.tone];
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-wrap items-center gap-2 border px-3 py-2 text-[11px] ${tone.container} ${tone.text}`}
    >
      <span
        aria-hidden="true"
        className={`h-2 w-2 rounded-full ${tone.dot} ${
          summary.animated ? 'animate-pulse' : ''
        }`}
      />
      <span className="font-medium">{summary.text}</span>
      {state.collaborators > 0 && (
        <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-[#48574d]">
          <Users size={11} />
          {state.collaborators} collaborator
          {state.collaborators === 1 ? '' : 's'}
        </span>
      )}
      {onRetry && summary.tone === 'error' && (
        <button
          type="button"
          onClick={onRetry}
          className="ml-auto border border-current px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide hover:bg-white/60"
        >
          Retry
        </button>
      )}
    </div>
  );
}

function errorMessage(error: unknown, fallback: string): string {
  const value = error as {
    data?: { error?: { message?: string; code?: string } };
    message?: string;
  };
  if (value?.data?.error?.code === 'version_conflict') {
    return 'This document changed since you loaded it. Reopen it, review the latest revision, and apply your edits again.';
  }
  return value?.data?.error?.message || value?.message || fallback;
}

function visibilityLabel(value: string): string {
  return value === 'universe'
    ? 'Universe'
    : value === 'restricted'
      ? 'Restricted'
      : value === 'draft'
        ? 'Draft only'
        : 'Private';
}

function statusClass(value: string): string {
  switch (value) {
    case 'published':
      return 'bg-[#64856b]/20 text-[#2e4c35]';
    case 'review':
      return 'bg-[#b18b4d]/20 text-[#6b5327]';
    case 'archived':
      return 'bg-[#ded7ca] text-[#53655b]';
    default:
      return 'bg-[#9b4a36]/10 text-[#9b4a36]';
  }
}

function flattenTree(
  nodes: DocumentTreeNode[],
  depth = 0
): Array<{ node: DocumentTreeNode; depth: number }> {
  const output: Array<{ node: DocumentTreeNode; depth: number }> = [];
  for (const node of nodes) {
    output.push({ node, depth });
    output.push(...flattenTree(node.children, depth + 1));
  }
  return output;
}

function filterTree(
  nodes: DocumentTreeNode[],
  term: string
): DocumentTreeNode[] {
  const needle = term.trim().toLowerCase();
  if (!needle) return nodes;
  const matches: DocumentTreeNode[] = [];
  for (const node of nodes) {
    const children = filterTree(node.children, term);
    const hit =
      node.title.toLowerCase().includes(needle) ||
      node.slug.toLowerCase().includes(needle) ||
      node.document_type.includes(needle);
    if (hit || children.length > 0) {
      matches.push({ ...node, children });
    }
  }
  return matches;
}

export interface UniverseChronicleProps {
  universeId: string;
  role: UniverseRole;
  readOnly: boolean;
  initialDocumentId?: string;
}

interface CollaborationSession {
  provider: CollaborationProvider;
  documentId: string;
  epoch: number;
}

export function UniverseChronicle({
  universeId,
  role,
  readOnly,
  initialDocumentId,
}: UniverseChronicleProps) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(initialDocumentId ?? null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');
  const [notice, setNotice] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);
  const [sidebarTab, setSidebarTab] = useState<
    'links' | 'history' | 'comments'
  >('links');
  const [showCreate, setShowCreate] = useState(false);
  const [createParentId, setCreateParentId] = useState<string | null>(null);
  const [createType, setCreateType] = useState<string>('chapter');
  const [createTitle, setCreateTitle] = useState('');
  const [createVisibility, setCreateVisibility] = useState<string>(
    role === 'contributor' ? 'draft' : 'universe'
  );
  const [createStatus, setCreateStatus] = useState<string>('draft');
  const [createContent, setCreateContent] = useState<JSONContent>(EMPTY_CONTENT);

  const [draftTitle, setDraftTitle] = useState('');
  const [draftType, setDraftType] = useState<string>('chapter');
  const [draftStatus, setDraftStatus] = useState<string>('draft');
  const [draftVisibility, setDraftVisibility] = useState<string>('universe');
  const [draftParentId, setDraftParentId] = useState<string | null>(null);
  const [draftContent, setDraftContent] = useState<JSONContent>(EMPTY_CONTENT);
  const [changeSummary, setChangeSummary] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [commentBody, setCommentBody] = useState('');
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [selectedLinkEntity, setSelectedLinkEntity] = useState<string | null>(
    null
  );
  const [openRevisionId, setOpenRevisionId] = useState<string | null>(null);
  const [collabSession, setCollabSession] =
    useState<CollaborationSession | null>(null);
  const [collabEpoch, setCollabEpoch] = useState(0);

  const treeQuery = useGetDocumentTree(universeId);
  const documentQuery = useGetDocument(universeId, selectedId ?? '', {
    query: { enabled: Boolean(selectedId) },
  });
  const document = documentQuery.data ?? null;
  const revisionsQuery = useListDocumentRevisions(
    universeId,
    selectedId ?? '',
    { include_content: true, limit: 100 },
    { query: { enabled: Boolean(selectedId) && sidebarTab === 'history' } }
  );
  const revisionDetailQuery = useGetDocumentRevision(
    universeId,
    selectedId ?? '',
    openRevisionId ?? '',
    {
      query: {
        enabled: Boolean(selectedId) && Boolean(openRevisionId),
      },
    }
  );
  const commentsQuery = useListDocumentComments(
    universeId,
    selectedId ?? '',
    { limit: 200 },
    { query: { enabled: Boolean(selectedId) && sidebarTab === 'comments' } }
  );
  const entitiesQuery = useListEntities(universeId, { limit: 500 });
  const accountQuery = useGetCurrentAccount();
  const backlinksQuery = useListEntityDocuments(
    universeId,
    selectedLinkEntity ?? '',
    { limit: 50 },
    { query: { enabled: Boolean(selectedLinkEntity) } }
  );

  const createDocument = useCreateDocument();
  const updateDocument = useUpdateDocument();
  const deleteDocument = useDeleteDocument();
  const restoreRevision = useRestoreDocumentRevision();
  const createComment = useCreateDocumentComment();
  const updateComment = useUpdateDocumentComment();
  const deleteComment = useDeleteDocumentComment();

  const activeCollabSession =
    collabSession && document && collabSession.documentId === document.id
      ? collabSession
      : null;
  const collabProvider = activeCollabSession?.provider ?? null;
  const collabState = useSyncExternalStore(
    collabProvider?.subscribe ?? emptyCollabSubscribe,
    collabProvider?.getSnapshot ?? getEmptyCollabState,
    getEmptyCollabState
  );

  const collabDisplayName =
    accountQuery.data?.display_name ?? 'Collaborator';
  const collabUserId = accountQuery.data?.id ?? 'anonymous';

  useEffect(() => {
    if (!document) return;
    const provider = new CollaborationProvider({
      universeId,
      documentId: document.id,
      user: {
        name: collabDisplayName,
        color: collaboratorColor(collabUserId),
      },
      onReset: () => {
        // The server discarded the CRDT generation (revision restore or a
        // schema-invalid projection). Rebuild the editor from durable JSON.
        setCollabEpoch((value) => value + 1);
        void queryClient.invalidateQueries();
      },
    });
    const session: CollaborationSession = {
      provider,
      documentId: document.id,
      epoch: collabEpoch,
    };
    setCollabSession(session);
    provider.connect();
    return () => {
      provider.destroy();
      setCollabSession((current) => (current === session ? null : current));
    };
  }, [
    collabDisplayName,
    collabEpoch,
    collabUserId,
    document?.id,
    queryClient,
    universeId,
  ]);

  const collabActive = Boolean(activeCollabSession);

  useEffect(() => {
    if (!collabActive || !document || collabState.lastAckSequence === 0) {
      return;
    }
    const documentId = document.id;
    // Materialisation runs after a short debounce on the server, so refresh
    // the REST projection (mentions, revision counters, tree excerpts) once
    // the edit burst has settled.
    const timer = window.setTimeout(() => {
      void queryClient.invalidateQueries({
        queryKey: getGetDocumentQueryKey(universeId, documentId),
      });
      void queryClient.invalidateQueries({
        queryKey: getGetDocumentTreeQueryKey(universeId),
      });
    }, 2200);
    return () => window.clearTimeout(timer);
  }, [
    collabActive,
    collabState.lastAckSequence,
    document?.id,
    queryClient,
    universeId,
  ]);

  const canCreate = role !== 'viewer' && !readOnly;
  const flatTree = useMemo(
    () => flattenTree(treeQuery.data?.items ?? []),
    [treeQuery.data]
  );
  const visibleTree = useMemo(
    () => filterTree(treeQuery.data?.items ?? [], search),
    [treeQuery.data, search]
  );

  useEffect(() => {
    if (!selectedId && treeQuery.data?.items.length) {
      setSelectedId(treeQuery.data.items[0].id);
    }
  }, [selectedId, treeQuery.data]);

  useEffect(() => {
    if (!document) return;
    setDraftTitle(document.title);
    setDraftType(document.document_type);
    setDraftStatus(document.status);
    setDraftVisibility(document.visibility);
    setDraftParentId(document.parent_id ?? null);
    setDraftContent(
      (document.content_json as unknown as JSONContent) ?? EMPTY_CONTENT
    );
    setChangeSummary('');
    setExpanded((current) => {
      const next = new Set(current);
      for (const crumb of document.breadcrumbs ?? []) next.add(crumb.id);
      next.add(document.id);
      return next;
    });
  }, [document?.id, document?.version]);

  useEffect(() => {
    setSelectedLinkEntity(null);
    setOpenRevisionId(null);
    setReplyTo(null);
    setCommentBody('');
  }, [selectedId]);

  const refresh = async () => {
    await queryClient.invalidateQueries();
  };

  const notify = (type: 'success' | 'error', text: string) => {
    setNotice({ type, text });
  };

  const canEditDocument =
    Boolean(document?.permissions.can_edit) && !readOnly;
  const canEditContent =
    canEditDocument && (!collabActive || collabState.canWrite);

  const permissions = document?.permissions;
  const isEditor = role === 'owner' || role === 'admin' || role === 'editor';
  const isDirty = useMemo(() => {
    if (!document) return false;
    return (
      draftTitle.trim() !== document.title ||
      draftType !== document.document_type ||
      draftStatus !== document.status ||
      draftVisibility !== document.visibility ||
      draftParentId !== (document.parent_id ?? null) ||
      (!collabActive &&
        JSON.stringify(draftContent) !== JSON.stringify(document.content_json))
    );
  }, [
    collabActive,
    document,
    draftTitle,
    draftType,
    draftStatus,
    draftVisibility,
    draftParentId,
    draftContent,
  ]);

  const blockedParentIds = useMemo(() => {
    const blocked = new Set<string>();
    if (!document) return blocked;
    const current = flatTree.find(({ node }) => node.id === document.id);
    if (!current) return blocked;
    for (const entry of flattenTree([current.node])) {
      blocked.add(entry.node.id);
    }
    return blocked;
  }, [document, flatTree]);

  const parentOptions = useMemo(() => {
    const allowedParents =
      draftType === 'collection'
        ? []
        : flatTree.filter(({ node }) => {
            if (blockedParentIds.has(node.id)) return false;
            if (draftType === 'work') return node.document_type === 'collection';
            if (draftType === 'part')
              return ['collection', 'work'].includes(node.document_type);
            if (draftType === 'chapter')
              return ['collection', 'work', 'part'].includes(node.document_type);
            if (draftType === 'scene') return node.document_type === 'chapter';
            return ['collection', 'work', 'part', 'chapter', 'scene'].includes(
              node.document_type
            );
          });
    return allowedParents;
  }, [blockedParentIds, draftType, flatTree]);

  const openCreate = (parent: DocumentSummary | null) => {
    const parentType = parent?.document_type ?? null;
    const types = parentType
      ? ALLOWED_CHILD_TYPES[parentType] ?? []
      : DOCUMENT_TYPES;
    setCreateParentId(parent?.id ?? null);
    setCreateType(types[0] ?? 'chapter');
    setCreateTitle('');
    setCreateContent(EMPTY_CONTENT);
    setCreateVisibility(role === 'contributor' ? 'draft' : 'universe');
    setCreateStatus('draft');
    setShowCreate(true);
  };

  const submitCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!createTitle.trim()) return;
    try {
      const created = await createDocument.mutateAsync({
        universeId,
        data: {
          title: createTitle.trim(),
          document_type: createType as (typeof DOCUMENT_TYPES)[number],
          parent_id: createParentId,
          content_json: createContent as unknown as Record<string, unknown>,
          visibility: createVisibility as (typeof DOCUMENT_VISIBILITIES)[number],
          status: createStatus as (typeof DOCUMENT_STATUSES)[number],
        },
      });
      setShowCreate(false);
      setSelectedId(created.id);
      if (createParentId) {
        setExpanded((current) => new Set(current).add(createParentId));
      }
      setSidebarTab('links');
      await refresh();
      notify('success', `Created "${created.title}".`);
    } catch (error) {
      notify('error', errorMessage(error, 'Could not create the document.'));
    }
  };

  const saveDocument = async () => {
    if (!document) return;
    if (!draftTitle.trim()) {
      notify('error', 'A document title is required.');
      return;
    }
    try {
      await updateDocument.mutateAsync({
        universeId,
        documentId: document.id,
        data: {
          title: draftTitle.trim(),
          document_type: draftType as (typeof DOCUMENT_TYPES)[number],
          status: draftStatus as (typeof DOCUMENT_STATUSES)[number],
          visibility: draftVisibility as (typeof DOCUMENT_VISIBILITIES)[number],
          parent_id: draftParentId,
          // While a collaboration room is open the CRDT stream is the only
          // content write path; sending stale draftContent would be rejected
          // with ``collaboration_content_conflict``.
          ...(collabActive
            ? {}
            : {
                content_json: draftContent as unknown as Record<
                  string,
                  unknown
                >,
              }),
          change_summary: changeSummary.trim() || undefined,
          expected_version: document.version,
        },
      });
      await refresh();
      notify(
        'success',
        collabActive
          ? 'Document metadata saved. The body autosaves through live collaboration.'
          : 'Document saved as a new version.'
      );
    } catch (error) {
      notify('error', errorMessage(error, 'Could not save the document.'));
    }
  };

  const removeDocument = async () => {
    if (!document) return;
    if (
      !window.confirm(
        `Delete "${document.title}" and all of its accessible child documents? They can be restored by an administrator.`
      )
    ) {
      return;
    }
    try {
      await deleteDocument.mutateAsync({
        universeId,
        documentId: document.id,
      });
      setSelectedId(null);
      await refresh();
      notify('success', 'Document moved to the archive trash.');
    } catch (error) {
      notify('error', errorMessage(error, 'Could not delete the document.'));
    }
  };

  const restoreFromRevision = async (revision: DocumentRevisionResponse) => {
    if (!document) return;
    if (
      !window.confirm(
        `Restore revision ${revision.revision_number}? The current content is preserved as a checkpoint revision.`
      )
    ) {
      return;
    }
    try {
      await restoreRevision.mutateAsync({
        universeId,
        documentId: document.id,
        revisionId: revision.id,
        data: { expected_version: document.version },
      });
      if (collabActive) {
        // The backend has already invalidated the CRDT generation. Rebuild
        // the room now instead of waiting for the socket close notification.
        setCollabEpoch((value) => value + 1);
      }
      await refresh();
      setSidebarTab('history');
      notify(
        'success',
        `Revision ${revision.revision_number} restored into a new revision.${
          collabActive ? ' Live collaborators were reconnected.' : ''
        }`
      );
    } catch (error) {
      notify(
        'error',
        errorMessage(error, 'Could not restore this revision.')
      );
    }
  };

  const submitComment = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!document || !commentBody.trim()) return;
    try {
      await createComment.mutateAsync({
        universeId,
        documentId: document.id,
        data: {
          body: commentBody.trim(),
          parent_comment_id: replyTo,
        },
      });
      setCommentBody('');
      setReplyTo(null);
      await refresh();
      notify('success', 'Comment posted.');
    } catch (error) {
      notify('error', errorMessage(error, 'Could not post the comment.'));
    }
  };

  const editComment = async (comment: CommentResponse) => {
    if (!document) return;
    const next = window.prompt('Edit comment', comment.body);
    if (!next || !next.trim() || next.trim() === comment.body) return;
    try {
      await updateComment.mutateAsync({
        universeId,
        documentId: document.id,
        commentId: comment.id,
        data: { body: next.trim() },
      });
      await refresh();
    } catch (error) {
      notify('error', errorMessage(error, 'Could not edit the comment.'));
    }
  };

  const removeComment = async (comment: CommentResponse) => {
    if (!document) return;
    if (!window.confirm('Delete this comment and its replies?')) return;
    try {
      await deleteComment.mutateAsync({
        universeId,
        documentId: document.id,
        commentId: comment.id,
      });
      await refresh();
    } catch (error) {
      notify('error', errorMessage(error, 'Could not delete the comment.'));
    }
  };

  const comments = commentsQuery.data?.items ?? [];
  const topLevelComments = comments.filter(
    (comment) => !comment.parent_comment_id
  );
  const repliesFor = (commentId: string) =>
    comments.filter((comment) => comment.parent_comment_id === commentId);
  const currentUserId = accountQuery.data?.id;
  const entities = entitiesQuery.data?.items ?? [];

  return (
    <div className="space-y-5">
      {notice && (
        <div
          role="status"
          className={`flex items-start justify-between border-l-4 p-3 text-xs ${
            notice.type === 'success'
              ? 'border-[#64856b] bg-[#eef4ef] text-[#2e4c35]'
              : 'border-[#a4523b] bg-[#fdf2ef] text-[#7d3e30]'
          }`}
        >
          <span>{notice.text}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            className="ml-4 opacity-70 hover:opacity-100"
            aria-label="Dismiss notification"
          >
            <X size={13} />
          </button>
        </div>
      )}

      <div className="flex flex-col justify-between gap-3 border border-[#d9d1c2] bg-[#faf7ef] p-4 sm:flex-row sm:items-center">
        <div>
          <p className="ww-kicker text-[#9b4a36]">Chronicle</p>
          <h2 className="font-serif text-2xl text-[#253a32]">
            Narratives & documents
          </h2>
          <p className="mt-1 text-xs text-[#6e786f]">
            {treeQuery.data?.total ?? 0} accessible documents · hierarchy,
            revisions, mentions, and commentary.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search
              size={14}
              className="absolute left-2.5 top-2.5 text-[#899087]"
            />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter the Chronicle…"
              className="w-60 rounded-sm border border-[#d5cebf] bg-white py-1.5 pl-8 pr-3 text-xs text-[#253a32] focus:border-[#9b4a36] focus:outline-none"
            />
          </div>
          {canCreate && (
            <button
              type="button"
              onClick={() => openCreate(null)}
              className="ww-button inline-flex items-center gap-1.5 bg-[#294238] px-3.5 py-2 text-xs font-semibold text-[#f7f2e7] hover:bg-[#38574a]"
            >
              <Plus size={14} /> New document
            </button>
          )}
        </div>
      </div>

      {showCreate && (
        <form
          onSubmit={submitCreate}
          className="border border-[#9b4a36]/40 bg-[#faf7ef] p-5 shadow-sm"
        >
          <div className="flex items-center justify-between border-b border-[#ded7ca] pb-3">
            <div>
              <p className="ww-kicker text-[#9b4a36]">New Chronicle document</p>
              <h3 className="font-serif text-xl text-[#253a32]">
                {createParentId
                  ? 'Create a nested document'
                  : 'Create a root document'}
              </h3>
            </div>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="text-xs text-[#788078] hover:text-black"
            >
              Cancel
            </button>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="text-xs font-semibold text-[#48574d]">
              Title
              <input
                required
                value={createTitle}
                onChange={(event) => setCreateTitle(event.target.value)}
                placeholder="The Ashen Concord"
                className="mt-1 w-full rounded-sm border border-[#d5cebf] bg-white px-3 py-2 text-xs font-normal text-[#253a32]"
              />
            </label>
            <label className="text-xs font-semibold text-[#48574d]">
              Type
              <select
                value={createType}
                onChange={(event) => setCreateType(event.target.value)}
                className="mt-1 w-full rounded-sm border border-[#d5cebf] bg-white px-3 py-2 text-xs font-normal text-[#253a32]"
              >
                {(createParentId
                  ? ALLOWED_CHILD_TYPES[
                      flatTree.find(({ node }) => node.id === createParentId)
                        ?.node.document_type ?? 'collection'
                    ] ?? []
                  : DOCUMENT_TYPES
                ).map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-semibold text-[#48574d]">
              Status
              <select
                value={createStatus}
                onChange={(event) => setCreateStatus(event.target.value)}
                className="mt-1 w-full rounded-sm border border-[#d5cebf] bg-white px-3 py-2 text-xs font-normal text-[#253a32]"
              >
                {(role === 'contributor'
                  ? ['draft', 'review']
                  : DOCUMENT_STATUSES
                ).map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-semibold text-[#48574d]">
              Visibility
              <select
                value={createVisibility}
                onChange={(event) => setCreateVisibility(event.target.value)}
                className="mt-1 w-full rounded-sm border border-[#d5cebf] bg-white px-3 py-2 text-xs font-normal text-[#253a32]"
              >
                {(role === 'contributor'
                  ? ['draft', 'private']
                  : DOCUMENT_VISIBILITIES
                ).map((visibility) => (
                  <option key={visibility} value={visibility}>
                    {visibilityLabel(visibility)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="mt-4">
            <RichTextEditor
              key={`create-${createType}`}
              initialContent={EMPTY_CONTENT}
              editable
              entities={entities}
              onChange={setCreateContent}
              placeholder="Begin the first draft… Type [[ to link a Codex entity."
            />
          </div>
          <div className="mt-4 flex gap-2">
            <button
              type="submit"
              disabled={createDocument.isPending || !createTitle.trim()}
              className="ww-button bg-[#294238] px-4 py-2 text-xs font-semibold text-[#f7f2e7] hover:bg-[#38574a] disabled:opacity-60"
            >
              {createDocument.isPending ? 'Creating…' : 'Create document'}
            </button>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="border border-[#c9c1b2] px-4 py-2 text-xs text-[#53655b]"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <div className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="h-fit border border-[#d9d1c2] bg-[#faf7ef]">
          <div className="flex items-center justify-between border-b border-[#ded7ca] px-4 py-3">
            <div>
              <p className="ww-kicker text-[#899087]">Document tree</p>
              <p className="text-[11px] text-[#6e786f]">
                {treeQuery.data?.total ?? 0} entries
              </p>
            </div>
            <button
              type="button"
              onClick={() => treeQuery.refetch()}
              className="text-[#899087] hover:text-[#9b4a36]"
              title="Reload tree"
            >
              <Clock size={14} />
            </button>
          </div>
          <div className="max-h-[70vh] overflow-y-auto px-2 py-2">
            {treeQuery.isLoading ? (
              <div className="space-y-2 p-2">
                {[0, 1, 2, 3].map((index) => (
                  <div
                    key={index}
                    className="h-7 animate-pulse bg-[#e8e1d4]"
                  />
                ))}
              </div>
            ) : visibleTree.length === 0 ? (
              <div className="px-3 py-10 text-center text-xs text-[#899087]">
                {search
                  ? 'No document matches this filter.'
                  : 'No documents yet. Create the first collection or chapter.'}
              </div>
            ) : (
              <DocumentTreeBranch
                nodes={visibleTree}
                depth={0}
                expanded={expanded}
                selectedId={selectedId}
                canCreate={canCreate}
                onToggle={(id) =>
                  setExpanded((current) => {
                    const next = new Set(current);
                    if (next.has(id)) next.delete(id);
                    else next.add(id);
                    return next;
                  })
                }
                onSelect={(id) => setSelectedId(id)}
                onCreateChild={(node) => openCreate(node)}
              />
            )}
          </div>
        </aside>

        <section className="min-w-0">
          {!document ? (
            <div className="border border-[#d9d1c2] bg-[#faf7ef] px-8 py-20 text-center">
              <BookOpen size={28} className="mx-auto text-[#b8aa8d]" />
              <h3 className="font-serif mt-3 text-2xl text-[#253a32]">
                Open a Chronicle entry
              </h3>
              <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-[#6e786f]">
                Choose a document from the tree to read, edit, restore
                revisions, follow Codex mentions, and join the commentary.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="border border-[#d9d1c2] bg-[#faf7ef] p-5">
                <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-[#899087]">
                  {(document.breadcrumbs ?? []).length === 0 && (
                    <span className="ww-kicker">Root document</span>
                  )}
                  {(document.breadcrumbs ?? []).map((crumb, index) => (
                    <span key={crumb.id} className="flex items-center gap-1.5">
                      {index > 0 && <ChevronRight size={10} />}
                      <button
                        type="button"
                        onClick={() => setSelectedId(crumb.id)}
                        className="hover:text-[#9b4a36] hover:underline"
                      >
                        {crumb.title}
                      </button>
                    </span>
                  ))}
                </div>

                <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    {canEditDocument ? (
                      <input
                        value={draftTitle}
                        onChange={(event) => setDraftTitle(event.target.value)}
                        className="font-serif w-full max-w-2xl border-b border-transparent bg-transparent text-3xl text-[#253a32] hover:border-[#d5cebf] focus:border-[#9b4a36] focus:outline-none"
                        aria-label="Document title"
                      />
                    ) : (
                      <h2 className="font-serif text-3xl text-[#253a32]">
                        {document.title}
                      </h2>
                    )}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${statusClass(
                          document.status
                        )}`}
                      >
                        {document.status}
                      </span>
                      <span className="rounded bg-[#294238]/10 px-2 py-0.5 text-[10px] font-semibold text-[#294238]">
                        {document.document_type}
                      </span>
                      <span className="rounded bg-[#ded7ca]/60 px-2 py-0.5 text-[10px] text-[#53655b]">
                        {visibilityLabel(document.visibility)}
                      </span>
                      <span className="font-mono text-[10px] text-[#899087]">
                        v{document.version} · {document.revision_count}{' '}
                        revisions
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {canEditDocument && (
                      <button
                        type="button"
                        onClick={() => setSettingsOpen((open) => !open)}
                        className="inline-flex items-center gap-1 border border-[#c9c1b2] px-2.5 py-1.5 text-[11px] font-semibold text-[#48574d] hover:bg-white"
                      >
                        <Settings2 size={12} /> Settings
                      </button>
                    )}
                    {permissions?.can_delete && !readOnly && (
                      <button
                        type="button"
                        onClick={removeDocument}
                        className="inline-flex items-center gap-1 border border-[#a4523b]/40 px-2.5 py-1.5 text-[11px] font-semibold text-[#9b4a36] hover:bg-[#fdf2ef]"
                      >
                        <Trash2 size={12} /> Delete
                      </button>
                    )}
                  </div>
                </div>

                {settingsOpen && canEditDocument && (
                  <div className="mt-4 grid gap-3 border-t border-[#ded7ca] pt-4 sm:grid-cols-2 lg:grid-cols-4">
                    <label className="text-[11px] font-semibold text-[#48574d]">
                      Type
                      <select
                        value={draftType}
                        onChange={(event) => {
                          setDraftType(event.target.value);
                          setDraftParentId(null);
                        }}
                        className="mt-1 w-full rounded-sm border border-[#d5cebf] bg-white px-2 py-1.5 text-xs font-normal"
                      >
                        {DOCUMENT_TYPES.map((type) => (
                          <option key={type} value={type}>
                            {type}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="text-[11px] font-semibold text-[#48574d]">
                      Parent
                      <select
                        value={draftParentId ?? ''}
                        onChange={(event) =>
                          setDraftParentId(event.target.value || null)
                        }
                        className="mt-1 w-full rounded-sm border border-[#d5cebf] bg-white px-2 py-1.5 text-xs font-normal"
                      >
                        <option value="">No parent (root)</option>
                        {parentOptions.map(({ node, depth }) => (
                          <option key={node.id} value={node.id}>
                            {'— '.repeat(depth)}
                            {node.title}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="text-[11px] font-semibold text-[#48574d]">
                      Status
                      <select
                        value={draftStatus}
                        onChange={(event) => setDraftStatus(event.target.value)}
                        className="mt-1 w-full rounded-sm border border-[#d5cebf] bg-white px-2 py-1.5 text-xs font-normal"
                      >
                        {(role === 'contributor'
                          ? ['draft', 'review']
                          : DOCUMENT_STATUSES
                        ).map((status) => (
                          <option key={status} value={status}>
                            {status}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="text-[11px] font-semibold text-[#48574d]">
                      Visibility
                      <select
                        value={draftVisibility}
                        onChange={(event) =>
                          setDraftVisibility(event.target.value)
                        }
                        className="mt-1 w-full rounded-sm border border-[#d5cebf] bg-white px-2 py-1.5 text-xs font-normal"
                      >
                        {(role === 'contributor'
                          ? ['draft', 'private']
                          : DOCUMENT_VISIBILITIES
                        ).map((visibility) => (
                          <option key={visibility} value={visibility}>
                            {visibilityLabel(visibility)}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                )}
              </div>

              <div>
                <CollaborationStatusBar
                  state={collabState}
                  onRetry={
                    activeCollabSession &&
                    collabState.status === 'error'
                      ? () => setCollabEpoch((value) => value + 1)
                      : undefined
                  }
                />
                {activeCollabSession ? (
                  <RichTextEditor
                    key={`${document.id}-collab-${activeCollabSession.epoch}`}
                    initialContent={null}
                    editable={canEditContent}
                    entities={entities}
                    onChange={ignoreContentChange}
                    collaboration={{
                      provider: activeCollabSession.provider,
                      user: {
                        name: collabDisplayName,
                        color: collaboratorColor(collabUserId),
                      },
                      synced: collabState.status === 'synced',
                    }}
                  />
                ) : (
                  <div className="flex min-h-[360px] items-center justify-center border border-[#d5cebf] bg-white">
                    <div className="text-center">
                      <div className="mx-auto h-5 w-5 animate-spin rounded-full border-2 border-[#d5cebf] border-t-[#9b4a36]" />
                      <p className="mt-2 text-[11px] font-semibold uppercase tracking-wider text-[#899087]">
                        Preparing live collaboration…
                      </p>
                    </div>
                  </div>
                )}
                {canEditDocument && (
                  <div className="mt-3 flex flex-col gap-2 border border-[#d9d1c2] bg-[#faf7ef] p-3 sm:flex-row sm:items-center">
                    <input
                      value={changeSummary}
                      onChange={(event) =>
                        setChangeSummary(event.target.value)
                      }
                      placeholder={
                        collabActive
                          ? 'Checkpoint summary (optional)'
                          : 'Revision summary (optional)'
                      }
                      maxLength={500}
                      className="min-w-0 flex-1 rounded-sm border border-[#d5cebf] bg-white px-3 py-2 text-xs"
                    />
                    {collabActive && (
                      <span className="text-[10px] text-[#899087]">
                        Body autosaves live
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={saveDocument}
                      disabled={updateDocument.isPending || !isDirty}
                      className="ww-button bg-[#294238] px-4 py-2 text-xs font-semibold text-[#f7f2e7] hover:bg-[#38574a] disabled:opacity-50"
                    >
                      {updateDocument.isPending
                        ? 'Saving…'
                        : isDirty
                          ? collabActive
                            ? 'Save metadata'
                            : 'Save new version'
                          : collabActive
                            ? 'Metadata saved'
                            : 'No unsaved changes'}
                    </button>
                  </div>
                )}
              </div>

              <div className="border border-[#d9d1c2] bg-[#faf7ef]">
                <div className="flex border-b border-[#ded7ca]">
                  {[
                    { id: 'links' as const, label: 'Codex links', icon: Link2 },
                    { id: 'history' as const, label: 'History', icon: History },
                    {
                      id: 'comments' as const,
                      label: `Comments (${commentsQuery.data?.total ?? 0})`,
                      icon: MessageSquare,
                    },
                  ].map((tab) => {
                    const Icon = tab.icon;
                    return (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => setSidebarTab(tab.id)}
                        className={`flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-[11px] font-semibold ${
                          sidebarTab === tab.id
                            ? 'border-[#9b4a36] text-[#9b4a36]'
                            : 'border-transparent text-[#6e786f] hover:text-[#253a32]'
                        }`}
                      >
                        <Icon size={13} /> {tab.label}
                      </button>
                    );
                  })}
                </div>

                <div className="p-4">
                  {sidebarTab === 'links' && (
                    <div className="grid gap-4 lg:grid-cols-2">
                      <div>
                        <p className="ww-kicker text-[#899087]">
                          Entity mentions in this document
                        </p>
                        {(document.entity_links ?? []).length === 0 ? (
                          <p className="mt-3 text-xs text-[#899087]">
                            No Codex entities linked yet. Type [[ in the editor
                            or use the Entity button to insert a mention.
                          </p>
                        ) : (
                          <ul className="mt-2 divide-y divide-[#ded7ca]">
                            {(document.entity_links ?? []).map((link) => (
                              <li key={link.entity_id}>
                                <button
                                  type="button"
                                  onClick={() =>
                                    setSelectedLinkEntity(link.entity_id)
                                  }
                                  className={`flex w-full items-center justify-between py-2 text-left text-xs hover:text-[#9b4a36] ${
                                    selectedLinkEntity === link.entity_id
                                      ? 'text-[#9b4a36]'
                                      : 'text-[#33483e]'
                                  }`}
                                >
                                  <span>
                                    <span className="font-medium">
                                      {link.label}
                                    </span>
                                    <span className="ml-2 text-[10px] text-[#899087]">
                                      {link.entity_type_name}
                                      {link.mention_count > 1
                                        ? ` · ${link.mention_count} mentions`
                                        : ''}
                                      {link.entity_deleted
                                        ? ' · deleted'
                                        : ''}
                                    </span>
                                  </span>
                                  <ChevronRight size={12} />
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                      <div className="border-t border-[#ded7ca] pt-3 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
                        <p className="ww-kicker text-[#899087]">
                          Backlinks from the Codex
                        </p>
                        {!selectedLinkEntity ? (
                          <p className="mt-3 text-xs text-[#899087]">
                            Select an entity mention to see every other
                            Chronicle document that references it.
                          </p>
                        ) : backlinksQuery.isLoading ? (
                          <p className="mt-3 text-xs text-[#899087]">
                            Loading backlinks…
                          </p>
                        ) : (backlinksQuery.data?.items.length ?? 0) === 0 ? (
                          <p className="mt-3 text-xs text-[#899087]">
                            No other accessible document mentions this entity.
                          </p>
                        ) : (
                          <ul className="mt-2 divide-y divide-[#ded7ca]">
                            {backlinksQuery.data?.items.map((item) => (
                              <li key={item.id}>
                                <button
                                  type="button"
                                  onClick={() => setSelectedId(item.id)}
                                  className="block w-full py-2 text-left text-xs text-[#33483e] hover:text-[#9b4a36]"
                                >
                                  <span className="font-medium">
                                    {item.title}
                                  </span>
                                  <span className="ml-2 text-[10px] text-[#899087]">
                                    {item.document_type}
                                  </span>
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>
                  )}

                  {sidebarTab === 'history' && (
                    <div>
                      <div className="flex items-center justify-between">
                        <p className="ww-kicker text-[#899087]">
                          Revision ledger
                        </p>
                        <span className="text-[10px] text-[#899087]">
                          {revisionsQuery.data?.total ?? 0} revisions
                        </span>
                      </div>
                      {revisionsQuery.isLoading ? (
                        <p className="mt-3 text-xs text-[#899087]">
                          Loading revision history…
                        </p>
                      ) : (revisionsQuery.data?.items.length ?? 0) === 0 ? (
                        <p className="mt-3 text-xs text-[#899087]">
                          This document has no revisions yet.
                        </p>
                      ) : (
                        <ul className="mt-2 divide-y divide-[#ded7ca]">
                          {revisionsQuery.data?.items.map((revision) => (
                            <li key={revision.id} className="py-3 text-xs">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div>
                                  <span className="font-mono text-[10px] font-semibold text-[#9b4a36]">
                                    rev {revision.revision_number}
                                  </span>
                                  <span className="ml-2 rounded bg-[#ded7ca]/50 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-[#53655b]">
                                    {revision.source}
                                  </span>
                                  <span className="ml-2 text-[10px] text-[#899087]">
                                    {new Date(
                                      revision.created_at
                                    ).toLocaleString()}
                                  </span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setOpenRevisionId(
                                        openRevisionId === revision.id
                                          ? null
                                          : revision.id
                                      )
                                    }
                                    className="text-[10px] font-semibold text-[#48574d] underline hover:text-[#9b4a36]"
                                  >
                                    {openRevisionId === revision.id
                                      ? 'Hide'
                                      : 'Preview'}
                                  </button>
                                  {(isEditor || role === 'contributor') &&
                                    !readOnly && (
                                      <button
                                        type="button"
                                        onClick={() =>
                                          restoreFromRevision(revision)
                                        }
                                        disabled={restoreRevision.isPending}
                                        className="inline-flex items-center gap-1 border border-[#9b4a36] px-2 py-0.5 text-[10px] font-semibold text-[#9b4a36] hover:bg-[#9b4a36] hover:text-white disabled:opacity-50"
                                      >
                                        <RotateCcw size={10} /> Restore
                                      </button>
                                    )}
                                </div>
                              </div>
                              {revision.change_summary && (
                                <p className="mt-1 text-[11px] text-[#657168]">
                                  {revision.change_summary}
                                </p>
                              )}
                              {openRevisionId === revision.id && (
                                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap border border-[#ded7ca] bg-white p-3 font-mono text-[10px] leading-relaxed text-[#48574d]">
                                  {revisionDetailQuery.isLoading
                                    ? 'Loading revision…'
                                    : revisionDetailQuery.data
                                        ?.markdown_snapshot ||
                                      'No Markdown snapshot stored.'}
                                </pre>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  {sidebarTab === 'comments' && (
                    <div>
                      <div className="flex items-center justify-between">
                        <p className="ww-kicker text-[#899087]">
                          Commentary thread
                        </p>
                        <span className="text-[10px] text-[#899087]">
                          {commentsQuery.data?.total ?? 0} comments
                        </span>
                      </div>

                      {commentsQuery.isLoading ? (
                        <p className="mt-3 text-xs text-[#899087]">
                          Loading comments…
                        </p>
                      ) : topLevelComments.length === 0 ? (
                        <p className="mt-3 text-xs text-[#899087]">
                          No comments yet. Start the conversation below.
                        </p>
                      ) : (
                        <ul className="mt-3 space-y-4">
                          {topLevelComments.map((comment) => (
                            <li key={comment.id}>
                              <CommentRow
                                comment={comment}
                                currentUserId={currentUserId}
                                canModerate={isEditor}
                                readOnly={readOnly}
                                onReply={() => {
                                  setReplyTo(comment.id);
                                  setCommentBody('');
                                }}
                                onEdit={() => editComment(comment)}
                                onDelete={() => removeComment(comment)}
                              />
                              {repliesFor(comment.id).length > 0 && (
                                <ul className="mt-2 space-y-2 border-l border-[#ded7ca] pl-4">
                                  {repliesFor(comment.id).map((reply) => (
                                    <li key={reply.id}>
                                      <CommentRow
                                        comment={reply}
                                        currentUserId={currentUserId}
                                        canModerate={isEditor}
                                        readOnly={readOnly}
                                        onEdit={() => editComment(reply)}
                                        onDelete={() => removeComment(reply)}
                                      />
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}

                      {permissions?.can_comment && !readOnly ? (
                        <form
                          onSubmit={submitComment}
                          className="mt-4 border-t border-[#ded7ca] pt-4"
                        >
                          {replyTo && (
                            <div className="mb-2 flex items-center justify-between text-[10px] text-[#9b4a36]">
                              <span>
                                Replying to{' '}
                                {comments.find((item) => item.id === replyTo)
                                  ?.author_display_name ?? 'comment'}
                              </span>
                              <button
                                type="button"
                                onClick={() => setReplyTo(null)}
                                className="underline"
                              >
                                Cancel reply
                              </button>
                            </div>
                          )}
                          <textarea
                            value={commentBody}
                            onChange={(event) =>
                              setCommentBody(event.target.value)
                            }
                            rows={3}
                            maxLength={5000}
                            placeholder={
                              replyTo
                                ? 'Write a reply…'
                                : 'Leave a comment for the chroniclers…'
                            }
                            className="w-full rounded-sm border border-[#d5cebf] bg-white px-3 py-2 text-xs"
                          />
                          <button
                            type="submit"
                            disabled={
                              createComment.isPending || !commentBody.trim()
                            }
                            className="ww-button mt-2 bg-[#294238] px-3.5 py-1.5 text-[11px] font-semibold text-[#f7f2e7] hover:bg-[#38574a] disabled:opacity-50"
                          >
                            {createComment.isPending
                              ? 'Posting…'
                              : replyTo
                                ? 'Post reply'
                                : 'Post comment'}
                          </button>
                        </form>
                      ) : (
                        <p className="mt-4 border-t border-[#ded7ca] pt-3 text-[11px] text-[#899087]">
                          Your role can read this thread but cannot comment.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function DocumentTreeBranch({
  nodes,
  depth,
  expanded,
  selectedId,
  canCreate,
  onToggle,
  onSelect,
  onCreateChild,
}: {
  nodes: DocumentTreeNode[];
  depth: number;
  expanded: Set<string>;
  selectedId: string | null;
  canCreate: boolean;
  onToggle: (id: string) => void;
  onSelect: (id: string) => void;
  onCreateChild: (node: DocumentTreeNode) => void;
}) {
  return (
    <ul className={depth === 0 ? 'space-y-0.5' : 'space-y-0.5'}>
      {nodes.map((node) => {
        const Icon = TYPE_ICON[node.document_type] ?? FileText;
        const isOpen = expanded.has(node.id);
        const isSelected = node.id === selectedId;
        return (
          <li key={node.id}>
            <div
              className={`group flex items-center gap-1 rounded-sm pr-1 ${
                isSelected
                  ? 'bg-[#294238] text-[#f7f2e7]'
                  : 'text-[#33483e] hover:bg-[#e8e1d4]'
              }`}
            >
              <button
                type="button"
                onClick={() => onToggle(node.id)}
                className={`flex h-7 w-5 shrink-0 items-center justify-center ${
                  node.children.length === 0 ? 'invisible' : ''
                }`}
                aria-label={isOpen ? 'Collapse' : 'Expand'}
              >
                {isOpen ? (
                  <ChevronDown size={12} />
                ) : (
                  <ChevronRight size={12} />
                )}
              </button>
              <button
                type="button"
                onClick={() => onSelect(node.id)}
                className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 text-left text-[11px]"
                style={{ paddingLeft: depth === 0 ? 0 : 2 }}
              >
                <Icon size={12} className="shrink-0 opacity-70" />
                <span className="truncate">{node.title}</span>
              </button>
              {canCreate && ALLOWED_CHILD_TYPES[node.document_type].length > 0 && (
                <button
                  type="button"
                  onClick={() => onCreateChild(node)}
                  className={`hidden shrink-0 p-1 group-hover:block ${
                    isSelected
                      ? 'text-[#f7f2e7] hover:text-white'
                      : 'text-[#899087] hover:text-[#9b4a36]'
                  }`}
                  title="Add child document"
                >
                  <Plus size={11} />
                </button>
              )}
            </div>
            {isOpen && node.children.length > 0 && (
              <div className="ml-3 border-l border-[#ded7ca] pl-1">
                <DocumentTreeBranch
                  nodes={node.children}
                  depth={depth + 1}
                  expanded={expanded}
                  selectedId={selectedId}
                  canCreate={canCreate}
                  onToggle={onToggle}
                  onSelect={onSelect}
                  onCreateChild={onCreateChild}
                />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function CommentRow({
  comment,
  currentUserId,
  canModerate,
  readOnly,
  onReply,
  onEdit,
  onDelete,
}: {
  comment: CommentResponse;
  currentUserId?: string;
  canModerate: boolean;
  readOnly: boolean;
  onReply?: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const own = comment.created_by === currentUserId;
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold text-[#253a32]">
          {comment.author_display_name}
          {own && (
            <span className="ml-1.5 rounded bg-[#ded7ca]/60 px-1 py-0.5 text-[8px] uppercase tracking-wide text-[#53655b]">
              you
            </span>
          )}
        </span>
        <span className="text-[9px] text-[#899087]">
          {new Date(comment.created_at).toLocaleString()}
          {comment.edited_at ? ' · edited' : ''}
        </span>
      </div>
      <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-[#33483e]">
        {comment.body}
      </p>
      {!readOnly && (
        <div className="mt-1 flex items-center gap-3 text-[10px] text-[#899087]">
          {onReply && (
            <button
              type="button"
              onClick={onReply}
              className="hover:text-[#9b4a36]"
            >
              Reply
            </button>
          )}
          {(own || canModerate) && (
            <button
              type="button"
              onClick={onEdit}
              className="inline-flex items-center gap-0.5 hover:text-[#9b4a36]"
            >
              <Pencil size={9} /> Edit
            </button>
          )}
          {(own || canModerate) && (
            <button
              type="button"
              onClick={onDelete}
              className="inline-flex items-center gap-0.5 hover:text-[#9b4a36]"
            >
              <Trash2 size={9} /> Delete
            </button>
          )}
        </div>
      )}
    </div>
  );
}
