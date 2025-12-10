<script setup>
import { ref } from 'vue'

const emit = defineEmits(['upload'])

const isDragActive = ref(false)
const fileInput = ref(null)
const uploads = ref([])

const statusLabel = {
  success: '已完成',
  uploading: (progress) => (Number.isFinite(progress) ? `${progress}%` : '上传中'),
  failed: '上传失败',
  pending: '排队中',
}

const statusColor = {
  success: 'status-success',
  uploading: 'status-uploading',
  failed: 'status-danger',
  pending: 'status-warning',
}

const createUploadId = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

const updateUpload = (id, payload) => {
  uploads.value = uploads.value.map((item) => (item.id === id ? { ...item, ...payload } : item))
}

const startUpload = (file) => {
  const uploadItem = {
    id: createUploadId(),
    name: file.name,
    progress: 0,
    status: 'pending',
    error: '',
  }
  uploads.value = [uploadItem, ...uploads.value]

  const safeUpdate = (payload) => updateUpload(uploadItem.id, payload)

  emit('upload', {
    file,
    onProgress: (progress) => {
      safeUpdate({
        progress,
        status: 'uploading',
      })
    },
    onSuccess: () => {
      safeUpdate({
        progress: 100,
        status: 'success',
        error: '',
      })
    },
    onError: (message) => {
      safeUpdate({
        status: 'failed',
        error: message || '上传失败',
      })
    },
  })

  safeUpdate({ status: 'uploading' })
}

const openFilePicker = () => {
  fileInput.value?.click()
}

const handleFiles = (fileList) => {
  const files = Array.from(fileList || [])
  files.forEach(startUpload)
}

const onFileChange = (event) => {
  handleFiles(event.target.files)
  event.target.value = ''
}

const onDrop = (event) => {
  event.preventDefault()
  event.stopPropagation()
  isDragActive.value = false
  handleFiles(event.dataTransfer.files)
}

const onDragOver = (event) => {
  event.preventDefault()
  isDragActive.value = true
}

const onDragLeave = (event) => {
  event.preventDefault()
  isDragActive.value = false
}

defineExpose({
  openFilePicker,
})
</script>

<template>
  <section class="upload-section">
    <div
      class="dropzone"
      :class="{ 'dropzone--active': isDragActive }"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <div class="dropzone-inner">
        <div class="dropzone-icon">
          <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
            <path
              fill="currentColor"
              d="M11 4a1 1 0 0 0-1 1v6.17L8.4 9.6a1 1 0 1 0-1.4 1.42l3.29 3.3c.4.4 1.02.4 1.42 0l3.3-3.3a1 1 0 0 0-1.42-1.41L13 11.18V5a1 1 0 0 0-1-1Zm-5 9a5 5 0 0 1 9.9-.8 3.5 3.5 0 1 1 1.48 6.79H7.5A3.5 3.5 0 0 1 6 13Z"
            />
          </svg>
        </div>
        <p class="dropzone-title">拖拽文件到这里</p>
        <p class="dropzone-subtitle">支持 PDF, DOCX, TXT, MD 等格式</p>
        <button class="secondary-button" type="button" @click="openFilePicker">选择文件</button>
        <input ref="fileInput" class="sr-only" type="file" multiple @change="onFileChange" />
      </div>
    </div>

    <div class="upload-list">
      <div class="upload-list-head">
        <h2>上传列表</h2>
      </div>
      <div class="upload-items">
        <div v-for="item in uploads" :key="item.id" class="upload-item">
          <div class="upload-icon" :class="statusColor[item.status]">
            <svg v-if="item.status === 'success'" class="icon" viewBox="0 0 24 24" aria-hidden="true">
              <path fill="currentColor" d="m10.2 16.2 8-8-1.4-1.4-6.6 6.6-3-3-1.4 1.4 4.4 4.4Z" />
            </svg>
            <svg v-else-if="item.status === 'failed'" class="icon" viewBox="0 0 24 24" aria-hidden="true">
              <path fill="currentColor" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 14h-2v-2h2v2Zm0-4h-2V6h2v6Z" />
            </svg>
            <svg v-else class="icon" viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="currentColor"
                d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm-.75 4.5h1.5v6.1l3.37 1.94-.75 1.3-4.12-2.36V6.5Z"
              />
            </svg>
          </div>
          <div class="upload-body">
            <p class="upload-name">{{ item.name }}</p>
            <div class="upload-progress">
              <div class="upload-progress-bar" :class="statusColor[item.status]" :style="{ width: `${item.progress}%` }" />
            </div>
            <p v-if="item.error" class="upload-error">{{ item.error }}</p>
          </div>
          <span class="upload-status" :class="statusColor[item.status]">
            {{ typeof statusLabel[item.status] === 'function' ? statusLabel[item.status](item.progress) : statusLabel[item.status] }}
          </span>
        </div>
      </div>
    </div>
  </section>
</template>
