import { loadWorkspaceBootstrapFiles, type WorkspaceBootstrapFile } from "./workspace.js";

const cache = new Map<string, WorkspaceBootstrapFile[]>();

// ⭐️ 已讲（10 讲义，第 25 节）：同 sessionKey 可复用文件快照；磁盘保存后并不保证下一条输入立即重读。
export async function getOrLoadBootstrapFiles(params: {
  workspaceDir: string;
  sessionKey: string;
}): Promise<WorkspaceBootstrapFile[]> {
  const existing = cache.get(params.sessionKey);
  if (existing) {
    return existing;
  }
  // ⭐️ 加载相关文件
  const files = await loadWorkspaceBootstrapFiles(params.workspaceDir);
  cache.set(params.sessionKey, files);
  return files;
}

// ⭐️ 已讲（10 讲义，第 25 节）：显式失效指定会话快照，下一次解析才会重新读取。
export function clearBootstrapSnapshot(sessionKey: string): void {
  cache.delete(sessionKey);
}

// ⭐️ 已讲（10 讲义，第 25 节）：会话轮换时清理旧快照，避免继续沿用上一会话资料。
export function clearBootstrapSnapshotOnSessionRollover(params: {
  sessionKey?: string;
  previousSessionId?: string;
}): void {
  if (!params.sessionKey || !params.previousSessionId) {
    return;
  }

  clearBootstrapSnapshot(params.sessionKey);
}

export function clearAllBootstrapSnapshots(): void {
  cache.clear();
}
