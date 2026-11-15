type MessageFile = {
  url: string
  name: string
  size: number
  kind: 'image' | 'video' | 'pdf' | 'file'
}

export type ViewerFile = MessageFile & { owner: string; creation: string; message: number }

const FILE_SELECTOR = 'img[src]:not([data-emoji]), video[src], a[data-attachment][href]'

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'avif', 'bmp', 'svg'])
const VIDEO_EXTENSIONS = new Set(['mp4', 'webm', 'mov', 'ogv', 'm4v'])

export function messageFiles(content?: string | null): MessageFile[] {
  if (!content || !/<(img|video|a)\b/.test(content)) return []
  const doc = new DOMParser().parseFromString(content, 'text/html')
  return [...doc.querySelectorAll(FILE_SELECTOR)].map(toFile)
}

export function toFile(element: Element): MessageFile {
  const url = element.getAttribute('src') || element.getAttribute('href') || ''
  const name =
    element.getAttribute('data-file-name') ||
    decodeURIComponent(url.split('?')[0].split('/').pop() || 'file')
  const size = Number(element.getAttribute('data-file-size')) || 0
  return { url, name, size, kind: kindOf(element, name) }
}

function kindOf(element: Element, name: string): MessageFile['kind'] {
  if (element.tagName === 'IMG') return 'image'
  if (element.tagName === 'VIDEO') return 'video'
  const mime = element.getAttribute('data-mime-type') || ''
  const extension = name.split('.').pop()?.toLowerCase() || ''
  if (mime.startsWith('image/') || IMAGE_EXTENSIONS.has(extension)) return 'image'
  if (mime.startsWith('video/') || VIDEO_EXTENSIONS.has(extension)) return 'video'
  if (mime === 'application/pdf' || extension === 'pdf') return 'pdf'
  return 'file'
}

export function fileIcon(name: string) {
  const extension = name.split('.').pop()?.toLowerCase() || ''
  if (['ppt', 'pptx', 'key', 'odp'].includes(extension)) return 'lucide-presentation'
  if (['xls', 'xlsx', 'csv', 'ods', 'numbers'].includes(extension)) return 'lucide-file-spreadsheet'
  if (['doc', 'docx', 'txt', 'md', 'rtf', 'odt', 'pages'].includes(extension))
    return 'lucide-file-text'
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(extension)) return 'lucide-file-archive'
  if (['mp3', 'wav', 'm4a', 'ogg', 'flac'].includes(extension)) return 'lucide-file-audio'
  return 'lucide-file'
}

export function formatBytes(bytes: number) {
  const units = ['B', 'KB', 'MB', 'GB']
  let index = 0
  while (bytes >= 1024 && index < units.length - 1) {
    bytes /= 1024
    index++
  }
  return `${index ? bytes.toFixed(1) : bytes} ${units[index]}`
}

export function downloadFile(file: { url: string; name: string }) {
  const link = document.createElement('a')
  link.href = file.url
  link.download = file.name
  document.body.append(link)
  link.click()
  link.remove()
}

type MessageLink = { url: string; text: string }

export function messageLinks(content?: string | null): MessageLink[] {
  if (!content?.includes('href="http')) return []
  const doc = new DOMParser().parseFromString(content, 'text/html')
  return [...doc.querySelectorAll('a[href^="http"]:not([data-attachment])')].map((link) => {
    const url = link.getAttribute('href') || ''
    return { url, text: link.textContent?.trim() || url }
  })
}
