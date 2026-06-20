import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/chat',
    },
    {
      path: '/chat',
      name: 'agent-chat',
      component: () => import('@/pages/tools/AgentChat.vue'),
    },
    {
      path: '/projects',
      name: 'projects',
      component: () => import('@/pages/projects/ProjectList.vue'),
    },
    {
      path: '/projects/new',
      name: 'project-new',
      component: () => import('@/pages/projects/ProjectNew.vue'),
    },
    {
      path: '/projects/:id',
      name: 'project-detail',
      component: () => import('@/pages/projects/ProjectDetail.vue'),
    },
    {
      path: '/templates',
      name: 'templates',
      component: () => import('@/pages/templates/TemplateList.vue'),
    },
    {
      path: '/knowledge',
      name: 'knowledge',
      component: () => import('@/pages/knowledge/KnowledgeBaseList.vue'),
    },
    {
      path: '/mcp',
      name: 'mcp-servers',
      component: () => import('@/pages/mcp/MCPServerList.vue'),
    },
    {
      path: '/tools',
      name: 'tools',
      component: () => import('@/pages/tools/ToolManager.vue'),
    },
    {
      path: '/plugins',
      name: 'plugin-marketplace',
      component: () => import('@/pages/plugins/PluginMarketplace.vue'),
    },
    {
      path: '/plugins/manage',
      name: 'plugin-manage',
      component: () => import('@/pages/plugins/PluginManager.vue'),
    },
    {
      path: '/presets',
      name: 'model-presets',
      component: () => import('@/pages/features/ModelPresets.vue'),
    },
    {
      path: '/arena',
      name: 'model-arena',
      component: () => import('@/pages/features/ModelArena.vue'),
    },
    {
      path: '/analytics',
      name: 'analytics-dashboard',
      component: () => import('@/pages/features/AnalyticsDashboard.vue'),
    },
    {
      path: '/memory',
      name: 'memory-manager',
      component: () => import('@/pages/features/MemoryManager.vue'),
    },
    {
      path: '/structured-output',
      name: 'structured-output',
      component: () => import('@/pages/features/StructuredOutput.vue'),
    },
    {
      path: '/image-gen',
      name: 'image-gen',
      component: () => import('@/pages/features/ImageGen.vue'),
    },
    {
      path: '/voice',
      name: 'voice-manager',
      component: () => import('@/pages/features/VoiceManager.vue'),
    },
    {
      path: '/webhooks',
      name: 'webhook-manager',
      component: () => import('@/pages/features/WebhookManager.vue'),
    },
    {
      path: '/skills',
      name: 'skills-manager',
      component: () => import('@/pages/features/SkillsManager.vue'),
    },
    {
      path: '/prompt-templates',
      name: 'prompt-templates',
      component: () => import('@/pages/features/PromptTemplates.vue'),
    },
    {
      path: '/tasks',
      name: 'task-manager',
      component: () => import('@/pages/features/TaskManager.vue'),
    },
    {
      path: '/openapi',
      name: 'openapi-discovery',
      component: () => import('@/pages/features/OpenAPIDiscovery.vue'),
    },
    {
      path: '/knowledge-graph',
      name: 'knowledge-graph',
      component: () => import('@/pages/features/KnowledgeGraph.vue'),
    },
    {
      path: '/deployments',
      name: 'deployments',
      component: () => import('@/pages/deployments/DeployList.vue'),
    },
    {
      path: '/screenshot-to-code',
      name: 'screenshot-to-code',
      component: () => import('@/pages/tools/ScreenshotToCode.vue'),
    },
    {
      path: '/system',
      name: 'system-dashboard',
      component: () => import('@/pages/system/SystemDashboard.vue'),
    },
    {
      path: '/storage',
      name: 'storage-settings',
      component: () => import('@/pages/system/StorageSettings.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/projects',
    },
  ],
})

export default router
