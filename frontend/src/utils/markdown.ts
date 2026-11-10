import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({
  breaks: true,
  gfm: true,
});

export function renderMarkdown(text: string): string {
  return DOMPurify.sanitize(
    marked.parse(text, { async: false }),
  );
}
