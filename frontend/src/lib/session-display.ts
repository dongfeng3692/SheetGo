const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const WORKSPACE_PATTERN = /^workspace\s+(\d+)$/i;

export function formatSessionName(name: string | undefined, index?: number): string {
  if (!name) {
    return "未命名工作区";
  }

  const workspaceMatch = name.match(WORKSPACE_PATTERN);
  if (workspaceMatch) {
    return `工作区 ${workspaceMatch[1]}`;
  }

  if (!UUID_PATTERN.test(name)) {
    return name;
  }

  if (typeof index === "number" && Number.isFinite(index)) {
    return `工作区 ${index + 1}`;
  }

  return `工作区 ${name.slice(0, 8)}`;
}
