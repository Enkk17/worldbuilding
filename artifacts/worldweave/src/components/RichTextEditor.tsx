import { useEffect, useMemo, useRef, useState } from 'react';
import { EditorContent, useEditor } from '@tiptap/react';
import { Node, type JSONContent } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import Collaboration from '@tiptap/extension-collaboration';
import CollaborationCaret from '@tiptap/extension-collaboration-caret';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import Placeholder from '@tiptap/extension-placeholder';
import {
  Bold,
  Code,
  Heading1,
  Heading2,
  Heading3,
  Image as ImageIcon,
  Italic,
  Link as LinkIcon,
  List,
  ListOrdered,
  Minus,
  Quote,
  Redo2,
  Strikethrough,
  Undo2,
  Unlink,
} from 'lucide-react';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import type { EntityResponse } from '@workspace/api-client-react';
import type { CollaborationProvider } from '@/lib/collaboration-provider';

/**
 * Canonical TipTap node used by the Chronicle backend to index entity
 * mentions. Keeping this as a real inline node (instead of plain text) means
 * the stored JSON, Markdown snapshot, and backlink table always agree.
 */
const EntityMention = Node.create({
  name: 'entityMention',
  inline: true,
  group: 'inline',
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      entityId: {
        default: null,
        parseHTML: (element: HTMLElement) =>
          element.getAttribute('data-entity-id'),
      },
      label: {
        default: '',
        parseHTML: (element: HTMLElement) => element.textContent ?? '',
      },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-entity-mention]' }];
  },

  renderHTML({ node }) {
    return [
      'span',
      {
        'data-entity-mention': '',
        'data-entity-id': node.attrs.entityId ?? '',
        class: 'ww-entity-mention',
      },
      node.attrs.label || 'Entity',
    ];
  },
});

const EMPTY_DOCUMENT: JSONContent = {
  type: 'doc',
  content: [{ type: 'paragraph' }],
};

export interface RichTextEditorProps {
  initialContent: JSONContent | null;
  editable: boolean;
  entities: EntityResponse[];
  onChange: (content: JSONContent) => void;
  placeholder?: string;
  /**
   * When present the editor is backed by the shared Y.Doc managed by the
   * collaboration provider. ``initialContent`` is ignored: the Yjs room is
   * seeded from the server's durable state, and every keystroke is persisted
   * through the CRDT stream.
   */
  collaboration?: {
    provider: CollaborationProvider;
    user: { name: string; color: string };
    synced: boolean;
  };
}

export function RichTextEditor({
  initialContent,
  editable,
  entities,
  onChange,
  placeholder,
  collaboration,
}: RichTextEditorProps) {
  const [mentionState, setMentionState] = useState<{
    from: number;
    query: string;
  } | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [imageUrl, setImageUrl] = useState('');
  const [linkUrl, setLinkUrl] = useState('');
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const collaborationProvider = collaboration?.provider;
  const collaborationReady =
    !collaborationProvider || Boolean(collaboration?.synced);
  const canEdit = editable && collaborationReady;

  const editor = useEditor({
    editable: canEdit,
    content: collaborationProvider
      ? null
      : initialContent ?? EMPTY_DOCUMENT,
    extensions: [
      StarterKit.configure({
        link: false,
        heading: { levels: [1, 2, 3] },
        // The collaboration extension owns undo/redo through the shared Yjs
        // undo manager; keeping StarterKit's history would fork the stack.
        undoRedo: collaborationProvider ? false : undefined,
      }),
      ...(collaboration
        ? [
            Collaboration.configure({
              document: collaboration.provider.doc,
              field: 'content',
            }),
            CollaborationCaret.configure({
              provider: collaboration.provider,
              user: collaboration.user,
            }),
          ]
        : []),
      Link.configure({
        openOnClick: false,
        autolink: true,
        HTMLAttributes: { rel: 'noopener noreferrer', target: '_blank' },
      }),
      Image.configure({ allowBase64: false }),
      Placeholder.configure({
        placeholder:
          placeholder ??
          'Write your chronicle… Type [[ to link a Codex entity.',
      }),
      EntityMention,
    ],
    editorProps: {
      attributes: {
        class: 'ww-prose focus:outline-none',
        'aria-label': 'Document body',
      },
    },
    onUpdate: ({ editor: current }) => {
      onChangeRef.current(current.getJSON());

      const { from } = current.state.selection;
      const before = current.state.doc.textBetween(
        Math.max(0, from - 80),
        from,
        '\n',
        '\u0000'
      );
      const match = /\[\[([^[\]|]{0,80})$/.exec(before);
      if (match) {
        setMentionState({ from: from - match[0].length, query: match[1] });
        setPickerOpen(true);
      } else {
        setMentionState(null);
        setPickerOpen(false);
      }
    },
  });

  useEffect(() => {
    if (editor) editor.setEditable(canEdit);
  }, [canEdit, editor]);

  const mentionMatches = useMemo(() => {
    if (!mentionState) return [];
    const term = mentionState.query.trim().toLowerCase();
    return entities
      .filter((entity) =>
        term
          ? entity.title.toLowerCase().includes(term) ||
            entity.entity_type_name.toLowerCase().includes(term)
          : true
      )
      .slice(0, 8);
  }, [entities, mentionState]);

  if (!editor) {
    return (
      <div className="min-h-[320px] animate-pulse border border-[#d5cebf] bg-white" />
    );
  }

  const insertMention = (entity: EntityResponse) => {
    if (!mentionState) return;
    const { from } = editor.state.selection;
    editor
      .chain()
      .focus()
      .deleteRange({ from: mentionState.from, to: from })
      .insertContent([
        {
          type: 'entityMention',
          attrs: { entityId: entity.id, label: entity.title },
        },
        { type: 'text', text: ' ' },
      ])
      .run();
    setMentionState(null);
    setPickerOpen(false);
  };

  const applyLink = () => {
    const target = linkUrl.trim();
    if (!target) return;
    if (!/^(https?:\/\/|mailto:)/i.test(target)) return;
    editor.chain().focus().extendMarkRange('link').setLink({ href: target }).run();
    setLinkUrl('');
  };

  const applyImage = () => {
    const target = imageUrl.trim();
    if (!target) return;
    if (!/^(https?:\/\/|\/)/i.test(target)) return;
    editor.chain().focus().setImage({ src: target }).run();
    setImageUrl('');
  };

  const ToolbarButton = ({
    label,
    active,
    disabled,
    onClick,
    children,
  }: {
    label: string;
    active?: boolean;
    disabled?: boolean;
    onClick: () => void;
    children: React.ReactNode;
  }) => (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={`rounded-sm p-1.5 transition-colors ${
        active
          ? 'bg-[#294238] text-[#f7f2e7]'
          : 'text-[#53655b] hover:bg-[#e8e1d4] hover:text-[#253a32]'
      } disabled:cursor-not-allowed disabled:opacity-40`}
    >
      {children}
    </button>
  );

  return (
    <div className="relative">
      {canEdit && (
        <div className="flex flex-wrap items-center gap-1 border border-b-0 border-[#d5cebf] bg-[#f3eee3] p-1.5">
          <ToolbarButton
            label="Undo"
            disabled={!editor.can().undo()}
            onClick={() => editor.chain().focus().undo().run()}
          >
            <Undo2 size={14} />
          </ToolbarButton>
          <ToolbarButton
            label="Redo"
            disabled={!editor.can().redo()}
            onClick={() => editor.chain().focus().redo().run()}
          >
            <Redo2 size={14} />
          </ToolbarButton>
          <span className="mx-1 h-5 w-px bg-[#d5cebf]" />
          <ToolbarButton
            label="Heading 1"
            active={editor.isActive('heading', { level: 1 })}
            onClick={() =>
              editor.chain().focus().toggleHeading({ level: 1 }).run()
            }
          >
            <Heading1 size={14} />
          </ToolbarButton>
          <ToolbarButton
            label="Heading 2"
            active={editor.isActive('heading', { level: 2 })}
            onClick={() =>
              editor.chain().focus().toggleHeading({ level: 2 }).run()
            }
          >
            <Heading2 size={14} />
          </ToolbarButton>
          <ToolbarButton
            label="Heading 3"
            active={editor.isActive('heading', { level: 3 })}
            onClick={() =>
              editor.chain().focus().toggleHeading({ level: 3 }).run()
            }
          >
            <Heading3 size={14} />
          </ToolbarButton>
          <span className="mx-1 h-5 w-px bg-[#d5cebf]" />
          <ToolbarButton
            label="Bold"
            active={editor.isActive('bold')}
            onClick={() => editor.chain().focus().toggleBold().run()}
          >
            <Bold size={14} />
          </ToolbarButton>
          <ToolbarButton
            label="Italic"
            active={editor.isActive('italic')}
            onClick={() => editor.chain().focus().toggleItalic().run()}
          >
            <Italic size={14} />
          </ToolbarButton>
          <ToolbarButton
            label="Strikethrough"
            active={editor.isActive('strike')}
            onClick={() => editor.chain().focus().toggleStrike().run()}
          >
            <Strikethrough size={14} />
          </ToolbarButton>
          <ToolbarButton
            label="Inline code"
            active={editor.isActive('code')}
            onClick={() => editor.chain().focus().toggleCode().run()}
          >
            <Code size={14} />
          </ToolbarButton>
          <span className="mx-1 h-5 w-px bg-[#d5cebf]" />
          <ToolbarButton
            label="Bullet list"
            active={editor.isActive('bulletList')}
            onClick={() => editor.chain().focus().toggleBulletList().run()}
          >
            <List size={14} />
          </ToolbarButton>
          <ToolbarButton
            label="Numbered list"
            active={editor.isActive('orderedList')}
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
          >
            <ListOrdered size={14} />
          </ToolbarButton>
          <ToolbarButton
            label="Blockquote"
            active={editor.isActive('blockquote')}
            onClick={() => editor.chain().focus().toggleBlockquote().run()}
          >
            <Quote size={14} />
          </ToolbarButton>
          <ToolbarButton
            label="Horizontal rule"
            onClick={() => editor.chain().focus().setHorizontalRule().run()}
          >
            <Minus size={14} />
          </ToolbarButton>
          <span className="mx-1 h-5 w-px bg-[#d5cebf]" />

          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                title="Insert link"
                aria-label="Insert link"
                className={`rounded-sm p-1.5 transition-colors ${
                  editor.isActive('link')
                    ? 'bg-[#294238] text-[#f7f2e7]'
                    : 'text-[#53655b] hover:bg-[#e8e1d4] hover:text-[#253a32]'
                }`}
              >
                <LinkIcon size={14} />
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-72 border-[#d5cebf] bg-[#faf7ef] p-3">
              <label className="block text-[11px] font-semibold text-[#48574d]">
                Link target (http, https, mailto)
              </label>
              <input
                type="url"
                value={linkUrl}
                onChange={(event) => setLinkUrl(event.target.value)}
                placeholder="https://example.com"
                className="mt-1 w-full rounded-sm border border-[#d5cebf] bg-white px-2 py-1.5 text-xs"
              />
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={applyLink}
                  disabled={!/^(https?:\/\/|mailto:)/i.test(linkUrl.trim())}
                  className="rounded-sm bg-[#294238] px-2.5 py-1 text-[11px] font-semibold text-white disabled:opacity-50"
                >
                  Apply link
                </button>
                <button
                  type="button"
                  onClick={() => editor.chain().focus().unsetLink().run()}
                  className="inline-flex items-center gap-1 rounded-sm border border-[#d5cebf] px-2.5 py-1 text-[11px] text-[#53655b]"
                >
                  <Unlink size={12} /> Remove
                </button>
              </div>
            </PopoverContent>
          </Popover>

          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                title="Insert image"
                aria-label="Insert image"
                className="rounded-sm p-1.5 text-[#53655b] transition-colors hover:bg-[#e8e1d4] hover:text-[#253a32]"
              >
                <ImageIcon size={14} />
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-72 border-[#d5cebf] bg-[#faf7ef] p-3">
              <label className="block text-[11px] font-semibold text-[#48574d]">
                Image URL (https or /uploads)
              </label>
              <input
                type="url"
                value={imageUrl}
                onChange={(event) => setImageUrl(event.target.value)}
                placeholder="https://…"
                className="mt-1 w-full rounded-sm border border-[#d5cebf] bg-white px-2 py-1.5 text-xs"
              />
              <button
                type="button"
                onClick={applyImage}
                disabled={!/^(https?:\/\/|\/)/i.test(imageUrl.trim())}
                className="mt-2 rounded-sm bg-[#294238] px-2.5 py-1 text-[11px] font-semibold text-white disabled:opacity-50"
              >
                Insert image
              </button>
            </PopoverContent>
          </Popover>

          <Popover
            open={pickerOpen}
            onOpenChange={(open) => {
              setPickerOpen(open);
              if (!open) setMentionState(null);
            }}
          >
            <PopoverTrigger asChild>
              <button
                type="button"
                title="Link a Codex entity"
                className="rounded-sm px-2 py-1 text-[11px] font-semibold text-[#9b4a36] hover:bg-[#e8e1d4]"
              >
                @ Entity
              </button>
            </PopoverTrigger>
            <PopoverContent
              className="w-80 border-[#d5cebf] bg-[#faf7ef] p-0"
              align="start"
            >
              <Command className="bg-transparent">
                <div className="border-b border-[#ded7ca] px-3 py-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[#899087]">
                    Insert Codex mention
                  </p>
                </div>
                <CommandList>
                  <CommandEmpty className="px-3 py-4 text-xs text-[#899087]">
                    No matching entity.
                  </CommandEmpty>
                  <CommandGroup>
                    {(mentionState ? mentionMatches : entities.slice(0, 10)).map(
                      (entity) => (
                        <CommandItem
                          key={entity.id}
                          value={entity.title}
                          onSelect={() => {
                            if (mentionState) {
                              insertMention(entity);
                              return;
                            }
                            editor
                              .chain()
                              .focus()
                              .insertContent([
                                {
                                  type: 'entityMention',
                                  attrs: {
                                    entityId: entity.id,
                                    label: entity.title,
                                  },
                                },
                                { type: 'text', text: ' ' },
                              ])
                              .run();
                            setPickerOpen(false);
                          }}
                          className="cursor-pointer px-3 py-2 text-xs text-[#253a32] data-[selected=true]:bg-[#e8e1d4]"
                        >
                          <span className="font-medium">{entity.title}</span>
                          <span className="ml-2 text-[10px] text-[#899087]">
                            {entity.entity_type_name}
                          </span>
                        </CommandItem>
                      )
                    )}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        </div>
      )}

      <div
        className={`relative border border-[#d5cebf] bg-white px-5 py-4 ${
          canEdit ? '' : 'bg-[#fbf8f1]'
        }`}
      >
        <EditorContent editor={editor} />
        {collaborationProvider && !collaboration?.synced && (
          <div className="absolute inset-0 flex items-center justify-center bg-[#fbf8f1]/90">
            <div className="text-center">
              <div className="mx-auto h-5 w-5 animate-spin rounded-full border-2 border-[#d5cebf] border-t-[#9b4a36]" />
              <p className="mt-2 text-[11px] font-semibold uppercase tracking-wider text-[#899087]">
                Synchronizing shared document…
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
