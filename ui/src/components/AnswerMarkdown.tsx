import { createElement, Fragment, type ReactNode } from "react";

// Only construct the elements listed here. Model text always goes through React
// escaping, including HTML, image markup, and URLs.
function inline(text: string): ReactNode[] {
  return text.split(/(\x60[^\x60\n]+\x60|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_)/g).map((part, index) => {
    if (index % 2 === 0) return part;
    if (part.startsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") || part.startsWith("__")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <em key={index}>{part.slice(1, -1)}</em>;
  });
}

const listItem = /^\s*(\d+[.)]|[-+*•])\s+(.*)$/;
const tableRule = /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/;
const fence = /^\s*```/;
const heading = /^(#{1,6})\s+(.+)$/;

function cells(line: string): string[] {
  return line.trim().replace(/^\||\|$/g, "").split("|").map((value) => value.trim());
}

export function AnswerMarkdown({ text, suffix }: { text: string; suffix?: ReactNode }) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const key = index++;
    if (!line.trim()) continue;
    if (fence.test(line)) {
      const code: string[] = [];
      while (index < lines.length && !fence.test(lines[index])) code.push(lines[index++]);
      if (index < lines.length) index++;
      blocks.push(<pre key={key}><code>{code.join("\n")}</code></pre>);
      continue;
    }
    const title = heading.exec(line);
    if (title) {
      const level = Math.min(6, title[1].length + 2);
      blocks.push(createElement(`h${level}`, { key }, inline(title[2])));
      continue;
    }
    const item = listItem.exec(line);
    if (item) {
      const ordered = /^\d/.test(item[1]);
      const items = [item[2]];
      while (index < lines.length) {
        const next = listItem.exec(lines[index]);
        if (!next || /^\d/.test(next[1]) !== ordered) break;
        items.push(next[2]);
        index++;
      }
      const List = ordered ? "ol" : "ul";
      blocks.push(
        <List key={key} start={ordered ? Number.parseInt(item[1], 10) : undefined}>
          {items.map((value, position) => <li key={position}>{inline(value)}</li>)}
        </List>,
      );
      continue;
    }
    if (line.includes("|") && index < lines.length && tableRule.test(lines[index])) {
      index++;
      const header = cells(line);
      const rows: string[][] = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(cells(lines[index++]));
      }
      blocks.push(
        <table key={key}>
          <thead><tr>{header.map((value, column) => <th key={column} scope="col">{inline(value)}</th>)}</tr></thead>
          <tbody>{rows.map((row, position) => (
            <tr key={position}>{header.map((_, column) => <td key={column}>{inline(row[column] ?? "")}</td>)}</tr>
          ))}</tbody>
        </table>,
      );
      continue;
    }
    const paragraph = [line];
    while (index < lines.length && lines[index].trim() &&
      !fence.test(lines[index]) && !heading.test(lines[index]) && !listItem.test(lines[index]) &&
      !(lines[index].includes("|") && tableRule.test(lines[index + 1] ?? ""))) {
      paragraph.push(lines[index++]);
    }
    blocks.push(<p key={key}>{inline(paragraph.join("\n"))}{index === lines.length ? suffix : null}</p>);
    if (index === lines.length) suffix = undefined;
  }
  return <Fragment>{blocks}{suffix}</Fragment>;
}
