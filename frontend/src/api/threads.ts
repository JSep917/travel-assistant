import { http } from "./http";
import type { ChatMessage, ThreadItem } from "../types";

export async function listThreads(): Promise<ThreadItem[]> {
  const { data } = await http.get<ThreadItem[]>("/threads");
  return data;
}

export async function getMessages(
  threadId: string,
): Promise<ChatMessage[]> {
  const { data } = await http.get<ChatMessage[]>(
    `/threads/${encodeURIComponent(threadId)}/messages`,
  );
  return data;
}

export async function renameThread(
  threadId: string,
  title: string,
): Promise<void> {
  await http.patch(
    `/threads/${encodeURIComponent(threadId)}`,
    { title },
  );
}

export async function deleteThread(
  threadId: string,
): Promise<void> {
  await http.delete(
    `/threads/${encodeURIComponent(threadId)}`,
  );
}
