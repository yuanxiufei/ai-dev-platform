import { createRouter, createWebHistory } from "vue-router"
import { useAuthStore } from "@/stores/useAuthStore"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/pages/LoginPage.vue"),
    },
    {
      path: "/",
      redirect: "/projects",
    },
    {
      path: "/chat",
      name: "chat",
      component: () => import("@/pages/AgentChat.vue"),
    },
    {
      path: "/projects",
      name: "projects",
      component: () => import("@/pages/ProjectList.vue"),
    },
    {
      path: "/projects/new",
      name: "project-new",
      component: () => import("@/pages/ProjectNew.vue"),
    },
    {
      path: "/projects/:id",
      name: "project-detail",
      component: () => import("@/pages/ProjectDetail.vue"),
    },
    {
      path: "/knowledge",
      name: "knowledge",
      component: () => import("@/pages/KnowledgeBase.vue"),
    },
    {
      path: "/knowledge/:id",
      name: "knowledge-detail",
      component: () => import("@/pages/KnowledgeBaseDetail.vue"),
    },
    {
      path: "/knowledge/:id/hit-test",
      name: "knowledge-hit-test",
      component: () => import("@/pages/HitTesting.vue"),
    },
    {
      path: "/tools",
      name: "tools",
      component: () => import("@/pages/ToolsBrowser.vue"),
    },
    {
      path: "/plugins",
      name: "plugin-marketplace",
      component: () => import("@/pages/PluginMarketplace.vue"),
    },
    {
      path: "/arena",
      name: "arena",
      component: () => import("@/pages/ArenaPage.vue"),
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("@/pages/SettingsPage.vue"),
    },
    {
      path: "/jobs",
      name: "jobs",
      component: () => import("@/pages/ScheduledJobsPage.vue"),
    },
    {
      path: "/workflow",
      name: "workflow",
      component: () => import("@/pages/WorkflowPage.vue"),
    },
    {
      path: "/group-chat",
      name: "group-chat",
      component: () => import("@/pages/GroupChatPage.vue"),
    },
    {
      path: "/kanban",
      name: "kanban",
      component: () => import("@/pages/KanbanPage.vue"),
    },
    {
      path: "/memory",
      name: "memory",
      component: () => import("@/pages/MemoryPage.vue"),
    },
    {
      path: "/mcp",
      name: "mcp-settings",
      component: () => import("@/pages/MCPSettings.vue"),
    },
    {
      path: "/skills",
      name: "skills",
      component: () => import("@/pages/SkillsPage.vue"),
    },
    {
      path: "/image-gen",
      name: "image-gen",
      component: () => import("@/pages/ImageGenPage.vue"),
    },
    {
      path: "/prompt-templates",
      name: "prompt-templates",
      component: () => import("@/pages/PromptTemplatesPage.vue"),
    },
    {
      path: "/screenshot-to-code",
      name: "screenshot-to-code",
      component: () => import("@/pages/ScreenshotToCode.vue"),
    },
    {
      path: "/templates",
      name: "templates-browse",
      component: () => import("@/pages/TemplatesBrowse.vue"),
    },
    {
      path: "/voice",
      name: "voice-page",
      component: () => import("@/pages/VoicePage.vue"),
    },
    {
      path: "/analytics",
      name: "analytics-page",
      component: () => import("@/pages/AnalyticsPage.vue"),
    },
    {
      path: "/structured-output",
      name: "structured-output",
      component: () => import("@/pages/StructuredOutputPage.vue"),
    },
    {
      path: "/webhooks",
      name: "webhooks",
      component: () => import("@/pages/WebhookPage.vue"),
    },
    {
      path: "/openapi",
      name: "openapi-discovery",
      component: () => import("@/pages/OpenAPIPage.vue"),
    },
    {
      path: "/knowledge-graph",
      name: "knowledge-graph",
      component: () => import("@/pages/KnowledgeGraphPage.vue"),
    },
    {
      path: "/trajectory",
      name: "trajectory",
      component: () => import("@/pages/TrajectoryPage.vue"),
    },
    {
      path: "/traces",
      name: "agent-traces",
      component: () => import("@/pages/AgentTraces.vue"),
    },
    {
      path: "/traces/:traceId",
      name: "agent-trace-detail",
      component: () => import("@/pages/AgentTraceDetail.vue"),
    },
    {
      path: "/reflection",
      name: "agent-reflection",
      component: () => import("@/pages/AgentReflection.vue"),
    },
    {
      path: "/worktree",
      name: "worktree",
      component: () => import("@/pages/WorktreeManager.vue"),
    },
    {
      path: "/sessions",
      name: "session-summary",
      component: () => import("@/pages/SessionSummary.vue"),
    },
    {
      path: "/ckg",
      name: "code-kg",
      component: () => import("@/pages/CodeKnowledgeGraph.vue"),
    },
    {
      path: "/backup",
      name: "backup",
      component: () => import("@/pages/BackupManager.vue"),
    },
    {
      path: "/feature-flags",
      name: "feature-flags",
      component: () => import("@/pages/FeatureFlags.vue"),
    },
    {
      path: "/benchmarks",
      name: "benchmarks",
      component: () => import("@/pages/BenchmarksPage.vue"),
    },
    {
      path: "/catalog",
      name: "model-catalog",
      component: () => import("@/pages/ModelCatalog.vue"),
    },
    {
      path: "/cli-pipeline",
      name: "cli-pipeline",
      component: () => import("@/pages/CLIPipeline.vue"),
    },
    {
      path: "/config-resolver",
      name: "config-resolver",
      component: () => import("@/pages/ConfigResolver.vue"),
    },
    {
      path: "/state",
      name: "state-manager",
      component: () => import("@/pages/StateManager.vue"),
    },
    {
      path: "/remote-sessions",
      name: "remote-sessions",
      component: () => import("@/pages/RemoteSessions.vue"),
    },
    {
      path: "/cli-history",
      name: "cli-history",
      component: () => import("@/pages/CLIHistoryPage.vue"),
    },
    {
      path: "/memory-graph",
      name: "memory-graph",
      component: () => import("@/pages/MemoryGraph.vue"),
    },
    {
      path: "/problem-matchers",
      name: "problem-matchers",
      component: () => import("@/pages/ProblemMatchers.vue"),
    },
    {
      path: "/storage",
      name: "storage-settings",
      component: () => import("@/pages/StorageSettings.vue"),
    },
    {
      path: "/integrations",
      name: "integrations",
      component: () => import("@/pages/IntegrationsPage.vue"),
    },
    {
      path: "/rules",
      name: "rules",
      component: () => import("@/pages/RulesPage.vue"),
    },
    {
      path: "/agents",
      name: "agents",
      component: () => import("@/pages/AgentsPage.vue"),
    },
    {
      path: "/standalone",
      name: "standalone",
      component: () => import("@/pages/StandaloneDashboard.vue"),
    },
    {
      path: "/keybindings",
      name: "keybindings",
      component: () => import("@/pages/KeybindingsPage.vue"),
    },
    {
      path: "/snippets",
      name: "snippets",
      component: () => import("@/components/ide/SnippetsPanel.vue"),
    },
    /* ===== 系统工具页面 (7 个新API模块) ===== */
    {
      path: "/models",
      name: "model-manager",
      component: () => import("@/pages/ModelManager.vue"),
    },
    {
      path: "/gpu",
      name: "gpu-monitor",
      component: () => import("@/pages/GpuMonitor.vue"),
    },
    {
      path: "/global-search",
      name: "global-search",
      component: () => import("@/pages/GlobalSearchPage.vue"),
    },
    {
      path: "/file-explorer",
      name: "file-explorer",
      component: () => import("@/pages/FileExplorerPage.vue"),
    },
    {
      path: "/diagnostics",
      name: "diagnostics",
      component: () => import("@/pages/DiagnosticsPage.vue"),
    },
    {
      path: "/terminal",
      name: "terminal-page",
      component: () => import("@/pages/TerminalPage.vue"),
    },
    {
      path: "/testing",
      name: "testing-page",
      component: () => import("@/pages/TestingPage.vue"),
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: "/projects",
    },
  ],
})

export default router

router.beforeEach((to) => {
  const authStore = useAuthStore()
  if (!authStore.isAuthenticated && to.path !== '/login') {
    return '/login'
  }
  if (authStore.isAuthenticated && to.path === '/login') {
    return '/projects'
  }
})
