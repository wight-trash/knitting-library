// GitHub release notes as plain text for the release pop-up and Settings. Upstream shows the body as written, so
// HTML from GitHub (mostly <img> tags for screenshots, which the app's content security policy blocks anyway)
// appeared as raw code. Tags and Markdown images are removed; text, line breaks and links are kept. Fork-only.

/** The release body without HTML tags, HTML comments or Markdown images. */
export function releaseText(body) {
  if (!body) return '';
  return String(body)
    .replace(/\r\n?/g, '\n')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li|h[1-6]|tr)>/gi, '\n')
    .replace(/<\/?[A-Za-z][^<>]*>/g, '')
    .replace(/!\[[^\]]*\]\([^)\s]*\)/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/[ \t]+$/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
