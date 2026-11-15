// The folder tree of the profile list. Folders come from the profiles that name
// them plus the saved list, so an empty folder stays until it is deleted.

import type { Row } from "./bridge";

export interface FolderNode {
  path: string;
  name: string;
  depth: number;
  /** Profiles in this folder and everything below it. */
  count: number;
  /** Profiles exactly here. */
  own: number;
  children: FolderNode[];
}

export function folderTree(rows: Row[], saved: string[]): FolderNode[] {
  const paths = new Set(saved.filter(Boolean));
  for (const row of rows) {
    if (!row.folder) continue;
    const parts = row.folder.split("/");
    for (let i = 1; i <= parts.length; i++) paths.add(parts.slice(0, i).join("/"));
  }
  const nodes = new Map<string, FolderNode>();
  for (const path of [...paths].sort()) {
    const parts = path.split("/");
    nodes.set(path, {
      path,
      name: parts[parts.length - 1],
      depth: parts.length - 1,
      count: 0,
      own: 0,
      children: [],
    });
  }
  for (const node of nodes.values()) {
    if (node.depth === 0) continue;
    nodes.get(node.path.split("/").slice(0, -1).join("/"))?.children.push(node);
  }
  for (const row of rows) {
    if (!row.folder) continue;
    const parts = row.folder.split("/");
    for (let i = 1; i <= parts.length; i++) {
      const node = nodes.get(parts.slice(0, i).join("/"));
      if (node) node.count++;
    }
    const own = nodes.get(row.folder);
    if (own) own.own++;
  }
  const sort = (list: FolderNode[]): FolderNode[] =>
    list.sort((a, b) => a.name.localeCompare(b.name)).map((n) => ((n.children = sort(n.children)), n));
  return sort([...nodes.values()].filter((n) => n.depth === 0));
}

/** A row belongs to the chosen folder and everything under it; null means all. */
export function inFolder(row: Row, folder: string | null): boolean {
  if (folder === null) return true;
  if (folder === "") return row.folder === "";
  return row.folder === folder || row.folder.startsWith(folder + "/");
}

/** Every path in the tree, for pickers. */
export function flatten(nodes: FolderNode[]): FolderNode[] {
  return nodes.flatMap((n) => [n, ...flatten(n.children)]);
}

export function rootCount(rows: Row[]): number {
  return rows.filter((r) => !r.folder).length;
}
