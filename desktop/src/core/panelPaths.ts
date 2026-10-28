/** 文件路径身份与聊天链接解析；明确绝对路径可位于项目外，相对路径不得越根。 */
export function normalizePath(path: string): string {
  const value = path.replaceAll("\\", "/");
  const root = value.startsWith("//") ? "//" : value.startsWith("/") ? "/" : "";
  const parts: string[] = [];
  for (const part of value.slice(root.length).split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (parts.length && !parts.at(-1)?.endsWith(":")) parts.pop();
    } else parts.push(part);
  }
  const result = root + parts.join("/");
  return /^[a-z]:$/i.test(result) ? `${result}/` : result || root;
}
export function pathKey(path: string): string {
  const normalized = normalizePath(path);
  return /^[a-z]:/i.test(normalized) || normalized.startsWith("//")
    ? normalized.toLowerCase()
    : normalized;
}
export function isAbsolutePath(path: string): boolean {
  return /^(?:[a-z]:[\\/]|[\\/])/i.test(path);
}
export function insidePath(root: string, path: string): boolean {
  const key = pathKey(root).replace(/\/$/, "");
  const target = pathKey(path);
  return target === key || target.startsWith(`${key}/`);
}
export function pathName(path: string): string {
  return normalizePath(path).split("/").at(-1) || path;
}
export function parentPath(path: string): string {
  const value = normalizePath(path);
  const index = value.lastIndexOf("/");
  return normalizePath(
    value.slice(0, index + (index === 0 || index === 2 ? 1 : 0)),
  );
}
export interface FileReference {
  path: string;
  line?: number;
}
export function resolveFileReference(
  root: string,
  href: string,
  base = root,
): FileReference | null {
  let target = href.trim();
  if (!target || target.startsWith("#")) return null;
  try {
    if (/^file:\/\//i.test(target)) {
      const url = new URL(target);
      target =
        `${url.hostname && url.hostname !== "localhost" ? `//${url.hostname}` : ""}${url.pathname}${url.hash}`.replace(
          /^\/([a-z]:\/)/i,
          "$1",
        );
    } else if (/^[a-z][\w+.-]*:/i.test(target) && !/^[a-z]:[\\/]/i.test(target))
      return null;
    target = decodeURIComponent(target);
  } catch {
    return null;
  }
  const suffix = /(?:#L(\d+)(?:-L?\d+)?|:(\d+)(?::\d+)?)$/.exec(target);
  const line = suffix ? Number(suffix[1] ?? suffix[2]) : undefined;
  if (suffix) target = target.slice(0, suffix.index);
  const absolute = isAbsolutePath(target);
  const path = normalizePath(absolute ? target : `${base}/${target}`);
  if (!absolute && !insidePath(root, path)) return null;
  return { path, ...(line !== undefined && line > 0 ? { line } : {}) };
}
