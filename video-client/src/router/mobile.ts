import type { RouteRecordRaw } from 'vue-router'

export const mobileRoutes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('../pages/home/HomeMobile.vue'),
  },
  {
    path: '/gallery',
    name: 'gallery',
    component: () => import('../pages/gallery/GalleryMobile.vue'),
  },
  {
    path: '/play/:id',
    name: 'player',
    component: () => import('../pages/player/PlayerMobile.vue'),
  },
]
