# User Guide

## Create the first account

Open WORLDWEAVE and choose **Create account**. Enter an email address, a password of at least 12 characters, and a display name. On a new installation, the first account is created and signed in automatically.

The default registration policy is bootstrap-only: later public sign-ups are disabled. An administrator can change `REGISTRATION_MODE` in `.env` and restart the application if broader registration is intended.

## Sign in and out

Use the sign-in page with the email and password used for registration. Choose **Sign out** to revoke the current server-side session.

## Universes and roles

A universe is a self-contained worldbuilding project. Create one from the account home page. Each universe has members with one of five roles:

- **Owner**: full control, including ownership transfer and archiving.
- **Administrator**: manage members, invitations, and settings.
- **Editor**: create and edit all content, publish documents, review proposals.
- **Contributor**: create and edit their own drafts, submit them for review, and comment.
- **Viewer**: read-only access to shared content.

An owner or administrator invites members by email and role from the universe's Society tab. Invitations are bound to the invited email address.

## Codex and the Nexus graph

The Codex holds typed entities (characters, places, peoples, organizations, and so on) with custom fields, tags, and relations. The Nexus graph visualizes entities and their typed relations; use the focus control, depth selector, and type filters to explore. Private entities are visible only to their author and to privileged roles.

## Chronicle

The Chronicle stores documents in a hierarchy (collection, work, part, chapter, scene, note). Write with the rich-text editor, mention entities to create canonical links, and leave inline or document-level comments. Every save creates a revision you can review and restore. Once a document has a realtime collaboration history, edit its content through the collaborative editor; metadata edits remain available.

## Realtime collaboration

Open a chapter that you can edit and start typing. Presence indicators show who else is active, and changes are acknowledged once durably stored. If the server restarts, reopen the document and the acknowledged content is restored.

## Atlas and Chronos

Atlas maps hold a background image, markers, and polygon regions. Markers and regions link to Codex entities. Chronos defines custom calendars (variable months, leap rules, weekdays, eras) and timeline events with exact or approximate dates.

## Search

Press **Ctrl+K** (or **Cmd+K**) in a universe to open the command palette, or use the search box on the universe overview. Results cover entities, documents, and timeline events, and are filtered to what you are allowed to see.

## Import and export

Export a universe from the universe settings to download a portable ZIP bundle. To bring a universe in, use the import wizard: it validates the bundle (schema version, checksums, references) and reports conflicts before you confirm. Import requires an elevated role.

## Current scope

Milestones M1 through M9 are delivered: identity, universes and roles, Codex, Chronicle, realtime collaboration, Atlas, Chronos, search, and import/export. See `docs/IMPLEMENTATION_STATUS.md` for details.
