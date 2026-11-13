import { useState, useMemo, useRef, useEffect } from 'react';
import { useLocation, useRoute } from 'wouter';
import {
  useGetUniverse,
  useUpdateUniverse,
  useArchiveUniverse,
  useListUniverseMembers,
  useUpdateMemberRole,
  useRemoveMember,
  useCreateInvitation,
  useListAuditLogs,
  useListActivity,
  useListEntityTypes,
  useListEntities,
  useCreateEntity,
  useUpdateEntity,
  useDeleteEntity,
  useRestoreEntity,
  useListRelationTypes,
  useListEntityRelations,
  useCreateEntityRelation,
  useDeleteEntityRelation,
  useGetNexusGraph,
  useSearchUniverse,
  type MemberResponse,
  type EntityResponse,
  type EntityTypeResponse,
  type RelationTypeResponse,
} from '@workspace/api-client-react';
import {
  ArrowLeft,
  BookOpen,
  Check,
  Clock3,
  Copy,
  Crown,
  Filter,
  Globe,
  Layers,
  Lock,
  MapPin,
  Network,
  Plus,
  RefreshCw,
  Search,
  ScrollText,
  Share2,
  Shield,
  Tag as TagIcon,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { UniverseChronicle } from '@/pages/UniverseChronicle';
import AtlasChronos from '@/pages/AtlasChronos';
import { DataPortability } from '@/components/data-portability';

export default function UniverseDetail() {
  const [, params] = useRoute('/universes/:id');
  const [, setLocation] = useLocation();
  const queryClient = useQueryClient();
  const universeId = params?.id || '';

  const [activeTab, setActiveTab] = useState<'overview' | 'codex' | 'chronicle' | 'nexus' | 'atlas' | 'chronos' | 'society' | 'audit' | 'settings'>('overview');
  const [globalSearchQuery, setGlobalSearchQuery] = useState('');
  const [globalSearchPage, setGlobalSearchPage] = useState(0);
  const [openDocumentId, setOpenDocumentId] = useState<string | null>(null);
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Queries
  const { data: universe, isLoading: loadingUniverse, error: universeError } = useGetUniverse(universeId);
  const { data: members, refetch: refetchMembers } = useListUniverseMembers(universeId);
  const { data: auditLogs, refetch: refetchAudit } = useListAuditLogs(universeId);
  const { data: activity, refetch: refetchActivity } = useListActivity(universeId);
  const searchResults = useSearchUniverse(
    universeId,
    { q: globalSearchQuery.trim(), limit: 8, offset: globalSearchPage * 8 },
    { query: { enabled: globalSearchQuery.trim().length >= 2 } },
  );
  const [pageSearchVisible, setPageSearchVisible] = useState(false);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPageSearchVisible(true);
        window.setTimeout(() => document.getElementById('universe-global-search')?.focus(), 0);
      }
      if (event.key === 'Escape') setPageSearchVisible(false);
    };
    window.addEventListener('keydown', handleShortcut);
    return () => window.removeEventListener('keydown', handleShortcut);
  }, []);

  // Codex & Nexus Queries
  const { data: entityTypes } = useListEntityTypes(universeId);
  const { data: relationTypes } = useListRelationTypes(universeId);
  const [selectedTypeFilter, setSelectedTypeFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const { data: entitiesData, refetch: refetchEntities } = useListEntities(universeId, {
    type: selectedTypeFilter === 'all' ? undefined : selectedTypeFilter,
    q: searchQuery.trim() || undefined,
  });

  // Graph state
  const [graphFocusNode, setGraphFocusNode] = useState<string | undefined>(undefined);
  const [graphDepth, setGraphDepth] = useState<number>(1);
  const { data: graphData, refetch: refetchGraph } = useGetNexusGraph(universeId, {
    focus_entity_id: graphFocusNode,
    depth: graphDepth,
  });

  // Selected entity for detail panel
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const selectedEntity = useMemo(() => {
    return entitiesData?.items.find((e: EntityResponse) => e.id === selectedEntityId) || null;
  }, [entitiesData, selectedEntityId]);

  const { data: selectedEntityRelations, refetch: refetchSelectedRelations } = useListEntityRelations(
    universeId,
    selectedEntityId || '',
    { query: { enabled: Boolean(selectedEntityId) } }
  );

  // Entity mutations
  const createEntity = useCreateEntity();
  const updateEntity = useUpdateEntity();
  const deleteEntity = useDeleteEntity();
  const restoreEntity = useRestoreEntity();
  const createRelation = useCreateEntityRelation();
  const deleteRelation = useDeleteEntityRelation();

  // Universe & Society mutations
  const updateUniverse = useUpdateUniverse();
  const archiveUniverse = useArchiveUniverse();
  const updateMemberRole = useMemberRoleMutation();
  const removeMember = useRemoveMemberMutation();
  const createInvitation = useCreateInvitationMutation();

  function useMemberRoleMutation() {
    return useUpdateMemberRole();
  }
  function useRemoveMemberMutation() {
    return useRemoveMember();
  }
  function useCreateInvitationMutation() {
    return useCreateInvitation();
  }

  // Modals & local state
  const [showCreateEntityModal, setShowCreateEntityModal] = useState(false);
  const [newEntityTitle, setNewEntityTitle] = useState('');
  const [newEntityTypeKey, setNewEntityTypeKey] = useState('character');
  const [newEntitySummary, setNewEntitySummary] = useState('');
  const [newEntityTags, setNewEntityTags] = useState('');

  // Relation modal
  const [showAddRelationModal, setShowAddRelationModal] = useState(false);
  const [relTargetId, setRelTargetId] = useState('');
  const [relTypeKey, setRelTypeKey] = useState('');

  // Society state
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'admin' | 'editor' | 'contributor' | 'viewer'>('viewer');
  const [generatedInviteToken, setGeneratedInviteToken] = useState<string | null>(null);
  const [copiedInvite, setCopiedInvite] = useState(false);

  // Settings state
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [isEditingSettings, setIsEditingSettings] = useState(false);

  // Editing entity state
  const [isEditingEntity, setIsEditingEntity] = useState(false);
  const [editEntityTitle, setEditEntityTitle] = useState('');
  const [editEntitySummary, setEditEntitySummary] = useState('');

  if (loadingUniverse) {
    return (
      <div className="mx-auto max-w-[1240px] px-5 py-16">
        <div className="h-6 w-32 animate-pulse bg-[#ddd5c6]" />
        <div className="mt-6 h-12 max-w-md animate-pulse bg-[#e4ddce]" />
        <div className="mt-8 h-64 animate-pulse bg-[#faf7ef]" />
      </div>
    );
  }

  if (universeError || !universe) {
    return (
      <div className="mx-auto max-w-[900px] px-5 py-20">
        <p className="ww-kicker text-[#9b4a36]">Access Denied or Not Found</p>
        <h1 className="ww-display mt-3 text-4xl text-[#263b32]">Universe Not Found</h1>
        <p className="mt-4 text-[#657168]">You may not have permission to access this universe, or it has been removed.</p>
        <button
          onClick={() => setLocation('/')}
          className="ww-button mt-6 inline-flex items-center gap-2 border border-[#294238] px-4 py-2 text-xs font-semibold text-[#294238] hover:bg-[#294238] hover:text-[#f7f2e7]"
        >
          <ArrowLeft size={14} /> Return Home
        </button>
      </div>
    );
  }

  const isOwner = universe.role === 'owner';
  const isAdminOrOwner = isOwner || universe.role === 'admin';
  const canEdit = isAdminOrOwner || universe.role === 'editor';

  // Handle Create Entity
  const handleCreateEntity = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEntityTitle.trim()) return;
    try {
      const tagsList = newEntityTags.split(',').map((t) => t.trim()).filter(Boolean);
      const res = await createEntity.mutateAsync({
        universeId,
        data: {
          entity_type_key: newEntityTypeKey,
          title: newEntityTitle.trim(),
          summary: newEntitySummary.trim() || undefined,
          tags: tagsList,
        },
      });
      await refetchEntities();
      setShowCreateEntityModal(false);
      setNewEntityTitle('');
      setNewEntitySummary('');
      setNewEntityTags('');
      setSelectedEntityId(res.id);
      setFeedbackMsg({ type: 'success', text: `Created entity "${res.title}" in Codex.` });
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err?.data?.error?.message || 'Failed to create entity.' });
    }
  };

  // Handle Save Entity Update (Optimistic Concurrency)
  const handleUpdateEntity = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEntity) return;
    try {
      await updateEntity.mutateAsync({
        universeId,
        entityId: selectedEntity.id,
        data: {
          title: editEntityTitle.trim() || selectedEntity.title,
          summary: editEntitySummary.trim() || selectedEntity.summary,
          expected_version: selectedEntity.version,
        },
      });
      await refetchEntities();
      setIsEditingEntity(false);
      setFeedbackMsg({ type: 'success', text: 'Entity updated successfully.' });
    } catch (err: any) {
      setFeedbackMsg({
        type: 'error',
        text: err?.data?.error?.code === 'version_conflict'
          ? 'Conflict: This entity was updated by someone else. Please refresh and try again.'
          : err?.data?.error?.message || 'Failed to update entity.',
      });
    }
  };

  // Handle Delete Entity
  const handleDeleteEntity = async (entityId: string) => {
    if (!confirm('Are you sure you want to delete this entity? (It can be restored later)')) return;
    try {
      await deleteEntity.mutateAsync({ universeId, entityId });
      await refetchEntities();
      setSelectedEntityId(null);
      setFeedbackMsg({ type: 'success', text: 'Entity moved to trash.' });
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err?.data?.error?.message || 'Failed to delete entity.' });
    }
  };

  // Handle Add Relation
  const handleAddRelation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEntity || !relTargetId || !relTypeKey) return;
    try {
      await createRelation.mutateAsync({
        universeId,
        data: {
          source_entity_id: selectedEntity.id,
          relation_type_key: relTypeKey,
          target_entity_id: relTargetId,
        },
      });
      await refetchSelectedRelations();
      setShowAddRelationModal(false);
      setRelTargetId('');
      setRelTypeKey('');
      setFeedbackMsg({ type: 'success', text: 'Directed relation established.' });
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err?.data?.error?.message || 'Failed to establish relation.' });
    }
  };

  // Handle Delete Relation
  const handleDeleteRelation = async (relationId: string) => {
    try {
      await deleteRelation.mutateAsync({ universeId, relationId });
      await refetchSelectedRelations();
      setFeedbackMsg({ type: 'success', text: 'Relation deleted.' });
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err?.data?.error?.message || 'Failed to delete relation.' });
    }
  };

  // Handle Member Invite
  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    try {
      const res = await createInvitation.mutateAsync({
        universeId,
        data: { email: inviteEmail.trim(), role: inviteRole },
      });
      if (res.invitation_token) setGeneratedInviteToken(res.invitation_token);
      setInviteEmail('');
      setFeedbackMsg({ type: 'success', text: `Invitation generated for ${inviteEmail}` });
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err?.data?.error?.message || 'Failed to invite.' });
    }
  };

  // Handle Member Role Update
  const handleRoleChange = async (targetUserId: string, newRole: string) => {
    try {
      await updateMemberRole.mutateAsync({
        universeId,
        userId: targetUserId,
        data: { role: newRole as any },
      });
      await refetchMembers();
      setFeedbackMsg({ type: 'success', text: 'Member role updated.' });
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err?.data?.error?.message || 'Failed to update role.' });
    }
  };

  // Handle Remove Member
  const handleRemoveMember = async (targetUserId: string) => {
    if (!confirm('Are you sure you want to remove this member?')) return;
    try {
      await removeMember.mutateAsync({ universeId, userId: targetUserId });
      await refetchMembers();
      setFeedbackMsg({ type: 'success', text: 'Member removed from universe.' });
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err?.data?.error?.message || 'Failed to remove member.' });
    }
  };

  return (
    <div className="mx-auto max-w-[1240px] px-5 py-8 sm:px-8 lg:px-12">
      {/* Back button & status banner */}
      <div className="mb-6 flex items-center justify-between">
        <button
          onClick={() => setLocation('/')}
          className="inline-flex items-center gap-2 text-xs font-semibold text-[#53655b] hover:text-[#9b4a36]"
          data-testid="link-back-universes"
        >
          <ArrowLeft size={14} /> Back to all universes
        </button>
        <div className="flex items-center gap-2">
          <span className="rounded bg-[#ded7ca]/60 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-[#48574d]">
            {universe.status}
          </span>
          <span className="inline-flex items-center gap-1 rounded bg-[#294238]/10 px-2.5 py-0.5 text-[11px] font-semibold text-[#294238]">
            <Crown size={12} className="text-[#a4523b]" /> {universe.role}
          </span>
        </div>
      </div>

      {feedbackMsg && (
        <div
          role="alert"
          className={`mb-6 border-l-4 p-3 text-xs ${
            feedbackMsg.type === 'success'
              ? 'border-[#64856b] bg-[#eef4ef] text-[#2e4c35]'
              : 'border-[#a4523b] bg-[#fdf2ef] text-[#7d3e30]'
          }`}
        >
          {feedbackMsg.text}
        </div>
      )}

      {/* Universe Title Banner */}
      <div className="border-b border-[#d8d0c1] pb-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <p className="ww-kicker text-[#9b4a36]">Folio / {universe.slug}</p>
            <h1 className="ww-display mt-2 text-4xl text-[#263b32] sm:text-5xl" data-testid="text-universe-title">
              {universe.name}
            </h1>
            {universe.description && (
              <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[#657168]">{universe.description}</p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <span className="ww-kicker text-[10px] text-[#788078]">
              Created: {new Date(universe.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>

        <section className="relative mt-5" data-testid="universe-search">
          <div className="flex items-center gap-2">
            <Search size={15} className="text-[#9b4a36]" />
            <label className="sr-only" htmlFor="universe-global-search">Search this universe</label>
            <input id="universe-global-search" className="w-full max-w-lg rounded border border-[#d5cebf] bg-[#faf7ef] px-3 py-2 text-xs text-[#253a32] focus:border-[#9b4a36] focus:outline-none" placeholder="Search Codex, Chronicle and Chronos… (Ctrl/⌘ K)" value={globalSearchQuery} onFocus={() => setPageSearchVisible(true)} onChange={(event) => { setGlobalSearchQuery(event.target.value); setGlobalSearchPage(0); setPageSearchVisible(true); }} data-testid="input-universe-global-search" />
            <kbd className="hidden rounded border border-[#d9d1c2] px-1.5 py-1 text-[10px] text-[#788078] sm:inline">Ctrl / ⌘ K</kbd>
          </div>
          {pageSearchVisible && globalSearchQuery.trim().length >= 2 && (
            <div className="absolute z-30 mt-2 w-full max-w-2xl border border-[#d9d1c2] bg-[#fffdf7] p-3 shadow-xl" role="region" aria-label="Search results" data-testid="universe-search-results">
              {searchResults.isLoading ? <p className="p-3 text-xs text-[#788078]">Searching this universe…</p> : <>
                <p className="px-2 pb-2 text-[10px] text-[#788078]" aria-live="polite">{searchResults.data?.total ?? 0} authorized results</p>
                <ul className="max-h-[55vh] divide-y divide-[#e2dccf] overflow-y-auto">
                  {(searchResults.data?.items ?? []).map((result) => <li key={`${result.kind}:${result.id}`}><button type="button" className="w-full px-2 py-3 text-left hover:bg-[#f3eee2] focus:bg-[#f3eee2] focus:outline-none" onClick={() => { setPageSearchVisible(false); if (result.kind === 'entity') { setActiveTab('codex'); setSelectedEntityId(result.id); } else if (result.kind === 'document') { setOpenDocumentId(result.id); setActiveTab('chronicle'); } else setActiveTab('chronos'); }}>
                    <span className="ww-kicker text-[9px] text-[#9b4a36]">{result.kind.replace('_', ' ')}</span><span className="ml-2 text-xs font-semibold text-[#34473d]">{result.title}</span>
                    <span className="mt-1 block text-[11px] text-[#657168]">{result.snippet.slice(0, result.highlight_start)}<mark className="bg-[#f1dca8] text-[#34473d]">{result.snippet.slice(result.highlight_start, result.highlight_end)}</mark>{result.snippet.slice(result.highlight_end)}</span>
                  </button></li>)}
                  {searchResults.data?.items.length === 0 && <li className="p-3 text-xs text-[#788078]">No matching content found.</li>}
                </ul>
                {(searchResults.data?.total ?? 0) > 8 && <div className="mt-3 flex items-center justify-between border-t border-[#e2dccf] pt-3"><button type="button" className="border border-[#c9c1b2] px-2 py-1 text-xs disabled:opacity-40" disabled={globalSearchPage === 0} onClick={() => setGlobalSearchPage((page) => Math.max(0, page - 1))}>Previous</button><span className="text-[10px] text-[#788078]">Page {globalSearchPage + 1} of {Math.ceil((searchResults.data?.total ?? 0) / 8)}</span><button type="button" className="border border-[#c9c1b2] px-2 py-1 text-xs disabled:opacity-40" disabled={(globalSearchPage + 1) * 8 >= (searchResults.data?.total ?? 0)} onClick={() => setGlobalSearchPage((page) => page + 1)}>Next</button></div>}
              </>}
            </div>
          )}
        </section>

        {/* Tab Navigation */}
        <div className="mt-8 flex flex-wrap gap-5 border-b border-[#e2dccf] text-sm">
          {[
            { id: 'overview', label: 'Overview', icon: Globe },
            { id: 'codex', label: 'Codex (Entities)', icon: BookOpen },
            { id: 'chronicle', label: 'Chronicle', icon: ScrollText },
            { id: 'nexus', label: 'Nexus (Graph)', icon: Network },
            { id: 'atlas', label: 'Atlas', icon: MapPin },
            { id: 'chronos', label: 'Chronos', icon: Clock3 },
            { id: 'society', label: 'Society & Members', icon: Users },
            { id: 'audit', label: 'Audit Trail', icon: Shield },
            { id: 'settings', label: 'Settings', icon: Lock },
          ].map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 border-b-2 pb-2.5 text-xs font-semibold tracking-wide transition-colors ${
                  active
                    ? 'border-[#9b4a36] text-[#9b4a36]'
                    : 'border-transparent text-[#6e786f] hover:text-[#253a32]'
                }`}
                data-testid={`tab-${tab.id}`}
              >
                <Icon size={14} /> {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Contents */}
      <div className="mt-8">
        {/* TAB 1: OVERVIEW */}
        {activeTab === 'overview' && (
          <div className="space-y-8">
            <div className="grid gap-5 sm:grid-cols-4">
              <div className="border border-[#d9d1c2] bg-[#faf7ef] p-5">
                <span className="ww-kicker text-[#899087]">Codex Entries</span>
                <p className="ww-display mt-2 text-3xl text-[#253a32]">{entitiesData?.total || 0}</p>
                <p className="mt-1 text-[11px] text-[#657168]">Canonical entities cataloged</p>
              </div>
              <div className="border border-[#d9d1c2] bg-[#faf7ef] p-5">
                <span className="ww-kicker text-[#899087]">Entity Types</span>
                <p className="ww-display mt-2 text-3xl text-[#253a32]">{entityTypes?.length || 0}</p>
                <p className="mt-1 text-[11px] text-[#657168]">System & custom schemas</p>
              </div>
              <div className="border border-[#d9d1c2] bg-[#faf7ef] p-5">
                <span className="ww-kicker text-[#899087]">Collaborators</span>
                <p className="ww-display mt-2 text-3xl text-[#253a32]">{(members as MemberResponse[])?.length || 1}</p>
                <p className="mt-1 text-[11px] text-[#657168]">Enrolled members</p>
              </div>
              <div className="border border-[#d9d1c2] bg-[#faf7ef] p-5">
                <span className="ww-kicker text-[#899087]">Your Authority</span>
                <p className="ww-display mt-2 text-3xl capitalize text-[#9b4a36]">{universe.role}</p>
                <p className="mt-1 text-[11px] text-[#657168]">
                  {isOwner ? 'Full sovereign control' : 'Role-based access'}
                </p>
              </div>
            </div>

            {/* Modules Directory */}
            <div className="border border-[#d9d1c2] bg-[#faf7ef] p-6">
              <p className="ww-kicker mb-3 text-[#9b4a36]">Archive Modules</p>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div
                  onClick={() => setActiveTab('codex')}
                  className="cursor-pointer border border-[#ded7ca] bg-white/60 p-4 transition-all hover:border-[#9b4a36]"
                >
                  <h3 className="font-serif text-lg text-[#253a32]">Codex</h3>
                  <p className="mt-1 text-xs text-[#6e786f]">Typed encyclopedia, custom fields & directed relations.</p>
                  <span className="mt-3 inline-block rounded bg-[#64856b]/20 px-2 py-0.5 text-[10px] font-semibold text-[#294238]">Active · M3</span>
                </div>
                <div
                  onClick={() => setActiveTab('nexus')}
                  className="cursor-pointer border border-[#ded7ca] bg-white/60 p-4 transition-all hover:border-[#9b4a36]"
                >
                  <h3 className="font-serif text-lg text-[#253a32]">Nexus</h3>
                  <p className="mt-1 text-xs text-[#6e786f]">Interactive knowledge graph & depth traversal.</p>
                  <span className="mt-3 inline-block rounded bg-[#64856b]/20 px-2 py-0.5 text-[10px] font-semibold text-[#294238]">Active · M3</span>
                </div>
                <div
                  onClick={() => setActiveTab('chronicle')}
                  className="cursor-pointer border border-[#ded7ca] bg-white/60 p-4 transition-all hover:border-[#9b4a36]"
                >
                  <h3 className="font-serif text-lg text-[#253a32]">Chronicle</h3>
                  <p className="mt-1 text-xs text-[#6e786f]">Hierarchical narratives, TipTap & cross-linking.</p>
                  <span className="mt-3 inline-block rounded bg-[#64856b]/20 px-2 py-0.5 text-[10px] font-semibold text-[#294238]">Active · M4</span>
                </div>
                <div className="border border-[#ded7ca] bg-white/60 p-4">
                  <h3 className="font-serif text-lg text-[#253a32]">Atlas & Chronos</h3>
                  <p className="mt-1 text-xs text-[#6e786f]">Normalized maps, POIs & fictional calendars.</p>
                  <span className="mt-3 inline-block rounded bg-[#64856b]/20 px-2 py-0.5 text-[10px] font-semibold text-[#294238]">Active · M6</span>
                </div>
              </div>
            </div>

            {/* Activity Feed */}
            <div className="border border-[#d9d1c2] bg-[#faf7ef] p-6">
              <p className="ww-kicker mb-4 text-[#9b4a36]">Chronological Activity</p>
              {activity && activity.length > 0 ? (
                <ul className="divide-y divide-[#ded7ca]">
                  {activity.map((act) => (
                    <li key={act.id} className="py-3 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-[#253a32]">{act.event_type}</span>
                        <span className="text-[#899087]">{new Date(act.created_at).toLocaleTimeString()}</span>
                      </div>
                      <p className="mt-1 text-[#657168]">
                        Target: {act.target_type} ({act.target_id || 'universe'})
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-[#899087]">No recent events recorded in this universe.</p>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: CODEX (ENTITIES & RELATIONS) */}
        {activeTab === 'codex' && (
          <div className="space-y-6">
            {/* Top Toolbar */}
            <div className="flex flex-col justify-between gap-4 border border-[#d9d1c2] bg-[#faf7ef] p-4 sm:flex-row sm:items-center">
              <div className="flex flex-wrap items-center gap-3">
                {/* Search */}
                <div className="relative w-64">
                  <Search size={14} className="absolute left-2.5 top-2.5 text-[#899087]" />
                  <input
                    type="text"
                    placeholder="Search Codex…"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full rounded border border-[#d5cebf] bg-white pl-8 pr-3 py-1.5 text-xs text-[#253a32] focus:border-[#9b4a36] focus:outline-none"
                    data-testid="input-search-codex"
                  />
                </div>

                {/* Type Filter */}
                <select
                  value={selectedTypeFilter}
                  onChange={(e) => setSelectedTypeFilter(e.target.value)}
                  className="rounded border border-[#d5cebf] bg-white px-2.5 py-1.5 text-xs text-[#253a32] focus:border-[#9b4a36] focus:outline-none"
                  data-testid="select-type-filter"
                >
                  <option value="all">All Entity Types</option>
                  {entityTypes?.map((et: EntityTypeResponse) => (
                    <option key={et.key} value={et.key}>
                      {et.name}
                    </option>
                  ))}
                </select>
              </div>

              {canEdit && (
                <button
                  onClick={() => setShowCreateEntityModal(true)}
                  className="ww-button inline-flex items-center gap-1.5 bg-[#294238] px-3.5 py-2 text-xs font-semibold text-[#f7f2e7] hover:bg-[#38574a]"
                  data-testid="button-open-create-entity"
                >
                  <Plus size={14} /> New Codex Entry
                </button>
              )}
            </div>

            {/* Modal: Create Entity */}
            {showCreateEntityModal && (
              <div className="rounded border border-[#d8d0c1] bg-[#faf7ef] p-6 shadow-md">
                <div className="flex items-center justify-between border-b border-[#ded7ca] pb-3">
                  <h3 className="font-serif text-xl text-[#253a32]">Create Codex Entity</h3>
                  <button onClick={() => setShowCreateEntityModal(false)} className="text-xs text-[#788078] hover:text-black">Cancel</button>
                </div>
                <form onSubmit={handleCreateEntity} className="mt-4 space-y-4 max-w-xl" data-testid="form-create-entity">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-[#48574d]">Entity Type</label>
                      <select
                        value={newEntityTypeKey}
                        onChange={(e) => setNewEntityTypeKey(e.target.value)}
                        className="mt-1 w-full rounded border border-[#d5cebf] bg-white px-3 py-2 text-xs text-[#253a32]"
                        data-testid="select-entity-type"
                      >
                        {entityTypes?.map((et: EntityTypeResponse) => (
                          <option key={et.key} value={et.key}>
                            {et.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-[#48574d]">Title</label>
                      <input
                        type="text"
                        required
                        placeholder="e.g. Citadel of Sun"
                        value={newEntityTitle}
                        onChange={(e) => setNewEntityTitle(e.target.value)}
                        className="mt-1 w-full rounded border border-[#d5cebf] bg-white px-3 py-2 text-xs text-[#253a32]"
                        data-testid="input-entity-title"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-[#48574d]">Summary</label>
                    <textarea
                      rows={2}
                      placeholder="Brief overview of canonical lore…"
                      value={newEntitySummary}
                      onChange={(e) => setNewEntitySummary(e.target.value)}
                      className="mt-1 w-full rounded border border-[#d5cebf] bg-white px-3 py-2 text-xs text-[#253a32]"
                      data-testid="input-entity-summary"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-[#48574d]">Tags (comma separated)</label>
                    <input
                      type="text"
                      placeholder="ancient, magic, solar"
                      value={newEntityTags}
                      onChange={(e) => setNewEntityTags(e.target.value)}
                      className="mt-1 w-full rounded border border-[#d5cebf] bg-white px-3 py-2 text-xs text-[#253a32]"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={createEntity.isPending}
                    className="ww-button bg-[#294238] px-4 py-2 text-xs font-semibold text-[#f7f2e7] hover:bg-[#38574a]"
                    data-testid="button-submit-create-entity"
                  >
                    {createEntity.isPending ? 'Cataloging…' : 'Record Entity'}
                  </button>
                </form>
              </div>
            )}

            {/* Split View: Entities List + Entity Detail Panel */}
            <div className="grid gap-6 lg:grid-cols-[1fr_1.3fr]">
              {/* Entities List */}
              <div className="space-y-3">
                {entitiesData?.items && entitiesData.items.length > 0 ? (
                  entitiesData.items.map((entity: EntityResponse) => {
                    const isSelected = entity.id === selectedEntityId;
                    return (
                      <div
                        key={entity.id}
                        onClick={() => {
                          setSelectedEntityId(entity.id);
                          setIsEditingEntity(false);
                        }}
                        className={`cursor-pointer border p-4 transition-all ${
                          isSelected
                            ? 'border-[#9b4a36] bg-[#faf7ef] shadow-sm'
                            : 'border-[#ded7ca] bg-white/70 hover:border-[#b8aa8d]'
                        }`}
                        data-testid={`entity-card-${entity.id}`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="rounded bg-[#294238]/10 px-2 py-0.5 text-[10px] font-semibold text-[#294238] capitalize">
                            {entity.entity_type_name}
                          </span>
                          <span className="ww-kicker text-[10px] text-[#899087]">v{entity.version}</span>
                        </div>
                        <h4 className="font-serif mt-1.5 text-lg font-medium text-[#253a32]">{entity.title}</h4>
                        {entity.summary && (
                          <p className="mt-1 line-clamp-2 text-xs text-[#657168]">{entity.summary}</p>
                        )}
                        {entity.tags && entity.tags.length > 0 && (
                          <div className="mt-2.5 flex flex-wrap gap-1">
                            {entity.tags.map((tag) => (
                              <span key={tag} className="rounded bg-[#ded7ca]/40 px-1.5 py-0.5 text-[9px] text-[#53655b]">
                                #{tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })
                ) : (
                  <div className="border border-[#ded7ca] bg-[#faf7ef] p-8 text-center text-xs text-[#899087]">
                    No entities found matching filters.
                  </div>
                )}
              </div>

              {/* Entity Detail Panel */}
              <div className="border border-[#d9d1c2] bg-[#faf7ef] p-6">
                {selectedEntity ? (
                  <div className="space-y-6">
                    <div className="flex items-start justify-between border-b border-[#ded7ca] pb-4">
                      <div>
                        <span className="rounded bg-[#294238]/10 px-2 py-0.5 text-[10px] font-semibold text-[#294238] capitalize">
                          {selectedEntity.entity_type_name}
                        </span>
                        {isEditingEntity ? (
                          <input
                            type="text"
                            value={editEntityTitle}
                            onChange={(e) => setEditEntityTitle(e.target.value)}
                            className="mt-2 block w-full rounded border border-[#d5cebf] bg-white px-3 py-1.5 font-serif text-2xl text-[#253a32]"
                          />
                        ) : (
                          <h2 className="font-serif mt-2 text-3xl text-[#253a32]">{selectedEntity.title}</h2>
                        )}
                        <span className="mt-1 block font-mono text-[10px] text-[#899087]">slug: {selectedEntity.slug}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {canEdit && !isEditingEntity && (
                          <button
                            onClick={() => {
                              setEditEntityTitle(selectedEntity.title);
                              setEditEntitySummary(selectedEntity.summary || '');
                              setIsEditingEntity(true);
                            }}
                            className="border border-[#c9c1b2] px-2.5 py-1 text-xs text-[#253a32] hover:bg-white"
                          >
                            Edit
                          </button>
                        )}
                        {canEdit && (
                          <button
                            onClick={() => handleDeleteEntity(selectedEntity.id)}
                            className="text-[#9b4a36] hover:text-[#7d3e30]"
                            title="Delete entity"
                          >
                            <Trash2 size={15} />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Summary / Body */}
                    <div>
                      <h4 className="ww-kicker text-[#899087]">Lore Summary</h4>
                      {isEditingEntity ? (
                        <div className="mt-2 space-y-3">
                          <textarea
                            rows={3}
                            value={editEntitySummary}
                            onChange={(e) => setEditEntitySummary(e.target.value)}
                            className="w-full rounded border border-[#d5cebf] bg-white px-3 py-2 text-xs text-[#253a32]"
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={handleUpdateEntity}
                              disabled={updateEntity.isPending}
                              className="ww-button bg-[#294238] px-3 py-1.5 text-xs font-semibold text-white"
                            >
                              Save Version
                            </button>
                            <button
                              onClick={() => setIsEditingEntity(false)}
                              className="border border-[#c9c1b2] px-3 py-1.5 text-xs text-[#53655b]"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <p className="mt-2 text-xs leading-relaxed text-[#33483e]">
                          {selectedEntity.summary || 'No summary entered.'}
                        </p>
                      )}
                    </div>

                    {/* Directed Relations Section */}
                    <div className="border-t border-[#ded7ca] pt-5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <Share2 size={14} className="text-[#9b4a36]" />
                          <h4 className="font-serif text-lg text-[#253a32]">Connected Relations</h4>
                        </div>
                        {canEdit && (
                          <button
                            onClick={() => setShowAddRelationModal(true)}
                            className="inline-flex items-center gap-1 border border-[#9b4a36] px-2 py-1 text-[11px] font-semibold text-[#9b4a36] hover:bg-[#9b4a36] hover:text-white"
                            data-testid="button-open-add-relation"
                          >
                            <Plus size={12} /> Add Relation
                          </button>
                        )}
                      </div>

                      {/* Modal: Add Relation */}
                      {showAddRelationModal && (
                        <form onSubmit={handleAddRelation} className="mt-4 rounded border border-[#ded7ca] bg-white/80 p-4 space-y-3" data-testid="form-add-relation">
                          <h5 className="font-semibold text-xs text-[#253a32]">Connect to Another Entity</h5>
                          <div className="grid grid-cols-2 gap-2">
                            <div>
                              <label className="block text-[11px] font-semibold text-[#48574d]">Relationship Type</label>
                              <select
                                required
                                value={relTypeKey}
                                onChange={(e) => setRelTypeKey(e.target.value)}
                                className="mt-1 w-full rounded border border-[#d5cebf] bg-white px-2 py-1.5 text-xs"
                                data-testid="select-relation-type"
                              >
                                <option value="">Select relation…</option>
                                {relationTypes?.map((rt: RelationTypeResponse) => (
                                  <option key={rt.key} value={rt.key}>
                                    {rt.label} ({rt.key})
                                  </option>
                                ))}
                              </select>
                            </div>
                            <div>
                              <label className="block text-[11px] font-semibold text-[#48574d]">Target Entity</label>
                              <select
                                required
                                value={relTargetId}
                                onChange={(e) => setRelTargetId(e.target.value)}
                                className="mt-1 w-full rounded border border-[#d5cebf] bg-white px-2 py-1.5 text-xs"
                                data-testid="select-relation-target"
                              >
                                <option value="">Select entity…</option>
                                {entitiesData?.items
                                  .filter((e: EntityResponse) => e.id !== selectedEntity.id)
                                  .map((e: EntityResponse) => (
                                    <option key={e.id} value={e.id}>
                                      {e.title} ({e.entity_type_name})
                                    </option>
                                  ))}
                              </select>
                            </div>
                          </div>
                          <div className="flex gap-2 pt-1">
                            <button
                              type="submit"
                              disabled={createRelation.isPending}
                              className="ww-button bg-[#294238] px-3 py-1.5 text-xs font-semibold text-white"
                              data-testid="button-submit-relation"
                            >
                              Create Link
                            </button>
                            <button
                              type="button"
                              onClick={() => setShowAddRelationModal(false)}
                              className="border border-[#c9c1b2] px-3 py-1.5 text-xs text-[#53655b]"
                            >
                              Cancel
                            </button>
                          </div>
                        </form>
                      )}

                      {/* Relations List */}
                      <div className="mt-3 space-y-2">
                        {selectedEntityRelations && selectedEntityRelations.length > 0 ? (
                          selectedEntityRelations.map((rel: any) => {
                            const isSource = rel.source_entity_id === selectedEntity.id;
                            return (
                              <div
                                key={rel.id}
                                className="flex items-center justify-between rounded border border-[#ded7ca] bg-white/60 p-2.5 text-xs"
                              >
                                <div>
                                  <span className="font-semibold text-[#9b4a36]">
                                    {isSource ? rel.relation_label : `(Inverse) ${rel.relation_label}`}
                                  </span>
                                  <span className="mx-2 text-[#899087]">→</span>
                                  <span
                                    onClick={() => setSelectedEntityId(isSource ? rel.target_entity_id : rel.source_entity_id)}
                                    className="cursor-pointer font-medium text-[#253a32] underline hover:text-[#9b4a36]"
                                  >
                                    {isSource ? rel.target_entity_title : rel.source_entity_title}
                                  </span>
                                </div>
                                {canEdit && (
                                  <button
                                    onClick={() => handleDeleteRelation(rel.id)}
                                    className="text-[#9b4a36] hover:text-[#7d3e30]"
                                    title="Unlink"
                                  >
                                    <Trash2 size={13} />
                                  </button>
                                )}
                              </div>
                            );
                          })
                        ) : (
                          <p className="text-xs text-[#899087]">No connected relations yet.</p>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="py-20 text-center text-xs text-[#899087]">
                    Select an entity from the left to view details and manage relations.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* TAB: CHRONICLE (DOCUMENTS) */}
        {activeTab === 'chronicle' && (
          <UniverseChronicle
            key={openDocumentId ?? 'chronicle-root'}
            universeId={universeId}
            role={universe.role as 'owner' | 'admin' | 'editor' | 'contributor' | 'viewer'}
            readOnly={universe.status === 'archived'}
            initialDocumentId={openDocumentId ?? undefined}
          />
        )}

        {/* TAB 3: NEXUS (KNOWLEDGE GRAPH) */}
        {activeTab === 'atlas' && <AtlasChronos universeId={universeId} canEdit={canEdit} initialView="atlas" />}
        {activeTab === 'chronos' && <AtlasChronos universeId={universeId} canEdit={canEdit} initialView="chronos" />}
        {activeTab === 'nexus' && (
          <div className="space-y-4">
            {/* Graph Controls */}
            <div className="flex flex-wrap items-center justify-between gap-3 border border-[#d9d1c2] bg-[#faf7ef] p-4 text-xs">
              <div className="flex flex-wrap items-center gap-4">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-[#48574d]">Focus Node:</span>
                  <select
                    value={graphFocusNode || ''}
                    onChange={(e) => setGraphFocusNode(e.target.value || undefined)}
                    className="rounded border border-[#d5cebf] bg-white px-2 py-1"
                    data-testid="select-graph-focus"
                  >
                    <option value="">Global View (All)</option>
                    {entitiesData?.items.map((e: EntityResponse) => (
                      <option key={e.id} value={e.id}>
                        {e.title}
                      </option>
                    ))}
                  </select>
                </div>
                {graphFocusNode && (
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-[#48574d]">Depth:</span>
                    <select
                      value={graphDepth}
                      onChange={(e) => setGraphDepth(Number(e.target.value))}
                      className="rounded border border-[#d5cebf] bg-white px-2 py-1"
                      data-testid="select-graph-depth"
                    >
                      <option value={1}>1 Degree</option>
                      <option value={2}>2 Degrees</option>
                      <option value={3}>3 Degrees (Max)</option>
                    </select>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="ww-kicker text-[#899087]">
                  {graphData?.nodes?.length || 0} nodes · {graphData?.edges?.length || 0} edges
                </span>
                <button
                  onClick={() => refetchGraph()}
                  className="rounded border border-[#c9c1b2] p-1 text-[#48574d] hover:bg-white"
                  title="Reload graph"
                >
                  <RefreshCw size={13} />
                </button>
              </div>
            </div>

            {/* Interactive Graph Canvas / SVG */}
            <div className="relative min-h-[500px] w-full rounded border border-[#d9d1c2] bg-[#fdfbf7] overflow-hidden flex items-center justify-center">
              <NexusGraphViewer
                nodes={graphData?.nodes || []}
                edges={graphData?.edges || []}
                onSelectNode={(id) => {
                  setSelectedEntityId(id);
                  setActiveTab('codex');
                }}
              />
            </div>
          </div>
        )}

        {/* TAB 4: SOCIETY & MEMBERS */}
        {activeTab === 'society' && (
          <div className="space-y-8">
            {isAdminOrOwner && (
              <div className="border border-[#d9d1c2] bg-[#faf7ef] p-6">
                <div className="flex items-center gap-2 border-b border-[#ded7ca] pb-3">
                  <UserPlus size={16} className="text-[#9b4a36]" />
                  <h2 className="font-serif text-xl text-[#253a32]">Invite Collaborator</h2>
                </div>
                <form onSubmit={handleInvite} className="mt-5 flex flex-wrap items-end gap-3" data-testid="form-invite-member">
                  <div className="flex-1 min-w-[240px]">
                    <label className="block text-xs font-semibold text-[#48574d]">Email Address</label>
                    <input
                      type="email"
                      required
                      placeholder="collaborator@example.com"
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      className="mt-1.5 w-full rounded-sm border border-[#d5cebf] bg-white px-3 py-2 text-xs text-[#253a32] focus:border-[#9b4a36] focus:outline-none"
                      data-testid="input-invite-email"
                    />
                  </div>
                  <div className="w-36">
                    <label className="block text-xs font-semibold text-[#48574d]">Assigned Role</label>
                    <select
                      value={inviteRole}
                      onChange={(e) => setInviteRole(e.target.value as any)}
                      className="mt-1.5 w-full rounded-sm border border-[#d5cebf] bg-white px-3 py-2 text-xs text-[#253a32] focus:border-[#9b4a36] focus:outline-none"
                      data-testid="select-invite-role"
                    >
                      {isOwner && <option value="admin">Administrator</option>}
                      <option value="editor">Editor</option>
                      <option value="contributor">Contributor</option>
                      <option value="viewer">Viewer</option>
                    </select>
                  </div>
                  <button
                    type="submit"
                    disabled={createInvitation.isPending}
                    className="ww-button inline-flex items-center gap-2 bg-[#294238] px-4 py-2 text-xs font-semibold text-[#f7f2e7] hover:bg-[#38574a]"
                    data-testid="button-submit-invite"
                  >
                    <Plus size={14} /> Send Invitation
                  </button>
                </form>

                {generatedInviteToken && (
                  <div className="mt-4 rounded border border-[#64856b]/40 bg-[#f1f6f2] p-3 text-xs text-[#2b4c33]">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold">One-time Invitation Token:</span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(generatedInviteToken);
                          setCopiedInvite(true);
                          setTimeout(() => setCopiedInvite(false), 2000);
                        }}
                        className="inline-flex items-center gap-1 font-semibold text-[#294238] underline"
                      >
                        {copiedInvite ? <Check size={13} /> : <Copy size={13} />}
                        {copiedInvite ? 'Copied' : 'Copy'}
                      </button>
                    </div>
                    <code className="mt-1 block break-all font-mono text-[11px] text-[#294238]">{generatedInviteToken}</code>
                  </div>
                )}
              </div>
            )}

            {/* Members List Table */}
            <div className="border border-[#d9d1c2] bg-[#faf7ef] p-6">
              <div className="flex items-center justify-between border-b border-[#ded7ca] pb-3">
                <div className="flex items-center gap-2">
                  <UserCheck size={16} className="text-[#9b4a36]" />
                  <h2 className="font-serif text-xl text-[#253a32]">Enrolled Society</h2>
                </div>
                <span className="ww-kicker text-xs text-[#788078]">
                  {(members as MemberResponse[])?.length || 0} active members
                </span>
              </div>

              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-xs text-[#33483e]">
                  <thead className="border-b border-[#d8d0c1] bg-[#efe9dc]/50 text-[11px] uppercase tracking-wider text-[#6e786f]">
                    <tr>
                      <th className="py-2.5 px-3">Collaborator</th>
                      <th className="py-2.5 px-3">Email</th>
                      <th className="py-2.5 px-3">Role</th>
                      <th className="py-2.5 px-3">Joined</th>
                      {isAdminOrOwner && <th className="py-2.5 px-3 text-right">Actions</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#ded7ca]">
                    {(members as MemberResponse[])?.map((m) => {
                      const canChange = isOwner ? m.role !== 'owner' : (universe.role === 'admin' && m.role !== 'owner' && m.role !== 'admin');
                      return (
                        <tr key={m.id} className="hover:bg-[#f5efe4]">
                          <td className="py-3 px-3 font-medium text-[#253a32]">{m.display_name}</td>
                          <td className="py-3 px-3 text-[#657168]">{m.email}</td>
                          <td className="py-3 px-3">
                            {canChange ? (
                              <select
                                value={m.role}
                                onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                                className="rounded border border-[#d5cebf] bg-white px-2 py-1 text-xs"
                                data-testid={`select-role-${m.user_id}`}
                              >
                                {isOwner && <option value="admin">Admin</option>}
                                <option value="editor">Editor</option>
                                <option value="contributor">Contributor</option>
                                <option value="viewer">Viewer</option>
                              </select>
                            ) : (
                              <span className="font-semibold capitalize text-[#9b4a36]">{m.role}</span>
                            )}
                          </td>
                          <td className="py-3 px-3 text-[#788078]">{new Date(m.joined_at).toLocaleDateString()}</td>
                          {isAdminOrOwner && (
                            <td className="py-3 px-3 text-right">
                              {canChange && (
                                <button
                                  onClick={() => handleRemoveMember(m.user_id)}
                                  className="text-[#9b4a36] hover:text-[#7d3e30]"
                                  title="Remove member"
                                  data-testid={`button-remove-${m.user_id}`}
                                >
                                  <Trash2 size={14} />
                                </button>
                              )}
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 5: AUDIT TRAIL */}
        {activeTab === 'audit' && (
          <div className="border border-[#d9d1c2] bg-[#faf7ef] p-6">
            <div className="flex items-center gap-2 border-b border-[#ded7ca] pb-3">
              <Shield size={16} className="text-[#9b4a36]" />
              <h2 className="font-serif text-xl text-[#253a32]">Immutable Audit Trail</h2>
            </div>
            <p className="mt-2 text-xs text-[#6e786f]">
              Direct ledger of state-altering mutations recorded in this universe tenant.
            </p>

            <div className="mt-5 overflow-x-auto">
              <table className="w-full text-left text-xs text-[#33483e]">
                <thead className="border-b border-[#d8d0c1] bg-[#efe9dc]/50 text-[11px] uppercase tracking-wider text-[#6e786f]">
                  <tr>
                    <th className="py-2.5 px-3">Action</th>
                    <th className="py-2.5 px-3">Target</th>
                    <th className="py-2.5 px-3">Actor Ref</th>
                    <th className="py-2.5 px-3">Timestamp (UTC)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#ded7ca]">
                  {auditLogs?.map((log) => (
                    <tr key={log.id} className="hover:bg-[#f5efe4]">
                      <td className="py-2.5 px-3 font-mono font-medium text-[#9b4a36]">{log.action}</td>
                      <td className="py-2.5 px-3 text-[#48574d]">{log.target_type}</td>
                      <td className="py-2.5 px-3 font-mono text-[11px] text-[#788078]">{log.actor_user_id || 'system'}</td>
                      <td className="py-2.5 px-3 text-[#788078]">{new Date(log.created_at).toISOString()}</td>
                    </tr>
                  ))}
                  {(!auditLogs || auditLogs.length === 0) && (
                    <tr>
                      <td colSpan={4} className="py-4 text-center text-xs text-[#899087]">
                        No audit records present.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 6: SETTINGS */}
        {activeTab === 'settings' && (
          <div className="space-y-6">
            <div className="border border-[#d9d1c2] bg-[#faf7ef] p-6">
              <h2 className="font-serif text-xl text-[#253a32]">Universe Properties</h2>
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    await updateUniverse.mutateAsync({
                      universeId,
                      data: { name: editName.trim() || universe.name, description: editDesc.trim() || universe.description },
                    });
                    await queryClient.invalidateQueries();
                    setIsEditingSettings(false);
                    setFeedbackMsg({ type: 'success', text: 'Universe updated.' });
                  } catch (err: any) {
                    setFeedbackMsg({ type: 'error', text: err?.data?.error?.message || 'Update failed.' });
                  }
                }}
                className="mt-4 space-y-4 max-w-lg"
              >
                <div>
                  <label className="block text-xs font-semibold text-[#48574d]">Universe Name</label>
                  <input
                    type="text"
                    disabled={!isAdminOrOwner || !isEditingSettings}
                    defaultValue={universe.name}
                    onChange={(e) => setEditName(e.target.value)}
                    className="mt-1 w-full rounded border border-[#d5cebf] bg-white px-3 py-2 text-xs text-[#253a32] disabled:bg-[#f2ece1]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#48574d]">Description</label>
                  <textarea
                    rows={3}
                    disabled={!isAdminOrOwner || !isEditingSettings}
                    defaultValue={universe.description || ''}
                    onChange={(e) => setEditDesc(e.target.value)}
                    className="mt-1 w-full rounded border border-[#d5cebf] bg-white px-3 py-2 text-xs text-[#253a32] disabled:bg-[#f2ece1]"
                  />
                </div>
                {isAdminOrOwner && (
                  <div className="pt-2">
                    {isEditingSettings ? (
                      <div className="flex gap-2">
                        <button
                          type="submit"
                          disabled={updateUniverse.isPending}
                          className="ww-button bg-[#294238] px-4 py-2 text-xs font-semibold text-white hover:bg-[#38574a]"
                        >
                          Save Changes
                        </button>
                        <button
                          type="button"
                          onClick={() => setIsEditingSettings(false)}
                          className="border border-[#c9c1b2] px-4 py-2 text-xs text-[#53655b]"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setEditName(universe.name);
                          setEditDesc(universe.description || '');
                          setIsEditingSettings(true);
                        }}
                        className="ww-button border border-[#294238] px-4 py-2 text-xs font-semibold text-[#294238] hover:bg-[#294238] hover:text-white"
                      >
                        Edit Details
                      </button>
                    )}
                  </div>
                )}
              </form>
            </div>

            {isOwner && universe.status === 'active' && (
              <div className="border border-[#a4523b]/30 bg-[#fdf2ef] p-6">
                <h3 className="font-serif text-lg font-semibold text-[#7d3e30]">Archive Universe</h3>
                <p className="mt-1 text-xs text-[#7d3e30]/80">
                  Archiving marks this universe as read-only.
                </p>
                <button
                  type="button"
                  onClick={async () => {
                    if (!confirm('Are you sure you want to archive this universe?')) return;
                    try {
                      await archiveUniverse.mutateAsync({ universeId });
                      await queryClient.invalidateQueries();
                      setFeedbackMsg({ type: 'success', text: 'Universe archived.' });
                    } catch (err: any) {
                      setFeedbackMsg({ type: 'error', text: err?.data?.error?.message || 'Archive failed.' });
                    }
                  }}
                  className="mt-4 rounded border border-[#a4523b] bg-transparent px-4 py-2 text-xs font-semibold text-[#9b4a36] hover:bg-[#9b4a36] hover:text-white"
                  data-testid="button-archive-universe"
                >
                  Archive this universe
                </button>
              </div>
            )}

            <DataPortability
              universeId={universeId}
              universeSlug={universe.slug}
              canExport={isAdminOrOwner}
              canImport={isAdminOrOwner}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------------
// Interactive Nexus Graph Visualizer (SVG Force Layout)
// -----------------------------------------------------------------------------

function NexusGraphViewer({
  nodes,
  edges,
  onSelectNode,
}: {
  nodes: Array<{ id: string; title: string; color?: string | null; entity_type_name: string }>;
  edges: Array<{ id: string; source: string; target: string; label: string }>;
  onSelectNode: (id: string) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const startPanRef = useRef({ x: 0, y: 0 });

  // Compute 2D node coordinates using circular placement
  const nodePositions = useMemo(() => {
    const pos = new Map<string, { x: number; y: number }>();
    const count = nodes.length;
    if (count === 0) return pos;

    const centerX = 350;
    const centerY = 250;
    const radius = Math.min(220, Math.max(120, count * 22));

    nodes.forEach((n, idx) => {
      const angle = (idx / count) * 2 * Math.PI;
      pos.set(n.id, {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      });
    });
    return pos;
  }, [nodes]);

  if (nodes.length === 0) {
    return (
      <div className="text-center text-xs text-[#899087]">
        No entities or relations available to render in this graph scope.
      </div>
    );
  }

  return (
    <div
      className="relative h-full w-full select-none cursor-grab active:cursor-grabbing"
      onMouseDown={(e) => {
        setIsPanning(true);
        startPanRef.current = { x: e.clientX - offset.x, y: e.clientY - offset.y };
      }}
      onMouseMove={(e) => {
        if (!isPanning) return;
        setOffset({
          x: e.clientX - startPanRef.current.x,
          y: e.clientY - startPanRef.current.y,
        });
      }}
      onMouseUp={() => setIsPanning(false)}
      onMouseLeave={() => setIsPanning(false)}
    >
      {/* Zoom controls */}
      <div className="absolute top-3 right-3 z-10 flex gap-1 rounded border border-[#d5cebf] bg-white/90 p-1 shadow-sm">
        <button
          onClick={(e) => {
            e.stopPropagation();
            setZoom((z) => Math.min(z + 0.2, 2.5));
          }}
          className="p-1 hover:text-[#9b4a36]"
          title="Zoom in"
        >
          <ZoomIn size={14} />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setZoom((z) => Math.max(z - 0.2, 0.4));
          }}
          className="p-1 hover:text-[#9b4a36]"
          title="Zoom out"
        >
          <ZoomOut size={14} />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setZoom(1);
            setOffset({ x: 0, y: 0 });
          }}
          className="px-1 text-[10px] font-semibold text-[#53655b] hover:text-[#9b4a36]"
          title="Reset"
        >
          Reset
        </button>
      </div>

      <svg className="h-[520px] w-full" viewBox="0 0 700 500">
        <g transform={`translate(${offset.x}, ${offset.y}) scale(${zoom})`}>
          {/* Edges */}
          {edges.map((e) => {
            const p1 = nodePositions.get(e.source);
            const p2 = nodePositions.get(e.target);
            if (!p1 || !p2) return null;
            const midX = (p1.x + p2.x) / 2;
            const midY = (p1.y + p2.y) / 2;
            return (
              <g key={e.id}>
                <line
                  x1={p1.x}
                  y1={p1.y}
                  x2={p2.x}
                  y2={p2.y}
                  stroke="#b8aa8d"
                  strokeWidth="1.5"
                  strokeDasharray="3 3"
                />
                <text
                  x={midX}
                  y={midY - 4}
                  fill="#788078"
                  fontSize="9"
                  fontFamily="sans-serif"
                  textAnchor="middle"
                >
                  {e.label}
                </text>
              </g>
            );
          })}

          {/* Nodes */}
          {nodes.map((n) => {
            const p = nodePositions.get(n.id);
            if (!p) return null;
            return (
              <g
                key={n.id}
                transform={`translate(${p.x}, ${p.y})`}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectNode(n.id);
                }}
                className="cursor-pointer transition-transform hover:scale-110"
              >
                <circle
                  r="20"
                  fill={n.color || '#253a32'}
                  stroke="#FAF7EF"
                  strokeWidth="2.5"
                  className="shadow"
                />
                <text
                  textAnchor="middle"
                  dy="4"
                  fill="#FAF7EF"
                  fontSize="10"
                  fontWeight="bold"
                >
                  {n.title.charAt(0).toUpperCase()}
                </text>
                <text
                  textAnchor="middle"
                  dy="32"
                  fill="#253a32"
                  fontSize="10"
                  fontWeight="600"
                >
                  {n.title}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
