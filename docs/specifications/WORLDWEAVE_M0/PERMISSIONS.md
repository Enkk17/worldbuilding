# Authorization and Permission Model

## 1. Model

Use deny-by-default authorization combining:
1. Universe membership role (RBAC).
2. Optional resource-level grants.
3. Resource visibility.
4. Explicit action policy.

Every authorization decision is made server-side. Frontend visibility is only a UX convenience.

## 2. Roles

### Owner
- Full control of universe and members.
- Transfer ownership.
- Delete/archive universe.
- Manage all settings, content, roles, exports, and audit history.

### Administrator
- Manage members except owner transfer/removal.
- Manage universe settings and entity schemas.
- Manage content, review queue, exports, and audit visibility.
- Cannot delete or transfer ownership unless explicitly granted by owner.

### Editor
- Read all content visible to the team.
- Create/update/publish canonical content.
- Manage documents, entities, maps, calendars, and relationships.
- Review proposals if granted.

### Contributor
- Read content visible to them.
- Create drafts and propose edits.
- Edit own drafts.
- Comment if permitted.
- Cannot change universe settings or membership.

### Viewer
- Read content visible to them.
- No mutation by default.
- Comment only if explicitly enabled.

## 3. Actions

Use explicit action identifiers:
- `universe.read`, `universe.update`, `universe.archive`, `universe.delete`
- `member.read`, `member.invite`, `member.update_role`, `member.remove`
- `entity.read`, `entity.create`, `entity.update`, `entity.delete`, `entity.restore`, `entity.publish`
- `relation.create`, `relation.delete`
- `document.read`, `document.create`, `document.update`, `document.delete`, `document.restore`
- `document.comment`, `document.review`
- `map.read`, `map.create`, `map.update`, `map.delete`
- `timeline.read`, `timeline.create`, `timeline.update`, `timeline.delete`
- `export.create`, `import.validate`, `import.execute`
- `audit.read`

## 4. Baseline role matrix

| Action group | Owner | Admin | Editor | Contributor | Viewer |
|---|---:|---:|---:|---:|---:|
| Read accessible universe | Yes | Yes | Yes | Yes | Yes |
| Manage universe settings | Yes | Yes | No | No | No |
| Manage members | Yes | Yes* | No | No | No |
| Manage entity schemas | Yes | Yes | No | No | No |
| Create/edit canonical entities | Yes | Yes | Yes | Draft/proposal | No |
| Delete/restore canonical entities | Yes | Yes | Yes** | No | No |
| Manage documents | Yes | Yes | Yes | Own drafts/proposals | No |
| Review proposals | Yes | Yes | If granted | No | No |
| Manage maps/calendars | Yes | Yes | Yes | Propose | No |
| Export universe | Yes | Yes | If granted | No | No |
| Read audit log | Yes | Yes | If granted | No | No |
| Transfer ownership | Yes | No | No | No | No |

* Admin cannot remove owner or grant a role above their own authority.  
** Entity deletion may be restricted by universe policy.

## 5. Resource-level controls

Resource visibility:
- `universe`: visible to all active members;
- `restricted`: visible only to explicitly granted members and privileged roles;
- `draft`: visible to creator and editors/reviewers according to policy;
- `private`: visible only to creator and owner/admin unless policy says otherwise.

Resource grants support `read`, `comment`, `edit`, `review`. Explicit denies, if implemented, take precedence over inherited grants. Avoid building an overly complex ACL engine in v1.0.

## 6. Tenant isolation

- Every repository method receives an authorized universe context.
- Never fetch a record by ID alone when it is universe-scoped.
- Queries include universe scope and visibility predicates.
- Verify both source and target universe on relationship creation.
- Verify linked entities/documents share universe with maps/events.
- Graph, search, exports, activity, comments, and notifications must apply the same scope.
- Return 404 for inaccessible resources where revealing existence would be a leak.
- Test cross-tenant ID substitution attacks.

## 7. Realtime authorization

A collaboration ticket is short-lived and scoped to one document and allowed operations. On room join, verify membership and document access. Re-check or revoke room access after role changes, membership removal, or resource visibility changes.

## 8. Audit

Record:
- member and role changes;
- universe setting changes;
- publish/review decisions;
- content delete/restore;
- import/export initiation;
- permission changes;
- ownership transfer.

Do not store full document contents or secrets in audit metadata. Store hashes and safe metadata where appropriate.
