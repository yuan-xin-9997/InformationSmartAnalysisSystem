import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ breaks: true, gfm: true })

/** 将 Markdown 渲染为已消毒的 HTML（用于 v-html 展示分析结果）。 */
export function renderMarkdown(text: string): string {
  if (!text) return ''
  const html = marked.parse(text, { async: false }) as string
  return DOMPurify.sanitize(html)
}

/** 去除常见 Markdown 标记，返回纯文本（用于列表预览）。 */
export function stripMarkdown(text: string): string {
  if (!text) return ''
  return text
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/^[-*+]\s+/gm, '')
    .replace(/`(.+?)`/g, '$1')
    .replace(/\[(.+?)\]\(.+?\)/g, '$1')
    .replace(/\n+/g, ' ')
    .trim()
}
