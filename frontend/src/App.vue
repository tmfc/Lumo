<script setup>
import { computed, onMounted, ref } from 'vue'
import DocumentDetail from './components/DocumentDetail.vue'
import DocumentUpload from './components/DocumentUpload.vue'
import Sidebar from './components/Sidebar.vue'
import LoginForm from './components/LoginForm.vue'
import { documentApi, authApi, setAuthToken } from './api.js'

const createDefaultPagination = () => ({
  page: 1,
  pageSize: 10,
  totalPages: 1,
  totalItems: 0,
  hasNext: false,
  hasPrevious: false,
})

const activePage = ref('list')
const currentView = ref('list')
const filters = ['全部', '已完成', '处理中', '失败']
const activeFilter = ref('全部')
const searchTerm = ref('')
const loading = ref(false)
const error = ref('')
const uploading = ref(false)
const activeUploads = ref(0)
const uploadRef = ref(null)

const documents = ref([])
const detailDocument = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
const detailActionLoading = ref(false)
const pagination = ref(createDefaultPagination())

const isAuthenticated = ref(false)
const authToken = ref('')
const currentUser = ref(null)
const authLoading = ref(false)
const authError = ref('')

const statusTone = {
  已完成: 'status-success',
  处理中: 'status-warning',
  失败: 'status-danger',
}

const statusMap = {
  已完成: 'completed',
  处理中: 'pending',
  失败: 'failed',
}

const isUnauthorizedError = (err) => err?.status === 401 || err?.message === 'UNAUTHORIZED'

const resetViewState = () => {
  documents.value = []
  detailDocument.value = null
  detailError.value = ''
  detailLoading.value = false
  detailActionLoading.value = false
  loading.value = false
  error.value = ''
  uploading.value = false
  activeUploads.value = 0
  activeFilter.value = '全部'
  searchTerm.value = ''
  pagination.value = createDefaultPagination()
  activePage.value = 'list'
  currentView.value = 'list'
}

const persistAuthState = () => {
  if (authToken.value) {
    localStorage.setItem('lumo_auth_token', authToken.value)
    localStorage.setItem('lumo_auth_user', JSON.stringify(currentUser.value || {}))
  }
}

const handleLogout = async (silent = false) => {
  if (!silent && isAuthenticated.value) {
    try {
      await authApi.logout()
    } catch (err) {
      console.error('退出登录失败:', err)
    }
  }

  setAuthToken('')
  authToken.value = ''
  currentUser.value = null
  isAuthenticated.value = false
  localStorage.removeItem('lumo_auth_token')
  localStorage.removeItem('lumo_auth_user')
  resetViewState()

  if (!silent) {
    authError.value = ''
  }
}

const handleAuthExpired = async () => {
  await handleLogout(true)
  authError.value = '登录已过期，请重新登录'
}

const handleLogin = async ({ username, password }) => {
  authLoading.value = true
  authError.value = ''

  try {
    if (!username || !password) {
      throw new Error('请输入完整的登录信息')
    }

    const data = await authApi.login({ username, password })
    authToken.value = data?.token || ''
    currentUser.value = data?.user || { username }
    isAuthenticated.value = true
    setAuthToken(authToken.value)
    persistAuthState()
    resetViewState()
    await fetchDocuments()
  } catch (err) {
    authError.value = err?.message || '登录失败'
  } finally {
    authLoading.value = false
  }
}

const loadStoredSession = () => {
  const storedToken = localStorage.getItem('lumo_auth_token')
  if (storedToken) {
    authToken.value = storedToken
    setAuthToken(storedToken)
    isAuthenticated.value = true
    const storedUser = localStorage.getItem('lumo_auth_user')
    if (storedUser) {
      try {
        currentUser.value = JSON.parse(storedUser)
      } catch (err) {
        currentUser.value = { username: storedUser }
      }
    }
  } else {
    setAuthToken('')
  }
}

loadStoredSession()

const getStatusLabel = (doc) => doc.status_display || doc.status || '未知'
const getStatusClass = (doc) => statusTone[getStatusLabel(doc)] || 'status-warning'
const getName = (doc) => doc.original_name || doc.name || '未命名文件'
const getUploadedAt = (doc) => doc.uploaded_at || doc.created_at || doc.uploadedAt || ''

const filteredDocuments = computed(() => {
  const term = searchTerm.value.trim().toLowerCase()
  return documents.value.filter((doc) => {
    const statusLabel = getStatusLabel(doc)
    const docName = getName(doc).toLowerCase()
    const matchesFilter = activeFilter.value === '全部' || statusLabel === activeFilter.value
    const matchesSearch = !term || docName.includes(term)
    return matchesFilter && matchesSearch
  })
})

const setFilter = (filter) => {
  activeFilter.value = filter
  pagination.value.page = 1
  fetchDocuments()
}

const setPage = (page) => {
  activePage.value = page
  if (page === 'upload') {
    currentView.value = 'upload'
  } else if (page === 'list') {
    currentView.value = detailDocument.value ? 'detail' : 'list'
  } else {
    currentView.value = 'list'
  }
  if (page !== 'list') {
    detailDocument.value = null
    detailError.value = ''
  }
}

const pageNumbers = computed(() => {
  const total = pagination.value.totalPages || 1
  const current = pagination.value.page || 1

  if (total <= 7) {
    return Array.from({ length: total }, (_, index) => index + 1)
  }

  const siblings = 1
  let left = current - siblings
  let right = current + siblings

  if (left <= 2) {
    left = 2
    right = left + siblings * 2
  }

  if (right >= total - 1) {
    right = total - 1
    left = right - siblings * 2
  }

  left = Math.max(2, left)
  right = Math.min(total - 1, right)

  const pages = [1]

  if (left > 2) {
    pages.push('left-ellipsis')
  }

  for (let page = left; page <= right; page += 1) {
    pages.push(page)
  }

  if (right < total - 1) {
    pages.push('right-ellipsis')
  }

  pages.push(total)
  return pages
})

const fetchDocuments = async () => {
  if (!isAuthenticated.value) {
    documents.value = []
    return
  }

  loading.value = true
  error.value = ''

  try {
    const statusFilter = activeFilter.value === '全部' ? 'all' : statusMap[activeFilter.value]
    const params = {
      status: statusFilter,
      search: searchTerm.value,
      page: pagination.value.page,
      page_size: pagination.value.pageSize,
    }
    const response = await documentApi.getDocuments(params)
    const isLegacy = Array.isArray(response)
    const results = isLegacy
      ? response
      : Array.isArray(response?.results)
        ? response.results
        : []

    documents.value = results
    pagination.value = {
      page: isLegacy ? 1 : response?.page ?? pagination.value.page,
      pageSize: isLegacy
        ? results.length || pagination.value.pageSize
        : response?.page_size ?? pagination.value.pageSize,
      totalPages: Math.max(isLegacy ? 1 : response?.total_pages ?? 1, 1),
      totalItems: typeof response?.count === 'number' ? response.count : results.length,
      hasNext: isLegacy ? false : Boolean(response?.has_next),
      hasPrevious: isLegacy ? false : Boolean(response?.has_previous),
    }
  } catch (err) {
    console.error('获取文档失败:', err)
    if (isUnauthorizedError(err)) {
      await handleAuthExpired()
      return
    }
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const handleFileUpload = async ({ file, onProgress, onSuccess, onError } = {}) => {
  if (!file) return
  if (!isAuthenticated.value) {
    onError?.('请先登录')
    return
  }

  activeUploads.value += 1
  uploading.value = true
  error.value = ''

  try {
    await documentApi.uploadDocument(file, { onProgress })
    onSuccess?.()
    pagination.value.page = 1
    await fetchDocuments()
  } catch (err) {
    const message = err?.message || '上传失败'
    error.value = message
    if (isUnauthorizedError(err)) {
      await handleAuthExpired()
      onError?.('登录已过期，请重新登录')
    } else {
      onError?.(message)
    }
    console.error('上传失败:', err)
  } finally {
    activeUploads.value = Math.max(0, activeUploads.value - 1)
    if (activeUploads.value === 0) {
      uploading.value = false
    }
  }
}

const formatDate = (dateString) => {
  if (!dateString) return '--'
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatFileSize = (bytes) => {
  if (!bytes && bytes !== 0) return '--'
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
}

let searchTimeout
const handleSearch = () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    pagination.value.page = 1
    fetchDocuments()
  }, 400)
}

const handleSearchInput = (event) => {
  searchTerm.value = event.target.value
  handleSearch()
}

const openUploadPicker = () => {
  if (activePage.value !== 'upload') {
    activePage.value = 'upload'
    currentView.value = 'upload'
  }
  uploadRef.value?.openFilePicker()
}

const openDocumentDetail = async (id) => {
  if (!id) return
  if (!isAuthenticated.value) return
  detailError.value = ''
  detailLoading.value = true
  currentView.value = 'detail'

  try {
    detailDocument.value = await documentApi.getDocument(id)
  } catch (err) {
    console.error('加载文档详情失败:', err)
    if (isUnauthorizedError(err)) {
      await handleAuthExpired()
      return
    }
    detailError.value = err.message
  } finally {
    detailLoading.value = false
  }
}

const closeDetailView = () => {
  detailDocument.value = null
  detailError.value = ''
  if (activePage.value === 'list') {
    currentView.value = 'list'
  } else {
    currentView.value = activePage.value
  }
}

const handleReprocessDocument = async () => {
  if (!detailDocument.value?.id) return
  if (!isAuthenticated.value) return
  detailActionLoading.value = true
  detailError.value = ''
  try {
    await documentApi.reprocessDocument(detailDocument.value.id)
    await fetchDocuments()
    await openDocumentDetail(detailDocument.value.id)
  } catch (err) {
    console.error('重新处理失败:', err)
    if (isUnauthorizedError(err)) {
      await handleAuthExpired()
      return
    }
    detailError.value = err.message
  } finally {
    detailActionLoading.value = false
  }
}

const handleDeleteDocument = async (id) => {
  if (!id) return
  if (!isAuthenticated.value) return
  if (!confirm('确定要删除这个文档吗？')) {
    return
  }

  try {
    await documentApi.deleteDocument(id)
    await fetchDocuments()
    if (detailDocument.value?.id === id) {
      closeDetailView()
    }
  } catch (err) {
    console.error('删除失败:', err)
    if (isUnauthorizedError(err)) {
      await handleAuthExpired()
      return
    }
    error.value = err.message
  }
}

const goToPreviousPage = () => {
  if (!pagination.value.hasPrevious && pagination.value.page <= 1) return
  pagination.value.page = Math.max(1, pagination.value.page - 1)
  fetchDocuments()
}

const goToNextPage = () => {
  if (!pagination.value.hasNext && pagination.value.page >= pagination.value.totalPages) return
  pagination.value.page = Math.min(pagination.value.totalPages, pagination.value.page + 1)
  fetchDocuments()
}

const handlePageButtonClick = (pageNumber) => {
  if (typeof pageNumber !== 'number' || pageNumber === pagination.value.page) return
  pagination.value.page = pageNumber
  fetchDocuments()
}

onMounted(() => {
  if (isAuthenticated.value) {
    fetchDocuments()
  }
})
</script>

<template>
  <div class="app-root">
    <div v-if="!isAuthenticated" class="auth-screen">
      <div class="auth-panel">
        <div class="auth-hero">
          <div class="auth-icon">
            <span>R</span>
          </div>
          <div>
            <p class="auth-hero-title">RAG Admin</p>
            <p class="auth-hero-subtitle">登录后管理上传的文档与索引</p>
          </div>
        </div>
        <LoginForm :loading="authLoading" :error="authError" @submit="handleLogin" />
      </div>
    </div>

    <div v-else class="app-shell">
      <Sidebar :active-page="activePage" @change="setPage" />
      <div class="main">
        <header class="topbar">
          <div class="topbar-left">
            <template v-if="currentView === 'upload'">
              <h1 class="topbar-title">文档上传</h1>
            </template>
            <template v-else-if="currentView === 'detail'">
              <button class="back-link" type="button" @click="closeDetailView">
                <svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <path fill="currentColor" d="m14.7 6.3-1.4-1.4L6.2 12l7.1 7.1 1.4-1.4L9 12l5.7-5.7Z" />
                </svg>
                <span>返回文档列表</span>
              </button>
              <div class="detail-heading">
                <h1 class="topbar-title">文档详情</h1>
                <p class="topbar-subtitle">{{ detailDocument?.original_name || '加载中...' }}</p>
              </div>
            </template>
            <template v-else>
              <label class="search">
                <svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <path
                    fill="currentColor"
                    d="M15.8 14.4a6.2 6.2 0 1 0-1.4 1.4l3.7 3.7a1 1 0 0 0 1.4-1.4l-3.7-3.7ZM11 15.2a4.2 4.2 0 1 1 0-8.4 4.2 4.2 0 0 1 0 8.4Z"
                  />
                </svg>
                <input :value="searchTerm" placeholder="搜索文件名..." @input="handleSearchInput" />
              </label>
            </template>
          </div>
          <div class="topbar-right">
            <div class="topbar-actions">
              <template v-if="currentView === 'detail' && detailDocument">
                <button class="danger-button" type="button" @click="handleDeleteDocument(detailDocument.id)">
                  <svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path
                      fill="currentColor"
                      d="M10 4a1 1 0 0 0-1 1v1H5.5a.75.75 0 0 0 0 1.5h.47l.73 9.1A2.25 2.25 0 0 0 8.95 19h6.1a2.25 2.25 0 0 0 2.25-2.4l.73-9.1h.47a.75.75 0 0 0 0-1.5H15V5a1 1 0 0 0-1-1h-4Zm3 2.5V5.5h-2v1h2Zm-4.98 1.5h6.96l-.7 8.5a.75.75 0 0 1-.75.69H8.95a.75.75 0 0 1-.75-.69l-.7-8.5Z"
                    />
                  </svg>
                  <span>删除文档</span>
                </button>
              </template>
              <template v-else>
                <button v-if="activePage === 'list'" class="primary-button" type="button" @click="openUploadPicker">
                  <svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path
                      fill="currentColor"
                      d="M12.75 6a.75.75 0 0 0-1.5 0v5.25H6a.75.75 0 0 0 0 1.5h5.25V18a.75.75 0 0 0 1.5 0v-5.25H18a.75.75 0 0 0 0-1.5h-5.25Z"
                    />
                  </svg>
                  <span>上传新文档</span>
                </button>
                <button v-else class="primary-button" type="button" @click="openUploadPicker">
                  <svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path
                      fill="currentColor"
                      d="M11 4a1 1 0 0 0-1 1v6.17L8.4 9.6a1 1 0 1 0-1.4 1.42l3.29 3.3c.4.4 1.02.4 1.42 0l3.3-3.3a1 1 0 0 0-1.42-1.41L13 11.18V5a1 1 0 0 0-1-1Zm-5 9a5 5 0 0 1 9.9-.8 3.5 3.5 0 1 1 1.48 6.79H7.5A3.5 3.5 0 0 1 6 13Z"
                    />
                  </svg>
                  <span>上传</span>
                </button>
              </template>
            </div>
            <div class="user-menu">
              <div class="user-meta">
                <span class="user-name">{{ currentUser?.username || '管理员' }}</span>
              </div>
              <button class="ghost-button" type="button" @click="handleLogout()">退出</button>
            </div>
          </div>
        </header>

        <main class="content">
        <div v-if="currentView === 'list'" class="content-inner">
          <div class="content-head">
            <h1 class="page-title">文档列表</h1>
          </div>

          <div class="filters">
            <button
              v-for="filter in filters"
              :key="filter"
              class="filter-chip"
              :class="{ active: activeFilter === filter }"
              type="button"
              @click="setFilter(filter)"
            >
              {{ filter }}
            </button>
          </div>

          <div class="table-card">
            <div class="table-scroll">
              <table class="doc-table">
                <thead>
                  <tr>
                    <th class="table-col-filename">文件名</th>
                    <th class="table-col-upload-time">上传时间</th>
                    <th class="table-col-status">状态</th>
                    <th class="table-col-actions">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="doc in filteredDocuments" :key="doc.id || getName(doc)">
                    <td class="doc-name table-col-filename">
                      <div class="doc-name-wrap">
                        <span class="doc-name-text">{{ getName(doc) }}</span>
                        <span class="doc-meta">{{ formatFileSize(doc.file_size) }}</span>
                      </div>
                    </td>
                    <td class="doc-time table-col-upload-time">{{ formatDate(getUploadedAt(doc)) }}</td>
                    <td class="table-col-status">
                      <span class="status-pill" :class="getStatusClass(doc)">
                        <span class="status-dot" />
                        {{ getStatusLabel(doc) }}
                      </span>
                    </td>
                    <td class="table-col-actions">
                      <div class="table-actions">
                        <button class="table-link primary" type="button" @click="openDocumentDetail(doc.id)">查看详情</button>
                        <button class="table-link danger" type="button" @click="handleDeleteDocument(doc.id)">删除</button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="!filteredDocuments.length && !loading">
                    <td colspan="4" class="empty-row">暂无文档</td>
                  </tr>
                  <tr v-if="loading">
                    <td colspan="4" class="empty-row">加载中...</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="error" class="error-banner">
            {{ error }}
          </div>

          <div v-if="pagination.totalPages > 1" class="pagination">
            <div class="pagination-inner">
              <button
                class="page-btn"
                type="button"
                aria-label="上一页"
                :disabled="!pagination.hasPrevious && pagination.page <= 1"
                @click="goToPreviousPage"
              >
                <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path fill="currentColor" d="m14.7 6.3-1.4-1.4L6.2 12l7.1 7.1 1.4-1.4L9 12l5.7-5.7Z" />
                </svg>
              </button>

              <template v-for="item in pageNumbers" :key="typeof item === 'string' ? item : `page-${item}`">
                <span v-if="typeof item === 'string'" class="page-ellipsis">...</span>
                <button
                  v-else
                  class="page-btn"
                  :class="{ active: item === pagination.page }"
                  type="button"
                  :disabled="item === pagination.page"
                  @click="handlePageButtonClick(item)"
                >
                  {{ item }}
                </button>
              </template>

              <button
                class="page-btn"
                type="button"
                aria-label="下一页"
                :disabled="!pagination.hasNext && pagination.page >= pagination.totalPages"
                @click="goToNextPage"
              >
                <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path fill="currentColor" d="M9.3 17.7 10.7 19 18 11.8 10.7 4.5 9.3 5.9 14.6 11 9.3 16.3Z" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <div v-else-if="currentView === 'detail'" class="content-inner detail-container">
          <DocumentDetail
            :document="detailDocument"
            :loading="detailLoading"
            :error="detailError"
            :action-loading="detailActionLoading"
            @reprocess="handleReprocessDocument"
          />
        </div>

        <div v-else class="content-inner">
          <DocumentUpload ref="uploadRef" @upload="handleFileUpload" />
        </div>
        </main>
      </div>
    </div>
  </div>
</template>
