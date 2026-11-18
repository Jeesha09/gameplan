/**
 * Draws a censored word as drifting dust, as Telegram draws a spoiler. The word keeps its
 * masked ■ text, made transparent by `.censor-dust`, so it holds its place in the line. A
 * canvas over it draws particles in the text colour. Each particle drifts its own way, fades in
 * and out, and starts again somewhere new, and the edges fade so the word has no box around it.
 *
 * One animation frame loop serves every censored word on the page, and skips those off screen.
 */

/** CSS pixels at each edge over which the dust fades out, inside the word's own box. */
const FADE = 2
/** CSS pixels of word per particle. Smaller is denser. */
const AREA_PER_PARTICLE = 2.2
// Each particle is 6 numbers: x, y, x speed, y speed, age, lifetime.
const FIELDS = 6

type Dust = {
  canvas: HTMLCanvasElement
  target: () => HTMLElement | null
  context: CanvasRenderingContext2D
  particles: Float32Array
  width: number
  height: number
  ratio: number
  color: string
  visible: boolean
  resize: ResizeObserver
}

const active = new Set<Dust>()
const stillMotion =
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
let frame = 0
let last = 0

const visibility =
  typeof IntersectionObserver === 'undefined'
    ? null
    : new IntersectionObserver((entries) => {
        for (const entry of entries) {
          for (const dust of active) {
            if (dust.canvas === entry.target) dust.visible = entry.isIntersecting
          }
        }
      })

/**
 * Starts dust on `canvas`, over the element `target` returns. The canvas's parent must be
 * positioned. Returns a function that stops it.
 */
export function startDust(canvas: HTMLCanvasElement, target: () => HTMLElement | null) {
  const context = canvas.getContext('2d')
  if (!context) return () => {}
  const dust: Dust = {
    canvas,
    target,
    context,
    particles: new Float32Array(0),
    width: 0,
    height: 0,
    ratio: 1,
    color: '',
    visible: true,
    resize: new ResizeObserver(() => layout(dust)),
  }
  active.add(dust)
  visibility?.observe(canvas)
  // The target may not be in the document yet, as when an editor inserts the canvas first.
  requestAnimationFrame(() => {
    const element = target()
    if (element) dust.resize.observe(element)
    layout(dust)
    if (stillMotion) draw(dust, 0)
  })
  if (!stillMotion && !frame) frame = requestAnimationFrame(tick)
  return () => stop(dust)
}

function stop(dust: Dust) {
  active.delete(dust)
  dust.resize.disconnect()
  visibility?.unobserve(dust.canvas)
}

function layout(dust: Dust) {
  const element = dust.target()
  const parent = dust.canvas.parentElement
  if (!element || !parent) return
  const word = element.getBoundingClientRect()
  const origin = parent.getBoundingClientRect()
  // Whole device pixels throughout, so the canvas is never scaled and no dot is smeared.
  const ratio = window.devicePixelRatio || 1
  dust.ratio = ratio
  dust.canvas.width = Math.ceil(word.width * ratio)
  dust.canvas.height = Math.ceil(word.height * ratio)
  dust.width = dust.canvas.width / ratio
  dust.height = dust.canvas.height / ratio
  Object.assign(dust.canvas.style, {
    left: `${Math.round((word.left - origin.left) * ratio) / ratio}px`,
    top: `${Math.round((word.top - origin.top) * ratio) / ratio}px`,
    width: `${dust.width}px`,
    height: `${dust.height}px`,
  })
  dust.color = getComputedStyle(element).color
  const count = Math.max(8, Math.round((word.width * word.height) / AREA_PER_PARTICLE))
  dust.particles = new Float32Array(count * FIELDS)
  for (let index = 0; index < count; index++) {
    // Start at a random age, so they do not all fade in together.
    spawn(dust, index * FIELDS, Math.random())
  }
}

function spawn(dust: Dust, at: number, age = 0) {
  const p = dust.particles
  const angle = Math.random() * Math.PI * 2
  const speed = 3 + Math.random() * 12
  const lifetime = 0.6 + Math.random() * 1.8
  p[at] = Math.random() * dust.width
  p[at + 1] = Math.random() * dust.height
  p[at + 2] = Math.cos(angle) * speed
  p[at + 3] = Math.sin(angle) * speed
  p[at + 4] = age * lifetime
  p[at + 5] = lifetime
}

function tick(now: number) {
  const seconds = last ? Math.min((now - last) / 1000, 0.05) : 0
  last = now
  // Browser zoom changes the device pixel ratio but not a word's size, so no ResizeObserver
  // fires. A canvas left at the old ratio is stretched and looks pixelated.
  const ratio = window.devicePixelRatio || 1
  for (const dust of active) {
    if (!dust.canvas.isConnected) stop(dust)
    else if (dust.visible) {
      if (dust.ratio !== ratio) layout(dust)
      draw(dust, seconds)
    }
  }
  frame = active.size ? requestAnimationFrame(tick) : 0
  if (!frame) last = 0
}

function draw(dust: Dust, seconds: number) {
  const { context, particles: p, width, height, ratio } = dust
  // One CSS pixel per dot, drawn on whole device pixels so it stays sharp.
  const size = Math.max(1, Math.round(ratio))
  context.clearRect(0, 0, dust.canvas.width, dust.canvas.height)
  context.fillStyle = dust.color
  for (let at = 0; at < p.length; at += FIELDS) {
    p[at + 4] += seconds
    if (p[at + 4] >= p[at + 5]) spawn(dust, at)
    const x = (p[at] += p[at + 2] * seconds)
    const y = (p[at + 1] += p[at + 3] * seconds)
    // Fade in and out over its life, and towards every edge, so no box shows.
    const life = Math.sin((Math.PI * p[at + 4]) / p[at + 5])
    const edge = Math.min(1, x / FADE, (width - x) / FADE, y / FADE, (height - y) / FADE)
    if (edge <= 0) continue
    context.globalAlpha = (stillMotion ? 0.8 : life) * edge
    context.fillRect(Math.round(x * ratio), Math.round(y * ratio), size, size)
  }
  context.globalAlpha = 1
}

/** Marks each censored run in server HTML, for content shown with `v-html` and `vCensorDust`. */
export function censorHtml(html: string) {
  return (html || '').replace(/■+/g, '<span class="censor-dust" aria-label="Censored">$&</span>')
}

/**
 * Starts dust on the censored runs in `v-html` content. Vue replaces that content whole on
 * each update, so the canvases go with it and the loop drops them.
 */
export const vCensorDust = {
  mounted: attachAll,
  updated: attachAll,
}

function attachAll(container: HTMLElement) {
  for (const word of container.querySelectorAll<HTMLElement>('.censor-dust')) {
    if (word.querySelector('.censor-dust-canvas')) continue
    const canvas = document.createElement('canvas')
    canvas.className = 'censor-dust-canvas'
    canvas.setAttribute('aria-hidden', 'true')
    word.append(canvas)
    startDust(canvas, () => word)
  }
}
