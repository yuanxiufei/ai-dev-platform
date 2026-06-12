import type { RouteRecordRaw } from 'vue-router'

export const desktopRoutes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('../pages/home/HomeDesktop.vue'),
  },
  {
    path: '/gallery',
    name: 'gallery',
    component: () => import('../pages/gallery/GalleryDesktop.vue'),
  },
  {
    path: '/play/:id',
    name: 'player',
    component: () => import('../pages/player/PlayerDesktop.vue'),
  },
]
