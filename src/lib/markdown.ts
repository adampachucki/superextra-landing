import { marked, Renderer, type Tokens } from 'marked';

const renderer = new Renderer();
const renderTable = renderer.table.bind(renderer);

const htmlEntities: Record<string, string> = {
	'&': '&amp;',
	'<': '&lt;',
	'>': '&gt;',
	'"': '&quot;',
	"'": '&#39;'
};

function escapeHtml(value: string): string {
	return value.replace(/[&<>"']/g, (char) => htmlEntities[char]);
}

renderer.html = (token: Tokens.HTML | Tokens.Tag) => escapeHtml(token.raw);

renderer.table = (token: Tokens.Table) => {
	const columnCount = Math.max(token.header.length, 1);
	return `<div class="markdown-table-scroll" style="--markdown-table-columns:${columnCount}">${renderTable(token)}</div>`;
};

marked.setOptions({ breaks: true, gfm: true, renderer });

export function renderMarkdown(text: string): string {
	return marked.parse(text) as string;
}
