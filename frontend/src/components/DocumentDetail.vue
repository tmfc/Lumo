<script setup>
import { computed } from 'vue'

const props = defineProps({
  document: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
  actionLoading: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['reprocess'])

const statusTone = {
  completed: 'status-success',
  pending: 'status-warning',
  failed: 'status-danger',
}

const previewParagraphs = computed(() => {
  const text = props.document?.preview_text?.trim()
  if (!text) return []
  return text.split(/\n+/).map((paragraph) => paragraph.trim()).filter(Boolean)
})

const chunks = computed(() => props.document?.chunks ?? [])

const canReprocess = computed(() => {
  if (!props.document) return false
  if (props.document.status === 'failed') return true
  if (props.document.status === 'pending') {
    const seconds = Number(props.document.processing_duration_seconds ?? 0)
    return Number.isFinite(seconds) && seconds >= 30 * 60
  }
  return false
})
</script>

<template>
  <section class="detail-view">
    <div v-if="loading" class="detail-state">加载文档详情...</div>
    <div v-else-if="error" class="detail-state detail-state--error">{{ error }}</div>
    <div v-else-if="!document" class="detail-state">请选择一个文档查看详情</div>
    <div v-else class="detail-layout">
      <div class="detail-layout-main">
        <div class="detail-card">
          <header class="detail-card-head">
            <div>
              <h2>文档内容预览</h2>
              <p class="detail-card-subtitle">{{ document.original_name }}</p>
            </div>
            <button
              v-if="canReprocess"
              class="ghost-button"
              type="button"
              :disabled="actionLoading"
              @click="emit('reprocess')"
            >
              <span v-if="actionLoading">重新处理中...</span>
              <span v-else>重新处理</span>
            </button>
          </header>
          <div class="detail-preview">
            <template v-if="previewParagraphs.length">
              <p v-for="(paragraph, index) in previewParagraphs" :key="`preview-${index}`" class="detail-preview-text">
                {{ paragraph }}
              </p>
            </template>
            <p v-else class="detail-preview-text">暂无内容，稍后再试。</p>
          </div>
        </div>

        <div class="detail-card">
          <header class="detail-card-head">
            <div>
              <h2>文本分块</h2>
              <p class="detail-card-subtitle">展示自动生成的语义分块</p>
            </div>
          </header>
          <div class="chunk-list">
            <div v-if="!chunks.length" class="detail-state">暂无分块数据</div>
            <div v-else class="chunk-items">
              <article v-for="chunk in chunks" :key="chunk.index" class="chunk-item">
                <p class="chunk-text">{{ chunk.text }}</p>
                <span class="chunk-index">分块 #{{ chunk.index }}</span>
              </article>
            </div>
          </div>
        </div>
      </div>

      <div class="detail-layout-side">
        <div class="detail-card">
          <header class="detail-card-head">
            <h2>元数据</h2>
          </header>
          <dl class="metadata-list">
            <div class="metadata-row">
              <dt>状态</dt>
              <dd>
                <span class="status-pill" :class="statusTone[document.status] || 'status-warning'">
                  <span class="status-dot" />
                  {{ document.status_display || '未知' }}
                </span>
              </dd>
            </div>
            <div class="metadata-row">
              <dt>上传时间</dt>
              <dd>{{ document.uploaded_at_display || '--' }}</dd>
            </div>
            <div class="metadata-row">
              <dt>文件大小</dt>
              <dd>{{ document.file_size_display || '--' }}</dd>
            </div>
            <div class="metadata-row">
              <dt>分块数量</dt>
              <dd>{{ document.chunk_count ?? '--' }}</dd>
            </div>
            <div class="metadata-row">
              <dt>处理时长</dt>
              <dd>{{ document.processing_duration_display || '--' }}</dd>
            </div>
            <div v-if="document.error_message" class="metadata-row metadata-row--error">
              <dt>错误信息</dt>
              <dd>{{ document.error_message }}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  </section>
</template>
