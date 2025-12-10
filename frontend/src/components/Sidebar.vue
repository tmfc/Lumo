<script setup>
const props = defineProps({
  activePage: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['change'])

const navItems = [
  {
    key: 'list',
    label: '文档管理',
    paths: [
      'M6 4.75A1.75 1.75 0 0 0 4.25 6.5v11A1.75 1.75 0 0 0 6 19.25h12A1.75 1.75 0 0 0 19.75 17.5v-11A1.75 1.75 0 0 0 18 4.75H6ZM6.5 7h11v7.75a.75.75 0 0 1-.75.75H7.25a.75.75 0 0 1-.75-.75V7Zm7.25 8.75v-1.5h3v1.5h-3Z',
    ],
  },
  {
    key: 'upload',
    label: '文档上传',
    paths: [
      'M11.25 17a.75.75 0 0 0 1.5 0V9.56l1.97 1.97a.75.75 0 1 0 1.06-1.06l-3.25-3.25a.75.75 0 0 0-1.06 0L6.22 10.47a.75.75 0 0 0 1.06 1.06L9.25 9.56V17Zm-4.5 2.75a.75.75 0 0 1-.75-.75v-2a.75.75 0 0 1 1.5 0v1.25h9V17a.75.75 0 0 1 1.5 0v2a.75.75 0 0 1-.75.75h-10.5Z',
    ],
  },
  {
    key: 'settings',
    label: '设置',
    paths: [
      'M12 8.25a3.75 3.75 0 1 0 0 7.5 3.75 3.75 0 0 0 0-7.5Zm-1-6.5a1 1 0 0 0-1 1v1.11a7.52 7.52 0 0 0-2.2 1.27L6.09 4.52a1 1 0 0 0-1.42 1.42l1.61 1.61a7.52 7.52 0 0 0-1.27 2.2H3a1 1 0 0 0 0 2h1.11a7.52 7.52 0 0 0 1.27 2.2l-1.6 1.6a1 1 0 1 0 1.41 1.42l1.6-1.6a7.52 7.52 0 0 0 2.2 1.27V20a1 1 0 1 0 2 0v-1.11a7.52 7.52 0 0 0 2.2-1.27l1.6 1.6a1 1 0 0 0 1.41-1.42l-1.6-1.6a7.52 7.52 0 0 0 1.27-2.2H21a1 1 0 1 0 0-2h-1.11a7.52 7.52 0 0 0-1.27-2.2l1.6-1.6A1 1 0 0 0 18.8 4.5l-1.6 1.6a7.52 7.52 0 0 0-2.2-1.27V2.75a1 1 0 0 0-1-1h-2Z',
    ],
  },
]

const handleClick = (key) => {
  emit('change', key)
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" class="nav-icon">
          <path d="M3 15.5V4.5L10 1l7 3.5v11l-7 3.5-7-3.5Z" stroke="currentColor" stroke-width="1.4" />
          <path d="M5.5 6.5 10 4l4.5 2.5V10l-4.5 2.5L5.5 10V6.5Z" fill="currentColor" />
        </svg>
      </div>
      <span>RAG Admin</span>
    </div>
    <nav class="nav" aria-label="主导航">
      <button
        v-for="item in navItems"
        :key="item.key"
        class="nav-item"
        :class="{ active: activePage === item.key }"
        type="button"
        @click="handleClick(item.key)"
      >
        <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path v-for="path in item.paths" :key="path" fill="currentColor" :d="path" />
        </svg>
        <span>{{ item.label }}</span>
      </button>
    </nav>
  </aside>
</template>
