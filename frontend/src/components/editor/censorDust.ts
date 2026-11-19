import { Extension } from '@tiptap/core'
import { Plugin } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import type { Node as ProseMirrorNode } from '@tiptap/pm/model'
import { startDust } from '@/utils/censorDust'

/** The server masks a censored word as a run of these (gameplan/watched_word_matching.py). */
export const CENSOR_MASK = /■+/g

/**
 * Draws each censored run as drifting dust (`utils/censorDust.ts`). The run is hidden by
 * `.censor-dust`, and a widget just before it holds the canvas. Decorations only change how
 * the text is shown: the document, and what a copy takes, stay the same.
 */
export const CensorDust = Extension.create({
  name: 'censorDust',
  addProseMirrorPlugins() {
    return [
      new Plugin({
        state: {
          init: (_, { doc }) => decorations(doc),
          apply: (tr, set) => (tr.docChanged ? decorations(tr.doc) : set),
        },
        props: {
          decorations(state) {
            return this.getState(state)
          },
        },
      }),
    ]
  },
})

function decorations(doc: ProseMirrorNode) {
  const found: Decoration[] = []
  doc.descendants((node, pos) => {
    if (!node.isText || !node.text?.includes('■')) return
    for (const match of node.text.matchAll(CENSOR_MASK)) {
      const from = pos + (match.index ?? 0)
      found.push(
        Decoration.widget(from, dustWidget, {
          side: -1,
          ignoreSelection: true,
          destroy: stopWidget,
        }),
        Decoration.inline(from, from + match[0].length, {
          class: 'censor-dust',
          'aria-label': 'Censored',
        }),
      )
    }
  })
  return DecorationSet.create(doc, found)
}

const stops = new WeakMap<Node, () => void>()

// A zero-width anchor holding the canvas, which covers the censored run that follows it.
function dustWidget() {
  const anchor = document.createElement('span')
  anchor.className = 'censor-dust-anchor'
  anchor.contentEditable = 'false'
  const canvas = document.createElement('canvas')
  canvas.className = 'censor-dust-canvas'
  canvas.setAttribute('aria-hidden', 'true')
  anchor.append(canvas)
  stops.set(
    anchor,
    startDust(canvas, () => anchor.nextElementSibling as HTMLElement | null),
  )
  return anchor
}

function stopWidget(node: Node) {
  stops.get(node)?.()
}
