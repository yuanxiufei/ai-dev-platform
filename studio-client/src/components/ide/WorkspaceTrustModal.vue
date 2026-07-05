<script setup lang="ts">
/**
 * WorkspaceTrustModal.vue — 工作区信任确认弹窗
 *
 * 借鉴: VSCode src/vs/workbench/contrib/workspace/
 * 能力:
 *   - 打开不受信任的文件夹时弹窗确认
 *   - 列出受限功能
 *   - 信任 / 以受限模式打开 / 取消
 */
import { Shield, ShieldOff, ShieldAlert, Terminal as TerminalIcon, Bug, Blocks, Play } from "lucide-vue-next"
import { useWorkspaceTrustStore } from "@/stores/useWorkspaceTrustStore"

const trustStore = useWorkspaceTrustStore()

const restrictedItems = [
  { id: "tasks", label: "任务运行", icon: Play, desc: "构建、测试、监听等任务可能执行任意命令" },
  { id: "debug", label: "调试", icon: Bug, desc: "调试器可能启动不受信任的进程" },
  { id: "extensions", label: "扩展", icon: Blocks, desc: "扩展可能访问文件系统和网络" },
  { id: "terminal", label: "终端", icon: TerminalIcon, desc: "终端可执行任意系统命令" },
]

function trustAndOpen(): void {
  trustStore.trustWorkspace(trustStore.currentPath)
}

function openRestricted(): void {
  trustStore.showTrustDialog = false
}

function cancel(): void {
  trustStore.showTrustDialog = false
  trustStore.currentPath = ""
}
</script>

<template>
  <Teleport to="body">
    <div v-if="trustStore.showTrustDialog" class="trust-overlay">
      <div class="trust-dialog" style="background:var(--color-ide-surface); color:var(--color-ide-text)">
        <!-- Header -->
        <div class="flex items-center gap-3 p-6 pb-4">
          <div class="w-10 h-10 rounded-full flex items-center justify-center" style="background: rgba(245,158,11,0.12)">
            <ShieldAlert :size="20" style="color: #f59e0b" />
          </div>
          <div>
            <h2 class="text-[16px] font-semibold mb-0.5">是否信任此工作区文件夹？</h2>
            <p class="text-[12px] text-[var(--color-ide-text-dim)]">
              信任后，所有功能将完全可用。在受限模式下，部分功能将被禁用以确保安全。
            </p>
          </div>
        </div>

        <!-- 工作区路径 -->
        <div class="mx-6 px-3 py-1.5 rounded-[4px] text-[11px] font-mono break-all mb-4"
          style="background: var(--color-editor-bg); border: 1px solid var(--color-ide-border)">
          {{ trustStore.currentPath }}
        </div>

        <!-- 受限功能列表 -->
        <div class="px-6 pb-2">
          <p class="text-[11px] font-semibold text-[var(--color-ide-text-dim)] mb-2 uppercase tracking-wider">
            受限模式将禁用以下功能：
          </p>
          <div class="space-y-1.5">
            <div v-for="item in restrictedItems" :key="item.id"
              class="flex items-start gap-2.5 px-2.5 py-1.5 rounded-[4px] text-[12px]"
              style="background: rgba(239,68,68,0.06)">
              <component :is="item.icon" :size="13" class="shrink-0 mt-0.5" style="color: #ef4444" />
              <div>
                <span class="font-medium">{{ item.label }}</span>
                <span class="block text-[11px] opacity-50 mt-0.5">{{ item.desc }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="flex items-center justify-between p-4" style="border-top:1px solid var(--color-ide-border)">
          <button class="text-[11px] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors"
            @click="cancel">
            取消
          </button>
          <div class="flex gap-2">
            <button class="trust-btn secondary" @click="openRestricted">
              <ShieldOff :size="14" /> 受限模式打开
            </button>
            <button class="trust-btn primary" @click="trustAndOpen">
              <Shield :size="14" /> 信任此工作区
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.trust-overlay {
  position: fixed; inset: 0; z-index: 10000;
  background: rgba(0,0,0,0.55); display: flex; align-items: center; justify-content: center;
}
.trust-dialog {
  width: 480px; border-radius: 8px; border: 1px solid var(--color-ide-border);
  box-shadow: 0 12px 40px rgba(0,0,0,0.45); overflow: hidden;
}
.trust-btn {
  display: flex; align-items: center; gap: 6px; padding: 7px 16px;
  font-size: 12px; font-weight: 500; border-radius: 5px; border: none;
  cursor: pointer; transition: all 0.15s;
}
.trust-btn.primary { background: var(--color-ide-accent); color: white; }
.trust-btn.primary:hover { filter: brightness(1.15); }
.trust-btn.secondary { background: transparent; border: 1px solid var(--color-ide-border); color: var(--color-ide-text-dim); }
.trust-btn.secondary:hover { background: var(--color-ide-surface-hover); color: var(--color-ide-text); }
</style>
