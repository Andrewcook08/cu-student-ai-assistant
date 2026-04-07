import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'course-search',
      component: () => import('../views/CourseSearchView.vue'),
    },
  ],
})

export default router
