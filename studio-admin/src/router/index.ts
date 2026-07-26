import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/pages/auth/LoginPage.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/',
      component: () => import('@/components/layout/AppLayout.vue'),
      redirect: '/chat',
      meta: { requiresAuth: true },
      children: [
        {
          path: 'chat',
          name: 'agent-chat',
          component: () => import('@/pages/tools/AgentChat.vue'),
        },
        {
          path: 'projects',
          name: 'projects',
          component: () => import('@/pages/projects/ProjectList.vue'),
        },
        {
          path: 'projects/new',
          name: 'project-new',
          component: () => import('@/pages/projects/ProjectNew.vue'),
        },
        {
          path: 'projects/:id',
          name: 'project-detail',
          component: () => import('@/pages/projects/ProjectDetail.vue'),
        },
        {
          path: 'templates',
          name: 'templates',
          component: () => import('@/pages/templates/TemplateList.vue'),
        },
        {
          path: 'knowledge',
          name: 'knowledge',
          component: () => import('@/pages/knowledge/KnowledgeBaseList.vue'),
        },
        {
          path: 'knowledge/:id',
          name: 'knowledge-detail',
          component: () => import('@/pages/knowledge/KnowledgeBaseDetail.vue'),
        },
        {
          path: 'rag-test',
          name: 'rag-test',
          component: () => import('@/pages/knowledge/RAGTest.vue'),
        },
        {
          path: 'mcp',
          name: 'mcp-servers',
          component: () => import('@/pages/mcp/MCPServerList.vue'),
        },
        {
          path: 'tools',
          name: 'tools',
          component: () => import('@/pages/tools/ToolManager.vue'),
        },
        {
          path: 'plugins',
          name: 'plugin-marketplace',
          component: () => import('@/pages/plugins/PluginMarketplace.vue'),
        },
        {
          path: 'plugins/manage',
          name: 'plugin-manage',
          component: () => import('@/pages/plugins/PluginManager.vue'),
        },
        {
          path: 'presets',
          name: 'model-presets',
          component: () => import('@/pages/features/ModelPresets.vue'),
        },
        {
          path: 'arena',
          name: 'model-arena',
          component: () => import('@/pages/features/ModelArena.vue'),
        },
        {
          path: 'analytics',
          name: 'analytics-dashboard',
          component: () => import('@/pages/features/AnalyticsDashboard.vue'),
        },
        {
          path: 'memory',
          name: 'memory-manager',
          component: () => import('@/pages/features/MemoryManager.vue'),
        },
        {
          path: 'structured-output',
          name: 'structured-output',
          component: () => import('@/pages/features/StructuredOutput.vue'),
        },
        {
          path: 'image-gen',
          name: 'image-gen',
          component: () => import('@/pages/features/ImageGen.vue'),
        },
        {
          path: 'voice',
          name: 'voice-manager',
          component: () => import('@/pages/features/VoiceManager.vue'),
        },
        {
          path: 'webhooks',
          name: 'webhook-manager',
          component: () => import('@/pages/features/WebhookManager.vue'),
        },
        {
          path: 'skills',
          name: 'skills-manager',
          component: () => import('@/pages/features/SkillsManager.vue'),
        },
        {
          path: 'prompt-templates',
          name: 'prompt-templates',
          component: () => import('@/pages/features/PromptTemplates.vue'),
        },
        {
          path: 'tasks',
          name: 'task-manager',
          component: () => import('@/pages/features/TaskManager.vue'),
        },
        {
          path: 'openapi',
          name: 'openapi-discovery',
          component: () => import('@/pages/features/OpenAPIDiscovery.vue'),
        },
        {
          path: 'knowledge-graph',
          name: 'knowledge-graph',
          component: () => import('@/pages/features/KnowledgeGraph.vue'),
        },
        {
          path: 'deployments',
          name: 'deployments',
          component: () => import('@/pages/deployments/DeployList.vue'),
        },
        {
          path: 'screenshot-to-code',
          name: 'screenshot-to-code',
          component: () => import('@/pages/tools/ScreenshotToCode.vue'),
        },
        {
          path: 'system',
          name: 'system-dashboard',
          component: () => import('@/pages/system/SystemDashboard.vue'),
        },
        {
          path: 'storage',
          name: 'storage-settings',
          component: () => import('@/pages/system/StorageSettings.vue'),
        },
        {
          path: 'models',
          name: 'model-manager',
          component: () => import('@/pages/system/ModelManager.vue'),
        },
        {
          path: ':pathMatch(.*)*',
          redirect: '/projects',
        },
      ],
    },
  ],
})

// 路由守卫：未登录 → /login；已登录访问 /login → /
router.beforeEach((to, _from) => {
  const token = localStorage.getItem('token')

  if (to.path === '/login') {
    if (token) return '/'
    return
  }

  if (to.meta.requiresAuth !== false && !token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
})

export default router
