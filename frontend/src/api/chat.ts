import { http } from "./http";
import type { ChatResult } from "../types";

export interface StreamEvent {
  type: "meta" | "token" | "done" | "error";
  thread_id?: string;
  content?: string;
  answer?: string;
  detail?: string;
}

export async function sendMessage(
  message: string,
  threadId: string | null,
): Promise<ChatResult> {
  const { data } = await http.post<ChatResult>("/chat", {
    message,
    thread_id: threadId,
  });

  return data;
}

export async function streamChat(
  message: string,
  threadId: string | null,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message,
      thread_id: threadId,
    }),
  });

  if (!response.ok || !response.body) {
    let detail = `HTTP ${response.status}`;

    try {
      const data = await response.json();
      if (typeof data?.detail === "string") {
        detail = data.detail;
      }
    } catch {
      // 忽略非 JSON 错误体
    }

    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();

    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");

    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      for (const line of block.split("\n")) {
        if (!line.startsWith("data:")) continue;

        const payload = line.slice(5).trim();

        if (!payload) continue;

        onEvent(JSON.parse(payload) as StreamEvent);
      }

      boundary = buffer.indexOf("\n\n");
    }
  }
}
