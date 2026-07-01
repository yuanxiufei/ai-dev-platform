import { createRouter, createWebHistory } from "vue-router"

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
      redirect: "/chat",
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
      path: "/:pathMatch(.*)*",
      redirect: "/chat",
    },
  ],
})

export default router

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (!token && to.path !== '/login') {
    return '/login'
  }
  if (token && to.path === '/login') {
    return '/chat'
  }
})
