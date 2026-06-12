import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/projects',
    },
    {
      path: '/projects',
      name: 'projects',
      component: () => import('@/pages/projects/ProjectList.vue'),
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
      path: '/deployments',
      name: 'deployments',
      component: () => import('@/pages/deployments/DeployList.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/projects',
    },
  ],
})

export default router
