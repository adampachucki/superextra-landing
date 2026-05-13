import { marked, Renderer, type Tokens } from 'marked';

const renderer = new Renderer();
const renderTable = renderer.table.bind(renderer);

renderer.table = (token: Tokens.Table) =>
	`<div class="markdown-table-scroll">${renderTable(token)}</div>`;

marked.setOptions({ breaks: true, gfm: true, renderer });

export function renderMarkdown(text: string): string {
	return marked.parse(text) as string;
}
