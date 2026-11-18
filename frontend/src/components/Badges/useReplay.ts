import { nextTick, ref } from 'vue'

/** A CSS animation that restarts on every call, even while it is still running. */
export function useReplay() {
  const playing = ref(false)
  async function play() {
    playing.value = false
    await nextTick()
    playing.value = true
  }
  return { playing, play, stop: () => (playing.value = false) }
}
