<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from "vue";

import { streamChat } from "./api/chat";
import { errorMessage } from "./api/http";
import {
  getProfile,
  updateProfile,
} from "./api/profile";
import {
  deleteThread,
  getMessages,
  listThreads,
  renameThread,
} from "./api/threads";
import type {
  ChatMessage,
  ThreadItem,
  UserProfile,
} from "./types";
import { emptyProfile } from "./types";
import { renderMarkdown } from "./utils/markdown";

const threads = ref<ThreadItem[]>([]);
const currentThreadId = ref<string | null>(null);
const messages = ref<ChatMessage[]>([]);
const messagesEl = ref<HTMLElement | null>(null);
const input = ref("");
const loading = ref(false);
const loadingThreads = ref(false);
const error = ref("");

const profileOpen = ref(false);
const profile = ref<UserProfile>(emptyProfile());
const profileDraft = ref<UserProfile>(emptyProfile());
const savingProfile = ref(false);

const menuThread = ref<ThreadItem | null>(null);
const menuPosition = ref({ top: 0, left: 0 });

const hoverTip = ref<{
  text: string;
  top: number;
  left: number;
} | null>(null);
const renameOpen = ref(false);
const renameTarget = ref<ThreadItem | null>(null);
const renameTitle = ref("");
const renaming = ref(false);
const renameInput = ref<HTMLInputElement | null>(null);

const deleteOpen = ref(false);
const deleteTarget = ref<ThreadItem | null>(null);
const deleting = ref(false);

const diningText = ref("");
const transportText = ref("");
const accommodationText = ref("");
const activityText = ref("");

function splitList(value: string): string[] {
  return value
    .split(/[，,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function cloneProfile(value: UserProfile): UserProfile {
  return {
    city: value.city,
    dining_preferences: [...value.dining_preferences],
    transport_preferences: [...value.transport_preferences],
    accommodation_preferences: [
      ...value.accommodation_preferences,
    ],
    activity_preferences: [...value.activity_preferences],
  };
}

function formatTime(value: string | null): string {
  if (!value) return "";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "";

  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function scrollToBottom() {
  await nextTick();

  const element = messagesEl.value;

  if (element) {
    element.scrollTop = element.scrollHeight;

    requestAnimationFrame(() => {
      element.scrollTop = element.scrollHeight;
    });
  }
}

async function refreshThreads() {
  loadingThreads.value = true;

  try {
    threads.value = await listThreads();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loadingThreads.value = false;
  }
}

async function refreshProfile() {
  try {
    profile.value = await getProfile();
    profileDraft.value = cloneProfile(profile.value);
  } catch (err) {
    error.value = errorMessage(err);
  }
}

async function newChat() {
  currentThreadId.value = null;
  messages.value = [];
  input.value = "";
  error.value = "";
}

async function openThread(thread: ThreadItem) {
  if (loading.value) return;

  currentThreadId.value = thread.thread_id;
  error.value = "";

  try {
    messages.value = await getMessages(thread.thread_id);
    await scrollToBottom();
  } catch (err) {
    error.value = errorMessage(err);
  }
}

async function onSend() {
  const text = input.value.trim();

  if (!text || loading.value) return;

  loading.value = true;
  error.value = "";
  input.value = "";

  messages.value.push({
    role: "user",
    content: text,
  });

  const assistant = reactive<ChatMessage>({
    role: "assistant",
    content: "",
  });
  messages.value.push(assistant);

  await scrollToBottom();

  try {
    await streamChat(
      text,
      currentThreadId.value,
      (event) => {
        if (event.type === "meta" && event.thread_id) {
          currentThreadId.value = event.thread_id;
        }

        if (event.type === "token" && event.content) {
          assistant.content += event.content;
          void scrollToBottom();
        }

        if (event.type === "error") {
          error.value =
            event.detail ?? "生成回答失败，请稍后重试";
        }

        if (event.type === "done") {
          if (!assistant.content && event.answer) {
            assistant.content = event.answer;
          }
        }
      },
    );

    if (!assistant.content) {
      messages.value = messages.value.filter(
        (message) => message !== assistant,
      );
    }

    await Promise.all([
      refreshThreads(),
      refreshProfile(),
    ]);
  } catch (err) {
    error.value =
      err instanceof Error
        ? err.message
        : errorMessage(err);
  } finally {
    loading.value = false;
  }
}

function showHoverTip(
  event: MouseEvent,
  text: string,
) {
  const rect = (
    event.currentTarget as HTMLElement
  ).getBoundingClientRect();

  const center = rect.left + rect.width / 2;
  const halfWidth = Math.max(48, text.length * 7);

  hoverTip.value = {
    text,
    top: Math.max(8, rect.top - 38),
    left: Math.min(
      window.innerWidth - halfWidth - 8,
      Math.max(halfWidth + 8, center),
    ),
  };
}

function hideHoverTip() {
  hoverTip.value = null;
}

function toggleThreadMenu(
  thread: ThreadItem,
  event: MouseEvent,
) {
  hideHoverTip();

  if (menuThread.value?.thread_id === thread.thread_id) {
    menuThread.value = null;
    return;
  }

  const rect = (
    event.currentTarget as HTMLElement
  ).getBoundingClientRect();
  const menuWidth = 120;
  const menuHeight = 82;

  const left = Math.min(
    window.innerWidth - menuWidth - 8,
    Math.max(8, rect.right - menuWidth),
  );

  let top = rect.bottom + 6;

  if (top + menuHeight > window.innerHeight) {
    top = rect.top - menuHeight - 6;
  }

  menuPosition.value = { top, left };
  menuThread.value = thread;
}

function openRename(thread: ThreadItem) {
  menuThread.value = null;
  renameTarget.value = thread;
  renameTitle.value = thread.title;

  renameOpen.value = true;
  void nextTick(() => renameInput.value?.focus());
}

async function submitRename() {
  const target = renameTarget.value;
  const title = renameTitle.value.trim();

  if (!target || !title || renaming.value) return;

  renaming.value = true;
  error.value = "";

  try {
    await renameThread(target.thread_id, title);
    renameOpen.value = false;
    await refreshThreads();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    renaming.value = false;
  }
}

function openDelete(thread: ThreadItem) {
  menuThread.value = null;
  deleteTarget.value = thread;
  deleteOpen.value = true;
}

function renameMenuThread() {
  if (menuThread.value) {
    openRename(menuThread.value);
  }
}

function deleteMenuThread() {
  if (menuThread.value) {
    openDelete(menuThread.value);
  }
}

async function confirmDelete() {
  const target = deleteTarget.value;

  if (!target || deleting.value) return;

  deleting.value = true;
  error.value = "";

  try {
    await deleteThread(target.thread_id);

    if (currentThreadId.value === target.thread_id) {
      await newChat();
    }

    deleteOpen.value = false;
    await refreshThreads();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    deleting.value = false;
  }
}

function openProfile() {
  profileDraft.value = cloneProfile(profile.value);

  diningText.value = profile.value.dining_preferences.join("，");
  transportText.value = profile.value.transport_preferences.join("，");
  accommodationText.value =
    profile.value.accommodation_preferences.join("，");
  activityText.value =
    profile.value.activity_preferences.join("，");

  profileOpen.value = true;
}

async function saveProfile() {
  savingProfile.value = true;
  error.value = "";

  profileDraft.value.dining_preferences = splitList(
    diningText.value,
  );
  profileDraft.value.transport_preferences = splitList(
    transportText.value,
  );
  profileDraft.value.accommodation_preferences = splitList(
    accommodationText.value,
  );
  profileDraft.value.activity_preferences = splitList(
    activityText.value,
  );

  try {
    profile.value = await updateProfile(profileDraft.value);
    profileOpen.value = false;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    savingProfile.value = false;
  }
}

onMounted(async () => {
  error.value = "";

  await Promise.all([
    refreshThreads(),
    refreshProfile(),
  ]);
});
</script>

<template>
  <div class="app" @click="menuThread = null">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-dot"></div>
        <div>
          <h1>出行助手</h1>
          <p>MCP · LangGraph</p>
        </div>
      </div>

      <button class="new-chat" @click="newChat">
        ＋ 新会话
      </button>

      <div class="sidebar-label">
        会话
        <button
          class="icon-button"
          aria-label="刷新会话"
          @mouseenter="showHoverTip($event, '刷新会话')"
          @mouseleave="hideHoverTip"
          @click="refreshThreads"
        >
          ↻
        </button>
      </div>

      <div
        class="thread-list"
        @scroll="
          menuThread = null;
          hideHoverTip();
        "
      >
        <div
          v-for="thread in threads"
          :key="thread.thread_id"
          class="thread-item"
          :class="{
            active: thread.thread_id === currentThreadId,
          }"
          role="button"
          tabindex="0"
          @click="openThread(thread)"
          @keydown.enter="openThread(thread)"
        >
          <span class="thread-title">{{ thread.title }}</span>
          <span class="thread-preview">
            {{ thread.last_message_preview || "暂无消息" }}
          </span>
          <span class="thread-time">
            {{ formatTime(thread.updated_at) }}
          </span>

          <button
            class="thread-more"
            aria-label="更多操作"
            @mouseenter="showHoverTip($event, '会话操作')"
            @mouseleave="hideHoverTip"
            @click.stop="toggleThreadMenu(thread, $event)"
          >
            ⋯
          </button>
        </div>

        <p
          v-if="!loadingThreads && !threads.length"
          class="empty-hint"
        >
          还没有会话，发第一句话开始吧。
        </p>
      </div>

      <button class="profile-entry" @click="openProfile">
        <span class="avatar">我</span>
        <span>
          <strong>用户画像</strong>
          <small>
            {{ profile.city || "未设置城市" }}
          </small>
        </span>
      </button>
    </aside>

    <main class="main">
      <header class="topbar">
        <div>
          <h2>
            {{
              currentThreadId
                ? "继续对话"
                : "新的出行问题"
            }}
          </h2>
          <p>
            查地点、路线、营业时间、周边和出行建议
          </p>
        </div>
        <span class="status">
          {{ currentThreadId ? "已连接会话" : "草稿" }}
        </span>
      </header>

      <p v-if="error" class="error-banner">
        {{ error }}
      </p>

      <section ref="messagesEl" class="messages">
        <div v-if="!messages.length" class="welcome">
          <h3>想去哪里？</h3>
          <p>
            例如：北京有什么好吃的？从酒店到欢乐谷怎么走？
          </p>
        </div>

        <article
          v-for="(message, index) in messages"
          :key="index"
          class="message"
          :class="message.role"
        >
          <div class="message-content">
            <template v-if="message.role === 'assistant'">
              <div
                v-if="message.content"
                class="markdown-body"
                v-html="renderMarkdown(message.content)"
              ></div>
              <span v-else-if="loading" class="typing">
                正在查询并整理结果…
              </span>
            </template>
            <template v-else>
              {{ message.content }}
            </template>
          </div>
        </article>
      </section>

      <footer class="composer">
        <textarea
          v-model="input"
          :disabled="loading"
          rows="3"
          placeholder="输入你的问题，Enter 发送，Shift + Enter 换行"
          @keydown.enter.exact.prevent="onSend"
        ></textarea>

        <div class="composer-bottom">
          <span>回答由工具结果和记忆辅助生成</span>
          <button
            class="send-button"
            :disabled="loading || !input.trim()"
            @click="onSend"
          >
            {{ loading ? "发送中…" : "发送" }}
          </button>
        </div>
      </footer>
    </main>

    <Teleport to="body">
      <div
        v-if="menuThread"
        class="thread-menu thread-menu-fixed"
        :style="{
          top: `${menuPosition.top}px`,
          left: `${menuPosition.left}px`,
        }"
        @click.stop
      >
        <button @click="renameMenuThread">
          重命名
        </button>
        <button class="danger" @click="deleteMenuThread">
          删除
        </button>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="hoverTip"
        class="hover-tip"
        :style="{
          top: `${hoverTip.top}px`,
          left: `${hoverTip.left}px`,
        }"
      >
        {{ hoverTip.text }}
      </div>
    </Teleport>

    <div
      v-if="profileOpen"
      class="modal-mask"
      @click.self="profileOpen = false"
    >
      <section class="modal">
        <header class="modal-header">
          <div>
            <h3>用户画像</h3>
            <p>用于跨会话记住你的稳定偏好</p>
          </div>
          <button
            class="icon-button"
            @click="profileOpen = false"
          >
            ×
          </button>
        </header>

        <label class="field">
          <span>城市</span>
          <input
            v-model="profileDraft.city"
            placeholder="例如：北京"
          />
        </label>

        <label class="field">
          <span>餐饮偏好（逗号分隔）</span>
          <input v-model="diningText" />
        </label>

        <label class="field">
          <span>交通偏好（逗号分隔）</span>
          <input v-model="transportText" />
        </label>

        <label class="field">
          <span>住宿偏好（逗号分隔）</span>
          <input v-model="accommodationText" />
        </label>

        <label class="field">
          <span>游玩偏好（逗号分隔）</span>
          <input v-model="activityText" />
        </label>

        <footer class="modal-footer">
          <button
            class="secondary-button"
            @click="profileOpen = false"
          >
            取消
          </button>
          <button
            class="send-button"
            :disabled="savingProfile"
            @click="saveProfile"
          >
            {{ savingProfile ? "保存中…" : "保存" }}
          </button>
        </footer>
      </section>
    </div>

    <div
      v-if="renameOpen"
      class="modal-mask"
      @click.self="renameOpen = false"
    >
      <section class="modal modal-small">
        <header class="modal-header">
          <div>
            <h3>重命名会话</h3>
            <p>修改后会显示在左侧会话列表</p>
          </div>
          <button
            class="icon-button"
            @click="renameOpen = false"
          >
            ×
          </button>
        </header>

        <label class="field">
          <span>会话标题</span>
          <input
            ref="renameInput"
            v-model="renameTitle"
            maxlength="50"
            placeholder="请输入会话标题"
            @keydown.enter.prevent="submitRename"
          />
        </label>

        <footer class="modal-footer">
          <button
            class="secondary-button"
            @click="renameOpen = false"
          >
            取消
          </button>
          <button
            class="send-button"
            :disabled="renaming || !renameTitle.trim()"
            @click="submitRename"
          >
            {{ renaming ? "保存中…" : "保存" }}
          </button>
        </footer>
      </section>
    </div>

    <div
      v-if="deleteOpen"
      class="modal-mask"
      @click.self="deleteOpen = false"
    >
      <section class="modal modal-small">
        <header class="modal-header">
          <div>
            <h3>删除会话</h3>
            <p>删除后无法恢复</p>
          </div>
          <button
            class="icon-button"
            @click="deleteOpen = false"
          >
            ×
          </button>
        </header>

        <p class="modal-text">
          确定删除「{{ deleteTarget?.title }}」吗？
          该会话的历史记录和记忆会一起清除。
        </p>

        <footer class="modal-footer">
          <button
            class="secondary-button"
            @click="deleteOpen = false"
          >
            取消
          </button>
          <button
            class="danger-button"
            :disabled="deleting"
            @click="confirmDelete"
          >
            {{ deleting ? "删除中…" : "删除" }}
          </button>
        </footer>
      </section>
    </div>
  </div>
</template>
