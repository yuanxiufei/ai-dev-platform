import { createRouter, createWebHistory } from 'vue-router'
import { isMobileDevice } from './deviceGuard'
import { mobileRoutes } from './mobile'
import { desktopRoutes } from './desktop'

const router = createRouter({
  history: createWebHistory(),
  routes: isMobileDevice() ? mobileRoutes : desktopRoutes,
})

export default router
