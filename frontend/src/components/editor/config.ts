import type { Component } from 'vue'
import { Extension, type AnyExtension } from '@tiptap/core'
import { Plugin, PluginKey, type Transaction } from '@tiptap/pm/state'
import { call, useFileUpload, type UploadedFile } from 'frappe-ui'
import { SuggestionExtension } from 'frappe-ui/editor'
import type { MediaUploadRequestOptions } from 'frappe-ui/editor'
import DiscussionLinkList, {
  type DiscussionLinkItem,
} from '@/components/editor/DiscussionLinkList.vue'
import RichQuoteNodeExtension from '@/components/RichQuoteExtension/rich-quote-node-extension'
import QuoteBacklinkDecoration from '@/components/RichQuoteExtension/quote-backlink-decoration'
import type { RichQuoteController } from '@/components/RichQuoteExtension/useRichQuotes'
import TextEditorMentionComponent from '@/components/TextEditorMentionComponent.vue'
import MentionList, { type MentionItem } from '@/components/editor/MentionList.vue'
import { searchUsers } from '@/data/users'
import { tags as tagList } from '@/data/tags'
import { loadDiscussionPreview } from '@/data/discussionPreviews'
import { discussionHref, parseDiscussionUrl } from '@/utils/discussionLinks'

// @-mention items: gameplan users plus an "Everyone" entry. The mention node stores
// `id`/`label`; the suggestion command maps value→id, so we provide all three.
let mentionTimer: number | undefined
let mentionRequest = 0
let mentionWaiting: ((items: MentionItem[]) => void)[] = []

function mentionItems(query: string): Promise<MentionItem[]> {
  return new Promise((resolve) => {
    mentionWaiting.push(resolve)
    window.clearTimeout(mentionTimer)
    mentionTimer = window.setTimeout(async () => {
      const waiting = mentionWaiting
      mentionWaiting = []
      const current = ++mentionRequest
      const users = await searchUsers({ query, limit: 10 }).catch(() => [])
      if (current !== mentionRequest) return
      const everyone = { id: '_everyone_', label: 'Everyone', value: '_everyone_' }
      const items = ('everyone'.startsWith(query.toLowerCase()) ? [everyone] : []).concat(
        users.map((user) => ({
          id: user.name,
          label: user.full_name.trimEnd(),
          value: user.name,
        })),
      )
      waiting.forEach((done) => done(items))
    }, 150)
  })
}

const MENTION_PREFIXES = [
  ' ',
  ' ',
  '(',
  '[',
  '{',
  '<',
  '（',
  '【',
  '《',
  '「',
  '『',
  '«',
  '‹',
  '"',
  "'",
  '“',
  '”',
  '‘',
  '’',
  '」',
  '』',
  '»',
  '›',
]

export function mentionExtension() {
  return SuggestionExtension.configure<MentionItem>({
    name: 'mentionSearch',
    trigger: '@',
    items: mentionItems,
    listComponent: MentionList as Component,
    allowedPrefixes: MENTION_PREFIXES,
    command: ({ editor, item, range }) => {
      editor
        .chain()
        .focus()
        .insertContentAt(range, [
          { type: 'mention', attrs: { id: item.value, label: item.label } },
          { type: 'text', text: ' ' },
        ])
        .run()
    },
  })
}

function tagItems() {
  return (tagList.data ?? []).map((tag) => ({ id: tag.name, label: tag.label }))
}

function discussionLinkItems(query: string): Promise<DiscussionLinkItem[]> {
  if (query && !/^[\p{L}\p{N}]/u.test(query)) return Promise.resolve([])
  const pattern = /^\p{N}/u.test(query) ? `${query}%` : `%${query}%`
  return call('frappe.client.get_list', {
    doctype: 'GP Discussion',
    fields: ['name', 'title', 'project'],
    filters: query ? { title: ['like', pattern] } : {},
    order_by: 'last_post_at desc',
    limit_page_length: 10,
  })
}

export function discussionLinkExtension() {
  return SuggestionExtension.configure<DiscussionLinkItem>({
    name: 'discussionLink',
    trigger: '+',
    items: discussionLinkItems,
    listComponent: DiscussionLinkList as Component,
    allowSpaces: true,
    command: ({ editor, item, range }) => {
      const href = discussionHref(item.project, item.name)
      if (item.preview) {
        editor
          .chain()
          .focus()
          .deleteRange(range)
          .insertDiscussionCard({ discussion: item.name, href, title: item.title })
          .run()
        return
      }
      editor
        .chain()
        .focus()
        .insertContentAt(range, [
          { type: 'text', text: item.title, marks: [{ type: 'link', attrs: { href } }] },
          { type: 'text', text: ' ' },
        ])
        .run()
    },
  })
}

export const DiscussionLinkPasteExtension = Extension.create({
  name: 'discussionLinkPaste',

  addProseMirrorPlugins() {
    const editor = this.editor
    return [
      new Plugin({
        key: new PluginKey('discussionLinkPaste'),
        props: {
          handlePaste: (view, event) => {
            const href = event.clipboardData?.getData('text/plain').trim() ?? ''
            if (!view.state.selection.empty || !/^https?:\/\/\S+$/.test(href)) return false
            const discussion = parseDiscussionUrl(href)?.name
            if (!discussion) return false

            let from = view.state.selection.from
            editor
              .chain()
              .insertContent({
                type: 'text',
                text: href,
                marks: [{ type: 'link', attrs: { href } }],
              })
              .run()

            const track = ({ transaction }: { transaction: Transaction }) => {
              from = transaction.mapping.map(from)
            }
            editor.on('transaction', track)

            const isPastedLink = (to: number) => {
              const { doc, schema } = editor.state
              if (to > doc.content.size || doc.textBetween(from, to) !== href) return false
              let linked = true
              doc.nodesBetween(from, to, (node) => {
                if (!node.isText) return
                const mark = node.marks.find((m) => m.type === schema.marks.link)
                if (mark?.attrs.href !== href) linked = false
              })
              return linked
            }

            loadDiscussionPreview(discussion)
              .then((preview) => {
                editor.off('transaction', track)
                const to = from + href.length
                if (!preview || editor.isDestroyed || !isPastedLink(to)) return
                editor
                  .chain()
                  .insertContentAt(
                    { from, to },
                    {
                      type: 'text',
                      text: preview.title,
                      marks: [{ type: 'link', attrs: { href } }],
                    },
                  )
                  .run()
              })
              .catch(() => editor.off('transaction', track))
            return true
          },
        },
      }),
    ]
  },
})

/**
 * gameplan drops H1 everywhere — kits are configured with these heading levels.
 * Kept here (kit-free) so both extension stacks share one source of truth.
 */
export const gameplanHeadingLevels = [2, 3, 4, 5, 6] as const

/**
 * Kit-member config for @-mentions + #-tags, applied via `kit.configure(...)`
 * (spec §3 — data-driven members configured, never proxied through props). Passing
 * a getter keeps the live tag list reactive. Mention popups come from
 * `mentionExtension()`, so the kit's own are always off. `suggestions: false` keeps the
 * nodes (so existing mentions/tags still render) but disables the live popups —
 * used by Pages, which never had them.
 */
export function suggestionConfig(suggestions = true) {
  return {
    mention: {
      items: null,
      nodeView: TextEditorMentionComponent as Component,
    },
    tag: { items: suggestions ? tagItems : null },
  }
}

/**
 * gameplan-local RichQuote extensions, appended after the kit (spec §6).
 *
 * Both the inserted quote's click handler and the "quoted by" badges talk to the
 * single RichQuoteController directly — no event re-emitting. Pass the controller
 * (and the surface's `sourceId`) inside a discussion; omit it for rich editors
 * outside one (Pages/Tasks), where quotes still render but aren't interactive.
 * The floating Reply button is a component (QuoteReplyButton.vue), not an extension.
 */
export function richQuoteExtensions(controller?: RichQuoteController | null, sourceId?: string) {
  const extensions: AnyExtension[] = [
    RichQuoteNodeExtension.configure({
      onClick: controller ? (payload) => controller.navigateToQuote(payload) : () => {},
    }),
  ]
  if (controller && sourceId) {
    extensions.push(
      QuoteBacklinkDecoration.configure({
        getBacklinks: () => controller.getFor(sourceId),
        onBacklinkClick: ({ anchorEl, items }) => controller.openPopover(anchorEl, items),
      }),
    )
  }
  return extensions
}

/**
 * The frappe file upload the v0 monolith invoked silently as its default. v1's
 * editor requires an explicit `uploadFunction`, so gameplan passes this one.
 *
 * Uploads default to `private: true` so editor images/attachments are not served
 * from the unauthenticated `/files/` path (frappe/security#206). The backend
 * attaches each file to its parent doc on save (see gameplan/mixins/attachments.py),
 * which is what lets other space members read the now-private file. The runtime
 * `{ signal, onProgress }` the editor engine passes is preserved.
 */
export function uploadFile(file: File, options?: MediaUploadRequestOptions): Promise<UploadedFile> {
  return useFileUpload().upload(file, { private: true, ...(options ?? {}) })
}
